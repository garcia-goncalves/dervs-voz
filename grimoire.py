#!/usr/bin/env python3
"""Grimoire — companheiro de voz do assistente.

Um selo flutuante embaixo da tela. Clique nele e abre um pop-up no centro:
Gravar/Parar, um campo que recebe o texto da sua fala, e três ações — Copiar,
Enviar e Executar. A fala é transcrita offline pelo Whisper large-v3-turbo
(faster-whisper).

Copiar/Enviar são o simples: copia o texto, ou cola na janela onde você estava.
Executar é o coração: abre uma CONVERSA com o cérebro (o Claude, rodando nesta
máquina). Você fala, ele pergunta até não ter dúvida, propõe um plano com o
comando à vista, e só roda depois que você confirma — com três trilhos de risco
e a palavra final da máquina sobre o perigo. Pode falar de volta (voz, Piper).

Identidade visual: segue o "Grimório Arcano" do produto — geométrico, ouro (o
que se ganha) + arcano (o que se descobre) sobre fundo quase preto."""
import os, subprocess, signal, json, sys, threading
# Forca XWayland para 'sempre no topo' funcionar de forma confiavel no KDE Wayland
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
from PyQt6 import QtCore, QtGui, QtWidgets

import time
import grimoire_safety as seg
import grimoire_brain as brain
import grimoire_exec as execu
import grimoire_atalhos as atalhos
import grimoire_config as cfg
from grimoire_tts import Voz
from grimoire_listen import Endpointer, salvar_wav, separar_chamada, FRAME_BYTES

HOME = os.path.expanduser("~")

# --- caminhos da voz (mesmos do script 'falar') ---
VOICE_DIR = f"{HOME}/voice"
PY_VOZ    = f"{VOICE_DIR}/.venv/bin/python"
ND        = f"{VOICE_DIR}/nerd-dictation/nerd-dictation"   # motor antigo (Vosk), aposentado
MODEL     = f"{VOICE_DIR}/model"

# --- motor de voz novo: Whisper large-v3-turbo via faster-whisper ---
STT_PY    = f"{VOICE_DIR}/whisper-venv/bin/python"   # python do ambiente isolado do Whisper
STT_DMN   = f"{VOICE_DIR}/grimoire_stt_daemon.py"    # cérebro que fica carregado esperando fala
REC_WAV   = "/tmp/grimoire_rec.wav"                  # onde a gravação é salva antes de transcrever

# --- paleta Grimorio Arcano (valores do globals.css do produto) ---
INK      = "#07080e"   # fundo mais fundo
INK_CARD = "#12151f"   # cartao
INK_LINE = "#262d3d"   # bordas
PARCH    = "#ece8dc"   # texto (pergaminho)
PARCH_DIM= "#9c9ca8"   # texto secundario
GOLD     = "#f2c568"   # ouro — o que se GANHA
GOLD_DEEP= "#e7b34e"
ARCANE   = "#8a93f2"   # arcano — o que se DESCOBRE
ARCANE_LT= "#b3b9ff"
REC      = "#e8677a"   # sinal baixo — usado so como ponto de 'gravando'

FONTE_UI     = "Inter, 'Noto Sans', sans-serif"
FONTE_TITULO = "Fraunces, Georgia, serif"

# --- rótulos e cores de cada trilho de risco ---
RISCO_COR = {"reversivel": ARCANE, "muda_estado": GOLD, "destrutivo": REC}
RISCO_TXT = {
    "reversivel":  "reversível — um Confirmar basta",
    "muda_estado": "muda algo — confira o comando",
    "destrutivo":  "perigoso — dupla confirmação",
}


