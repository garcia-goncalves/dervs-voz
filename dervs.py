#!/usr/bin/env python3
"""DERVS — companheiro de voz do assistente.

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
import os, subprocess, signal, json, sys, threading, tempfile
WINDOWS = sys.platform == "win32"
if not WINDOWS:
    # Forca XWayland para 'sempre no topo' funcionar de forma confiavel no KDE
    # Wayland. No Windows nao existe xcb: forcar aqui deixaria o Qt sem tela.
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
from PyQt6 import QtCore, QtGui, QtWidgets

import time
import dervs_safety as seg
import dervs_brain as brain
import dervs_exec as execu
import dervs_browser as navegador
import dervs_enrich as enriquecimento
import dervs_atalhos as atalhos
import dervs_config as cfg
import dervs_instancia as instancia
from dervs_tts import Voz
from dervs_listen import (Endpointer, salvar_wav, separar_chamada,
                          FRAME_BYTES, FRAME_AMOSTRAS, TAXA)

HOME = os.path.expanduser("~")
AQUI = os.path.dirname(os.path.abspath(__file__))
TMP  = tempfile.gettempdir()      # /tmp no Linux, %TEMP% no Windows

# --- caminhos da voz (mesmos do script 'falar') ---
VOICE_DIR = f"{HOME}/voice"
PY_VOZ    = f"{VOICE_DIR}/.venv/bin/python"
ND        = f"{VOICE_DIR}/nerd-dictation/nerd-dictation"   # motor antigo (Vosk), aposentado
MODEL     = f"{VOICE_DIR}/model"


def _python_do_ouvido() -> str:
    """O Python que tem faster-whisper instalado — é ele que roda o daemon.

    Ordem: variável de ambiente (quem quiser mandar), depois o ambiente isolado
    do próprio repositório (é onde o instalador do Windows põe tudo), depois o
    ambiente do Linux, e por fim o Python que está rodando este arquivo.
    """
    for caminho in (os.environ.get("DERVS_PY"),
                    os.path.join(AQUI, "dervs-venv", "Scripts", "python.exe"),
                    f"{VOICE_DIR}/whisper-venv/bin/python"):
        if caminho and os.path.exists(caminho):
            return caminho
    return sys.executable


# --- motor de voz: porteiro local + transcrição precisa ---
STT_PY    = _python_do_ouvido()
STT_DMN   = os.path.join(AQUI, "dervs_stt_daemon.py")   # fica ao lado deste arquivo
REC_WAV   = os.path.join(TMP, "dervs_rec.wav")   # gravação manual, antes de transcrever
# Quantas vezes tentar levantar o motor de voz se ele cair, e quanto esperar
# pelo "pronto" antes de avisar o dono. A primeira partida carrega o Whisper
# do disco e pode demorar: 90 s é folgado de propósito, para não gritar à toa.
STT_TENTATIVAS = 2
STT_ESPERA_SEG = 90

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


def nivel_do_plano(plano) -> str:
    """O maior risco entre todos os passos de um plano, decidido ANTES de rodar.

    Serve para saber se a confirmação por voz basta. Passo de navegador ou de
    enriquecimento não tem comando de terminal e conta como reversível, que é
    como `_processar_passo` já os trata.
    """
    pior = "reversivel"
    for passo in plano or []:
        if passo.get("tipo") in ("navegador", "enriquecer"):
            continue
        d = seg.decidir_risco(passo.get("comando", ""), passo.get("risco", "reversivel"))
        pior = seg._nivel_max(pior, d["nivel"])
    return pior


def descartar_wav(caminho):
    """Apaga o .wav de uma frase assim que ele não é mais necessário.

    Isto NÃO é faxina de disco: é privacidade, e é parte inseparável do que o
    porteiro promete. Cada frase captada vira um arquivo ANTES de o porteiro
    decidir — inclusive as que ele descarta por não terem sido com o DERVS. Sem
    apagar, um dia de trabalho deixaria centenas de gravações da sala do dono
    paradas no disco, para sempre: a pasta temporária do Windows, ao contrário
    da do Linux, não se limpa sozinha no desligamento. O áudio não sairia da
    máquina — mas ficaria acumulado dentro dela, que é quase tão ruim.

    A gravação manual (REC_WAV) é poupada: reusa sempre o mesmo caminho e o
    dono pode querer reenviá-la.
    """
    if not caminho or caminho == REC_WAV:
        return
    try:
        os.remove(caminho)
    except OSError:
        pass    # já sumiu, ou está em uso: não vale derrubar nada por isso


def _colar_na_janela_em_foco():
    """Aperta Ctrl+V na janela onde o dono estava.

    Não dá para fazer isso de um jeito só: cada sistema tem a própria maneira de
    o programa 'apertar uma tecla' por você. No Linux é o `ydotool` (que escreve
    em /dev/uinput); no Windows é a função `keybd_event` do próprio sistema,
    chamada direto pelo `ctypes` — sem instalar nada.
    """
    if WINDOWS:
        import ctypes
        VK_CONTROL, VK_V, SOLTAR = 0x11, 0x56, 0x0002
        teclado = ctypes.windll.user32
        teclado.keybd_event(VK_CONTROL, 0, 0, 0)          # segura Ctrl
        teclado.keybd_event(VK_V, 0, 0, 0)                # aperta V
        teclado.keybd_event(VK_V, 0, SOLTAR, 0)           # solta V
        teclado.keybd_event(VK_CONTROL, 0, SOLTAR, 0)     # solta Ctrl
        return
    _ydotoold()
    # keycodes do kernel Linux: 29 = Ctrl, 47 = V
    subprocess.Popen(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])


# Estado de gravação compartilhado entre o pop-up e o selo flutuante (que o lê para acender).
_ESTADO = {"gravando": False}


def gravando() -> bool:
    return _ESTADO["gravando"]


def _icone_app() -> QtGui.QIcon:
    """O ícone do app, desenhado em cada tamanho que o Windows pede.

    Um QIcon com um pixmap só (era `_selo(64)`) fica borrado onde o sistema
    precisa de 16 ou 32 px — barra de tarefas, canto da janela, bandeja —,
    porque quem reduz é o Windows. Desenhar cada tamanho sai nítido em todos.
    """
    icone = QtGui.QIcon()
    for px in (16, 24, 32, 48, 64, 128, 256):
        icone.addPixmap(_selo(px))
    return icone


def _selo(px: int = 44, aceso: bool = False) -> QtGui.QPixmap:
    """O selo do DERVS: losango (grimorio fechado) + faceta dourada + um raio
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


