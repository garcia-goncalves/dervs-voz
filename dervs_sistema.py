#!/usr/bin/env python3
"""DERVS — leitura real de CPU/RAM/disco desta máquina, para o painel do HUD.

Fase 1 da esteira `dervs-painel-completo` (ver `docs/esteira/dervs-painel-completo/`):
o dono pediu um "painel de desktop completo" com dado real, "sem firula" — isto é
literalmente isso, nada além do que `psutil` já sabe medir.

Regra de ouro do projeto (a mesma de `dervs_config.py`): um recurso novo NUNCA pode
deixar o DERVS mudo/quebrado. Se `psutil` não estiver instalado (dono ainda não rodou
`pip install -r requirements.txt` depois de puxar esta mudança), `coletar_stats()`
devolve `None` e o chamador some com o painel de sistema em silêncio — o núcleo com
os anéis, a voz e o resto continuam funcionando exatamente como antes.
"""
import os
import sys
import threading

try:
    import psutil
except ImportError:  # ver docstring — nunca derruba o DERVS por isto
    psutil = None

INTERVALO_PADRAO_SEG = 2.0

# Sentinela para distinguir "não passou o argumento" (usa o psutil de
# verdade) de "passou None de propósito" (simula "psutil não instalado" —
# é exatamente o que os testes fazem). Usar None como valor-padrão do
# parâmetro confundia os dois casos: um teste passando `modulo_psutil=None`
# acabava caindo no psutil real da máquina, em vez de simular a ausência.
_SEM_ARGUMENTO = object()


def _disco_padrao() -> str:
    """A unidade onde o próprio DERVS está instalado — é o disco que importa
    para o dono, não necessariamente o `C:` (a máquina pode ter o repositório
    em outra unidade)."""
    raiz = os.path.splitdrive(os.path.abspath(__file__))[0] or os.path.abspath(os.sep)
    return raiz + os.sep if raiz else os.path.abspath(os.sep)


def coletar_stats(caminho_disco: str | None = None, modulo_psutil=_SEM_ARGUMENTO) -> dict | None:
    """Lê CPU%, RAM% e disco (livre/total em GB) desta máquina.

    `modulo_psutil` existe só para teste (injeta um dublê, ou `None` para
    simular "psutil não instalado", sem precisar medir a máquina de
    verdade). Sem argumento nenhum, usa o `psutil` real — ou devolve `None`
    se ele não estiver instalado.
    """
    mod = psutil if modulo_psutil is _SEM_ARGUMENTO else modulo_psutil
    if mod is None:
        return None
    caminho = caminho_disco or _disco_padrao()
    try:
        cpu = float(mod.cpu_percent(interval=None))
        ram = float(mod.virtual_memory().percent)
        uso_disco = mod.disk_usage(caminho)
        livre_gb = uso_disco.free / (1024 ** 3)
        total_gb = uso_disco.total / (1024 ** 3)
    except (OSError, ValueError, AttributeError):
        return None
    return {
        "cpu": round(max(0.0, min(100.0, cpu)), 1),
        "ram": round(max(0.0, min(100.0, ram)), 1),
        "disco_livre_gb": round(max(0.0, livre_gb), 1),
        "disco_total_gb": round(max(0.0, total_gb), 1),
    }


def _um_passo(ponte, coletar=coletar_stats) -> bool:
    """Uma leitura + um envio. Separado do laço só para dar para testar sem
    precisar de thread nem de tempo real (ver `test_dervs_sistema.py`)."""
    stats = coletar()
    if stats is None:
        return False
    ponte.enviar_sistema(**stats)
    return True


def iniciar_loop_sistema(ponte, parar_evento: threading.Event,
                          intervalo: float = INTERVALO_PADRAO_SEG,
                          coletar=coletar_stats) -> threading.Thread:
    """Sobe a thread (daemon) que manda CPU/RAM/disco pela ponte a cada
    `intervalo` segundos, até `parar_evento` ser marcado. Avisa no stderr UMA
    vez só se `psutil` não estiver disponível — nunca em laço, para não
    inundar o log."""
    def _laco():
        avisou_falta = False
        while not parar_evento.is_set():
            if not _um_passo(ponte, coletar) and not avisou_falta:
                sys.stderr.write(
                    "sistema: psutil nao instalado — paineis de CPU/RAM/disco do "
                    "HUD ficam sem dado ate 'pip install -r requirements.txt'\n")
                avisou_falta = True
            parar_evento.wait(intervalo)
    t = threading.Thread(target=_laco, daemon=True)
    t.start()
    return t
