#!/usr/bin/env python3
"""Nenhum ajudante do DERVS pode abrir uma janela preta na cara do dono.

Por que existe: em 02/09/2026 o dono relatou "fica uma janela preta aberta".
O rastro no Windows era direto — dois `conhost.exe` (o programa que DESENHA a
janela de terminal) pendurados nos ajudantes do DERVS:

    conhost.exe 22744  <- pai 19008  dervs_stt_daemon.py    (o ouvido)
    conhost.exe 41280  <- pai  3528  dervs_kokoro_daemon.py (a voz)

Causa: os dois eram abertos com `python.exe`, que é a versão do Python COM
terminal, e sem nenhuma bandeira mandando o Windows esconder a janela. O
Windows então cria um terminal — e ele fica lá, preto, sobrando na tela.

A correção tem duas camadas de propósito: usar `pythonw.exe` (a versão sem
terminal) E passar a bandeira CREATE_NO_WINDOW. Uma sozinha já resolveria o
caso de hoje; as duas juntas resolvem também o dia em que alguém apontar o
`DERVS_PY` para um `python.exe` na mão.

Rodar: python -m pytest test_dervs_processos.py -q
"""
import os
import subprocess
import sys

import pytest

import dervs_processos as proc


# ---- trocar python.exe por pythonw.exe ---------------------------------

def test_troca_python_por_pythonw_quando_ele_existe(tmp_path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "python.exe").write_text("")
    (scripts / "pythonw.exe").write_text("")
    escolhido = proc.python_sem_console(str(scripts / "python.exe"))
    assert os.path.basename(escolhido) == "pythonw.exe"


def test_mantem_python_quando_nao_ha_pythonw_ao_lado(tmp_path):
    """Ambiente incompleto não pode virar caminho quebrado: melhor a janela
    preta do que um ajudante que não abre."""
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "python.exe").write_text("")
    alvo = str(scripts / "python.exe")
    assert proc.python_sem_console(alvo) == alvo


def test_pythonw_ja_escolhido_fica_como_esta(tmp_path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "pythonw.exe").write_text("")
    alvo = str(scripts / "pythonw.exe")
    assert proc.python_sem_console(alvo) == alvo


def test_caminho_vazio_nao_estoura():
    assert proc.python_sem_console("") == ""


def test_no_linux_nada_muda(monkeypatch, tmp_path):
    """`pythonw` é invenção do Windows; no Linux não existe janela preta."""
    monkeypatch.setattr(proc, "WINDOWS", False)
    alvo = str(tmp_path / "bin" / "python")
    assert proc.python_sem_console(alvo) == alvo


# ---- a bandeira que esconde a janela -----------------------------------

def test_no_windows_pede_para_nao_criar_janela(monkeypatch):
    monkeypatch.setattr(proc, "WINDOWS", True)
    assert proc.sem_janela()["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_no_linux_nao_manda_bandeira_nenhuma(monkeypatch):
    """`creationflags` não existe fora do Windows — passar quebraria o app."""
    monkeypatch.setattr(proc, "WINDOWS", False)
    assert proc.sem_janela() == {}


@pytest.mark.skipif(sys.platform != "win32", reason="a bandeira é do Windows")
def test_a_bandeira_e_aceita_pelo_subprocess_de_verdade():
    """Prova que o valor é o que o `subprocess` espera — não um número solto."""
    p = subprocess.Popen([sys.executable, "-c", "pass"], **proc.sem_janela())
    assert p.wait(timeout=30) == 0


# ---- a lista dos daemons que precisam disso ----------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="janela preta é do Windows")
def test_o_ouvido_do_dervs_nao_usa_python_com_console():
    pytest.importorskip("PyQt6", reason="dervs.py é Qt; rode no dervs-venv")
    import dervs
    assert not dervs.STT_PY.lower().endswith("python.exe"), (
        "o daemon de transcrição abriria uma janela preta")


@pytest.mark.skipif(sys.platform != "win32", reason="janela preta é do Windows")
def test_a_voz_do_dervs_nao_usa_python_com_console():
    import dervs_tts
    for nome in ("PIPER_PY", "KOKORO_PY", "XTTS_PY"):
        caminho = getattr(dervs_tts, nome)
        assert not caminho.lower().endswith("python.exe"), (
            f"{nome} abriria uma janela preta")
