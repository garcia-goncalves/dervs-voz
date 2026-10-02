"""Controle do DERVS (ligar, parar, reiniciar, resetar) — o dono não usa
terminal e o app já sumiu da bandeja uma vez; precisa de botão que resolva."""
import json
import os

import pytest

from scripts import dervs_controle as c

RAIZ = c.RAIZ


class Falso:
    def __init__(self, pid, nome, linha, cwd=RAIZ, exe=""):
        self.pid, self._nome, self._linha, self._cwd, self._exe = pid, nome, linha, cwd, exe

    def name(self): return self._nome
    def cmdline(self): return self._linha
    def cwd(self): return self._cwd
    def exe(self): return self._exe


def test_reconhece_so_os_processos_do_dervs():
    meus = [
        Falso(1, "pythonw.exe", ["pythonw.exe", "dervs_electron.py"]),
        Falso(2, "pythonw.exe", ["C:/Python312/pythonw.exe", "dervs_stt_daemon.py"]),
        Falso(3, "electron.exe", ["x"], exe=os.path.join(RAIZ, "electron", "node_modules", "electron", "dist", "electron.exe")),
    ]
    alheios = [
        Falso(4, "pythonw.exe", ["pythonw.exe", "dervs_electron.py"], cwd="C:/outro"),
        Falso(5, "electron.exe", ["x"], exe="C:/Users/x/Code.exe"),
        Falso(6, "python.exe", ["python.exe", "outra_coisa.py"]),
        Falso(7, "python.exe", ["python.exe", "scripts/dervs_controle.py", "reiniciar"]),
    ]
    achados = c.filtrar(meus + alheios)
    assert sorted(p.pid for p in achados) == [1, 2, 3]


def test_reset_guarda_copia_e_limpa_trava(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"a": 1}))
    (tmp_path / "instancia.json").write_text("{}")
    (tmp_path / "cerebro.json").write_text("{}")
    c.resetar(str(tmp_path))
    assert not (tmp_path / "config.json").exists()
    assert not (tmp_path / "instancia.json").exists()
    copias = [f for f in os.listdir(tmp_path) if f.startswith("config.json.bak-")]
    assert len(copias) == 1
    assert json.loads((tmp_path / copias[0]).read_text()) == {"a": 1}
    assert (tmp_path / "cerebro.json").exists()   # só a config volta ao padrão


def test_reset_sem_config_nao_quebra(tmp_path):
    c.resetar(str(tmp_path))