def _ydotoold():
    if subprocess.run(["pgrep", "-x", "ydotoold"], capture_output=True).returncode != 0:
        subprocess.Popen(["ydotoold"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# Estado de gravação compartilhado entre o pop-up e o selo flutuante (que o lê para acender).
_ESTADO = {"gravando": False}


def gravando() -> bool:
    return _ESTADO["gravando"]


def _selo(px: int = 44, aceso: bool = False) -> QtGui.QPixmap:
    """O selo do Grimoire: losango (grimorio fechado) + faceta dourada + um raio
    curto que termina num ponto aceso (o achado). 'aceso' = gravando (ponto brilha)."""
    pm = QtGui.QPixmap(px, px); pm.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    c = px / 2; d = px * 0.40

    # losango (selo fechado)
    losango = QtGui.QPolygonF([QtCore.QPointF(c, c-d), QtCore.QPointF(c+d, c),
                               QtCore.QPointF(c, c+d), QtCore.QPointF(c-d, c)])
    p.setPen(QtGui.QPen(QtGui.QColor(GOLD_DEEP), max(1.5, px*0.045)))
    p.setBrush(QtGui.QBrush(QtGui.QColor(INK_CARD)))
    p.drawPolygon(losango)

    # faceta dourada revelada por dentro (triangulo)
    faceta = QtGui.QPolygonF([QtCore.QPointF(c, c-d*0.55), QtCore.QPointF(c+d*0.5, c),
                              QtCore.QPointF(c, c+d*0.15)])
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(QtGui.QBrush(QtGui.QColor(GOLD)))
    p.drawPolygon(faceta)

    # raio curto ate o ponto aceso
    fim = QtCore.QPointF(c+d*0.62, c-d*0.62)
    p.setPen(QtGui.QPen(QtGui.QColor(ARCANE), max(1.0, px*0.03)))
    p.drawLine(QtCore.QPointF(c, c), fim)

    # ponto aceso (arcano parado; ouro forte e maior quando gravando)
    cor_ponto = QtGui.QColor(GOLD if aceso else ARCANE_LT)
    r = px*0.09 if aceso else px*0.06
    if aceso:  # halo
        halo = QtGui.QColor(GOLD); halo.setAlpha(70)
        p.setBrush(QtGui.QBrush(halo)); p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawEllipse(fim, r*2.1, r*2.1)
    p.setBrush(QtGui.QBrush(cor_ponto)); p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawEllipse(fim, r, r)
    p.end()
    return pm


class Tarefa(QtCore.QThread):
    """Roda uma função pesada (chamar o cérebro, rodar um comando) fora da tela,
    para a janela não congelar. Emite 'pronto' com o resultado, ou 'erro'."""
    pronto = QtCore.pyqtSignal(object)
    erro = QtCore.pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn; self._args = args; self._kwargs = kwargs

    def run(self):
        try:
            self.pronto.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:
            self.erro.emit(str(e))


class Escuta(QtCore.QThread):
    """Escuta o microfone o tempo todo e, quando você termina uma frase, avisa
    (emite o caminho de um .wav pronto para transcrever). É o que permite
    conversar sem clicar em Gravar/Parar. Enquanto o Grimoire fala ou trabalha,
    fica 'pausado' — para não escutar a própria voz nem atropelar."""
    fala = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._rodando = False
        self.pausado = False
        self._proc = None

    def run(self):
        self._rodando = True
        ep = Endpointer()
        estava_pausado = False
        while self._rodando:
            try:
                self._proc = subprocess.Popen(
                    ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                sys.stderr.write("grimoire: não consegui abrir o microfone (%s)\n" % e)
                sys.stderr.flush()
                return
            try:
                while self._rodando:
                    frame = self._proc.stdout.read(FRAME_BYTES)
                    if not frame or len(frame) < FRAME_BYTES:
                        break               # arecord morreu: sai para religar
                    if self.pausado:
                        if not estava_pausado:
                            ep.reset()      # entrou na pausa: descarta a frase pela metade
                            estava_pausado = True
                        # aquecer mantém o pre-roll cheio: quando a pausa acabar, a
                        # primeira sílaba da resposta não se perde
                        ep.aquecer(frame)
                        continue
                    estava_pausado = False
                    pcm = ep.processar(frame)
                    if pcm:
                        caminho = "/tmp/grimoire_fala_%d.wav" % int(time.time() * 1000)
                        salvar_wav(pcm, caminho)
                        self.fala.emit(caminho)
            finally:
                erro = b""
                try:
                    erro = self._proc.stderr.read() or b""
                except Exception:
                    pass
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            if self._rodando:
                # o microfone caiu sozinho (troca de dispositivo, pipewire reiniciou):
                # religa em vez de ficar surdo para sempre, como acontecia antes.
                sys.stderr.write("grimoire: microfone caiu, religando em 1s %s\n"
                                 % erro.decode("utf-8", "replace").strip()[:200])
                sys.stderr.flush()
                time.sleep(1.0)

    def parar(self):
        """Para a escuta de verdade: mata o arecord para o read() destravar na
        hora (senão a thread ficaria presa lendo o microfone)."""
        self._rodando = False
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass


class PopUp(QtWidgets.QWidget):
    """Janela central: gravar, conversa, e as três ações (copiar/enviar/executar)."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Grimoire")
        self.setWindowFlags(QtCore.Qt.WindowType.Window
                            | QtCore.Qt.WindowType.FramelessWindowHint
                            | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowIcon(QtGui.QIcon(_selo(64)))
        self._drag = None
        self._trava = 0
        self._ultimo = None
        self._confirma = 0

        # --- estado do Executar (a conversa) ---
        # config do dono (~/.config/grimoire/config.json): voz, tempo até dormir
        # e se os atalhos locais estão ligados. Cai no padrão se faltar/tortar.
        cfg.garantir_arquivo()
        self._conf = cfg.carregar()
        # Voz LIGADA por padrão (se o Piper/voz existirem): o dono ouve as
        # respostas sem precisar caçar botão. Desliga no botão se quiser silêncio.
        self.voz = Voz(ligada=False, motor=self._conf["motor"],
                       voz=self._conf["voz"], voz_kokoro=self._conf["voz_kokoro"])
        self.voz.ligada = self.voz.disponivel()
        self.escuta = None             # thread de escuta contínua (modo conversa)
        self._auto_submeter = False    # a próxima transcrição veio da conversa contínua?
        self._transcrevendo = False    # esperando o Whisper terminar uma frase da conversa
        self._fila_fala = []           # frases que chegaram enquanto ele estava ocupado
        self.MAX_FILA = 4              # guarda no máximo 4 — depois é conversa velha demais
        self._desperto = False         # já acordou pela palavra "Grimoire"?
        self._desperto_ate = 0.0       # até quando fica desperto sem repetir o nome
        self.JANELA_DESPERTO = self._conf["janela_desperto_seg"]  # segs ouvindo após te atender
        self._atalhos_ligados = self._conf["atalhos_ligados"]     # responder trivial sem o cérebro
        self.conversa = []             # transcript: [{papel, texto}]
        self.plano = []                # passos aprovados pelo cérebro, esperando confirmação
        self.passo_i = 0               # qual passo do plano está na vez
        self._plano_local = False      # plano veio de atalho local? (não chama o cérebro no fim)
        self._aguardando_ok = False    # plano montado, esperando o dono confirmar (voz/botão)
        self._2conf = False            # 2a confirmação pendente (trilho destrutivo)
        self._tarefa = None            # thread lógica em andamento (cérebro/execução)
        self._threads = []             # referência forte a TODA thread viva (senão o Qt aborta)
        self._auto_seguidos = 0        # passos rodados sozinhos desde a última fala sua (trava anti-loop)

        # motor de voz (Whisper): sobe o cérebro já no arranque
        self._stt_pronto = False
        self._stt_buf = b""
        self._pendente = None
        self.rec = None
        self._rec_enviado = True       # nada gravado ainda para mandar
        self.stt = QtCore.QProcess(self)
        self.stt.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.SeparateChannels)
        self.stt.readyReadStandardOutput.connect(self._stt_saida)
        self.stt.start(STT_PY, [STT_DMN])

        # Sobe o cérebro adiantado, junto com o Whisper. MEDIDO: o 1º turno depois
        # de subir custa ~10 s (paga a partida do CLI uma vez) e os seguintes ~2,7 s.
        # Fazendo isso aqui, quem paga a partida é a abertura do app — não a sua
        # primeira frase. Vai numa thread porque não pode segurar a janela.
        threading.Thread(target=brain.aquecer, daemon=True).start()

        card = QtWidgets.QWidget(self); card.setObjectName("card")
        out = QtWidgets.QVBoxLayout(self); out.setContentsMargins(0,0,0,0); out.addWidget(card)
        v = QtWidgets.QVBoxLayout(card); v.setContentsMargins(18,14,18,16); v.setSpacing(10)

        # cabecalho
        top = QtWidgets.QHBoxLayout()
        self.selo = QtWidgets.QLabel(); self.selo.setPixmap(_selo(26)); self.selo.setFixedSize(26,26)
        titulo = QtWidgets.QLabel("Grimoire"); titulo.setObjectName("titulo")
        self.status = QtWidgets.QLabel("pronto"); self.status.setObjectName("status")
        # Dois interruptores que ACENDEM (dourado) quando ligados — sem adivinhação.
        self.b_voz = QtWidgets.QPushButton("🔊 Voz"); self.b_voz.setObjectName("toggle")
        self.b_voz.setCheckable(True); self.b_voz.setChecked(self.voz.ligada)
        self.b_voz.setToolTip("Ligado = o Grimoire fala as respostas em voz alta. Desligado = você só lê.")
        self.b_voz.toggled.connect(self.alternar_voz)
        self.b_conversa = QtWidgets.QPushButton("🎙️ Ei Grimoire"); self.b_conversa.setObjectName("toggle")
        self.b_conversa.setCheckable(True)
        self.b_conversa.setToolTip("Ligado = fica sempre ouvindo. Diga 'Grimoire' e ele te atende na "
                                   "hora, como a Siri. Depois de responder, segue ouvindo uns segundos "
                                   "para você emendar sem repetir o nome.")
        self.b_conversa.toggled.connect(self.alternar_conversa)
        fechar = QtWidgets.QPushButton("✕"); fechar.setObjectName("x"); fechar.setFixedSize(22,22)
        fechar.setToolTip("Fechar (o selo continua flutuando)")
        fechar.clicked.connect(self.hide)
        top.addWidget(self.selo); top.addSpacing(6); top.addWidget(titulo)
        top.addSpacing(10); top.addWidget(self.status); top.addStretch()
        top.addWidget(self.b_voz); top.addWidget(self.b_conversa); top.addWidget(fechar)
        v.addLayout(top)

        # botao gravar
        self.b_grav = QtWidgets.QPushButton("▶  Gravar"); self.b_grav.setObjectName("gravar")
        self.b_grav.setMinimumHeight(46); self.b_grav.clicked.connect(self.toggle_gravar)
        v.addWidget(self.b_grav)

        # a conversa (histórico) — escondida até o primeiro Executar
        self.chat = QtWidgets.QTextEdit(); self.chat.setObjectName("chat"); self.chat.setReadOnly(True)
        self.chat.setMinimumHeight(160); self.chat.hide()
        v.addWidget(self.chat, 1)

        # campo da fala atual (editável — dá para corrigir uma palavra antes de agir)
        self.entrada = QtWidgets.QTextEdit(); self.entrada.setObjectName("notas")
        self.entrada.setPlaceholderText("Aperte Gravar e fale. Depois: Copiar, Enviar, "
                                        "ou Executar (o Grimoire conversa e faz).")
        self.entrada.setMinimumSize(420, 96); self.entrada.setMaximumHeight(140)
        v.addWidget(self.entrada)

        # barra de confirmação (aparece só quando há um passo esperando OK)
        self.barra = QtWidgets.QWidget(); self.barra.setObjectName("barra")
        bl = QtWidgets.QVBoxLayout(self.barra); bl.setContentsMargins(12,10,12,10); bl.setSpacing(6)
        self.b_desc = QtWidgets.QLabel(); self.b_desc.setObjectName("bdesc"); self.b_desc.setWordWrap(True)
        self.b_chip = QtWidgets.QLabel(); self.b_chip.setObjectName("bchip")
        linha_chip = QtWidgets.QHBoxLayout(); linha_chip.addWidget(self.b_chip); linha_chip.addStretch()
        self.b_cmd = QtWidgets.QLineEdit(); self.b_cmd.setObjectName("bcmd")
        self.b_cmd.setToolTip("O comando exato — dá para corrigir antes de rodar")
        self.b_auth = QtWidgets.QCheckBox("Tenho autorização (é meu, laboratório, ou por escrito)")
        self.b_auth.setObjectName("bauth"); self.b_auth.hide()
        self.b_auth.stateChanged.connect(self._reavaliar_confirmar)
        botoes = QtWidgets.QHBoxLayout()
        self.b_cancelar = QtWidgets.QPushButton("Cancelar"); self.b_cancelar.setObjectName("ghost")
        self.b_cancelar.clicked.connect(self.cancelar_plano)
        self.b_confirmar = QtWidgets.QPushButton("Confirmar e rodar"); self.b_confirmar.setObjectName("acao")
        self.b_confirmar.clicked.connect(self.confirmar_passo)
        botoes.addWidget(self.b_cancelar); botoes.addStretch(); botoes.addWidget(self.b_confirmar)
        bl.addWidget(self.b_desc); bl.addLayout(linha_chip); bl.addWidget(self.b_cmd)
        bl.addWidget(self.b_auth); bl.addLayout(botoes)
        self.barra.hide()
        v.addWidget(self.barra)

        # rodape — as três ações
        rod = QtWidgets.QHBoxLayout(); rod.setSpacing(8)
        self.b_copiar = QtWidgets.QPushButton("Copiar"); self.b_copiar.setObjectName("acao2")
        self.b_copiar.clicked.connect(self.copiar)
        self.b_enviar = QtWidgets.QPushButton("Enviar"); self.b_enviar.setObjectName("acao2")
        self.b_enviar.setToolTip("Copia e cola na janela que você estava usando")
        self.b_enviar.clicked.connect(self.enviar)
        self.b_exec = QtWidgets.QPushButton("Executar"); self.b_exec.setObjectName("acao")
        self.b_exec.setToolTip("Conversa com o Grimoire e faz o que você pedir — sempre com confirmação")
        self.b_exec.clicked.connect(self.executar)
        self.b_limpar = QtWidgets.QPushButton("Limpar"); self.b_limpar.setObjectName("ghost")
        self.b_limpar.clicked.connect(self.limpar)
        rod.addWidget(self.b_copiar); rod.addWidget(self.b_enviar); rod.addWidget(self.b_exec)
        rod.addStretch(); rod.addWidget(self.b_limpar)
        v.addLayout(rod)

        self.setStyleSheet(f"""
            #card {{ background:{INK}; border:1px solid {INK_LINE}; border-radius:16px; }}
            #titulo {{ color:{PARCH}; font-family:{FONTE_TITULO}; font-size:18px; font-weight:600; }}
            #status {{ color:{PARCH_DIM}; font-family:{FONTE_UI}; font-size:12px; }}
            #toggle {{ color:{PARCH_DIM}; background:transparent; border:1px solid {INK_LINE};
                       border-radius:9px; font-family:{FONTE_UI}; font-size:11px; font-weight:600;
                       padding:3px 9px; }}
            #toggle:hover {{ color:{PARCH}; border-color:{PARCH_DIM}; }}
            #toggle:checked {{ color:{INK}; background:{GOLD}; border-color:{GOLD}; }}
            #x {{ color:{PARCH_DIM}; border:none; background:transparent; font-size:14px; }}
            #x:hover {{ color:{REC}; }}
            #gravar {{ color:{INK}; background:{GOLD}; border:none; border-radius:12px;
                       font-family:{FONTE_UI}; font-size:16px; font-weight:700; }}
            #gravar:hover {{ background:{GOLD_DEEP}; }}
            #chat {{ color:{PARCH}; background:{INK_CARD}; border:1px solid {INK_LINE};
                     border-radius:12px; font-family:{FONTE_UI}; font-size:14px; padding:10px; }}
            #notas {{ color:{PARCH}; background:{INK_CARD}; border:1px solid {INK_LINE};
                      border-radius:12px; font-family:{FONTE_UI}; font-size:15px; padding:10px; }}
            #barra {{ background:{INK_CARD}; border:1px solid {INK_LINE}; border-radius:12px; }}
            #bdesc {{ color:{PARCH}; font-family:{FONTE_UI}; font-size:13px; }}
            #bchip {{ font-family:{FONTE_UI}; font-size:11px; font-weight:700; padding:2px 8px;
                      border-radius:8px; }}
            #bcmd {{ color:{GOLD}; background:{INK}; border:1px solid {INK_LINE}; border-radius:8px;
                     font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; font-size:13px; padding:7px; }}
            #bauth {{ color:{PARCH}; font-family:{FONTE_UI}; font-size:12px; }}
            #acao {{ color:{INK}; background:{GOLD}; border:none; border-radius:10px;
                     font-family:{FONTE_UI}; font-size:14px; font-weight:700; padding:8px 16px; }}
            #acao:hover {{ background:{GOLD_DEEP}; }}
            #acao:disabled {{ background:{INK_LINE}; color:{PARCH_DIM}; }}
            #acao2 {{ color:{INK}; background:{ARCANE}; border:none; border-radius:10px;
                      font-family:{FONTE_UI}; font-size:14px; font-weight:600; padding:8px 16px; }}
            #acao2:hover {{ background:{ARCANE_LT}; }}
            #ghost {{ color:{PARCH_DIM}; background:transparent; border:1px solid {INK_LINE};
                      border-radius:10px; font-family:{FONTE_UI}; font-size:14px; padding:8px 16px; }}
            #ghost:hover {{ color:{PARCH}; border-color:{PARCH_DIM}; }}
        """)
        self.resize(480, 380)

        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.atualizar)
        self.timer.start(500)

        # A ESCUTA JÁ NASCE LIGADA. Antes o botão "🎙️ Ei Grimoire" nascia
        # desligado: a cada reinício do serviço o Grimoire ficava SURDO até
        # alguém clicar nele de novo. Sintoma que o dono relatou — "não acorda
        # quando eu falo o nome dele" — e a prova foi zero captura de fala em
        # 40 minutos de serviço no ar. Ele não ignorava; não estava ouvindo.
        # Vai por timer para rodar só depois que a janela terminou de montar
        # (alternar_conversa usa self.voz e a barra de status).
        QtCore.QTimer.singleShot(800, lambda: self.b_conversa.setChecked(True))

    # ---- posicionar no centro e focar ----
    def abrir(self):
        tela = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.move(tela.center().x()-self.width()//2, tela.center().y()-self.height()//2)
        self.show(); self.raise_(); self.activateWindow()
        self.entrada.setFocus()

    # ---- interruptores de voz e mãos-livres ----
    def alternar_voz(self, ligar):
        if ligar and not self.voz.disponivel():
            self.b_voz.setChecked(False)
            self._toast("voz indisponível — instale o Piper")
            return
        self.voz.ligada = ligar
        if ligar:
            self._toast("voz ligada 🔊")
        else:
            self.voz.calar()
            self._toast("voz desligada 📖")

    def alternar_conversa(self, ligar):
        if ligar:
            self.escuta = Escuta()
            self._registrar(self.escuta)   # mantém referência até a thread morrer
            self.escuta.fala.connect(self._fala_continua)
            self.escuta.start()
            self._fila_fala = []
            self._desperto = False
            self._toast("ouvindo 🎙️ — me chame por 'Grimoire'")
            if self.voz.ligada:
                self.voz.falar("Tô ligado. É só me chamar de Grimoire.")
        else:
            if self.escuta is not None:
                self.escuta.parar()        # mata o arecord; a thread sai sozinha
                self.escuta = None         # (a referência forte segue em _threads)
            self._fila_fala = []           # não responder frase velha ao religar
            self._desperto = False
            self._toast("parei de ouvir")

    def _fala_continua(self, wav):
        """Chegou uma frase da conversa contínua. Manda transcrever e, quando o
        texto chegar, ele é enviado sozinho ao cérebro."""
        # ENFILEIRA em vez de descartar. Antes, tudo que você falava enquanto o
        # Whisper trabalhava (2 a 4 segundos) era jogado fora em silêncio — era a
        # causa principal do "meu áudio vai pela metade".
        self._fila_fala.append(wav)
        if len(self._fila_fala) > self.MAX_FILA:
            self._fila_fala.pop(0)
        self._puxar_da_fila()

    def _puxar_da_fila(self):
        """Manda a próxima frase da fila para transcrever, se der para atender agora."""
        if not self._fila_fala:
            return
        if self._tarefa is not None or self._transcrevendo or not self._stt_pronto:
            n = len(self._fila_fala)
            self.status.setText("ouvi — %d na fila…" % n if n > 1 else "ouvi — já respondo…")
            self.status.setStyleSheet(f"color:{ARCANE};")
            return
        wav = self._fila_fala.pop(0)
        self._transcrevendo = True
        self._auto_submeter = True
        self.status.setText("ouvi — transcrevendo…"); self.status.setStyleSheet(f"color:{ARCANE};")
        self.stt.write((wav + "\n").encode())

    def _entrada_continua(self, texto):
        """Aplica a palavra de acordar. Dormindo, só reage se ouvir 'Grimoire'.
        Desperto (janela de alguns segundos), atende tudo — como a Siri."""
        tem_nome, resto = separar_chamada(texto)
        agora = time.time()
        desperto = self._desperto and agora < self._desperto_ate

        if not desperto and not tem_nome:
            self.status.setText("💤 me chame por 'Grimoire'")
            self.status.setStyleSheet(f"color:{PARCH_DIM};")
            return

        if tem_nome:
            texto = resto
        self._desperto = True
        self._desperto_ate = agora + self.JANELA_DESPERTO

        if not texto.strip():
            # você só chamou o nome: atende e fica ouvindo o pedido
            self._diz("grimoire", "Oi! Pode falar.")
            if self.voz.ligada:
                self.voz.falar("Oi! Pode falar.")
            return
        self.entrada.setPlainText(texto)
        self.executar()

    # ---- gravar / parar ----
    def toggle_gravar(self):
        if self._trava > 0:
            return
        self.voz.calar()  # se o Grimoire está falando, para para te ouvir (barge-in)
        self._trava = 4
        self.b_grav.setEnabled(False)
        if gravando():
            self.b_grav.setText("⏳  parando…")
            self._parar_gravacao()
        else:
            self.b_grav.setText("⏳  iniciando…")
            self._iniciar_gravacao()

    def _iniciar_gravacao(self):
        self.rec = QtCore.QProcess(self)
        self.rec.start("pw-record",
                       ["--rate", "16000", "--channels", "1", "--format", "s16", REC_WAV])
        _ESTADO["gravando"] = True

    def _parar_gravacao(self):
        """Para a gravação SEM congelar a tela.

        Antes havia um `waitForFinished(2000)` aqui: a janela ficava travada até
        2 segundos esperando o pw-record fechar o arquivo. Agora só pedimos para
        parar e seguimos quando ele avisar que acabou (sinal `finished`) — a
        espera é obrigatória, senão o .wav vai incompleto para o Whisper, mas
        ela não precisa ser feita segurando a interface.
        """
        _ESTADO["gravando"] = False
        self.status.setText("transcrevendo…")
        self.status.setStyleSheet(f"color:{ARCANE};")
        self._rec_enviado = False       # trava: o wav desta gravação só vai UMA vez
        if self.rec is None:
            self._gravacao_fechada()
            return
        self.rec.finished.connect(lambda *_: self._gravacao_fechada())
        self.rec.terminate()
        # rede de segurança: se o pw-record não morrer, seguimos assim mesmo em 2s
        QtCore.QTimer.singleShot(2000, self._gravacao_fechada)

    def _gravacao_fechada(self):
        """O arquivo da gravação manual está fechado: manda transcrever.

        Chamado por DOIS caminhos (o sinal `finished` e o timer de segurança), e
        o que chegar primeiro vence — daí a trava `_rec_enviado`.
        """
        if self._rec_enviado:
            return
        self._rec_enviado = True
        if self.rec is not None:
            try:
                self.rec.kill()
            except Exception:
                pass
            self.rec = None
        if self._stt_pronto:
            self.stt.write((REC_WAV + "\n").encode())
        else:
            self._pendente = REC_WAV
            self.status.setText("preparando o motor de voz… já transcrevo")

    def _stt_saida(self):
        self._stt_buf += bytes(self.stt.readAllStandardOutput())
        while b"\n" in self._stt_buf:
            linha, self._stt_buf = self._stt_buf.split(b"\n", 1)
            s = linha.decode("utf-8", "replace").strip()
            if s == "READY":
                self._stt_pronto = True
                if self._pendente:
                    self.stt.write((self._pendente + "\n").encode())
                    self._pendente = None
            elif s.startswith("RESULT "):
                try:
                    texto = json.loads(s[7:])
                except Exception:
                    texto = ""
                auto = self._auto_submeter
                self._auto_submeter = False
                self._transcrevendo = False
                if texto and auto:
                    # veio da escuta contínua: passa pela palavra de acordar
                    self._entrada_continua(texto)
                elif texto:
                    atual = self.entrada.toPlainText()
                    sep = "" if (not atual or atual.endswith((" ", "\n"))) else " "
                    self.entrada.setPlainText((atual + sep + texto).strip())
                    self.entrada.moveCursor(QtGui.QTextCursor.MoveOperation.End)
                    self.status.setText("pronto"); self.status.setStyleSheet(f"color:{PARCH_DIM};")
                else:
                    self.status.setText("não peguei nada — fale um pouco mais alto")
                    self.status.setStyleSheet(f"color:{REC};")

    def atualizar(self):
        # Conversa contínua: só fica SURDO quando ouvir atrapalharia de verdade —
        # ele falando (senão escuta a própria voz) ou você gravando à mão.
        # Enquanto ele pensa ou transcreve ele CONTINUA ouvindo, e o que chegar
        # espera na fila. Antes ele parava de ouvir nesses segundos, e a metade
        # da frase que você falava nesse intervalo era perdida.
        if self.escuta is not None:
            self.escuta.pausado = (self.voz.falando() or gravando())
        self._puxar_da_fila()
        if self._trava > 0:
            self._trava -= 1
            if self._trava > 0:
                return
            self.b_grav.setEnabled(True)
        bruto = gravando()
        if bruto == self._ultimo:
            self._confirma += 1
        else:
            self._ultimo = bruto; self._confirma = 1
        if self._confirma < 2:
            return
        if bruto:
            self.b_grav.setText("■  Parar")
            self.b_grav.setStyleSheet(f"background:{REC}; color:{PARCH};")
            self.status.setText("● gravando — fale à vontade")
            self.status.setStyleSheet(f"color:{REC};")
        else:
            self.b_grav.setText("▶  Gravar")
            self.b_grav.setStyleSheet("")
            self.status.setText("pronto")
            self.status.setStyleSheet(f"color:{PARCH_DIM};")

    # ---- copiar / enviar / limpar ----
    def _toast(self, txt):
        self.status.setText(txt); self.status.setStyleSheet(f"color:{GOLD};")

    def copiar(self):
        QtWidgets.QApplication.clipboard().setText(self.entrada.toPlainText())
        self._toast("copiado ✓")

    def enviar(self):
        QtWidgets.QApplication.clipboard().setText(self.entrada.toPlainText())
        self.hide()
        QtCore.QTimer.singleShot(280, self._colar)

    def _colar(self):
        _ydotoold()
        subprocess.Popen(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])

    def limpar(self):
        """Recomeça do zero: apaga o campo de baixo, a conversa de cima E a
        memória do cérebro (senão ele ainda lembraria do papo antigo)."""
        self.voz.calar()
        self.entrada.clear()
        self.chat.clear(); self.chat.hide()
        self.conversa = []
        self.plano = []; self.passo_i = 0
        self._auto_seguidos = 0
        self._aguardando_ok = False
        self._plano_local = False
        self.barra.hide()
        self._toast("limpo ✓")

    # ==== EXECUTAR — a conversa que faz ====
    def _diz(self, papel, texto, cor=None):
        """Escreve uma linha na conversa (e fala, se a voz estiver ligada)."""
        self.chat.show()
        nome = {"dono": "você", "grimoire": "Grimoire", "resultado": "resultado", "erro": "erro"}.get(papel, papel)
        cor = cor or {"dono": PARCH, "grimoire": ARCANE_LT, "resultado": PARCH_DIM, "erro": REC}.get(papel, PARCH)
        txt = (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.chat.append(f'<div style="margin:4px 0;"><b style="color:{cor}">{nome}:</b> '
                         f'<span style="color:{PARCH}">{txt}</span></div>')
        self.chat.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _ocupado(self, on: bool, msg="pensando…"):
        self.b_exec.setEnabled(not on)
        self.b_grav.setEnabled(not on)
        if on:
            self.status.setText(msg); self.status.setStyleSheet(f"color:{ARCANE};")

    def executar(self):
        """Manda o que você falou para a conversa e chama o cérebro."""
        texto = self.entrada.toPlainText().strip()
        if not texto or self._tarefa is not None:
            return
        # ESPERANDO O OK DE UM PLANO? A fala curta é 'ok' (roda), 'não' (cancela),
        # ou uma correção (frase maior → re-planeja com o cérebro).
        if self._aguardando_ok:
            resposta = atalhos.eh_confirmacao(texto)
            if resposta == "sim":
                self._diz("dono", texto); self.entrada.clear()
                self.conversa.append({"papel": "dono", "texto": "(ok, pode executar)"})
                self.confirmar_plano_ok()
                return
            if resposta == "nao":
                self._diz("dono", texto); self.entrada.clear()
                self.cancelar_plano()
                return
            # correção/novo pedido: larga o plano pendente e manda pro cérebro re-planejar
            self._aguardando_ok = False
            self.plano = []; self.barra.hide()
        self.conversa.append({"papel": "dono", "texto": texto})
        self._diz("dono", texto)
        self.entrada.clear()
        self._auto_seguidos = 0   # você falou: zera a trava anti-loop
        # ATALHO LOCAL: se a fala é trivial e conhecida (hora, data, abrir app),
        # responde na hora, sem os ~2,7 s do cérebro. Se não reconhece, cai no
        # cérebro como sempre. É só otimização — nunca decide errado no lugar dele.
        if self._atalhos_ligados:
            ficha = atalhos.tentar(texto)
            if ficha is not None:
                self._cerebro_respondeu(ficha)
                return
        self._pensar()

    def _registrar(self, t):
        """Guarda uma referência forte à thread até ela terminar de verdade —
        sem isto o Python coleta o objeto e o Qt aborta ('Destroyed while thread
        is still running')."""
        self._threads.append(t)
        t.finished.connect(lambda: self._threads.remove(t) if t in self._threads else None)

    def _pensar(self):
        self._ocupado(True, "pensando…")
        self._tarefa = Tarefa(brain.pensar, list(self.conversa))
        self._registrar(self._tarefa)
        self._tarefa.pronto.connect(self._cerebro_respondeu)
        self._tarefa.erro.connect(self._cerebro_falhou)
        self._tarefa.finished.connect(self._tarefa_fim)
        self._tarefa.start()

    def _tarefa_fim(self):
        # Só limpa o estado 'ocupado' se quem terminou é a tarefa ATUAL. Sem esta
        # checagem, um passo que já começou o próximo teria a referência zerada
        # aqui e seria destruído rodando (aborta o app).
        if self.sender() is not self._tarefa:
            return
        self._tarefa = None
        self._ocupado(False)
        self.status.setText("pronto"); self.status.setStyleSheet(f"color:{PARCH_DIM};")

    def _cerebro_falhou(self, msg):
        self._diz("erro", f"não consegui pensar agora: {msg}")

    def _cerebro_respondeu(self, ficha):
        fala = ficha.get("fala", "")
        self.conversa.append({"papel": "grimoire", "texto": fala})
        self._diz("grimoire", fala)
        if fala:
            self.voz.falar(fala)
        # segue desperto após responder: você emenda sem repetir "Grimoire"
        if self.escuta is not None:
            self._desperto_ate = time.time() + self.JANELA_DESPERTO
        modo = ficha.get("modo")
        if modo == "planejar" and ficha.get("passos"):
            self.plano = ficha["passos"]; self.passo_i = 0
            # plano de atalho local: roda os passos mas NÃO chama o cérebro no fim
            self._plano_local = ficha.get("local", False)
            # NÃO roda de cara: mostra o plano e espera o OK do dono (voz ou botão).
            self._confirmar_plano()

    def _confirmar_plano(self):
        """Mostra o plano inteiro e ESPERA o OK do dono (voz 'ok/pode/faz' ou
        botão). Nada roda antes disso — é o fluxo assertivo que o dono pediu."""
        if not self.plano:
            return
        self._aguardando_ok = True
        cmds = [p.get("comando", "") for p in self.plano if p.get("comando")]
        n = len(self.plano)
        self.b_desc.setText("Vou fazer isto — dá um OK (ou diga 'ok') que eu executo:"
                            if n == 1 else
                            f"Vou fazer estes {n} passos — dá um OK (ou diga 'ok'):")
        self.b_chip.setText("esperando seu OK")
        self.b_chip.setStyleSheet(f"background:{ARCANE}; color:{INK};")
        self.b_cmd.setText("  •  ".join(cmds))
        self.b_auth.hide(); self.b_auth.setChecked(False)
        self.b_confirmar.setText("Confirmar e rodar")
        self.b_confirmar.setEnabled(True)
        self.barra.show()
        # a 'fala' do cérebro já disse o que vai fazer e pediu o OK; não repete voz aqui.

    def confirmar_plano_ok(self):
        """OK do dono ao plano inteiro: agora sim executa os passos."""
        if not self._aguardando_ok:
            return
        self._aguardando_ok = False
        self.barra.hide()
        self.passo_i = 0
        self._auto_seguidos = 0
        self._processar_passo()

    # ---- passo a passo: roda depois do OK do plano; destrutivo pede OK extra ----
    def _processar_passo(self):
        if self.passo_i >= len(self.plano):
            # acabou o plano
            self.plano = []; self.barra.hide()
            if getattr(self, "_plano_local", False):
                # atalho local: já resolveu, não gasta o cérebro num comentário.
                self._plano_local = False
                return
            # plano do cérebro: manda os resultados de volta e vê se ele continua.
            self._pensar()
            return
        passo = self.plano[self.passo_i]
        d = seg.decidir_risco(passo.get("comando", ""), passo.get("risco", "reversivel"))
        self._risco_atual = d
        self._2conf = False
        if d["nivel"] == "destrutivo":
            # perigoso ou toca um alvo de rede: mostra o cartão e espera você.
            self._mostrar_cartao(passo, d)
        else:
            # trava anti-loop: muitos passos sozinhos sem você falar → para e avisa
            self._auto_seguidos += 1
            if self._auto_seguidos > 8:
                self.plano = []; self.barra.hide()
                self._diz("grimoire", "fiz vários passos seguidos — parei aqui pra você "
                          "conferir. Me diga se continuo.", cor=GOLD)
                return
            # seguro e reversível/muda-estado: FAZ, sem pedir licença.
            self._diz("grimoire", f"fazendo: {passo.get('comando','')}", cor=GOLD)
            self._rodar_comando(passo.get("comando", ""), passo.get("terminal", False))

    def _mostrar_cartao(self, passo, d):
        n = self.passo_i + 1; total = len(self.plano)
        self.b_desc.setText(f"Passo {n} de {total}: {passo.get('descricao','')}")
        chip = RISCO_TXT.get(d["nivel"], d["nivel"])
        if d["toca_alvo"]:
            chip += " · toca um alvo de rede"
        cor = RISCO_COR.get(d["nivel"], PARCH_DIM)
        self.b_chip.setText(chip)
        self.b_chip.setStyleSheet(f"background:{cor}; color:{INK};")
        self.b_cmd.setText(passo.get("comando", ""))
        if d["motivos"]:
            self.b_desc.setText(self.b_desc.text() + "\n(" + "; ".join(d["motivos"]) + ")")
        self.b_auth.setVisible(d["precisa_autorizacao"])
        self.b_auth.setChecked(False)
        self.b_confirmar.setText("Confirmar e rodar")
        self.barra.show()
        self._reavaliar_confirmar()
        if self.voz.ligada:
            aviso = ("Esse passo toca uma rede de fora. Confirma se você tem "
                     "autorização, aí eu sigo." if d["precisa_autorizacao"]
                     else "Esse passo é mais delicado. Dá uma olhada e confirma.")
            self.voz.falar(aviso)

    def _reavaliar_confirmar(self):
        d = getattr(self, "_risco_atual", None)
        if not d:
            return
        pode = True
        if d["precisa_autorizacao"] and not self.b_auth.isChecked():
            pode = False
        self.b_confirmar.setEnabled(pode)

    def confirmar_passo(self):
        # se estamos esperando o OK do plano inteiro, é isso que o botão faz
        if self._aguardando_ok:
            self.confirmar_plano_ok()
            return
        d = getattr(self, "_risco_atual", None)
        if not d:
            return
        # trilho destrutivo: exige um segundo clique
        if d["dupla_confirmacao"] and not self._2conf:
            self._2conf = True
            self.b_confirmar.setText("Tem certeza? Clique de novo para rodar")
            return
        comando = self.b_cmd.text().strip()  # pega o comando (talvez corrigido)
        # ferramenta longa/interativa ou que toca alvo → terminal visível
        terminal = d["toca_alvo"] or self.plano[self.passo_i].get("terminal", False)
        self.barra.hide()
        self._diz("grimoire", f"rodando: {comando}", cor=GOLD)
        self._rodar_comando(comando, terminal)

    def _rodar_comando(self, comando, terminal=False):
        self._ocupado(True, "rodando…")
        self._cmd_atual = comando
        self._tarefa = Tarefa(execu.rodar, comando, 60, terminal)
        self._registrar(self._tarefa)
        self._tarefa.pronto.connect(self._passo_rodou)
        self._tarefa.erro.connect(lambda m: self._diz("erro", m))
        self._tarefa.finished.connect(self._tarefa_fim)
        self._tarefa.start()

    def _passo_rodou(self, res):
        codigo = res.get("codigo", 1); saida = res.get("saida", "")
        ok = "✓" if codigo == 0 else f"✗ (código {codigo})"
        prova = f"[{ok}] {saida}" if saida else f"[{ok}]"
        cmd = getattr(self, "_cmd_atual", "")
        self.conversa.append({"papel": "resultado",
                              "texto": f"comando: {cmd}\nsaída: {prova}"})
        self._diz("resultado", prova, cor=(PARCH_DIM if codigo == 0 else REC))
        # não fala "passo concluído" (robótico): o cérebro comenta o resultado
        # de forma natural na próxima fala, quando o plano termina.
        self.passo_i += 1
        QtCore.QTimer.singleShot(200, self._processar_passo)

    def cancelar_plano(self):
        self.plano = []; self.barra.hide()
        self._aguardando_ok = False
        self._plano_local = False
        self._diz("grimoire", "cancelado — nada foi executado.", cor=PARCH_DIM)
        if self.voz.ligada:
            self.voz.falar("Beleza, cancelei.")
        self.conversa.append({"papel": "dono", "texto": "(cancelei o plano)"})

    # ---- arrastar pelo cabecalho ----
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton and e.position().y() < 46:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)
    def mouseReleaseEvent(self, e):
        self._drag = None

    def closeEvent(self, e):
        e.ignore(); self.hide()


