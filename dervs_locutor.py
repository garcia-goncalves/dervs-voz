#!/usr/bin/env python3
"""DERVS — perfis de voz e "quem fala" (camada local da conversa natural).

Cada perfil é uma impressão numérica da voz (embedding do ERes2Net, via
sherpa-onnx), guardada em `%APPDATA%\\dervs\\vozes\\<slug>\\` junto com um
`perfil.json`. O ÁUDIO NUNCA É GUARDADO: só o vetor, que não permite refazer a
fala. `quem_fala` compara um trecho de áudio com os perfis ATIVOS e devolve
quem é (ou None) e a similaridade.

O modelo (~38 MB) é baixado sob demanda para `%LOCALAPPDATA%\\dervs\\modelos\\`,
com SHA-256 conferido; o arquivo baixado é só lido pelo onnxruntime, nunca
executado. Sem o modelo (sem rede, hash errado), `disponivel()` é falso e a
trava de perfil fica desligada — quem chama avisa o dono.
"""
import hashlib
import http.client
import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
import urllib.request
from dataclasses import dataclass

import numpy as np

import dervs_config

TAXA = 16000
JANELA_S = 3.0
MIN_FALA_S = 15.0          # fala útil mínima para cadastrar um perfil
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024     # teto do download (o modelo tem ~38 MB)
PAPEIS = ("dono", "convidado")

MODELO_NOME = "3dspeaker_eres2net_base_16k.onnx"
MODELO_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
              "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")
MODELO_SHA256 = "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b"


class ErroLocutor(Exception):
    """Erro com mensagem pronta para o dono (pt-BR)."""


@dataclass
class Perfil:
    nome: str
    slug: str
    papel: str
    ativo: bool


# ---------------------------------------------------------------- modelo

def pasta_modelos() -> str:
    base = os.path.expanduser("~/AppData/Local") if os.name == "nt" else os.path.expanduser("~/.local/share")
    return os.path.join(base, "dervs", "modelos")


def _sha256(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def caminho_modelo(baixar: bool = True, pasta: str | None = None, url: str = MODELO_URL,
                   sha256: str = MODELO_SHA256, timeout: float = 60) -> str | None:
    """Caminho do modelo já conferido, baixando-o se faltar. None se não der."""
    pasta = pasta or pasta_modelos()
    destino = os.path.join(pasta, MODELO_NOME)
    try:
        if os.path.isfile(destino) and _sha256(destino) == sha256:
            return destino
        if not baixar or not url.startswith("https://"):
            return None
        os.makedirs(pasta, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=pasta, suffix=".part")
        try:
            baixado = 0
            with os.fdopen(fd, "wb") as saida, urllib.request.urlopen(url, timeout=timeout) as r:
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    baixado += len(bloco)
                    if baixado > MAX_DOWNLOAD_BYTES:
                        return None          # maior que o modelo esperado: descarta
                    saida.write(bloco)
            if _sha256(tmp) != sha256:
                return None              # arquivo diferente do esperado: descarta
            os.replace(tmp, destino)     # atômico: nunca fica meio arquivo no lugar
            return destino
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    except (OSError, ValueError, http.client.HTTPException):    # HTTPException: IncompleteRead
        return None


class ExtratorSherpa:
    """Embedding de um trecho de áudio 16 kHz mono float32."""

    def __init__(self, modelo: str, threads: int = 2):
        import sherpa_onnx
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=modelo, num_threads=threads)
        self._ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        s = self._ext.create_stream()
        s.accept_waveform(TAXA, np.ascontiguousarray(audio, dtype=np.float32))
        s.input_finished()
        return np.asarray(self._ext.compute(s), dtype=np.float32)


# ---------------------------------------------------------------- perfis

def _slug(nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:40]
    if not s:
        raise ErroLocutor("O nome precisa ter ao menos uma letra ou número.")
    return s


def _validar_nome(nome) -> str:
    if not isinstance(nome, str) or not 1 <= len(nome.strip()) <= 40:
        raise ErroLocutor("O nome do perfil precisa ter de 1 a 40 caracteres.")
    if any(unicodedata.category(c).startswith("C") for c in nome):
        raise ErroLocutor("O nome do perfil não pode ter caracteres de controle.")
    return nome.strip()


