#!/usr/bin/env python3
"""DERVS — os cérebros que o DERVS-VOZ pode usar, e o seletor entre eles.

Três encaixes, cada um com um PAPEL diferente (não são intercambiáveis):

  - `claude_code`: o cérebro que conversa e programa (já existe, em
    `dervs_claude_code.py`; este módulo só diz se está disponível).
  - `hermes`: candidato a segundo cérebro de conversa (Hermes Agent, Nous Research).
    Roda em Linux/WSL2. Hoje só a VERIFICAÇÃO existe: `perguntar` se recusa até
    alguém instalar e revisar o que ele instala e com que permissão.
  - `jev`: NÃO conversa. É o modelo da TypeSafe que responde perguntas tipadas
    (choice/score/noul) em centenas de milissegundos. Serve de TRIAGEM — "isto é
    urgente?" — e nunca vira o cérebro ativo. Acesso por lista de espera: sem
    `TYPESAFE_API_KEY` o encaixe fica desligado e diz o motivo.

Travas que valem para qualquer cérebro e que este módulo não afrouxa:
  - a chave do JEV vem só do ambiente, não entra em `repr`, log nem mensagem;
  - o que vai para o JEV passa por `sanitizar` (segredo e caminho saem);
  - a triagem do JEV só pode AUMENTAR cautela: `pode_agir_sozinho` vem da regra
    fixa, nunca do modelo. Trocar de cérebro não destrava o clique do dono.
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

JEV_URL_PADRAO = "https://api.typesafe.ai/v1/systemone"
JEV_MODELO = "jev-latest"
TETO_DA_RESPOSTA = 64 * 1024
TETO_DO_ESTADO = 2000
CEREBROS_ESCOLHIVEIS = ("claude_code", "hermes")   # o JEV é triagem, nunca o ativo
_CAMINHO_WINDOWS = re.compile(r"[A-Za-z]:[\\/][^\s\"']*")
_CAMINHO_UNC = re.compile(r"\\\\[^\s\"']+")
_CAMINHO_HOME = re.compile(r"~[\\/][^\s\"']*")
_AUTOMATICOS = ("analisar", "status", "avisar")


class CerebroIndisponivel(Exception):
    """O cérebro não pode responder agora. A mensagem já está em português e sem segredo."""


def sanitizar(texto, limite: int = TETO_DO_ESTADO) -> str:
    """O que pode sair do computador rumo a um serviço de terceiros."""
    import dervs_log_acoes
    t = str(dervs_log_acoes.redigir(str(texto)))
    for padrao in (_CAMINHO_WINDOWS, _CAMINHO_UNC, _CAMINHO_HOME):
        t = padrao.sub("[caminho]", t)
    return t[:limite]


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


# ---------------------------------------------------------------- JEV

class Jev:
    nome = "jev"

    def __init__(self, chave=None, url: str = JEV_URL_PADRAO, permitir_http_local: bool = False,
                 modelo: str = JEV_MODELO):
        self._chave_dada = chave          # None = ler do ambiente a cada uso
        p = urllib.parse.urlsplit(url)
        local = p.hostname in ("localhost", "127.0.0.1", "::1")
        if not (p.scheme == "https" or (p.scheme == "http" and local and permitir_http_local)):
            raise CerebroIndisponivel("O JEV só é chamado por https.")
        self._url = url
        self._modelo = modelo
        self._abridor = urllib.request.build_opener(_SemRedirecionar)

    @property
    def _chave(self) -> str:
        return os.environ.get("TYPESAFE_API_KEY", "") if self._chave_dada is None else self._chave_dada

    def __repr__(self):
        return "<Jev %s>" % ("ligado" if self._chave else "desligado")

    def disponivel(self):
        if not self._chave:
            return False, "sem a chave TYPESAFE_API_KEY (acesso por lista de espera)"
        return True, ""

    def triar(self, estado, perguntas: dict) -> dict:
        """`perguntas`: {nome: {"type": "noul|choice|score", "instructions": "..."}}.
        Devolve {nome: valor}. Levanta `CerebroIndisponivel` em qualquer falha."""
        ok, motivo = self.disponivel()
        if not ok:
            raise CerebroIndisponivel(motivo)
        corpo = json.dumps({"state": sanitizar(estado), "model": self._modelo,
                            "questions": perguntas}, ensure_ascii=False).encode("utf-8")
        pedido = urllib.request.Request(self._url, data=corpo, method="POST")
        pedido.add_header("Authorization", "Bearer " + self._chave)
        pedido.add_header("Content-Type", "application/json")
        try:
            with self._abridor.open(pedido, timeout=10) as r:
                bruto = r.read(TETO_DA_RESPOSTA + 1)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise CerebroIndisponivel("O JEV não aceitou a chave (ou o acesso ainda não foi liberado).")
            if e.code == 429:
                raise CerebroIndisponivel("O JEV pediu para esperar (limite de uso).")
            raise CerebroIndisponivel("O JEV está com erro (HTTP %d)." % e.code)
        except Exception:
            raise CerebroIndisponivel("Não alcancei o JEV agora.")
        if len(bruto) > TETO_DA_RESPOSTA:
            raise CerebroIndisponivel("A resposta do JEV veio grande demais.")
        try:
            respostas = json.loads(bruto).get("answers")
        except (ValueError, AttributeError):
            return {}
        if not isinstance(respostas, dict):
            return {}
        saida = {}
        for nome, r in respostas.items():
            if not isinstance(r, dict):
                continue
            valor = r.get(r.get("type")) if r.get("type") in r else r.get("value")
            if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor == valor:
                saida[nome] = float(valor)
            elif isinstance(valor, str):
                saida[nome] = valor[:100]
        return saida


# ---------------------------------------------------------------- Hermes

def _executar_padrao(args, timeout: float = 10):
    p = subprocess.run(args, capture_output=True, timeout=timeout)
    saida = p.stdout.decode("utf-16-le" if b"\x00" in p.stdout[:4] else "utf-8", "replace")
    return p.returncode, saida.replace("\x00", "")


class Hermes:
    nome = "hermes"

    def __init__(self, executar=None, relogio=time.monotonic, validade_s: float = 600):
        self._executar = executar or _executar_padrao
        self._relogio = relogio
        self._validade = validade_s
        self._cache = None       # (quando, (ok, motivo))

    def disponivel(self):
        agora = self._relogio()
        if self._cache and agora - self._cache[0] < self._validade:
            return self._cache[1]
        resultado = self._verificar()
        self._cache = (agora, resultado)
        return resultado

    def _verificar(self):
        try:
            # `-l -q` só lista: não acorda a máquina virtual do WSL à toa
            rc, distros = self._executar(["wsl.exe", "-l", "-q"], timeout=10)
            if rc != 0 or not distros.strip():
                return False, "o Hermes Agent pede Linux (WSL2) e este computador não tem distribuição instalada"
            rc, onde = self._executar(["wsl.exe", "-e", "sh", "-c", "command -v hermes"], timeout=20)
            if rc != 0 or not onde.strip():
                return False, "o Hermes Agent ainda não está instalado no WSL deste computador"
            return True, ""
        except Exception:
            return False, "não consegui verificar o Hermes Agent (WSL indisponível)"

    def perguntar(self, texto, contexto=None):
        raise CerebroIndisponivel(
            "O Hermes Agent ainda não está ligado ao DERVS: falta revisar o que ele instala "
            "e com que permissão antes de deixá-lo responder.")


# ---------------------------------------------------------------- Claude Code

class ClaudeCode:
    nome = "claude_code"

    def __init__(self, resolver=None):
        self._resolver = resolver

    def disponivel(self):
        try:
            resolver = self._resolver
            if resolver is None:
                import dervs_brain
                resolver = dervs_brain._resolver_claude
            return (True, "") if resolver() else (False, "o programa claude não foi encontrado")
        except Exception:
            return False, "o programa claude não foi encontrado"


# ---------------------------------------------------------------- o seletor

def arquivo_padrao() -> str:
    import dervs_config
    return os.path.join(dervs_config.CONFIG_DIR, "cerebro.json")


def criar_padrao():
    return Seletor({"claude_code": ClaudeCode(), "hermes": Hermes(), "jev": Jev(chave=None)})


class Seletor:
    def __init__(self, cerebros: dict, arquivo=None):
        self._cerebros = cerebros
        self._arquivo = arquivo or arquivo_padrao()
        self.ativo = self._ler()

    def _ler(self) -> str:
        try:
            with open(self._arquivo, "r", encoding="utf-8") as f:
                nome = json.load(f).get("ativo")
        except (OSError, ValueError, AttributeError):
            return "claude_code"
        if nome in CEREBROS_ESCOLHIVEIS and nome in self._cerebros \
                and self._cerebros[nome].disponivel()[0]:
            return nome
        return "claude_code"

    def escolher(self, nome):
        if nome == "jev":
            return False, "O JEV faz só triagem rápida; ele não pode ser o cérebro que conversa."
        if nome not in CEREBROS_ESCOLHIVEIS or nome not in self._cerebros:
            return False, "Não conheço esse cérebro."
        ok, motivo = self._cerebros[nome].disponivel()
        if not ok:
            return False, "O %s não está disponível: %s." % (nome, motivo)
        self.ativo = nome
        try:
            os.makedirs(os.path.dirname(self._arquivo), exist_ok=True)
            with open(self._arquivo, "w", encoding="utf-8") as f:
                json.dump({"ativo": nome}, f)
        except OSError:
            pass                   # a escolha vale nesta sessão mesmo sem gravar
        return True, ""

    def estado(self) -> dict:
        """Só o que o painel web aceita: cerebro_ativo e cerebros{nome:{disponivel,motivo}}."""
        cerebros = {}
        for nome, cerebro in self._cerebros.items():
            ok, motivo = cerebro.disponivel()
            cerebros[nome] = {"disponivel": bool(ok), "motivo": str(motivo)[:200]}
        return {"cerebro_ativo": self.ativo, "cerebros": cerebros}

    def triar_recado(self, recado: dict) -> dict:
        """Regra fixa decide se pode agir sozinho; o JEV, quando existe, só mede urgência."""
        pode = recado.get("nivel") == "leitura" and recado.get("tipo") in _AUTOMATICOS
        triagem = {"origem": "regra", "urgencia": None, "pode_agir_sozinho": bool(pode)}
        jev = self._cerebros.get("jev")
        if jev is None or not jev.disponivel()[0]:
            return triagem
        try:
            r = jev.triar("%s %s: %s" % (recado.get("tipo"), recado.get("nivel"), recado.get("texto", "")),
                          {"urgencia": {"type": "noul",
                                        "instructions": "De 0 a 1, quão urgente é este aviso para o dono?"}})
        except CerebroIndisponivel:
            return triagem
        if isinstance(r.get("urgencia"), float):
            triagem["origem"] = "jev"
            triagem["urgencia"] = max(0.0, min(1.0, r["urgencia"]))
        return triagem
