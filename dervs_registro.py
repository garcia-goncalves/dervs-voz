#!/usr/bin/env python3
"""O DERVS anota a própria morte — e conta ao dono na vez seguinte.

Por que existe: em 02/09/2026 o dono disse "está fechando sozinho quando eu
aperto VOZ". O app abre com `pythonw`, que NÃO tem janela de terminal: quando
uma exceção escapa dentro de um sinal do Qt, o PyQt6 encerra o processo na
hora e o rastro vai para um `stderr` que não existe. O app sumia da tela sem
deixar uma linha em lugar nenhum — nem para o dono, nem para quem fosse
consertar. Foram 14 apertos reais nos dois botões sem reproduzir; sem registro,
o próximo passo seria adivinhar.

O que faz:

* guarda o motivo da queda em `%APPDATA%\\dervs\\ultimo_erro.txt`
  (`~/.config/dervs` no Linux), com data e hora;
* cobre os três jeitos de morrer: exceção na thread da tela (`sys.excepthook`),
  exceção em thread de fundo (`threading.excepthook`) e pane dura do próprio
  Python ou do Qt (`faulthandler`, que escreve mesmo quando não dá mais para
  rodar código Python);
* na abertura seguinte, `ler_e_limpar()` devolve o que aconteceu, para a tela
  dizer ao dono **por que** fechou da última vez.

Nunca guarda o que o dono falou nem o texto transcrito: só o tipo do erro e o
caminho do código.
"""
import io
import os
import sys
import time
import threading
import traceback

import dervs_config as cfg

CAMINHO = os.path.join(cfg.CONFIG_DIR, "ultimo_erro.txt")
LIMITE = 8000                  # o bastante para o rastro; não vira arquivo gigante

_arquivo_duro = None           # mantido aberto: o faulthandler escreve nele


def _agora() -> str:
    return time.strftime("%d/%m/%Y %H:%M:%S")


def anotar(texto: str, origem: str = "tela", caminho: str = CAMINHO) -> bool:
    """Guarda um motivo de queda. Devolve se conseguiu.

    Anotar não pode explodir por sua vez: estamos, por definição, no meio de
    algo já dando errado.
    """
    try:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        with io.open(caminho, "w", encoding="utf-8") as f:
            f.write("quando: %s\norigem: %s\n\n%s" % (_agora(), origem, texto[-LIMITE:]))
        return True
    except OSError:
        return False


def resumo(texto: str) -> str:
    """A última linha do rastro — que é onde mora o motivo, em uma frase.

    É isso que cabe na tela do dono; o arquivo inteiro fica para quem for
    consertar.
    """
    if not texto:
        return ""
    linhas = [l.strip() for l in texto.strip().splitlines() if l.strip()]
    return linhas[-1][:300] if linhas else ""


