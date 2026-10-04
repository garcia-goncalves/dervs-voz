#!/usr/bin/env python3
"""DERVS — modos de escuta: Desligado, Atalho e Voz.

Peças puras (sem Qt, sem microfone) para o que o briefing `dervs-jarvis` exige:
o microfone NÃO pode abrir sozinho nem ficar aberto esquecido.

  - `normalizar_modo`: só três valores valem; o resto cai em `desligado`.
  - `eh_pare_de_ouvir`: o comando de voz que fecha o microfone.
  - `AutoDesligamento`: relógio que vence depois de N minutos sem uso.
  - `TeclaSegurada`: detecta apertar/soltar de uma combinação de teclas, para o
    modo Atalho ("microfone só enquanto a tecla está apertada").

O relógio e a leitura do teclado entram por parâmetro, para o teste não
depender de tempo real nem de teclado de verdade.
"""
import re
import sys
import time
import unicodedata

DESLIGADO = "desligado"
ATALHO = "atalho"
VOZ = "voz"
MODOS = (DESLIGADO, ATALHO, VOZ)

# Teto de segurança do desligamento automático: 0 não existe — "nunca desligar"
# seria exatamente o microfone esquecido aberto que esta peça impede.
MIN_AUTO_DESLIGAR = 1
MAX_AUTO_DESLIGAR = 240
PADRAO_AUTO_DESLIGAR = 10

NOME_DO_ATALHO = "Ctrl+Alt+Espaço"


def normalizar_modo(valor) -> str:
    """Devolve um modo válido; qualquer coisa estranha vira `desligado` (o lado
    seguro: microfone fechado)."""
    if isinstance(valor, str) and valor.strip().lower() in MODOS:
        return valor.strip().lower()
    return DESLIGADO


def normalizar_minutos(valor) -> int:
    """Minutos de inatividade até fechar o microfone, entre 1 e 240."""
    if isinstance(valor, bool):
        return PADRAO_AUTO_DESLIGAR
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return PADRAO_AUTO_DESLIGAR
    return min(max(n, MIN_AUTO_DESLIGAR), MAX_AUTO_DESLIGAR)


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_VERBOS = r"(pare|parar|para|chega|cala|desliga|desligue|fecha|feche)"
_PEDIDO_PARE = re.compile(
    r"^(por favor )?" + _VERBOS + r" (de )?(me )?(ouvir|escutar)( agora| por favor)?$"
    r"|^(por favor )?" + _VERBOS + r" (o )?(microfone|mic)( agora| por favor)?$"
    r"|^(por favor )?(fecha|feche|desliga|desligue) a escuta( agora| por favor)?$"
    r"|^chega de (ouvir|escutar)$")


def eh_pare_de_ouvir(texto: str) -> bool:
    """A frase INTEIRA é o pedido de fechar o microfone?

    Conservador de propósito: "para de ouvir música" ou "não pare de ouvir"
    não casam. Falso positivo aqui só fecha o microfone (lado seguro), mas
    atrapalharia uma conversa; falso negativo o dono resolve no botão.
    """
    n = _norm(texto)
    if not n or len(n) > 60:
        return False
    return bool(_PEDIDO_PARE.match(n))


class AutoDesligamento:
    """Vence quando passam `minutos` sem `tocar()`.

    `tocar()` marca uso (o dono falou com o DERVS, apertou o atalho, trocou de
    modo). Fica parado até `armar()`; `desarmar()` o para (microfone fechado).
    """

    def __init__(self, minutos=PADRAO_AUTO_DESLIGAR, relogio=time.monotonic):
        self._relogio = relogio
        self.minutos = normalizar_minutos(minutos)
        self._ultimo = None

    def configurar(self, minutos) -> None:
        self.minutos = normalizar_minutos(minutos)

    def armar(self) -> None:
        self._ultimo = self._relogio()

    def desarmar(self) -> None:
        self._ultimo = None

    def tocar(self) -> None:
        if self._ultimo is not None:
            self._ultimo = self._relogio()

    @property
    def armado(self) -> bool:
        return self._ultimo is not None

    def restante_s(self):
        """Segundos até vencer, ou None se desarmado."""
        if self._ultimo is None:
            return None
        return max(0.0, self.minutos * 60 - (self._relogio() - self._ultimo))

    def venceu(self) -> bool:
        r = self.restante_s()
        return r is not None and r <= 0.0


# Códigos de tecla virtual do Windows (GetAsyncKeyState).
VK_CONTROL, VK_MENU, VK_SPACE = 0x11, 0x12, 0x20
COMBINACAO_PADRAO = (VK_CONTROL, VK_MENU, VK_SPACE)


def _estado_real_das_teclas(teclas):
    """True se TODAS as teclas estão apertadas agora (só Windows)."""
    if sys.platform != "win32":
        return False
    import ctypes
    f = ctypes.windll.user32.GetAsyncKeyState
    return all(f(t) & 0x8000 for t in teclas)


class TeclaSegurada:
    """Transforma o estado "combinação apertada?" em eventos de borda.

    `passo()` devolve `"apertou"` na primeira leitura apertada, `"soltou"` na
    primeira solta depois disso e `None` no resto. Quem chama lê de ~30 em 30 ms
    num timer do Qt. Sem gancho global de teclado: só pergunta ao Windows se a
    combinação está apertada, então não captura o que o dono digita.
    """

    def __init__(self, teclas=COMBINACAO_PADRAO, leitor=_estado_real_das_teclas):
        self.teclas = tuple(teclas)
        self._leitor = leitor
        self._apertada = False

    def passo(self):
        try:
            agora = bool(self._leitor(self.teclas))
        except Exception:
            agora = False        # falha de leitura = solta (lado seguro)
        if agora and not self._apertada:
            self._apertada = True
            return "apertou"
        if not agora and self._apertada:
            self._apertada = False
            return "soltou"
        return None

    @property
    def apertada(self) -> bool:
        return self._apertada
