#!/usr/bin/env python3
"""Gera os PNGs da bandeja do sistema a partir de `scripts/icone_hud.py`.

Não gera o `.ico` do app — isso é feito por `scripts/instalar_atalho.py`
(Etapa 10 da esteira `dervs-cara-nova`), que passou a desenhar
`icone_hud.pixmap(px)` em vez do selo antigo.

Rodar:  dervs-venv\\Scripts\\python.exe scripts\\gerar_icones.py
Refazer é seguro: sobrescreve o que já existe.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import icone_hud  # noqa: E402

DESTINO = os.path.join(RAIZ, "electron", "assets")

# 16px para o ícone padrão da bandeja do Windows, 32px para telas de alta
# densidade (o Windows escolhe sozinho conforme o DPI).
TAMANHOS_BANDEJA = [16, 32]


def main() -> None:
    from PyQt6 import QtWidgets
    # QPixmap exige uma aplicação Qt viva, mesmo sem mostrar janela nenhuma.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    os.makedirs(DESTINO, exist_ok=True)
    for px in TAMANHOS_BANDEJA:
        caminho = os.path.join(DESTINO, f"bandeja-{px}.png")
        if not icone_hud.pixmap_bandeja(px).save(caminho, "PNG"):
            raise SystemExit(f"não consegui salvar {caminho}")
        print("bandeja:", caminho)

    del app


if __name__ == "__main__":
    main()
