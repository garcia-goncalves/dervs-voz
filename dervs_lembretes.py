#!/usr/bin/env python3
"""DERVS — lembretes por voz, 100% locais (sem nuvem, sem custo).

O dono diz "me lembra em 10 minutos de ligar para o cliente" e o DERVS avisa,
em voz alta e no HUD, quando a hora chegar. Este módulo só tem a parte que
dá para testar sem tela nem microfone:

  - `interpretar(fala, agora)`  -> (quando, texto) ou None. Português do Brasil,
    CONSERVADOR: se não entendeu a hora, devolve None — NUNCA chuta um horário.
  - `descrever(quando, agora)`  -> "às 15h30", "em 10 minutos", "amanhã às 9h".
  - `Agenda`                    -> a lista de lembretes gravada em disco
    (`%APPDATA%\\dervs\\lembretes.json`), com relógio e caminho injetáveis.

Quem dispara (um QTimer na thread do Qt) é a `PopUp`, em `dervs.py`.

O TEXTO do lembrete vem da voz do dono: é dado, só é FALADO — nunca é
executado como comando. Corta em 200 caracteres.
"""
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta

LIMITE_DIAS = 7            # lembrete mais longe que isto: recusa (não chuta)
MAX_TEXTO = 200            # o que o dono dita é dado: corte duro
MAX_LEMBRETES = 20         # trava contra lista crescendo sem parar
ATRASO_AVISO_S = 120       # vencido há mais que isto = "você tinha um lembrete"


def _norm(texto: str) -> str:
    """Minúsculas, sem acento, pontuação virada em espaço — e do MESMO
    TAMANHO do original, letra por letra. É o que deixa casar a fala sem
    acento e, depois, recortar o texto do lembrete no original (com acento,
    que o Piper precisa para pronunciar direito)."""
    saida = []
    for c in texto or "":
        b = "".join(x for x in unicodedata.normalize("NFKD", c)
                    if not unicodedata.combining(x))
        b = (b[:1] or " ").lower()
        saida.append(b if (b.isalnum() or b == ":") else " ")
    return "".join(saida)


# ---------------------------------------------------------------------------
# Números: dígitos ou por extenso (até cinquenta e nove).
# ---------------------------------------------------------------------------
_PALAVRAS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
    "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14,
    "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18,
    "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40,
    "cinquenta": 50,
}
_NUM = (r"(?:\d{1,3}|(?:vinte|trinta|quarenta|cinquenta)"
        r"(?: e (?:um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove))?"
        r"|dezenove|dezessete|dezesseis|dezoito|catorze|quatorze|quinze|"
        r"treze|doze|onze|dez|nove|oito|sete|seis|cinco|quatro|tres|dois|"
        r"duas|uma|um)")


def _valor(s: str) -> int:
    s = s.strip()
    if s.isdigit():
        return int(s)
    return sum(_PALAVRAS[p] for p in s.split() if p in _PALAVRAS)


# "em 10 minutos", "daqui a 2 horas", "em meia hora", "em uma hora e meia"
_RE_DURACAO = re.compile(
    r"\b(?:em|daqui a|daqui|dentro de)\s+(?:"
    r"(?P<meia>meia)\s+hora"
    rf"|(?P<n>{_NUM})\s+(?P<u>segundos?|minutos?|horas?|dias?)"
    r"(?:\s+e\s+(?P<mm>meia))?)\b")

# "às 15h30", "às 15:30", "às 9 da noite", "amanhã às 9", "meio-dia"
_RE_RELOGIO = re.compile(
    r"\b(?:(?P<dia>hoje|amanha)\s+(?:(?:de|da|pela)\s+(?P<per0>manha|tarde|noite)\s+)?)?"
    rf"(?:(?:para\s+)?as\s+(?P<h>{_NUM})"
    r"(?:\s*(?P<marca>h|horas?|:)\s*(?P<m>\d{2})?)?"
    r"|(?:(?:para|ao|no|as|a|o)\s+)*(?P<mdia>meio dia|meia noite))"
    r"(?:\s+e\s+(?:(?P<meia>meia)|(?P<m2>\d{2})))?"
    r"(?:\s+(?:da|de)\s+(?P<per>manha|tarde|noite|madrugada))?\b")

# Depois de uma hora "seca" ("às 9") só pode vir o fim ou uma ligação como
# "de ligar..." — "às 2 caixas" não é horário.
_LIGACAO = {"me", "de", "da", "do", "das", "dos", "para", "pra", "que", "e", "sobre"}

_RE_PEDIDO = re.compile(r"\bme\s+(?:lembra|lembre|lembrar)\b")
_RE_AVISA = re.compile(r"\bme\s+(?:avisa|avise|avisar)\b")
_RE_LEMBRETE = re.compile(
    r"(?:\b(?:cria|crie|criar|faz|faca|define|marca|marque)\s+)?"
    r"(?:\bum\s+)?\blembrete\b")