def _normalizar(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _fala_util(audio: np.ndarray) -> np.ndarray:
    """Só os blocos de 30 ms com energia de fala (corta silêncio e pausa)."""
    bloco = int(TAXA * 0.03)
    n = len(audio) // bloco
    if n == 0:
        return audio[:0]
    b = audio[: n * bloco].reshape(n, bloco)
    rms = np.sqrt((b ** 2).mean(axis=1))
    teto = float(rms.max())
    if teto <= 0:
        return audio[:0]
    return b[rms > max(0.1 * teto, 0.003)].reshape(-1)


class Perfis:
    def __init__(self, pasta: str | None = None, extrator=None):
        self.pasta = pasta or os.path.join(dervs_config.CONFIG_DIR, "vozes")
        self._extrator = extrator
        self._trava_extrator = threading.Lock()
        self._modelo_ok = False                  # o hash de 38 MB só se confere uma vez

    def _extrair(self, audio: np.ndarray) -> np.ndarray:
        if self._extrator is None:
            with self._trava_extrator:           # dois threads não carregam o modelo duas vezes
                if self._extrator is None:
                    modelo = caminho_modelo()
                    if not modelo:
                        raise ErroLocutor("O modelo de reconhecimento de voz não está disponível "
                                          "(não consegui baixá-lo). Tente de novo com internet.")
                    self._extrator = ExtratorSherpa(modelo)
        return _normalizar(self._extrator(audio))

    def disponivel(self) -> bool:
        if self._extrator is not None or self._modelo_ok:
            return True
        self._modelo_ok = caminho_modelo(baixar=False) is not None
        return self._modelo_ok

    def _dir(self, nome: str) -> str:
        d = os.path.realpath(os.path.join(self.pasta, _slug(nome)))
        if os.path.dirname(d) != os.path.realpath(self.pasta):
            raise ErroLocutor("Nome de perfil inválido.")
        return d

    def _ler(self, d: str) -> Perfil | None:
        try:
            with open(os.path.join(d, "perfil.json"), encoding="utf-8") as f:
                j = json.load(f)
            if j["papel"] not in PAPEIS:
                return None
            return Perfil(str(j["nome"]), os.path.basename(d), j["papel"], bool(j.get("ativo", True)))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def gravar(self, nome: str, papel: str, audio16k: np.ndarray, substituir: bool = False) -> Perfil:
        nome = _validar_nome(nome)
        if papel not in PAPEIS:
            raise ErroLocutor("O papel do perfil é 'dono' ou 'convidado'.")
        if not substituir and os.path.exists(self._dir(nome)):
            raise ErroLocutor("Já existe um perfil com o nome '%s'. Apague-o antes ou peça para substituir."
                              % nome)
        util = _fala_util(np.asarray(audio16k, dtype=np.float32))
        if len(util) < MIN_FALA_S * TAXA:
            raise ErroLocutor("Preciso de pelo menos %d segundos de fala para aprender a voz; "
                              "só ouvi %.0f. Leia o texto inteiro, sem pausas longas."
                              % (MIN_FALA_S, len(util) / TAXA))
        passo = int(JANELA_S * TAXA)
        embs = [self._extrair(util[i:i + passo]) for i in range(0, len(util) - passo + 1, passo)]
        media = _normalizar(np.mean(embs, axis=0))
        d = self._dir(nome)
        os.makedirs(d, exist_ok=True)
        np.save(os.path.join(d, "voz.npy"), media)
        perfil = Perfil(nome, os.path.basename(d), papel, True)
        self._gravar_json(d, perfil)
        return perfil

    @staticmethod
    def _gravar_json(d: str, p: Perfil):
        with open(os.path.join(d, "perfil.json"), "w", encoding="utf-8") as f:
            json.dump({"nome": p.nome, "papel": p.papel, "ativo": p.ativo}, f, ensure_ascii=False)

    def listar(self) -> list[Perfil]:
        try:
            nomes = sorted(os.listdir(self.pasta))
        except OSError:
            return []
        achados = (self._ler(os.path.join(self.pasta, n)) for n in nomes)
        return [p for p in achados if p]

    def ativar(self, nome: str, ativo: bool) -> Perfil:
        d = self._dir(nome)
        p = self._ler(d)
        if not p:
            raise ErroLocutor("Não existe perfil com o nome '%s'." % nome)
        p.ativo = bool(ativo)
        self._gravar_json(d, p)
        return p

    def apagar(self, nome: str) -> bool:
        d = self._dir(nome)
        if not os.path.isdir(d):
            return False
        shutil.rmtree(d)
        return True

    def quem_fala(self, audio16k: np.ndarray) -> tuple[Perfil | None, float]:
        """(perfil ativo mais parecido, similaridade). Perfil é None se a
        similaridade ficar abaixo de `locutor_limiar` ou se não houver perfil ativo."""
        candidatos = []
        for p in self.listar():
            if p.ativo:
                try:
                    candidatos.append((p, np.load(os.path.join(self.pasta, p.slug, "voz.npy"))))
                except (OSError, ValueError):
                    continue
        if not candidatos or len(audio16k) == 0:
            return None, 0.0
        e = self._extrair(np.asarray(audio16k, dtype=np.float32))
        candidatos = [(p, v) for p, v in candidatos if v.shape == e.shape]   # voz.npy de outro modelo: pula
        if not candidatos:
            return None, 0.0
        p, score = max(((p, float(e @ v)) for p, v in candidatos), key=lambda t: t[1])
        limiar = dervs_config.carregar()["locutor_limiar"]
        return (p if score >= limiar else None), score
