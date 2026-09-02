#!/usr/bin/env python3
"""Cria o ícone do DERVS e os atalhos para abrir o app com dois cliques.

Por que existe: até 02/09/2026 o único jeito de abrir o DERVS era digitar
`dervs-venv\\Scripts\\python.exe dervs.py` num terminal. O dono não usa
terminal — na prática o app não tinha como ser aberto por ele.

O que faz:
  1. desenha `dervs.ico` a partir do MESMO selo que a janela usa (`dervs._selo`),
     em todos os tamanhos que o Windows pede (16 a 256);
  2. cria o atalho "DERVS" na Área de Trabalho e no menu Iniciar, apontando para
     o `pythonw.exe` do ambiente do projeto — `pythonw`, e não `python`, porque
     o `python.exe` abre junto uma janela preta de terminal que fica aberta o
     tempo todo atrás do app.

Rodar:  dervs-venv\\Scripts\\python.exe scripts\\instalar_atalho.py
Refazer é seguro: sobrescreve o que já existe.
"""
import os
import io
import sys
import struct
import subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

ICONE = os.path.join(RAIZ, "dervs.ico")

# O Windows escolhe o tamanho conforme o lugar: 16 no canto da janela, 32 na
# barra de tarefas, 48 na Área de Trabalho, 256 na visualização grande. Um .ico
# com só o tamanho grande fica BORRADO nos pequenos, porque quem reduz é o
# sistema. Desenhar cada tamanho sai nítido em todos.
TAMANHOS = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def _png_de(px: int) -> bytes:
    """Desenha o selo naquele tamanho e devolve os bytes de um PNG."""
    from PyQt6 import QtCore
    import dervs
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    if not dervs._selo(px).save(buf, "PNG"):
        raise SystemExit(f"não consegui desenhar o selo em {px}px")
    return bytes(buf.data())


def gerar_icone() -> str:
    """Monta o .ico com todos os tamanhos dentro e devolve o caminho.

    O formato .ico aceita cada imagem embutida como PNG — é o que o Windows
    Vista em diante usa. O Qt grava .ico com UM tamanho só, então o arquivo é
    montado aqui: cabeçalho de 6 bytes, uma entrada de 16 bytes por tamanho, e
    os PNGs em seguida.
    """
    from PyQt6 import QtWidgets
    # QPixmap exige uma aplicação Qt viva, mesmo sem mostrar janela nenhuma.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    imagens = [(px, _png_de(px)) for px in TAMANHOS]
    saida = io.BytesIO()
    saida.write(struct.pack("<HHH", 0, 1, len(imagens)))   # reservado, tipo 1=ícone, quantos
    deslocamento = 6 + 16 * len(imagens)
    for px, dados in imagens:
        # 0 no campo de tamanho significa 256 — o byte não vai além de 255.
        lado = px if px < 256 else 0
        saida.write(struct.pack("<BBBBHHII", lado, lado, 0, 0, 1, 32,
                                len(dados), deslocamento))
        deslocamento += len(dados)
    for _, dados in imagens:
        saida.write(dados)

    with open(ICONE, "wb") as f:
        f.write(saida.getvalue())
    del app
    return ICONE


_PS = r'''
$ws = New-Object -ComObject WScript.Shell
$l = $ws.CreateShortcut("{destino}")
$l.TargetPath       = "{alvo}"
$l.Arguments        = '"{script}"'
$l.WorkingDirectory = "{raiz}"
$l.IconLocation     = "{icone},0"
$l.Description      = "{descricao}"
$l.Save()
'''


def criar_atalho(destino: str, alvo: str, script: str, descricao: str) -> None:
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    ps = _PS.format(destino=destino, alvo=alvo, script=script, raiz=RAIZ,
                    icone=ICONE, descricao=descricao)
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"falhou criar {destino}: {r.stderr.strip()[:300]}")


# Os dois atalhos que o dono ganha. O segundo abre o seletor de arquivos e
# transcreve o áudio escolhido — usa `python.exe`, e não `pythonw`, porque aqui
# a janela de console É a interface: é nela que aparece o andamento
# ("pedaço 3 de 8") de um envio que pode levar minutos.
ATALHOS = [
    ("DERVS", "dervs.py", "pythonw.exe",
     "DERVS - seu parceiro de voz"),
    ("DERVS - Transcrever audio", "dervs_transcrever.py", "python.exe",
     "Escolha um audio e receba o texto"),
]


def _lugares_de_atalho() -> list:
    """Onde pôr o atalho. A Área de Trabalho pode estar dentro do OneDrive ou
    não, dependendo de o backup estar ligado — por isso as duas são tentadas e
    só as que existirem de fato recebem o atalho."""
    home = os.path.expanduser("~")
    appdata = os.path.join(home, "AppData", "Roaming")
    return [
        os.path.join(home, "Desktop"),
        os.path.join(home, "OneDrive", "Área de Trabalho"),
        os.path.join(home, "OneDrive", "Desktop"),
        os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"),
    ]


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("este instalador é do Windows; em Linux o projeto irmão "
                         "usa um arquivo .desktop")
    print("ícone:", gerar_icone())

    feitos = 0
    for pasta in _lugares_de_atalho():
        # o menu Iniciar é criado se faltar; a Área de Trabalho, não — se ela
        # não existe naquele lugar, é porque a de verdade está no outro.
        if "Start Menu" not in pasta and not os.path.isdir(pasta):
            continue
        for nome, script, exe, descricao in ATALHOS:
            alvo = os.path.join(RAIZ, "dervs-venv", "Scripts", exe)
            if not os.path.exists(alvo):
                raise SystemExit(f"não achei {alvo} — o ambiente do projeto não "
                                 "está criado")
            destino = os.path.join(pasta, nome + ".lnk")
            criar_atalho(destino, alvo, os.path.join(RAIZ, script), descricao)
            print("atalho:", destino)
            feitos += 1
    if not feitos:
        raise SystemExit("nenhum atalho criado — não achei nem Área de Trabalho "
                         "nem menu Iniciar")


if __name__ == "__main__":
    main()