_RE_GATILHO = re.compile(
    r"\bme\s+(?:lembra|lembre|lembrar|avisa|avise|avisar)\b"
    r"(?:\s+(?:de|que|para|pra))?")
_RE_INICIO = re.compile(r"^(?:de|da|do|das|dos|para|pra|que|sobre)\s+")
_RE_FIM = re.compile(
    r"\s+(?:de|em|e|as|para|por favor|pfv|pra mim|por gentileza)$")


def eh_pedido(fala: str) -> bool:
    """A fala PEDE um lembrete? ('me lembra ...', 'crie um lembrete ...').
    'me avisa ...' só conta quando a hora é entendida (ver `interpretar`)."""
    n = _norm(fala)
    return bool(_RE_PEDIDO.search(n) or _RE_LEMBRETE.search(n))


def _proxima_palavra(m):
    resto = m.string[m.end():].split()
    return resto[0] if resto else None


def _relogio(m, agora: datetime):
    """Converte o casamento de _RE_RELOGIO no instante, ou None."""
    if m.group("mdia"):
        h, minuto = (12, 0) if m.group("mdia") == "meio dia" else (0, 0)
    else:
        h = _valor(m.group("h"))
        minuto = 0
        if m.group("m"):
            minuto = int(m.group("m"))
        elif m.group("m2"):
            minuto = int(m.group("m2"))
        elif m.group("meia"):
            minuto = 30
        seca = not (m.group("marca") or m.group("m") or m.group("meia")
                    or m.group("m2") or m.group("per") or m.group("per0"))
        if seca:
            # "às 9" cru: o que vem depois tem de ser fim de frase/ligação.
            resto = _proxima_palavra(m)
            if resto is not None and resto not in _LIGACAO:
                return None
    periodo = m.group("per") or m.group("per0")
    if periodo in ("tarde", "noite"):
        if h < 12:
            h += 12
        elif h == 12 and periodo == "noite":
            h = 0
    elif periodo in ("manha", "madrugada") and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= minuto <= 59):
        return None
    alvo = agora.replace(hour=h, minute=minuto, second=0, microsecond=0)
    dia = m.group("dia")
    if dia == "amanha":
        alvo += timedelta(days=1)
    elif alvo <= agora:
        if dia == "hoje":
            return None          # "hoje às 8" com 8h já passadas: não chuta
        alvo += timedelta(days=1)
    return alvo


def _duracao(m, agora: datetime):
    if m.group("meia") and not m.group("n"):
        return agora + timedelta(minutes=30)
    n = _valor(m.group("n"))
    u = m.group("u")[0]           # s, m, h, d
    base = {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
            "h": timedelta(hours=n), "d": timedelta(days=n)}[u]
    if m.group("mm"):
        base += {"s": timedelta(seconds=30), "m": timedelta(seconds=30),
                 "h": timedelta(minutes=30), "d": timedelta(hours=12)}[u]
    if base <= timedelta(0):
        return None
    return agora + base