class Microfone:
    """De onde vêm os quadros de 30 ms de som. Esconde a diferença entre os
    sistemas, para a thread de escuta não precisar saber em qual está.

    Windows não tem `arecord` (utilitário do ALSA, que é do Linux), então a
    fonte padrão passou a ser a biblioteca `sounddevice`, que fala direto com o
    driver de áudio do sistema e funciona nos dois. O `arecord` fica só como
    reserva para uma máquina Linux que não tenha `sounddevice` instalado — é
    como o projeto nasceu e não custa nada manter.
    """

    def __init__(self):
        self._stream = None      # caminho sounddevice
        self._proc = None        # caminho arecord (Linux, reserva)

    def abrir(self):
        try:
            import sounddevice as sd
        except Exception:
            sd = None

        if sd is not None:
            # dtype int16 e 1 canal a 16 kHz: exatamente o que o Endpointer e o
            # Whisper esperam, sem conversão no meio do caminho.
            self._stream = sd.RawInputStream(
                samplerate=TAXA, blocksize=FRAME_AMOSTRAS,
                dtype="int16", channels=1, latency="low")
            self._stream.start()
            return

        if WINDOWS:
            raise RuntimeError(
                "não achei a biblioteca sounddevice, que é como eu ouço o "
                "microfone no Windows. Instale com: "
                "dervs-venv\\Scripts\\python.exe -m pip install sounddevice")

        self._proc = subprocess.Popen(
            ["arecord", "-q", "-f", "S16_LE", "-r", str(TAXA), "-c", "1", "-t", "raw"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def ler(self) -> bytes:
        """Um quadro de 30 ms, ou b'' se a fonte caiu (troca de dispositivo,
        driver reiniciou, `parar()` foi chamado)."""
        if self._stream is not None:
            try:
                dados, _estourou = self._stream.read(FRAME_AMOSTRAS)
            except Exception:
                return b""
            quadro = bytes(dados)
            return quadro if len(quadro) == FRAME_BYTES else b""
        if self._proc is not None:
            quadro = self._proc.stdout.read(FRAME_BYTES)
            return quadro if quadro and len(quadro) == FRAME_BYTES else b""
        return b""

    def motivo_da_queda(self) -> str:
        if self._proc is not None:
            try:
                return (self._proc.stderr.read() or b"").decode("utf-8", "replace").strip()[:200]
            except Exception:
                pass
        return ""

    def fechar(self):
        """Fecha a fonte. Precisa destravar um `ler()` que esteja bloqueado
        neste instante, senão a thread de escuta fica presa para sempre."""
        if self._stream is not None:
            try:
                self._stream.abort()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None


class GravacaoManual(QtCore.QThread):
    """A gravação do botão Gravar/Parar, para quem prefere clicar a falar o nome.

    Antes isto era o `pw-record` do PipeWire, que só existe no Linux, parado por
    `terminate()` num processo externo. Agora é uma thread que usa a mesma fonte
    de microfone da escuta contínua: um caminho só, igual nos dois sistemas, e
    sem depender de o processo externo fechar o arquivo a tempo.
    """
    pronta = QtCore.pyqtSignal()

    def __init__(self, caminho):
        super().__init__()
        self.caminho = caminho
        self._rodando = False
        # `parar()` pode chegar ANTES de `run()` começar (a thread é agendada,
        # não iniciada na hora). Sem esta marca, o `self._rodando = True` do
        # começo do run() apagaria o pedido de parada e a gravação ficaria
        # correndo para sempre, sem nunca emitir `pronta`.
        self._cancelado = False
        self._mic = None

    def run(self):
        if self._cancelado:
            self.pronta.emit()
            return
        self._rodando = True
        self._mic = Microfone()
        pedacos = []
        try:
            self._mic.abrir()
            while self._rodando:
                quadro = self._mic.ler()
                if not quadro:
                    break
                pedacos.append(quadro)
        except Exception as e:
            sys.stderr.write("dervs: gravação manual falhou (%s)\n" % e)
            sys.stderr.flush()
        finally:
            self._mic.fechar()
        # Grava mesmo se vier vazio: quem espera o arquivo prefere um .wav de
        # silêncio a ficar esperando para sempre por um arquivo que não vem.
        try:
            salvar_wav(b"".join(pedacos), self.caminho)
        except Exception as e:
            sys.stderr.write("dervs: não consegui salvar a gravação (%s)\n" % e)
            sys.stderr.flush()
        self.pronta.emit()

    def parar(self):
        self._cancelado = True
        self._rodando = False
        if self._mic is not None:
            self._mic.fechar()


class Escuta(QtCore.QThread):
    """Escuta o microfone o tempo todo e, quando você termina uma frase, avisa
    (emite o caminho de um .wav pronto para transcrever). É o que permite
    conversar sem clicar em Gravar/Parar. Enquanto o DERVS fala ou trabalha,
    fica 'pausado' — para não escutar a própria voz nem atropelar."""
    fala = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._rodando = False
        self.pausado = False
        self._mic = None

    def run(self):
        self._rodando = True
        ep = Endpointer()
        estava_pausado = False
        while self._rodando:
            self._mic = Microfone()
            try:
                self._mic.abrir()
            except Exception as e:
                sys.stderr.write("dervs: não consegui abrir o microfone (%s)\n" % e)
                sys.stderr.flush()
                return
            motivo = ""
            try:
                while self._rodando:
                    frame = self._mic.ler()
                    if not frame:
                        motivo = self._mic.motivo_da_queda()
                        break               # a fonte caiu: sai para religar
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
                        caminho = os.path.join(
                            TMP, "dervs_fala_%d.wav" % int(time.time() * 1000))
                        salvar_wav(pcm, caminho)
                        self.fala.emit(caminho)
            finally:
                self._mic.fechar()
            if self._rodando:
                # o microfone caiu sozinho (troca de dispositivo, driver de áudio
                # reiniciou): religa em vez de ficar surdo para sempre.
                sys.stderr.write("dervs: microfone caiu, religando em 1s %s\n" % motivo)
                sys.stderr.flush()
                time.sleep(1.0)

    def parar(self):
        """Para a escuta de verdade: fecha a fonte para o `ler()` destravar na
        hora (senão a thread ficaria presa esperando som do microfone)."""
        self._rodando = False
        if self._mic is not None:
            self._mic.fechar()


class PopUp(QtWidgets.QWidget):
    """Janela central: gravar, conversa, e as três ações (copiar/enviar/executar)."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DERVS")
        self.setWindowFlags(QtCore.Qt.WindowType.Window
                            | QtCore.Qt.WindowType.FramelessWindowHint
                            | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowIcon(_icone_app())
        self._drag = None
        self._trava = 0
        self._ultimo = None
        self._confirma = 0

        # --- estado do Executar (a conversa) ---
        # config do dono (~/.config/dervs/config.json): voz, tempo até dormir
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
        self._desperto = False         # já acordou pela palavra "DERVS"?
        self._desperto_ate = 0.0       # até quando fica desperto sem repetir o nome
        # Teto ABSOLUTO da janela de desperto, em segundos. A janela normal se
        # renova a cada resposta, o que é bom para conversar — mas sem um teto
        # ela nunca fecharia numa conversa longa, e enquanto ele está desperto
        # TUDO que é falado na sala vai direto para a nuvem, sem passar pelo
        # porteiro. Isso desmentiria a promessa do porteiro justamente na hora
        # em que a sala está mais falante.
        self.TETO_DESPERTO = 90.0
        self._wav_no_porteiro = None   # frase esperando o veredito do porteiro local
        self.JANELA_DESPERTO = self._conf["janela_desperto_seg"]  # segs ouvindo após te atender
        self._atalhos_ligados = self._conf["atalhos_ligados"]     # responder trivial sem o cérebro
        self.conversa = []             # transcript: [{papel, texto}]
        self.plano = []                # passos aprovados pelo cérebro, esperando confirmação
        self.passo_i = 0               # qual passo do plano está na vez
        self._plano_local = False      # plano veio de atalho local? (não chama o cérebro no fim)
        self._aguardando_ok = False    # plano montado, esperando o dono confirmar (voz/botão)
        self._plano_nivel_max = "reversivel"   # pior risco do plano pendente
        self._desperto_desde = 0.0     # quando ele acordou (teto absoluto da janela)
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
        self._stt_erro_texto = ""       # última reclamação do motor, para o aviso
        self._stt_recado = None         # o que a tela diz sobre o ouvido, e a cor
        self._stt_tentativas = 0
        self._stt_religando = False     # já há uma religada marcada
        self._stt_encerrando = False    # True quando o app está fechando de propósito
        self.stt = QtCore.QProcess(self)
        self.stt.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.SeparateChannels)
        self.stt.readyReadStandardOutput.connect(self._stt_saida)
        # O ouvido roda num processo separado. Até 02/09/2026 só a saída de
        # SUCESSO dele era escutada: se ele morresse na partida, `_stt_pronto`
        # ficava False para sempre e o botão Gravar deixava de fazer QUALQUER
        # coisa, sem uma linha na tela. O DERVS ficava surdo e calado — parte
        # do 'sumiu / bugou' que o dono relatou.
        self.stt.readyReadStandardError.connect(self._stt_reclamou)
        self.stt.finished.connect(self._stt_caiu)
        self.stt.errorOccurred.connect(self._stt_caiu)
        self.stt.start(STT_PY, [STT_DMN])
        # E se ele nem morrer nem ficar pronto? Também deixava o dono no escuro.
        QtCore.QTimer.singleShot(STT_ESPERA_SEG * 1000, self._conferir_ouvido)

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
        titulo = QtWidgets.QLabel("DERVS"); titulo.setObjectName("titulo")
        self.status = QtWidgets.QLabel("pronto"); self.status.setObjectName("status")
        # Dois interruptores que ACENDEM (dourado) quando ligados — sem adivinhação.
        self.b_voz = QtWidgets.QPushButton("🔊 Voz"); self.b_voz.setObjectName("toggle")
        self.b_voz.setCheckable(True); self.b_voz.setChecked(self.voz.ligada)
        self.b_voz.setToolTip("Ligado = o DERVS fala as respostas em voz alta. Desligado = você só lê.")
        self.b_voz.toggled.connect(self.alternar_voz)
        self.b_conversa = QtWidgets.QPushButton("🎙️ Ei DERVS"); self.b_conversa.setObjectName("toggle")
        self.b_conversa.setCheckable(True)
        self.b_conversa.setToolTip("Ligado = fica sempre ouvindo. Diga 'DERVS' e ele te atende na "
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
                                        "ou Executar (o DERVS conversa e faz).")
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
        self.b_exec.setToolTip("Conversa com o DERVS e faz o que você pedir — sempre com confirmação")
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

        # A ESCUTA JÁ NASCE LIGADA. Antes o botão "🎙️ Ei DERVS" nascia
        # desligado: a cada reinício do serviço o DERVS ficava SURDO até
        # alguém clicar nele de novo. Sintoma que o dono relatou — "não acorda
        # quando eu falo o nome dele" — e a prova foi zero captura de fala em
        # 40 minutos de serviço no ar. Ele não ignorava; não estava ouvindo.
        # Vai por timer para rodar só depois que a janela terminou de montar
        # (alternar_conversa usa self.voz e a barra de status).
        # ...mas respeitando a ULTIMA escolha dele: se desligou a escuta e
        # fechou o app, abre desligado. Sem isso o botao nao e um liga/desliga,
        # e um lembrete que se apaga sozinho toda vez que o app reabre.
        if cfg.carregar()["escuta_ao_abrir"]:
            QtCore.QTimer.singleShot(800, lambda: self.b_conversa.setChecked(True))
        else:
            QtCore.QTimer.singleShot(800, self._mostrar_escuta_desligada)

    def _mostrar_escuta_desligada(self):
        """Deixa claro, ao abrir, que o silencio e escolha dele e nao defeito.

        Sem esta linha o dono abre o app, fala o nome, nada acontece, e a
        conclusao natural e "quebrou de novo" -- exatamente o susto de 01/09.
        """
        self.b_conversa.setText("🎙️  Microfone desligado")
        self.status.setText("escuta desligada — clique no botao para ligar")

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
        """O liga/desliga da escuta. LIGADO = o microfone está aberto o tempo
        todo; DESLIGADO = nada é ouvido, nem localmente. A escolha fica gravada
        e vale para a próxima vez que o app abrir.

        O estado precisa ser óbvio num relance, sem abrir menu: quem deixa um
        microfone ligado o dia inteiro tem de conseguir olhar para a tela e
        saber, na hora, se ele está aberto. Daí o botão dizer com todas as
        letras em qual dos dois estados está, em vez de só ficar 'apertado'.
        """
        # grava ANTES de mexer no microfone: se a captura falhar, o que ele
        # escolheu continua valendo na próxima abertura.
        cfg.gravar("escuta_ao_abrir", bool(ligar))
        if ligar:
            self.escuta = Escuta()
            self._registrar(self.escuta)   # mantém referência até a thread morrer
            self.escuta.fala.connect(self._fala_continua)
            self.escuta.start()
            for velho in self._fila_fala:
                self._descartar_wav(velho)
            self._fila_fala = []
            self._desperto = False
            self._wav_no_porteiro = None
            self.b_conversa.setText("🔴  Ouvindo")
            self.b_conversa.setToolTip(
                "LIGADO: o microfone está aberto. Só respondo quando ouvir "
                "'DERVS' ou 'OK DERVS' — o resto é decidido aqui na sua "
                "máquina e não sai dela. Clique para desligar o microfone.")
            self._toast("ouvindo 🎙️ — me chame por 'DERVS'")
            if self.voz.ligada:
                self.voz.falar("Tô ligado. É só me chamar de DERVS.")
        else:
            if self.escuta is not None:
                self.escuta.parar()        # fecha o microfone; a thread sai sozinha
                self.escuta = None         # (a referência forte segue em _threads)
            # não responder frase velha ao religar — e não deixar a gravação
            # dessas frases largada no disco
            for velho in self._fila_fala:
                self._descartar_wav(velho)
            self._fila_fala = []
            self._desperto = False
            self._wav_no_porteiro = None
            self.b_conversa.setText("🎙️  Microfone desligado")
            self.b_conversa.setToolTip(
                "DESLIGADO: o microfone está fechado, não estou ouvindo nada. "
                "Clique para eu começar a ouvir.")
            self._toast("parei de ouvir")

    def _descartar_wav(self, caminho):
        descartar_wav(caminho)

    def _esta_desperto(self) -> bool:
        """Ele ainda está atendendo sem precisar do nome de novo?

        Duas condições, e as duas têm de valer: a janela curta (que se renova a
        cada resposta, para conversar) e o teto absoluto (que NÃO se renova).
        Sem o teto, uma conversa longa manteria o portão aberto para sempre, e
        tudo que fosse falado na sala iria para a nuvem.
        """
        agora = time.time()
        return (self._desperto
                and agora < self._desperto_ate
                and agora < self._desperto_desde + self.TETO_DESPERTO)

    def _acordar(self, novo=False):
        """Abre ou renova a janela de desperto.

        `novo=True` só quando ele OUVIU O NOME — aí o teto absoluto recomeça do
        zero, porque houve uma chamada nova. `novo=False` é continuação de
        conversa: renova a janela curta, mas **não** mexe no teto. Sem essa
        separação o teto seria decorativo: bastaria o DERVS responder para o
        relógio zerar, e o portão ficaria aberto para sempre numa conversa
        longa — com tudo que fosse falado na sala indo para a nuvem.
        """
        agora = time.time()
        if novo or not self._desperto:
            self._desperto_desde = agora
        elif agora >= self._desperto_desde + self.TETO_DESPERTO:
            return       # teto estourado: só volta a atender se o nome for dito
        self._desperto = True
        self._desperto_ate = agora + self.JANELA_DESPERTO

    def _fala_continua(self, wav):
        """Chegou uma frase da conversa contínua. Manda transcrever e, quando o
        texto chegar, ele é enviado sozinho ao cérebro."""
        # ENFILEIRA em vez de descartar. Antes, tudo que você falava enquanto o
        # Whisper trabalhava (2 a 4 segundos) era jogado fora em silêncio — era a
        # causa principal do "meu áudio vai pela metade".
        self._fila_fala.append(wav)
        if len(self._fila_fala) > self.MAX_FILA:
            self._descartar_wav(self._fila_fala.pop(0))   # conversa velha demais
        self._puxar_da_fila()

    def _puxar_da_fila(self):
        """Manda a próxima frase da fila para o motor de voz, se der para atender.

        AQUI mora a decisão que faz o DERVS poder ficar ligado o dia inteiro:
        se ele ainda está dormindo, a frase vai primeiro para o PORTEIRO, que
        decide na própria máquina se o nome foi dito. Só o que o porteiro deixa
        passar vai para a nuvem. Se ele já está desperto (você acabou de falar
        com ele), a frase vai direto para a transcrição precisa — não faz
        sentido pedir o nome de novo no meio de uma conversa.
        """
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

        # guardado até a resposta chegar: para reenviar se o portão abrir, e
        # para o arquivo ser apagado quando não for mais necessário
        self._wav_no_porteiro = wav
        if self._esta_desperto():
            self.status.setText("ouvi — transcrevendo…")
            self.status.setStyleSheet(f"color:{ARCANE};")
            self.stt.write(("TRANSCREVER " + wav + "\n").encode())
        else:
            self.status.setText("ouvindo…")
            self.status.setStyleSheet(f"color:{PARCH_DIM};")
            self.stt.write(("PORTEIRO " + wav + "\n").encode())

    def _entrada_continua(self, texto):
        """Aplica a palavra de acordar. Dormindo, só reage se ouvir 'DERVS'.
        Desperto (janela de alguns segundos), atende tudo — como a Siri."""
        tem_nome, resto = separar_chamada(texto)
        agora = time.time()
        desperto = self._esta_desperto()

        if not desperto and not tem_nome:
            self.status.setText("💤 me chame por 'DERVS'")
            self.status.setStyleSheet(f"color:{PARCH_DIM};")
            return

        if tem_nome:
            texto = resto
        self._acordar(novo=tem_nome)

        if not texto.strip():
            # você só chamou o nome: atende e fica ouvindo o pedido
            self._diz("dervs", "Oi! Pode falar.")
            if self.voz.ligada:
                self.voz.falar("Oi! Pode falar.")
            return
        self.entrada.setPlainText(texto)
        self.executar()

    # ---- gravar / parar ----
    def toggle_gravar(self):
        if self._trava > 0:
            return
        self.voz.calar()  # se o DERVS está falando, para para te ouvir (barge-in)
        self._trava = 4
        self.b_grav.setEnabled(False)
        if gravando():
            self.b_grav.setText("⏳  parando…")
            self._parar_gravacao()
        else:
            self.b_grav.setText("⏳  iniciando…")
            self._iniciar_gravacao()

    def _iniciar_gravacao(self):
        self.rec = GravacaoManual(REC_WAV)
        self._registrar(self.rec)      # referência forte até a thread morrer
        self.rec.pronta.connect(lambda: self._gravacao_fechada())
        self.rec.start()
        _ESTADO["gravando"] = True

    def _parar_gravacao(self):
        """Para a gravação SEM congelar a tela.

        Antes havia um `waitForFinished(2000)` aqui: a janela ficava travada até
        2 segundos esperando o gravador fechar o arquivo. Agora só pedimos para
        parar e seguimos quando ele avisar que acabou (sinal `pronta`) — a
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
        self.rec.parar()
        # rede de segurança: se a thread não terminar, seguimos assim mesmo em 2s
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
                self.rec.parar()
            except Exception:
                pass
            self.rec = None
        if self._stt_pronto:
            self.stt.write((REC_WAV + "\n").encode())
        else:
            self._pendente = REC_WAV
            self.status.setText("preparando o motor de voz… já transcrevo")

    def _recado_do_ouvido(self, texto, cor):
        """Fixa um recado sobre o ouvido — e ele SOBREVIVE ao relógio da tela.

        Sem isto o aviso durava meio segundo: `atualizar()` reescrevia 'pronto'
        duas vezes por segundo, por cima de tudo."""
        self._stt_recado = (texto, cor)
        self.status.setText(texto)
        self.status.setStyleSheet(f"color:{cor};")

    def _status_parado(self):
        """O que a tela mostra quando NÃO está gravando.

        Isto era um 'pronto' fixo, escrito duas vezes por segundo — inclusive
        com o ouvido morto. O DERVS afirmava estar pronto estando SURDO, e o
        dono só descobria apertando Gravar e nada acontecendo. Achado na
        investigação do 'o DERVS sumiu', 02/09/2026."""
        if self._stt_recado is not None:
            texto, cor = self._stt_recado
        elif not self._stt_pronto:
            texto, cor = "preparando o ouvido…", PARCH_DIM
        else:
            texto, cor = "pronto", PARCH_DIM
        if self.status.text() != texto:
            self.status.setText(texto)
            self.status.setStyleSheet(f"color:{cor};")

    def _stt_reclamou(self):
        """Guarda o que o motor de voz reclamou. Antes ninguém lia esse canal:
        o motivo real da surdez ia para o nada."""
        texto = bytes(self.stt.readAllStandardError()).decode("utf-8", "replace").strip()
        if texto:
            self._stt_erro_texto = texto.splitlines()[-1][:200]

    def _stt_caiu(self, *_):
        """O motor de voz morreu ou nem conseguiu subir. Avisa na tela e tenta
        levantar de novo — em vez de deixar o DERVS surdo em silêncio."""
        if self._stt_encerrando or self._stt_religando:
            # Uma queda faz o Qt avisar DUAS vezes (errorOccurred e finished).
            # Sem esta guarda, uma única morte gastava as duas tentativas de
            # uma vez e o dono via 'levantando (2 de 2)' já na primeira queda.
            return
        self._stt_pronto = False
        self._transcrevendo = False
        # A gravação que estava esperando o motor (`_pendente`) NÃO é jogada
        # fora: se a religada der certo, ela é enviada no READY. Descartá-la em
        # silêncio perderia o que o dono acabou de falar.
        if self._stt_tentativas < STT_TENTATIVAS:
            self._stt_tentativas += 1
            self._stt_religando = True
            self._recado_do_ouvido("o ouvido caiu — levantando de novo (%d de %d)…"
                                   % (self._stt_tentativas, STT_TENTATIVAS), GOLD)
            QtCore.QTimer.singleShot(1500, self._levantar_ouvido)
            return
        self._recado_do_ouvido(
            "não estou conseguindo ouvir — o motor de voz não sobe", REC)
        self.status.setToolTip(self._stt_erro_texto or
                               "o motor encerrou sem dizer o motivo")

    def _levantar_ouvido(self):
        self._stt_religando = False
        if self._stt_encerrando:
            return
        self.stt.start(STT_PY, [STT_DMN])
        # Rearma o vigia: sem isto, um motor que religa e fica PENDURADO (nem
        # morre nem fica pronto) deixava a tela congelada em 'levantando de
        # novo' para sempre, e Gravar voltava a não fazer nada sem novo aviso.
        QtCore.QTimer.singleShot(STT_ESPERA_SEG * 1000, self._conferir_ouvido)

    def _conferir_ouvido(self):
        """Passou o tempo de folga e o motor não disse 'pronto' nem morreu:
        está pendurado. O dono precisa saber, em vez de apertar Gravar e nada
        acontecer para sempre."""
        if self._stt_pronto or self._stt_encerrando:
            return
        if self.stt.state() == QtCore.QProcess.ProcessState.NotRunning:
            return                      # já morreu: _stt_caiu cuidou do aviso
        self._recado_do_ouvido("o ouvido está demorando demais para ficar pronto", REC)

    def _stt_saida(self):
        self._stt_buf += bytes(self.stt.readAllStandardOutput())
        while b"\n" in self._stt_buf:
            linha, self._stt_buf = self._stt_buf.split(b"\n", 1)
            s = linha.decode("utf-8", "replace").strip()
            if s == "READY":
                self._stt_pronto = True
                self._stt_recado = None      # o ouvido voltou: o aviso sai
                self._stt_tentativas = 0
                self._stt_religando = False
                self.status.setToolTip("")
                if self._pendente:
                    self.stt.write((self._pendente + "\n").encode())
                    self._pendente = None
            elif s.startswith("PORTEIRO "):
                # O porteiro decidiu, sem o áudio sair da máquina. Se não era
                # com ele, a frase morre aqui: nada vai para a nuvem, nada é
                # cobrado, e o que foi dito na sala não sai do computador.
                try:
                    veredito = json.loads(s[9:])
                except Exception:
                    veredito = {}
                wav = self._wav_no_porteiro
                if veredito.get("acordou") and wav:
                    # o portão abriu: SÓ AGORA o áudio vai para a nuvem. O
                    # arquivo continua guardado até a transcrição voltar.
                    self._acordar(novo=True)
                    self.status.setText("ouvi meu nome — transcrevendo…")
                    self.status.setStyleSheet(f"color:{ARCANE};")
                    self.stt.write(("TRANSCREVER " + wav + "\n").encode())
                else:
                    # não era com ele: a frase morre aqui e a gravação some do
                    # disco. Nada foi para a nuvem, e nada fica guardado.
                    self._wav_no_porteiro = None
                    self._descartar_wav(wav)
                    self._transcrevendo = False
                    self._auto_submeter = False
                    self.status.setText("💤 me chame por 'DERVS'")
                    self.status.setStyleSheet(f"color:{PARCH_DIM};")
                    self._puxar_da_fila()
            elif s.startswith("RESULT "):
                try:
                    texto = json.loads(s[7:])
                except Exception:
                    texto = ""
                # a transcrição chegou: a gravação já cumpriu o papel e some
                self._descartar_wav(self._wav_no_porteiro)
                self._wav_no_porteiro = None
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
            self._status_parado()

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
        try:
            _colar_na_janela_em_foco()
        except Exception as e:
            # o texto já está na área de transferência: o dono cola com Ctrl+V
            sys.stderr.write("dervs: não consegui colar sozinho (%s)\n" % e)
            sys.stderr.flush()
            self._toast("copiado — cole com Ctrl+V")

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
        nome = {"dono": "você", "dervs": "DERVS", "resultado": "resultado", "erro": "erro"}.get(papel, papel)
        cor = cor or {"dono": PARCH, "dervs": ARCANE_LT, "resultado": PARCH_DIM, "erro": REC}.get(papel, PARCH)
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
                # por_voz=True: este caminho vem de som captado pelo microfone,
                # que não prova que foi o dono quem falou
                self.confirmar_plano_ok(por_voz=True)
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
        self.conversa.append({"papel": "dervs", "texto": fala})
        self._diz("dervs", fala)
        if fala:
            self.voz.falar(fala)
        # segue desperto após responder: você emenda sem repetir "DERVS".
        # `_acordar` respeita o teto absoluto — passado ele, a janela não
        # renova mais e é preciso chamar pelo nome de novo.
        if self.escuta is not None:
            self._acordar()
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
        self._plano_nivel_max = self._nivel_do_plano()
        def _rotulo_passo(p):
            if p.get("tipo") == "navegador":
                return "🌐 navegador: " + p.get("objetivo", "")
            if p.get("tipo") == "enriquecer":
                return "🔎 enriquecer (público): " + p.get("dominio", "")
            return p.get("comando", "")
        cmds = [_rotulo_passo(p) for p in self.plano
                if p.get("tipo") in ("navegador", "enriquecer") or p.get("comando")]
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

    def _nivel_do_plano(self) -> str:
        return nivel_do_plano(self.plano)

    def confirmar_plano_ok(self, por_voz=False):
        """OK do dono ao plano inteiro: agora sim executa os passos.

        VOZ NÃO É SENHA. Qualquer som audível pelo microfone — a TV, um vídeo,
        uma visita, uma ligação no viva-voz — pode dizer "OK DERVS, faça X" e,
        segundos depois, dizer "ok". A palavra de acordar está publicada neste
        repositório e o casador dela é tolerante de propósito. Nada disso exige
        presença humana.

        Por isso a voz só confirma o que é reversível. Para qualquer coisa
        acima disso, é preciso um clique — que exige uma mão no computador.
        """
        if not self._aguardando_ok:
            return
        if por_voz and self._plano_nivel_max != "reversivel":
            aviso = ("Esse plano mexe em coisa que não dá para desfazer sozinha. "
                     "Confirma no botão, por favor — por voz eu não faço.")
            self._diz("dervs", aviso, cor=GOLD)
            if self.voz.ligada:
                self.voz.falar(aviso)
            self.status.setText("preciso de um clique para este plano")
            self.status.setStyleSheet(f"color:{REC};")
            return       # a barra continua à vista, esperando o clique
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
        # passo de navegador autônomo: age no Chrome logado do dono (o plano
        # inteiro já foi aprovado por ele). Despacha pro laço e conta como um
        # passo automático — não vira comando de terminal.
        if passo.get("tipo") == "navegador":
            self._auto_seguidos += 1
            objetivo = passo.get("objetivo", "") or passo.get("descricao", "")
            self._diz("dervs", f"abrindo o navegador e cuidando disso: {objetivo}", cor=GOLD)
            if self.voz.ligada:
                self.voz.falar("Beleza, tô no navegador cuidando disso. Deixa seu "
                               "Chrome fechado que eu abro ele.")
            self._rodar_navegador(objetivo)
            return
        # passo de enriquecimento passivo de lead: só fonte pública, não toca o
        # alvo — roda direto, como o navegador.
        if passo.get("tipo") == "enriquecer":
            self._auto_seguidos += 1
            dominio = passo.get("dominio", "") or passo.get("descricao", "")
            self._diz("dervs", f"levantando o que dá de público sobre {dominio}", cor=GOLD)
            if self.voz.ligada:
                self.voz.falar(f"Beleza, tô levantando o que dá de público sobre {dominio}.")
            self._rodar_enriquecimento(dominio)
            return
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
                self._diz("dervs", "fiz vários passos seguidos — parei aqui pra você "
                          "conferir. Me diga se continuo.", cor=GOLD)
                return
            # seguro e reversível/muda-estado: FAZ, sem pedir licença.
            self._diz("dervs", f"fazendo: {passo.get('comando','')}", cor=GOLD)
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
        # A caixa de autorização passou a aparecer por DOIS motivos diferentes:
        # tocar uma rede de fora, ou ler um arquivo de segredo (chave, senha,
        # credencial). O texto tem de dizer qual dos dois é — perguntar "tem
        # autorização?" falando de rede, quando na verdade ele vai ler a sua
        # chave privada, é pedir um sim sobre a coisa errada.
        le_segredo = d.get("le_segredo", False)
        self.b_auth.setVisible(d["precisa_autorizacao"])
        self.b_auth.setText(
            "Confirmo: pode ler esse arquivo de segredo" if le_segredo
            else "Tenho autorização (é meu, laboratório, ou por escrito)")
        self.b_auth.setChecked(False)
        self.b_confirmar.setText("Confirmar e rodar")
        self.barra.show()
        self._reavaliar_confirmar()
        if self.voz.ligada:
            if le_segredo:
                aviso = ("Atenção: esse passo lê um arquivo de segredo, e o que "
                         "sair dele pode ir junto na conversa. Confirma na tela "
                         "se você quer mesmo.")
            elif d["precisa_autorizacao"]:
                aviso = ("Esse passo toca uma rede de fora. Confirma se você tem "
                         "autorização, aí eu sigo.")
            else:
                aviso = "Esse passo é mais delicado. Dá uma olhada e confirma."
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
        self._diz("dervs", f"rodando: {comando}", cor=GOLD)
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

    def _rodar_navegador(self, objetivo):
        """Despacha a tarefa de navegador autônomo numa thread. O laço do
        dervs_browser gerencia o próprio tempo (tem teto de passos), então
        NÃO passa pelo timeout curto do executor de comando."""
        self._ocupado(True, "no navegador…")
        self._cmd_atual = f"navegador: {objetivo}"
        self._tarefa = Tarefa(navegador.rodar_para_app, objetivo)
        self._registrar(self._tarefa)
        self._tarefa.pronto.connect(self._passo_rodou)
        self._tarefa.erro.connect(lambda m: self._diz("erro", m))
        self._tarefa.finished.connect(self._tarefa_fim)
        self._tarefa.start()

    def _rodar_enriquecimento(self, dominio):
        """Despacha o enriquecimento passivo de lead numa thread. O bbot pode
        levar minutos; o próprio módulo tem timeout, então não usa o executor
        de comando (timeout curto)."""
        self._ocupado(True, "levantando o lead…")
        self._cmd_atual = f"enriquecer: {dominio}"
        self._tarefa = Tarefa(enriquecimento.rodar_para_app, dominio, False)
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
        self._diz("dervs", "cancelado — nada foi executado.", cor=PARCH_DIM)
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


class Ponte(QtCore.QObject):
    """Leva o “me chamaram” da thread do socket para a thread da TELA.

    Sem isto o segundo clique no ícone não fazia nada: `QTimer.singleShot`
    chamado de uma thread comum cria o relógio NESSA thread, que não tem laço
    de eventos do Qt — e ele nunca dispara. Passar um objeto de contexto
    também não resolve (medido em 02/09/2026: continuou não disparando).
    Sinal do Qt atravessa a fronteira de thread sozinho, e este é o caminho
    que a própria documentação do Qt indica.
    """
    chegou = QtCore.pyqtSignal()


class Launcher(QtWidgets.QWidget):
    """Selo pequeno sempre-no-topo, embaixo da tela. Clique abre o pop-up."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DERVS")
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint
                            | QtCore.Qt.WindowType.WindowStaysOnTopHint
                            | QtCore.Qt.WindowType.Tool)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(58, 58)
        self.setToolTip("DERVS — clique para gravar")
        self._press = None
        self._arrastou = False

        self.pop = PopUp()

        self._pos_canto()
        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.update)
        self.timer.start(500)

    def _pos_canto(self):
        tela = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.move(tela.center().x()-self.width()//2, tela.bottom()-self.height()-16)

    def _dentro_da_tela(self, ponto):
        """Impede o selo de ser arrastado para FORA da tela.

        Sem isto, um arrasto até a borda levava o selo para a área invisível e
        não havia como trazê-lo de volta — parte do 'o DERVS sumiu' relatado
        pelo dono em 02/09/2026."""
        # A tela SOB o ponto, não a principal: prender à principal impediria o
        # selo de ir para um segundo monitor, tirando algo que funcionava.
        alvo = QtWidgets.QApplication.screenAt(ponto)
        tela = (alvo or QtWidgets.QApplication.primaryScreen()).availableGeometry()
        x = min(max(ponto.x(), tela.left()), tela.right() - self.width() + 1)
        y = min(max(ponto.y(), tela.top()), tela.bottom() - self.height() + 1)
        return QtCore.QPoint(x, y)

    def aparecer(self):
        """Traz o selo de volta ao lugar de sempre, à vista e por cima de tudo.

        Roda quando o dono clica no ícone com o DERVS JÁ aberto, e no item
        'Trazer o selo de volta' da bandeja."""
        self._pos_canto()
        self.show(); self.raise_(); self.activateWindow()

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
            self.move(self._dentro_da_tela(novo))
    def mouseReleaseEvent(self, e):
        if self._press is not None and not self._arrastou:
            self.toggle_pop()
        self._press = None


def _montar_bandeja(app, launcher):
    """Ícone permanente na bandeja do sistema (a 'barra de tarefas'). Garante que
    o DERVS está sempre ao alcance, mesmo que o selo flutuante saia da vista.
    TEM 'Sair'. Até 02/09/2026 não tinha, de propósito — e o resultado foi que
    o dono não tinha NENHUM jeito de fechar o app sem o Gerenciador de Tarefas,
    que ele não usa. Somado à falta de trava de instância única, os DERVS iam se
    acumulando vivos e invisíveis a cada clique no ícone."""
    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QtWidgets.QSystemTrayIcon(_icone_app(), app)
    tray.setToolTip("DERVS — sempre aqui. Clique para abrir.")
    menu = QtWidgets.QMenu()
    menu.addAction("Abrir DERVS", launcher.pop.abrir)
    menu.addAction("Trazer o selo de volta", launcher.aparecer)
    menu.addAction("Recolher janela", launcher.pop.hide)
    menu.addSeparator()
    menu.addAction("Sair do DERVS", app.quit)
    tray.setContextMenu(menu)
    def _clique(motivo):
        if motivo == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            launcher.toggle_pop()
    tray.activated.connect(_clique)
    tray.show()
    return tray


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # UM DERVS só. Até 02/09/2026 cada clique no ícone abria mais um, empilhado
    # exatamente no mesmo ponto da tela e disputando o microfone — o de cima
    # comia o clique do de baixo, e sem 'Sair' na bandeja não havia como fechar
    # nenhum. Era o 'o DERVS sumiu / bugou' do dono. Agora o segundo clique TRAZ
    # de volta o que já está aberto e encerra sem subir. Ver dervs_instancia.py.
    _mostrar = []

    def _me_chamaram():
        # Roda numa thread de fundo. Mexer em janela daqui é proibido: quem
        # atravessa é o sinal da Ponte, ligado lá embaixo. Ver a Ponte para o
        # porquê de não ser um QTimer.
        if _mostrar:
            _mostrar[0]()

    posse = instancia.tomar_posse(_me_chamaram)
    if posse is None:
        sys.exit(0)          # o que já estava aberto acabou de pular na frente

    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    l = Launcher(); l.show()
    ponte = Ponte()                  # nasce na thread da tela: é o que importa
    ponte.chegou.connect(l.aparecer)
    _mostrar.append(ponte.chegou.emit)
    bandeja = _montar_bandeja(app, l)  # ícone fixo na bandeja

    def _encerrar():
        # Primeira linha de todas: a partir daqui, o motor de voz morrer é
        # ESPERADO. Sem isto o desligamento disparava o aviso de queda e uma
        # tentativa de religar, no meio do fechamento.
        l.pop._stt_encerrando = True
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
        posse.soltar()       # libera a vez para o próximo DERVS
    app.aboutToQuit.connect(_encerrar)

    app.exec()
