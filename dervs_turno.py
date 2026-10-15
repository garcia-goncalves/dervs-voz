"""Árbitro de vez: decide quando você TERMINOU de falar (e não só parou para pensar).

Entrada: quadros de 30 ms, PCM 16 kHz mono (bytes int16 ou array float32/int16).
Saída: eventos puros, sem Qt e sem rede em tempo de uso:

  InicioFala(t)        a voz começou
  Pausa(t)             parou há >= turno_silencio_min_ms (ainda pode continuar)
  FimDeVez(t, audio)   a vez acabou; `audio` é a frase inteira em PCM int16 (bytes)

Como decide: o VAD Silero marca fala. No primeiro silêncio de 300 ms roda o Smart Turn v3
(Pipecat) sobre os últimos 8 s: prob >= `turno_prob_fim` fecha a vez; abaixo disso espera mais e
reavalia a cada 300 ms de silêncio, até `turno_espera_max_s`. Fala retomada cancela a espera.
"Eu queria que você..." (1,5 s) + "abrisse o Chrome" vira uma frase só, não duas.

Modelos (baixados sob demanda para %LOCALAPPDATA%\\dervs\\modelos\\, SHA-256 conferido):
  - silero_vad.onnx   MIT, https://github.com/snakers4/silero-vad (2,3 MB)
  - smart-turn-v3.2-cpu.onnx  BSD-2-Clause, https://huggingface.co/pipecat-ai/smart-turn-v3 (8 MB, int8)
O pré-processamento do Smart Turn (log-mel tipo Whisper) é reimplementado em numpy: sem torch e sem
transformers. Sem os modelos, `criar()` devolve um árbitro que usa o `Endpointer` de energia
(`dervs_listen.py`, fim_ms=1100) e emite os mesmos eventos.
"""
import hashlib
import logging
import os
import tempfile
import urllib.request
from dataclasses import dataclass

import numpy as np

TAXA = 16000
FRAME_MS = 30
FRAME_AMOSTRAS = TAXA * FRAME_MS // 1000          # 480
JANELA_TURNO_S = 8                                 # o Smart Turn olha os últimos 8 s
BUFFER_MAX_S = 30                                  # fala contínua sem pausa: guarda só os últimos 30 s
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024             # teto do download (os modelos têm 2 e 8 MB)

log = logging.getLogger("dervs.turno")
_avisou_reserva = False

# nome do arquivo -> (url, sha256). Sem o hash batendo, o arquivo é descartado.
MODELOS = {
    "silero_vad.onnx": (
        "https://github.com/snakers4/silero-vad/raw/bfdc0193023f121ea5b3cc7b176dbed570a68a59/"
        "src/silero_vad/data/silero_vad.onnx",
        "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"),
    "smart-turn-v3.2-cpu.onnx": (
        "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/"
        "f766f81d3cfdf7737ac64aad813d91bbfd56bf93/smart-turn-v3.2-cpu.onnx",
        "2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f"),
}


# --- eventos -----------------------------------------------------------------

@dataclass(frozen=True)
class InicioFala:
    t: float


@dataclass(frozen=True)
class Pausa:
    t: float


@dataclass(frozen=True)
class FimDeVez:
    t: float
    audio: bytes


# --- entrada de áudio --------------------------------------------------------

def _para_float(frame) -> np.ndarray:
    """bytes int16 / array int16 / array float32 -> float32 em [-1, 1]."""
    if isinstance(frame, (bytes, bytearray, memoryview)):
        frame = np.frombuffer(frame, np.int16)
    a = np.asarray(frame)
    if a.dtype.kind in "iu":
        return a.astype(np.float32) / 32768.0
    return a.astype(np.float32, copy=False)


def _para_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


# --- características do Smart Turn (log-mel tipo Whisper, só numpy) ----------

def _hz_para_mel(f):
    f = np.asarray(f, dtype=np.float64)
    corte = 1000.0
    f_sp = 200.0 / 3
    passo = np.log(6.4) / 27.0
    return np.where(f >= corte, corte / f_sp + np.log(np.maximum(f, 1e-10) / corte) / passo, f / f_sp)