def interpretar(fala: str, agora: datetime | None = None):
    """(quando, texto) se a fala é um pedido de lembrete com hora ENTENDIDA;
    senão None. Nunca chuta: hora ambígua, duas horas na mesma frase, passada
    ou além de 7 dias => None."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    n = _norm(fala)
    if not (_RE_PEDIDO.search(n) or _RE_LEMBRETE.search(n)
            or _RE_AVISA.search(n)):
        return None
    dur = list(_RE_DURACAO.finditer(n))
    rel = list(_RE_RELOGIO.finditer(n))
    if len(dur) + len(rel) != 1:
        return None
    if dur:
        m = dur[0]
        quando = _duracao(m, agora)
    else:
        m = rel[0]
        quando = _relogio(m, agora)
    if quando is None:
        return None
    if quando <= agora or quando - agora > timedelta(days=LIMITE_DIAS):
        return None
    return quando, _extrair_texto(fala, n, m)


def _extrair_texto(fala: str, n: str, tempo) -> str:
    """O que o dono quer que seja lembrado: a fala sem o gatilho e sem a hora."""
    cortes = [tempo.span()]
    for rx in (_RE_GATILHO, _RE_LEMBRETE):
        for m in rx.finditer(n):
            cortes.append(m.span())
    cortes.sort()
    pedacos, pos = [], 0
    for a, b in cortes:
        if a > pos:
            pedacos.append(fala[pos:a])
        pos = max(pos, b)
    pedacos.append(fala[pos:])
    texto = " ".join(" ".join(pedacos).split())
    for _ in range(4):
        antes = texto
        texto = texto.strip(" .,;:!?")
        m = _RE_INICIO.match(_norm(texto))
        if m:
            texto = texto[m.end():]
        m = _RE_FIM.search(_norm(texto))
        if m:
            texto = texto[:m.start()]
        if texto == antes:
            break
    texto = texto.strip(" .,;:!?")
    return texto[:MAX_TEXTO].strip()


# ---------------------------------------------------------------------------
# Como o lembrete é DITO em voz alta.
# ---------------------------------------------------------------------------
def _hora_curta(dt: datetime) -> str:
    if dt.minute == 0:
        if dt.hour == 0:
            return "à meia-noite"
        if dt.hour == 12:
            return "ao meio-dia"
    h = f"{dt.hour}h" if dt.minute == 0 else f"{dt.hour}h{dt.minute:02d}"
    return ("à " if dt.hour == 1 else "às ") + h


def descrever(quando: datetime, agora: datetime) -> str:
    """'em 10 minutos' (curto), 'às 15h30', 'amanhã às 9h', 'dia 28 às 9h'."""
    delta = round((quando - agora).total_seconds())   # 59,6 s = "1 minuto"
    if delta < 60:
        s = max(1, delta)
        return f"em {s} segundo" + ("" if s == 1 else "s")
    if delta < 3600:
        mnt = max(1, int(round(delta / 60)))
        return f"em {mnt} minuto" + ("" if mnt == 1 else "s")
    dias = (quando.date() - agora.date()).days
    hora = _hora_curta(quando)
    if dias <= 0:
        return hora
    if dias == 1:
        return f"amanhã {hora}"
    return f"dia {quando.day} {hora}"


def _dia_passado(quando: datetime, agora: datetime) -> str:
    """Hora de um lembrete que já passou, com o dia se não for hoje."""
    dias = (agora.date() - quando.date()).days
    if dias <= 0:
        return _hora_curta(quando)
    if dias == 1:
        return f"ontem {_hora_curta(quando)}"
    return f"dia {quando.day} {_hora_curta(quando)}"


def frase_de_aviso(item: dict, agora: datetime) -> str:
    """O que é falado quando o lembrete vence. Se venceu com o app fechado
    (atraso grande), diz que TINHA um lembrete e a hora original."""
    texto = item.get("texto") or ""
    quando = item["quando"]
    if (agora - quando).total_seconds() > ATRASO_AVISO_S:
        base = f"Você tinha um lembrete {_dia_passado(quando, agora)}"
        return f"{base}: {texto}." if texto else f"{base}."
    return f"Lembrete: {texto}." if texto else "Lembrete! Você pediu para ser avisado agora."


# ---------------------------------------------------------------------------
# Persistência.
# ---------------------------------------------------------------------------
def _caminho_padrao() -> str:
    import dervs_config
    return os.path.join(dervs_config.CONFIG_DIR, "lembretes.json")


class Agenda:
    """Os lembretes pendentes, em `lembretes.json`. Só é usada pela thread da
    tela. Tolera arquivo ausente ou torto (vira lista vazia) e grava de forma
    atômica (arquivo temporário + rename): queda no meio não corrompe."""

    def __init__(self, caminho: str | None = None, relogio=None):
        self.caminho = caminho or _caminho_padrao()
        self._relogio = relogio or datetime.now

    def agora(self) -> datetime:
        return self._relogio().replace(microsecond=0)

    # -- disco --
    def _ler(self) -> list[dict]:
        try:
            with open(self.caminho, encoding="utf-8") as f:
                bruto = json.load(f)
        except (OSError, ValueError):
            return []
        if isinstance(bruto, dict):
            bruto = bruto.get("lembretes")
        if not isinstance(bruto, list):
            return []
        itens = []
        for x in bruto:
            try:
                quando = datetime.fromisoformat(x["quando"])
                texto = str(x.get("texto") or "")[:MAX_TEXTO]
            except (KeyError, TypeError, ValueError, AttributeError):
                continue      # entrada torta: ignora, não derruba as outras
            itens.append({"quando": quando, "texto": texto})
        itens.sort(key=lambda i: i["quando"])
        return itens

    def _gravar(self, itens: list[dict]) -> None:
        pasta = os.path.dirname(self.caminho)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        dados = {"lembretes": [
            {"quando": i["quando"].isoformat(timespec="seconds"),
             "texto": i["texto"]} for i in itens]}
        tmp = self.caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.caminho)

    # -- operações --
    def listar(self) -> list[dict]:
        return self._ler()

    def adicionar(self, quando: datetime, texto: str) -> bool:
        """False se a lista já está cheia (nada é gravado)."""
        itens = self._ler()
        if len(itens) >= MAX_LEMBRETES:
            return False
        itens.append({"quando": quando.replace(microsecond=0),
                      "texto": (texto or "")[:MAX_TEXTO].strip()})
        itens.sort(key=lambda i: i["quando"])
        self._gravar(itens)
        return True

    def cancelar_todos(self) -> int:
        itens = self._ler()
        if os.path.exists(self.caminho):
            self._gravar([])
        return len(itens)

    def retirar_vencido(self):
        """O lembrete mais antigo que já venceu, JÁ REMOVIDO do arquivo (assim
        não repete nem se o app cair logo depois); ou None."""
        itens = self._ler()
        if not itens or itens[0]["quando"] > self.agora():
            return None
        primeiro = itens.pop(0)
        self._gravar(itens)
        return primeiro
