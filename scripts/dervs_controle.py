#!/usr/bin/env python3
"""Liga, para, reinicia e reseta o DERVS — os botões que o dono usa quando o
ícone some da bandeja ou o app trava.

Rodar:  dervs-venv/Scripts/python.exe scripts/dervs_controle.py <comando>
  status      diz se está no ar e quais processos
  ligar       abre o DERVS (não abre um segundo se já estiver aberto)
  parar       fecha o DERVS e tudo que ele deixou vivo (voz, HUD)
  reiniciar   parar + ligar  (cura "sumiu da bandeja")
  resetar     parar, guarda cópia da config, volta ao padrão e liga
              (não apaga modelos de voz nem histórico de gasto)
"""
import os
import re
import sys
import time
import shutil
import subprocess

import psutil

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_DADOS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "dervs")
_SCRIPT = re.compile(r"^dervs.*\.py$", re.I)


def _dentro(caminho: str) -> bool:
    return os.path.normcase(caminho).startswith(os.path.normcase(RAIZ) + os.sep)


def _e_do_dervs(p) -> bool:
    try:
        nome = p.name().lower()
        if nome == "electron.exe":
            return _dentro(p.exe())
        if nome in ("python.exe", "pythonw.exe"):
            for arg in p.cmdline()[1:]:
                base = os.path.basename(arg)
                if base.lower() == "dervs_controle.py":
                    return False   # este próprio script (e o lançador dele) não é o app
                if _SCRIPT.match(base):
                    return _dentro(arg) or os.path.normcase(p.cwd()) == os.path.normcase(RAIZ)
    except (psutil.Error, OSError):
        pass
    return False


def filtrar(processos) -> list:
    return [p for p in processos if _e_do_dervs(p) and p.pid != os.getpid()]


def achar() -> list:
    return filtrar(psutil.process_iter())


def parar() -> int:
    vivos = achar()
    for p in vivos:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, restam = psutil.wait_procs(vivos, timeout=5)
    for p in restam:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(restam, timeout=3)
    return len(vivos)


def ligar() -> bool:
    if achar():
        return False
    py = os.path.join(RAIZ, "dervs-venv", "Scripts", "pythonw.exe")
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([py, "dervs_electron.py"], cwd=RAIZ, creationflags=flags,
                     close_fds=True)
    return True


def resetar(pasta: str = PASTA_DADOS) -> None:
    cfg = os.path.join(pasta, "config.json")
    if os.path.exists(cfg):
        shutil.move(cfg, f"{cfg}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    trava = os.path.join(pasta, "instancia.json")
    if os.path.exists(trava):
        os.remove(trava)


def main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        vivos = achar()
        print(f"DERVS no ar ({len(vivos)} processos)" if vivos else "DERVS parado")
        return 0
    if cmd in ("parar", "reiniciar", "resetar"):
        print(f"fechei {parar()} processos")
    if cmd == "resetar":
        resetar()
        print("config voltou ao padrão (cópia guardada ao lado)")
    if cmd in ("ligar", "reiniciar", "resetar"):
        if ligar():
            time.sleep(4)
            print("DERVS no ar" if achar() else "NÃO subiu — veja ultimo_erro.txt em " + PASTA_DADOS)
        else:
            print("já estava aberto")
    elif cmd not in ("parar",):
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