def _mel_para_hz(m):
    m = np.asarray(m, dtype=np.float64)
    corte = 1000.0
    f_sp = 200.0 / 3
    log_mel = corte / f_sp
    passo = np.log(6.4) / 27.0
    return np.where(m >= log_mel, corte * np.exp(passo * (m - log_mel)), f_sp * m)


def _filtros_mel(n_fft=400, n_mels=80, taxa=TAXA) -> np.ndarray:
    """Banco mel 'slaney' (o do Whisper): matriz (n_fft//2+1, n_mels)."""
    freqs = np.linspace(0, taxa / 2, n_fft // 2 + 1)
    pontos = _mel_para_hz(np.linspace(_hz_para_mel(0.0), _hz_para_mel(taxa / 2), n_mels + 2))
    dif = np.diff(pontos)
    rampa = pontos[None, :] - freqs[:, None]
    baixo = -rampa[:, :-2] / dif[:-1]
    alto = rampa[:, 2:] / dif[1:]
    filtros = np.maximum(0.0, np.minimum(baixo, alto))
    return filtros * (2.0 / (pontos[2:n_mels + 2] - pontos[:n_mels]))[None, :]


_FILTROS = None
_JANELA = np.hanning(401)[:-1]        # hann periódica de 400 pontos, como o Whisper


def caracteristicas(audio: np.ndarray) -> np.ndarray:
    """Áudio 16 kHz float -> (80, 800) float32, igual ao WhisperFeatureExtractor(chunk_length=8).

    Como o código do Pipecat: pega os últimos 8 s (ou completa com ZEROS NO COMEÇO), normaliza
    média 0 / variância 1, STFT 400/160 com reflexão, potência, banco mel, log10, teto -8, (x+4)/4.
    """
    global _FILTROS
    if _FILTROS is None:
        _FILTROS = _filtros_mel()
    n = JANELA_TURNO_S * TAXA
    x = np.asarray(audio, dtype=np.float64)[-n:]
    if len(x) < n:
        x = np.pad(x, (n - len(x), 0))
    x = (x - x.mean()) / np.sqrt(x.var() + 1e-7)
    x = np.pad(x, (200, 200), mode="reflect")
    passos = (len(x) - 400) // 160 + 1
    idx = np.arange(400)[None, :] + 160 * np.arange(passos)[:, None]
    espectro = np.abs(np.fft.rfft(x[idx] * _JANELA, axis=1)) ** 2          # (quadros, 201)
    mel = (espectro @ _FILTROS).T[:, :-1]                                   # descarta o último quadro
    log = np.log10(np.maximum(mel, 1e-10))
    log = np.maximum(log, log.max() - 8.0)
    return ((log + 4.0) / 4.0).astype(np.float32)


# --- modelos -----------------------------------------------------------------

def _sessao(caminho):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.inter_op_num_threads = 1
    so.intra_op_num_threads = 1
    return ort.InferenceSession(caminho, sess_options=so, providers=["CPUExecutionProvider"])


class VadSilero:
    """Silero VAD v5/v6 (onnx). `__call__(quadro 30 ms) -> probabilidade de fala` do último pedaço de
    512 amostras completo (os quadros de 480 são reagrupados em pedaços de 512)."""

    PEDACO = 512
    CONTEXTO = 64

    def __init__(self, caminho):
        self._s = _sessao(caminho)
        self.reset()

    def reset(self):
        self._estado = np.zeros((2, 1, 128), np.float32)
        self._contexto = np.zeros(self.CONTEXTO, np.float32)
        self._resto = np.zeros(0, np.float32)
        self._prob = 0.0

    def __call__(self, quadro) -> float:
        self._resto = np.concatenate([self._resto, _para_float(quadro)])
        while len(self._resto) >= self.PEDACO:
            pedaco, self._resto = self._resto[:self.PEDACO], self._resto[self.PEDACO:]
            entrada = np.concatenate([self._contexto, pedaco])[None, :]
            saida, self._estado = self._s.run(
                None, {"input": entrada, "state": self._estado, "sr": np.array(TAXA, np.int64)})
            self._contexto = entrada[0, -self.CONTEXTO:]
            self._prob = float(saida[0, 0])
        return self._prob


class ModeloTurno:
    """Smart Turn v3 (onnx int8). `__call__(audio 16 kHz) -> probabilidade de a vez ter acabado`."""

    def __init__(self, caminho):
        self._s = _sessao(caminho)

    def __call__(self, audio) -> float:
        feat = caracteristicas(_para_float(audio))[None, :, :]
        return float(self._s.run(None, {"input_features": feat})[0].reshape(-1)[0])


# --- árbitro -----------------------------------------------------------------

class Arbitro:
    """Máquina de estados. `processar(quadro) -> lista de eventos`.

    `vad(quadro) -> prob` e `turno(audio_float) -> prob` são injetados (os de verdade ou dublês).
    """

    def __init__(self, vad, turno, prob_fim=0.5, espera_max_s=3.0, silencio_min_ms=300,
                 limiar_fala=0.5, limiar_silencio=0.35, min_fala_quadros=3, pre_roll_quadros=10,
                 cola_max_ms=600, buffer_max_s=BUFFER_MAX_S):
        self.vad, self.turno = vad, turno
        self.prob_fim = prob_fim
        self.espera_max = max(1, round(espera_max_s * 1000 / FRAME_MS))
        self.sil_min = max(1, round(silencio_min_ms / FRAME_MS))
        self.cola_max = max(self.sil_min, round(cola_max_ms / FRAME_MS))   # silêncio que o modelo vê
        self.limiar_fala, self.limiar_silencio = limiar_fala, limiar_silencio
        self.min_fala = min_fala_quadros
        self.pre_max = pre_roll_quadros
        self.buf_max = max(1, round(buffer_max_s * 1000 / FRAME_MS))
        self.ultima_prob = None          # última prob do Smart Turn (para medir/depurar)
        self.reset()

    def reset(self):
        self.n = 0                       # quadros recebidos (relógio: n * 30 ms)
        self._pre = []
        self._buf = []
        self._em_fala = False
        self._candidatos = 0
        self._sil = 0
        self._proximo = self.sil_min     # em que silêncio rodar o modelo
        if hasattr(self.vad, "reset"):
            self.vad.reset()

    def _t(self):
        return self.n * FRAME_MS / 1000.0

    def processar(self, quadro) -> list:
        x = _para_float(quadro)
        self.n += 1
        p = self.vad(x)
        ev = []
        if not self._em_fala:
            self._pre.append(x)
            if len(self._pre) > self.pre_max + self.min_fala:
                self._pre.pop(0)
            self._candidatos = self._candidatos + 1 if p >= self.limiar_fala else 0
            if self._candidatos >= self.min_fala:
                self._em_fala = True
                self._buf = list(self._pre)
                self._pre = []
                self._sil = 0
                self._proximo = self.sil_min
                ev.append(InicioFala(self._t() - self.min_fala * FRAME_MS / 1000.0))
            return ev
        self._buf.append(x)
        if len(self._buf) > self.buf_max:
            del self._buf[:len(self._buf) - self.buf_max]        # monólogo longo: descarta o mais antigo
        # histerese: dentro da fala basta passar do limiar baixo; já em silêncio, só o alto retoma
        limiar = self.limiar_silencio if self._sil == 0 else self.limiar_fala
        if p >= limiar:
            self._sil = 0                # voz (ou retomada): cancela a espera
            self._proximo = self.sil_min
            return ev
        self._sil += 1
        if self._sil == self.sil_min:
            ev.append(Pausa(self._t()))
        if self._sil >= self.espera_max:
            return ev + [self._fechar()]
        if self._sil >= self._proximo:
            self._proximo += self.sil_min
            # o Smart Turn foi treinado com o áudio acabando logo depois da fala: dar a ele minutos de
            # silêncio no fim o faz achar que "acabou" só porque ficou quieto. Corta a cauda longa.
            sobra = max(0, self._sil - self.cola_max)
            self.ultima_prob = self.turno(np.concatenate(self._buf[:len(self._buf) - sobra]))
            if self.ultima_prob >= self.prob_fim:
                return ev + [self._fechar()]
        return ev

    def _fechar(self):
        fim = FimDeVez(self._t(), _para_pcm16(np.concatenate(self._buf)))
        self._buf, self._pre = [], list(self._buf[-self.pre_max:])
        self._em_fala, self._candidatos, self._sil = False, 0, 0
        if hasattr(self.vad, "reset"):
            self.vad.reset()
        return fim


class ArbitroEnergia:
    """Reserva sem modelos: o `Endpointer` por energia (fim_ms=1100) emitindo os mesmos eventos."""

    def __init__(self, fim_ms=1100):
        from dervs_listen import Endpointer
        self._ep = Endpointer(fim_ms=fim_ms)
        self.n = 0
        self._em_fala = False

    def reset(self):
        self._ep.reset()
        self.n = 0
        self._em_fala = False

    def processar(self, quadro) -> list:
        if not isinstance(quadro, (bytes, bytearray)):
            quadro = _para_pcm16(_para_float(quadro))
        self.n += 1
        t = self.n * FRAME_MS / 1000.0
        ev = []
        pcm = self._ep.processar(bytes(quadro))
        if self._ep.em_fala and not self._em_fala:
            ev.append(InicioFala(t))
        self._em_fala = self._ep.em_fala
        if pcm is not None:
            ev.append(FimDeVez(t, pcm))
        return ev


# --- modelos em disco --------------------------------------------------------

def pasta_modelos() -> str:
    base = os.path.expandvars("%LOCALAPPDATA%")
    if "%" in base or not base:
        base = os.path.expanduser("~/AppData/Local")
    return os.path.join(base, "dervs", "modelos")


def _sha256(caminho) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def garantir_modelo(nome, pasta=None, baixar=True):
    """Caminho do modelo com o SHA-256 conferido, baixando se faltar. None se não der."""
    url, sha = MODELOS[nome]
    pasta = pasta or pasta_modelos()
    destino = os.path.join(pasta, nome)
    if os.path.exists(destino) and _sha256(destino) == sha:
        return destino
    if not baixar:
        return None
    tmp = None
    try:
        os.makedirs(pasta, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=pasta, suffix=".parcial")
        with os.fdopen(fd, "wb") as f, urllib.request.urlopen(url, timeout=60) as r:
            baixado = 0
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                baixado += len(bloco)
                if baixado > MAX_DOWNLOAD_BYTES:
                    return None                  # maior que qualquer modelo esperado: descarta
                f.write(bloco)
        if _sha256(tmp) != sha:
            return None
        os.replace(tmp, destino)             # escrita atômica
        return destino
    except Exception:
        return None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def criar(conf=None, pasta=None, baixar=True):
    """O melhor árbitro disponível: Silero + Smart Turn se os modelos carregam, senão por energia."""
    conf = conf or {}
    motivo = "modelos indisponíveis (sem rede, arquivo ausente ou SHA-256 diferente)"
    try:
        vad = garantir_modelo("silero_vad.onnx", pasta, baixar)
        turno = garantir_modelo("smart-turn-v3.2-cpu.onnx", pasta, baixar)
        if vad and turno:
            return Arbitro(VadSilero(vad), ModeloTurno(turno),
                           prob_fim=conf.get("turno_prob_fim", 0.5),
                           espera_max_s=conf.get("turno_espera_max_s", 3.0),
                           silencio_min_ms=conf.get("turno_silencio_min_ms", 300))
    except Exception as exc:
        motivo = "modelo não carregou (%s)" % type(exc).__name__
    global _avisou_reserva
    if not _avisou_reserva:                  # uma vez só: o árbitro de energia é bem pior em hesitação
        _avisou_reserva = True
        log.warning("árbitro de vez caiu para o de energia: %s", motivo)
    return ArbitroEnergia()
