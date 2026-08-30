#!/usr/bin/env python3
"""Painel flutuante do Agente DERVS — dois botoes: Ouvir e Enviar.
Sempre no topo, arrastavel. Ouvir liga/desliga o ditado por voz;
Enviar manda a mensagem (tecla Enter) para a janela em foco (o DERVS).

Se a bandeja do sistema existir, o painel NUNCA morre ao clicar no X:
ele se esconde e fica um icone fixo na bandeja (perto do relogio); clicar
no icone traz o painel de volta. Botao direito no icone -> Sair para fechar
de verdade. Se NAO houver bandeja (ex.: painel subiu antes do KDE no login),
o X fecha normal, para o programa nunca ficar invisivel e travado."""
import os, subprocess, signal
# Forca XWayland para 'sempre no topo' funcionar de forma confiavel no KDE Wayland
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
from PyQt6 import QtCore, QtGui, QtWidgets

HOME = os.path.expanduser("~")
FALAR = f"{HOME}/.local/bin/falar"

def ouvindo() -> bool:
    return subprocess.run(["pgrep", "-f", "nerd-dictation begin"],
                          capture_output=True).returncode == 0

def enviar_enter():
    # garante o daemon do ydotool e envia Enter (keycode 28)
    if subprocess.run(["pgrep", "-x", "ydotoold"], capture_output=True).returncode != 0:
        subprocess.Popen(["ydotoold"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["ydotool", "key", "28:1", "28:0"])

def _icone_dervs(ativo: bool = False) -> QtGui.QIcon:
    """Icone do DERVS para a bandeja. Tenta o tema; se nao houver, desenha
    um ponto colorido (verde parado, vermelho ouvindo)."""
    tema = QtGui.QIcon.fromTheme("audio-input-microphone")
    if not tema.isNull() and not ativo:
        return tema
    pix = QtGui.QPixmap(64, 64); pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    cor = QtGui.QColor("#c0392b") if ativo else QtGui.QColor("#4ade80")
    p.setBrush(cor); p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawEllipse(10, 10, 44, 44)
    p.end()
    return QtGui.QIcon(pix)

class Painel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.tray = None
        self.tem_bandeja = QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()
        self.setWindowTitle("DERVS")
        # Janela NORMAL (sem Qt.Tool) para aparecer na barra de tarefas;
        # sem moldura e sempre no topo.
        self.setWindowFlags(QtCore.Qt.WindowType.Window
                            | QtCore.Qt.WindowType.FramelessWindowHint
                            | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowIcon(_icone_dervs(False))
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag = None

        card = QtWidgets.QWidget(self); card.setObjectName("card")
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.addWidget(card)
        v = QtWidgets.QVBoxLayout(card); v.setContentsMargins(12,8,12,10); v.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        titulo = QtWidgets.QLabel("● DERVS"); titulo.setObjectName("titulo")
        fechar = QtWidgets.QPushButton("✕"); fechar.setObjectName("x"); fechar.setFixedSize(20,20)
        fechar.setToolTip("Minimizar para a barra de tarefas (clique na barra para voltar)")
        fechar.clicked.connect(self._acao_fechar)
        top.addWidget(titulo); top.addStretch(); top.addWidget(fechar)
        v.addLayout(top)

        self.b_ouvir = QtWidgets.QPushButton("\U0001f3a4  Ouvir")
        self.b_ouvir.setObjectName("ouvir"); self.b_ouvir.setMinimumHeight(44)
        self.b_ouvir.clicked.connect(self.toggle_ouvir)
        v.addWidget(self.b_ouvir)

        self.b_enviar = QtWidgets.QPushButton("✉️  Enviar")
        self.b_enviar.setObjectName("enviar"); self.b_enviar.setMinimumHeight(40)
        self.b_enviar.clicked.connect(enviar_enter)
        v.addWidget(self.b_enviar)

        self.setStyleSheet("""
            #card { background:#151a21; border:1px solid #2b3540; border-radius:14px; }
            #titulo { color:#4ade80; font-weight:600; font-size:12px; }
            #x { color:#8a94a0; border:none; background:transparent; font-size:13px; }
            #x:hover { color:#ff6b6b; }
            QPushButton#ouvir  { color:#eaf2ff; background:#1f6feb; border:none; border-radius:10px; font-size:15px; font-weight:600; }
            QPushButton#ouvir:hover { background:#2b7cf7; }
            QPushButton#enviar { color:#eaf2ff; background:#2f3a46; border:none; border-radius:10px; font-size:14px; }
            QPushButton#enviar:hover { background:#3a4653; }
        """)
        self.resize(180, 130)
        self._posicionar_canto()

        if self.tem_bandeja:
            self._montar_bandeja()

        # estado anti-piscar do indicador de microfone
        self._trava = 0            # ciclos que o botao fica travado apos um clique
        self._ultimo = None        # ultima leitura crua de ouvindo()
        self._confirma = 0         # quantas leituras iguais seguidas (debounce)

        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.atualizar)
        self.timer.start(500); self.atualizar()

    def _montar_bandeja(self):
        """Icone fixo na bandeja do sistema. Sobrevive ao esconder o painel."""
        self.tray = QtWidgets.QSystemTrayIcon(_icone_dervs(False), self)
        self.tray.setToolTip("DERVS - clique para mostrar/esconder o painel")

        menu = QtWidgets.QMenu()
        self.acao_mostrar = menu.addAction("Mostrar painel")
        self.acao_mostrar.triggered.connect(self.mostrar_painel)
        menu.addSeparator()
        acao_sair = menu.addAction("Sair (fechar o DERVS)")
        acao_sair.triggered.connect(QtWidgets.QApplication.quit)
        self.tray.setContextMenu(menu)

        # clique (esquerdo) ou duplo clique no icone alterna o painel
        self.tray.activated.connect(self._clique_bandeja)
        self.tray.show()

    def _clique_bandeja(self, motivo):
        if motivo in (QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
                      QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.showMinimized()
            else:
                self.mostrar_painel()

    def mostrar_painel(self):
        self._posicionar_canto()
        self.showNormal(); self.raise_(); self.activateWindow()

    def _acao_fechar(self):
        # O X minimiza para a barra de tarefas (nao fecha o programa).
        self.showMinimized()

    # fechar pela janela (ex.: "Fechar" da barra do KDE) tambem so minimiza,
    # para o DERVS nunca sumir de vez. Sair de verdade: menu da bandeja.
    def closeEvent(self, e):
        e.ignore(); self.showMinimized()

    def _posicionar_canto(self):
        tela = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.move(tela.right()-self.width()-24, tela.bottom()-self.height()-24)

    def toggle_ouvir(self):
        # ignora clique repetido durante a transicao (evita ligar/desligar sem querer)
        if self._trava > 0:
            return
        indo_ligar = not ouvindo()
        self._trava = 4            # ~2s travado (4 x 500ms)
        self.b_ouvir.setEnabled(False)
        self.b_ouvir.setText("⏳  iniciando..." if indo_ligar else "⏳  parando...")
        self.b_ouvir.setStyleSheet("background:#6b7280;")
        subprocess.Popen(["bash", FALAR])

    def atualizar(self):
        # segura o estado transitorio logo apos o clique, sem piscar
        if self._trava > 0:
            self._trava -= 1
            if self._trava > 0:
                return
            self.b_ouvir.setEnabled(True)

        bruto = ouvindo()
        # debounce: so muda a UI apos 2 leituras iguais seguidas (mata o pisca-pisca)
        if bruto == self._ultimo:
            self._confirma += 1
        else:
            self._ultimo = bruto
            self._confirma = 1
        if self._confirma < 2:
            return
        ativo = bruto

        if ativo:
            self.b_ouvir.setText("\U0001f534  Ouvindo... (fale a vontade)")
            self.b_ouvir.setStyleSheet("background:#c0392b;")
        else:
            self.b_ouvir.setText("\U0001f3a4  Ouvir")
            self.b_ouvir.setStyleSheet("")
        if self.tray is not None:
            self.tray.setToolTip("DERVS - Ouvindo" if ativo
                                 else "DERVS - clique para mostrar/esconder o painel")
            self.tray.setIcon(_icone_dervs(ativo))

    # arrastar a janela pela area do card
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QtWidgets.QApplication([])
    p = Painel()
    # so segura o programa vivo sem janela se houver bandeja para reabrir
    app.setQuitOnLastWindowClosed(not p.tem_bandeja)
    p.show()
    app.exec()