def ler_e_limpar(caminho: str = CAMINHO):
    """Devolve o motivo da queda anterior e APAGA o arquivo. None se não houve.

    Apagar é o que faz o aviso aparecer uma vez só, na abertura seguinte à
    queda — e não para sempre.
    """
    try:
        with io.open(caminho, encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        return None
    try:
        os.remove(caminho)
    except OSError:
        pass
    return texto or None


QUEDA_ANTERIOR = None      # o que sobrou da execução passada, para a tela contar


PASTA_QUEDAS = os.path.join(cfg.CONFIG_DIR, "quedas")
MAX_QUEDAS = 20


def guardar_copia(texto: str, pasta: str = PASTA_QUEDAS):
    """Guarda uma cópia da queda em `queda-AAAAmmdd-HHMMSS.txt` (máx. 20).

    `ultimo_erro.txt` é apagado na abertura; sem a cópia o rastro se perderia
    antes de o piloto automático poder estudá-lo. Nunca levanta.
    """
    try:
        os.makedirs(pasta, exist_ok=True)
        nome = "queda-%s.txt" % time.strftime("%Y%m%d-%H%M%S")
        with io.open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
            f.write(texto)
        antigas = sorted(n for n in os.listdir(pasta)
                         if n.startswith("queda-") and n.endswith(".txt"))
        for n in antigas[:-MAX_QUEDAS]:
            os.remove(os.path.join(pasta, n))
    except OSError:
        pass
    return None


def colher_anterior(caminho: str = CAMINHO, pasta_quedas: str = PASTA_QUEDAS):
    """Lê o que sobrou da execução ANTERIOR e guarda em QUEDA_ANTERIOR.

    Chamar ANTES de `instalar()`: instalar zera o arquivo do faulthandler para
    poder escrever nele desta vez, e aí a queda de antes já se perdeu.
    """
    global QUEDA_ANTERIOR
    QUEDA_ANTERIOR = ler_e_limpar(caminho) or queda_dura(caminho)
    if QUEDA_ANTERIOR:
        guardar_copia(QUEDA_ANTERIOR, pasta_quedas)
    return QUEDA_ANTERIOR


def instalar(caminho: str = CAMINHO):
    """Liga os três laços de segurança. Chamar UMA vez, no arranque do app."""
    global _arquivo_duro

    def _da_tela(tipo, valor, tb):
        anotar("".join(traceback.format_exception(tipo, valor, tb)),
               origem="tela", caminho=caminho)
        sys.__excepthook__(tipo, valor, tb)

    def _de_thread(args):
        anotar("".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback)),
            origem="thread " + str(getattr(args.thread, "name", "?")),
            caminho=caminho)

    sys.excepthook = _da_tela
    threading.excepthook = _de_thread

    # Pane dura (o Qt abortando, falha de memória): aqui já não dá para rodar
    # Python, e só o faulthandler consegue deixar rastro.
    try:
        import faulthandler
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        _arquivo_duro = io.open(caminho + ".duro", "w", encoding="utf-8")
        faulthandler.enable(file=_arquivo_duro, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        _arquivo_duro = None


class _ComHora(io.TextIOBase):
    """Prefixa cada linha com a hora. É o `sys.stderr` do app aberto por `pythonw`."""

    def __init__(self, arquivo):
        self._f = arquivo
        self._inicio = True
        self._trava = threading.Lock()

    def writable(self):
        return True

    def write(self, texto):
        with self._trava:
            for parte in texto.splitlines(keepends=True):
                if self._inicio:
                    self._f.write(time.strftime("%d/%m %H:%M:%S "))
                self._f.write(parte)
                self._inicio = parte.endswith("\n")
            self._f.flush()
        return len(texto)

    def flush(self):
        self._f.flush()


def abrir_diario_de_execucao(caminho: str, limite: int = 2_000_000):
    """O diário do que o app faz por dentro (o que ia para o `stderr`). Aberto por `pythonw` o app
    não tem stderr, e no teste de voz de 15/10/2026 nenhuma decisão deixou rastro. Passou do
    `limite`, o atual vira `.1` (um só). Nunca guarda o que o dono falou: só o que o código escreve
    no stderr. Qualquer falha devolve None e o app segue sem diário."""
    try:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        if os.path.exists(caminho) and os.path.getsize(caminho) > limite:
            os.replace(caminho, caminho + ".1")
        return _ComHora(io.open(caminho, "a", encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def instalar_diario_de_execucao():
    """Sem console (pythonw), o stderr e o `logging` vão para %LOCALAPPDATA%\\dervs\\execucao.log."""
    if sys.stderr is not None and getattr(sys.stderr, "isatty", lambda: False)():
        return None
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/state")
    f = abrir_diario_de_execucao(os.path.join(base, "dervs", "execucao.log"))
    if f is None:
        return None
    sys.stderr = f
    import logging
    logging.basicConfig(level=logging.INFO, stream=f, format="%(name)s %(levelname)s %(message)s")
    sys.stderr.write("dervs: --- abriu ---\n")
    return f


def queda_dura(caminho: str = CAMINHO):
    """O que o faulthandler deixou na queda anterior, se deixou algo."""
    try:
        with io.open(caminho + ".duro", encoding="utf-8") as f:
            texto = f.read().strip()
    except OSError:
        return None
    return texto or None
