#!/usr/bin/env python3
"""Abrir os ajudantes do DERVS sem janela preta na tela do dono.

Por que este arquivo existe: em 02/09/2026 o dono relatou "fica uma janela
preta aberta". Não era enfeite nem sobra de instalação — era o terminal dos
dois processos ajudantes do DERVS, o ouvido (`dervs_stt_daemon.py`) e a voz
(`dervs_kokoro_daemon.py`). O rastro no Windows:

    conhost.exe 22744  <- pai 19008  dervs_stt_daemon.py
    conhost.exe 41280  <- pai  3528  dervs_kokoro_daemon.py

(`conhost.exe` é o programa que desenha a janela de terminal do Windows.)

Os dois eram abertos com `python.exe` — a versão do Python que VEM com
terminal — e sem nenhuma bandeira mandando escondê-lo. O Windows fez o que foi
pedido: criou a janela.

Duas camadas, de propósito:
  1. `python_sem_console` troca `python.exe` por `pythonw.exe`, que é o mesmo
     Python sem terminal nenhum. Resolve na raiz.
  2. `sem_janela` acrescenta a bandeira CREATE_NO_WINDOW. Resolve também o dia
     em que alguém apontar a variável `DERVS_PY` para um `python.exe` na mão.

Nada aqui vale fora do Windows: `pythonw` não existe no Linux, e lá um
processo filho simplesmente não abre janela.

De propósito, este arquivo NÃO importa PyQt6 nem nada do projeto — assim ele é
testável em qualquer Python, e um erro aqui nunca interrompe a coleta dos
outros testes.
"""
import os
import subprocess
import sys

WINDOWS = sys.platform == "win32"


def python_sem_console(caminho: str) -> str:
    """O mesmo Python, na versão que não abre terminal.

    Devolve o `pythonw.exe` que estiver ao lado do `python.exe` recebido. Se
    ele não estiver lá (ambiente incompleto, instalação estranha), devolve o
    caminho original sem reclamar: uma janela preta é um incômodo, um caminho
    quebrado deixaria o DERVS sem voz e sem ouvido — que é bem pior.
    """
    if not WINDOWS or not caminho:
        return caminho
    pasta, arquivo = os.path.split(caminho)
    if arquivo.lower() != "python.exe":
        return caminho
    sem_console = os.path.join(pasta, "pythonw.exe")
    return sem_console if os.path.exists(sem_console) else caminho


def sem_janela() -> dict:
    """Argumentos extras de `subprocess.Popen` que proíbem a janela preta.

    Devolve um dicionário para ser aberto com `**` na chamada. Fora do Windows
    vem vazio — `creationflags` não existe lá, e passar derrubaria a chamada.
    """
    if not WINDOWS:
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}
