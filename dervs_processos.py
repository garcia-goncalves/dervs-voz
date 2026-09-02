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


def encerrar_arvore(proc) -> None:
    """Mata o processo E tudo que ele abriu. Nunca levanta exceção.

    `proc.kill()` sozinho mata só a casca. No Windows, quem derruba a árvore
    inteira é o `taskkill /T` (T de *tree*); no Linux, o grupo de processos.
    """
    if proc.poll() is not None:
        return                          # já morreu sozinho: nada a fazer
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30, **sem_janela())
        else:
            os.killpg(os.getpgid(proc.pid), 9)
    except Exception:
        pass
    try:
        proc.kill()                     # rede: se o taskkill falhou, mata a casca
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def rodar_com_arvore(cmd, timeout=None, capture_output=False, **kwargs):
    """`subprocess.run` com UMA diferença, e ela importa muito.

    Quando o tempo estoura, o `subprocess.run` do Python mata só o processo que
    ele mesmo abriu. Os netos ficam vivos, órfãos, sem ninguém sabendo.

    Isso mordeu o DERVS em dois lugares (revisão de 02/09/2026):

      - o dono pede "roda o nmap no alvo"; o `powershell.exe` dispara o
        `nmap.exe`. Passa dos 60 s, o PowerShell morre, o **nmap continua
        varrendo a rede** — e a tela diz "foi interrompido";
      - o navegador autônomo abre o Chrome do dono com o perfil de verdade.
        Passa do tempo, o Python que o comandava morre sem rodar o `finally`
        que fecha o navegador, e sobra um `chrome.exe` **segurando o perfil**.
        Depois disso o dono não abre mais o próprio Chrome e não tem como
        adivinhar que foi o DERVS.

    Levanta `subprocess.TimeoutExpired` como o original — quem chama já trata
    essa exceção, e mudar o contrato quebraria os dois lugares de uma vez.
    """
    if capture_output:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    if not WINDOWS:
        # no Linux o grupo de processos é o que torna o `killpg` possível
        kwargs.setdefault("start_new_session", True)

    proc = subprocess.Popen(cmd, **kwargs)
    try:
        saida, erro = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        encerrar_arvore(proc)
        try:
            saida, erro = proc.communicate(timeout=10)
        except Exception:
            saida, erro = None, None
        raise subprocess.TimeoutExpired(cmd, timeout, output=saida, stderr=erro)
    return subprocess.CompletedProcess(cmd, proc.returncode, saida, erro)
