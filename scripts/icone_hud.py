"""Desenha os ícones do HUD (`assets/icone-app.svg` e `assets/icone-bandeja.svg`)
com QPainter, na linguagem "HUD/JARVIS" escolhida em `docs/esteira/dervs-cara-nova/
assets.md`.

Por que não carregar o `.svg` direto: o projeto já usa PyQt6 e já desenha ícones
via `QPainter` em `scripts/instalar_atalho.py:37-45` (o selo antigo); reaproveitar
o mesmo caminho evita depender de `QtSvg` só para isto. As coordenadas abaixo são
as mesmas do SVG mestre — cada arco é descrito pelos dois pontos do arquivo `.svg`
e o ângulo real de desenho é calculado a partir deles, para o resultado em Qt
reproduzir a mesma geometria, sem redigitar números aproximados à mão.
"""
import math

from PyQt6 import QtCore, QtGui

# Espaço de coordenadas do SVG mestre do ícone do app (0..256).
_LADO_SVG = 256.0
_CENTRO = (128.0, 128.0)
_RAIO_ANEL = 88.0

# Os quatro arcos do anel externo, cada um como (ponto inicial, ponto final),
# copiados de `assets/icone-app.svg`.
_ARCOS = [
    ((128, 40), (206, 90)),
    ((216, 128), (190, 196)),
    ((128, 216), (50, 190)),
    ((40, 128), (66, 60)),
]

# Os quatro ticks nos eixos cardeais, também copiados do mesmo SVG.
_TICKS = [
    ((128, 18), (128, 30)),
    ((238, 128), (226, 128)),
    ((128, 238), (128, 226)),
    ((18, 128), (30, 128)),
]


def _angulo(cx: float, cy: float, x: float, y: float) -> float:
    """Ângulo do ponto `(x, y)` visto do centro, na convenção do
    `QPainter.drawArc` (0° às 3 horas, positivo anti-horário)."""
    return math.degrees(math.atan2(-(y - cy), x - cx))


def pixmap(px: int) -> QtGui.QPixmap:
    """Desenha o ícone do app — anel de 4 arcos, 4 ticks nos eixos e núcleo
    ciano com centro branco — em um `QPixmap` quadrado de `px` pixels.

    É a versão completa, usada no `.ico` (`scripts/instalar_atalho.py`) e em
    qualquer lugar grande o bastante para o anel segmentado ler bem.
    """
    escala = px / _LADO_SVG
    pm = QtGui.QPixmap(px, px)
    pm.fill(QtGui.QColor("#050810"))

    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.scale(escala, escala)

    cx, cy = _CENTRO

    caneta_anel = QtGui.QPen(QtGui.QColor("#00E5FF"))
    caneta_anel.setWidthF(10)
    caneta_anel.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    p.setPen(caneta_anel)
    retangulo = QtCore.QRectF(cx - _RAIO_ANEL, cy - _RAIO_ANEL,
                              _RAIO_ANEL * 2, _RAIO_ANEL * 2)
    for (x0, y0), (x1, y1) in _ARCOS:
        a0 = _angulo(cx, cy, x0, y0)
        a1 = _angulo(cx, cy, x1, y1)
        p.drawArc(retangulo, round(a0 * 16), round((a1 - a0) * 16))

    caneta_tick = QtGui.QPen(QtGui.QColor("#0A6E82"))
    caneta_tick.setWidthF(4)
    p.setPen(caneta_tick)
    for (x0, y0), (x1, y1) in _TICKS:
        p.drawLine(QtCore.QPointF(x0, y0), QtCore.QPointF(x1, y1))

    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(QtGui.QColor("#00E5FF"))
    p.drawEllipse(QtCore.QPointF(cx, cy), 34, 34)
    p.setBrush(QtGui.QColor("#FFFFFF"))
    p.drawEllipse(QtCore.QPointF(cx, cy), 16, 16)

    p.end()
    return pm


def pixmap_bandeja(px: int) -> QtGui.QPixmap:
    """Desenha o ícone simplificado da bandeja — um anel fechado e o núcleo,
    sem ticks nem segmentação — em um `QPixmap` quadrado de `px` pixels.

    Por que é simplificado: em 16-32px, o anel de 4 arcos mais os 4 ticks e as
    duas cores do núcleo do ícone grande viram um borrão — a mesma composição
    que lê bem em 256px não sobrevive a menos de 5% do tamanho. A versão da
    bandeja (`assets/icone-bandeja.svg`) troca o anel segmentado por um anel
    fechado e o núcleo de duas cores por um único ponto cheio, porque nessa
    escala é isso que ainda lê como forma sólida (`assets.md`, seção 2).
    """
    lado_svg = 32.0
    escala = px / lado_svg
    pm = QtGui.QPixmap(px, px)
    pm.fill(QtGui.QColor("#050810"))

    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.scale(escala, escala)

    caneta_anel = QtGui.QPen(QtGui.QColor("#00E5FF"))
    caneta_anel.setWidthF(2.5)
    p.setPen(caneta_anel)
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawEllipse(QtCore.QPointF(16, 16), 11, 11)

    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(QtGui.QColor("#00E5FF"))
    p.drawEllipse(QtCore.QPointF(16, 16), 4, 4)

    p.end()
    return pm