class Launcher(QtWidgets.QWidget):
    """Selo pequeno sempre-no-topo, embaixo da tela. Clique abre o pop-up."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Grimoire")
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint
                            | QtCore.Qt.WindowType.WindowStaysOnTopHint
                            | QtCore.Qt.WindowType.Tool)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(58, 58)
        self.setToolTip("Grimoire — clique para gravar")
        self._press = None
        self._arrastou = False

        self.pop = PopUp()

        self._pos_canto()
        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.update)
        self.timer.start(500)

    def _pos_canto(self):
        tela = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.move(tela.center().x()-self.width()//2, tela.bottom()-self.height()-16)

    def paintEvent(self, _):
        p = QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(INK_CARD))
        p.drawEllipse(2, 2, self.width()-4, self.height()-4)
        p.setPen(QtGui.QPen(QtGui.QColor(INK_LINE), 1))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawEllipse(2, 2, self.width()-4, self.height()-4)
        selo = _selo(40, aceso=gravando())
        p.drawPixmap((self.width()-40)//2, (self.height()-40)//2, selo)

    def toggle_pop(self):
        if self.pop.isVisible():
            self.pop.hide()
        else:
            self.pop.abrir()

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._arrastou = False
    def mouseMoveEvent(self, e):
        if self._press is not None:
            novo = e.globalPosition().toPoint() - self._press
            if (e.globalPosition().toPoint() - (self.frameGeometry().topLeft()+self._press)).manhattanLength() > 6:
                self._arrastou = True
            self.move(novo)
    def mouseReleaseEvent(self, e):
        if self._press is not None and not self._arrastou:
            self.toggle_pop()
        self._press = None


def _montar_bandeja(app, launcher):
    """Ícone permanente na bandeja do sistema (a 'barra de tarefas'). Garante que
    o Grimoire está sempre ao alcance, mesmo que o selo flutuante saia da vista.
    Não tem 'Sair' — o Grimoire é para ficar sempre disponível."""
    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QtWidgets.QSystemTrayIcon(QtGui.QIcon(_selo(64)), app)
    tray.setToolTip("Grimoire — sempre aqui. Clique para abrir.")
    menu = QtWidgets.QMenu()
    menu.addAction("Abrir Grimoire", launcher.pop.abrir)
    menu.addAction("Recolher janela", launcher.pop.hide)
    tray.setContextMenu(menu)
    def _clique(motivo):
        if motivo == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            launcher.toggle_pop()
    tray.activated.connect(_clique)
    tray.show()
    return tray


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    l = Launcher(); l.show()
    bandeja = _montar_bandeja(app, l)  # ícone fixo na bandeja

    def _encerrar():
        try:
            if l.pop.rec is not None:
                l.pop.rec.kill()
            if l.pop.escuta is not None:
                l.pop.escuta.parar()
            l.pop.voz.desligar()
            # espera TODA thread viva terminar antes de fechar (senão o Qt aborta)
            for t in list(l.pop._threads):
                try:
                    t.wait(3000)
                except Exception:
                    pass
            l.pop.stt.kill()
        except Exception:
            pass
    app.aboutToQuit.connect(_encerrar)

    app.exec()
