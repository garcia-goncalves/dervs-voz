#!/usr/bin/env python3
"""DERVS — conversa natural: liga microfone, árbitro de vez, trava de voz e motor (sem Qt).

Spec `docs/esteira/conversa-natural/spec.md`, seções 1, 3 e 4. Quem usa (a `PopUp`)
entrega cada quadro de 30 ms do microfone em `quadro(pcm)`, na thread da escuta (o
microfone continua tendo um dono só); o resto acontece aqui:

  quadro -> [eco] -> árbitro (InicioFala / FimDeVez)
         -> trava de voz: o áudio fica NO PC, janela a janela, até `Perfis.quem_fala`
            confirmar que é um perfil ATIVO; janela de outra pessoa no meio do turno
            vira silêncio e turno sem nenhuma janela confirmada nunca sai do PC
         -> motor (`dervs_conversa.Conversa`): enviar_audio / fim_da_vez / interromper
  motor -> AudioSaida -> `PlayerFluxo` (toca o PCM conforme chega, sem arquivo)
        -> ChamadaFerramenta -> política (fácil = faz calado com um sinal; dúvida =
           pergunta; grave = o cartão com clique de hoje; convidado = só o fácil)

Trava de voz (revisão de segurança de 15/10/2026): com pelo menos UM perfil gravado
ela é FAIL-CLOSED — sem modelo, nenhum perfil ativo ou erro do `quem_fala`, nada vai
ao motor e o dono é avisado. Com ZERO perfis gravados funciona como antes (tudo vai)
e `estado()` traz `locutor_aviso: "grave sua voz"`. Com a trava aberta não há
interrupção por voz: enquanto o DERVS fala o microfone é ignorado, como hoje (sem
perfil, a própria voz dele saindo da caixa o interromperia).

Pausa para pensar: se o árbitro fechar a vez cedo demais e você retomar a fala antes
de qualquer som da resposta, a resposta é descartada calada (`interromper`) e a fala
nova continua o mesmo pedido. A resposta só começa a tocar depois de `segurar_s` de
silêncio desde a sua última voz (ou `SEGURAR_MAX_S` depois do fim da vez).

Eco: se o pacote `livekit` estiver instalado, `CancelaEco` limpa o microfone usando
o áudio tocado como referência (medido em 15/10 nesta máquina: 31 dB de atenuação
num eco sintético, 13 ms de CPU por segundo). Sem ele vale a trava de voz (a voz do
DERVS não é perfil) e o VAD fica mais exigente enquanto ele fala.
"""
import collections
import logging
import os
import threading
import time
import unicodedata
import wave

import numpy as np

import dervs_conversa as dc
import dervs_turno as dt

log = logging.getLogger("dervs.conversa_natural")

TAXA = 16000
QUADRO_S = 0.03
QUADRO_BYTES = 960
TAXA_SAIDA = dc.TAXA_SAIDA_GEMINI           # 24 kHz
PRE_ROLL = 10                               # 300 ms antes do InicioFala
LIMIAR_VOZ = 300                            # RMS int16 de um quadro "com voz" (o Endpointer usa 380)
JANELA_S = 1.5                              # fala que cada janela precisa para o quem_fala decidir
JANELA_INTERRUPCAO_S = 0.75                 # por cima do DERVS decide mais cedo (meta: parar <= 0,9 s)
CONTEXTO_MAX_S = 3.0                        # janela móvel: a anterior confirmada + a atual
FALA_MINIMA_S = 0.3                         # menos que isto numa janela = silêncio
ABAIXAR = 0.3
ESPERA_CONFIRMAR_S = 1.2                    # sem confirmar até aqui, o volume volta
SEGURAR_S = 1.3                             # silêncio, desde a sua última voz, antes de ele soar
                                            # (no "gagueja" de 15/10 a pessoa pausa 1,2 s e retoma)
SEGURAR_MAX_S = 2.0                         # teto depois do fim da vez (ruído não o deixa mudo)
LIMIAR_VAD_TOCANDO = 0.85                   # VAD mais exigente enquanto ele fala (eco)
DONO_RECENTE_S = 600

CHAVES_DOS_MOTORES = {"gemini_live": "GEMINI_API_KEY", "cascata": "GROQ_API_KEY",
                      "openai_realtime": "OPENAI_API_KEY"}
NOMES_DOS_MOTORES = {"gemini_live": "Google grátis", "cascata": "econômico",
                     "openai_realtime": "premium"}

RECUSA_CONVIDADO = ("Isso eu só faço para o dono. Com você eu converso e faço coisas simples, "
                    "como abrir um programa ou dizer a hora.")
AVISO_TRAVA = "Não consegui conferir a sua voz, então não mandei nada. Tente de novo."
AVISO_SEM_ATIVO = "Nenhum perfil de voz está ativo; ative um no painel para eu te ouvir."
AVISO_CAIU = "A conversa rápida caiu. Voltei ao jeito de antes."

SISTEMA = (
    "Você é o DERVS, assistente de voz pessoal, e conversa em português do Brasil como uma "
    "pessoa: frases curtas (uma ou duas), tom natural e caloroso, sem listas e sem markdown. "
    "Nunca anuncie o que vai fazer ('Entendi: vou...', 'Vou fazer...'): ou faz, ou pergunta. "
    "Quando o pedido for uma ação no computador, chame uma ferramenta. "
    "Se faltar informação ou houver mais de uma leitura ('apaga aquilo', 'abre o projeto' sem "
    "dizer qual), não chame ferramenta de ação: pergunte, numa frase, o que falta. Se mesmo "
    "assim chamar 'fazer' sem certeza, use clareza 'duvida'. "
    "Quando a ferramenta devolver silencioso=true, não diga NADA: a ação já foi feita e eu toco "
    "um sinal. Quando devolver 'diga', fale essa frase, curta, e mais nada. Quando devolver "
    "precisa_confirmacao, faça a pergunta de 'diga' e espere a resposta; se a pessoa disser "
    "sim, chame 'confirmar' com resposta 'sim'; se disser não, 'nao'. "
    "Se a pessoa te interromper, largue o assunto anterior e atenda o que ela disse agora, "
    "levando em conta o que mudou."
)


def _obj(propriedades, obrigatorios=()):
    return {"type": "object", "properties": propriedades, "required": list(obrigatorios)}


FERRAMENTAS = [
    {"name": "fazer", "description": "Faz um pedido de ação no computador do dono. 'pedido' é a "
     "frase completa, em português. 'clareza' é 'clara' só se não há dúvida nenhuma.",
     "parameters": _obj({"pedido": {"type": "string"},
                         "clareza": {"type": "string", "enum": ["clara", "duvida"]}},
                        ("pedido", "clareza"))},
    {"name": "abrir_app", "description": "Abre um programa pelo nome (Chrome, Bloco de Notas...).",
     "parameters": _obj({"nome": {"type": "string"}}, ("nome",))},
    {"name": "hora", "description": "Diz a hora certa.", "parameters": _obj({})},
    {"name": "volume", "description": "Muda o volume do computador (0 a 100).",
     "parameters": _obj({"nivel": {"type": "integer"}}, ("nivel",))},
    {"name": "abrir_pasta", "description": "Abre uma pasta no Explorador de Arquivos.",
     "parameters": _obj({"pasta": {"type": "string"}}, ("pasta",))},
    {"name": "confirmar", "description": "Responde a uma pergunta de confirmação que eu fiz.",
     "parameters": _obj({"resposta": {"type": "string", "enum": ["sim", "nao"]}}, ("resposta",))},
]
_ESQUEMAS = {f["name"]: f["parameters"] for f in FERRAMENTAS}


# --- ferramentas: lista fechada e argumentos conferidos ------------------------------

def _texto_limpo(v, limite=200):
    if not isinstance(v, str):
        return None
    v = "".join(c for c in v if unicodedata.category(c)[0] != "C").strip()
    return v if 0 < len(v) <= limite else None


def validar_ferramenta(nome, args):
    """(nome, args limpos) ou None. Só nomes da lista, `args` dict, só campos conhecidos."""
    esquema = _ESQUEMAS.get(nome)
    if esquema is None or not isinstance(args, dict) or set(args) - set(esquema["properties"]):
        return None
    limpos = {}
    for campo, regra in esquema["properties"].items():
        if campo not in args:
            if campo in esquema["required"]:
                return None
            continue
        v = args[campo]
        if regra["type"] == "integer":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) \
                    or not 0 <= v <= 100:
                return None
            v = int(v)
        else:
            v = _texto_limpo(v)
            if v is None or ("enum" in regra and v not in regra["enum"]):
                return None
        limpos[campo] = v
    return nome, limpos


def pedido_da_ferramenta(nome, args):
    """A frase que o resto do DERVS (atalhos, cérebro, roteador) entende."""
    if nome == "fazer":
        return args["pedido"]
    if nome == "abrir_app":
        return "abre o " + args["nome"]
    if nome == "hora":
        return "que horas são"
    if nome == "volume":
        return "coloca o volume do computador em %d por cento" % args["nivel"]
    return "abre a pasta " + args["pasta"]


def acao_por_texto(pedido, papel, confirmado, *, atalho, especial, planejar, pede_confirmacao,
                   rodar_plano, mostrar_plano, delegar):
    """Decide e executa um pedido vindo da voz direta. Devolve {"tipo": ..., "fala": ...}.

    tipo: "facil" (feito, reversível) | "resposta" (só fala) | "grave" (plano na tela,
    esperando o clique de hoje) | "confirmar" (nada feito: precisa de um sim antes) |
    "delegado" (entregue ao caminho de sempre) | "recusado" | "falhou".
    Convidado só passa pelos atalhos locais (hora, data, abrir app). Claude Code, Codex,
    cofre e infra (`especial`) nunca rodam sem `confirmado`. Plano que
    `pede_confirmacao` nunca roda daqui: vai para `mostrar_plano` (o cartão com clique).
    """
    if papel not in ("dono", "convidado"):
        return {"tipo": "recusado"}
    ficha = atalho(pedido)
    if ficha is None:
        if papel != "dono":
            return {"tipo": "recusado"}
        if especial(pedido):
            if not confirmado:
                return {"tipo": "confirmar", "fala": "Quer que eu faça isto: %s?" % pedido}
            delegar(pedido)
            return {"tipo": "delegado"}
        ficha = planejar(pedido)
    if not isinstance(ficha, dict):
        return {"tipo": "falhou"}
    passos = ficha.get("passos") or []
    if ficha.get("modo") == "planejar" and passos:
        ficha = dict(ficha, fala="", local=True)   # calado, e sem o cérebro comentar depois
        if pede_confirmacao(passos):
            if papel != "dono":
                return {"tipo": "recusado"}
            mostrar_plano(ficha)
            return {"tipo": "grave"}
        rodar_plano(ficha)
        return {"tipo": "facil"}
    return {"tipo": "resposta", "fala": str(ficha.get("fala") or "")}


def motor_disponivel(conf, segredo=None) -> bool:
    """Há chave para algum motor da ordem? (o valor nunca sai daqui)."""
    if segredo is None:
        import dervs_config
        segredo = dervs_config.segredo
    return any(segredo(CHAVES_DOS_MOTORES[m]) for m in conf.get("conversa_motores", [])
               if m in CHAVES_DOS_MOTORES)


# --- som ------------------------------------------------------------------------------

def reamostrar(x: np.ndarray, de: int, para: int) -> np.ndarray:
    if de == para or len(x) == 0:
        return x
    n = max(1, int(round(len(x) * para / de)))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x.astype(np.float64))


def _rms(pcm: bytes) -> float:
    a = np.frombuffer(pcm, np.int16).astype(np.float64)
    return float(np.sqrt((a * a).mean())) if len(a) else 0.0


def sinal_feito_pcm() -> bytes:
    """Dois toques curtos e suaves (24 kHz, int16): 'feito'."""
    def nota(freq, dur):
        t = np.arange(int(TAXA_SAIDA * dur)) / TAXA_SAIDA
        return 0.18 * np.sin(np.pi * t / dur) ** 2 * np.sin(2 * np.pi * freq * t)
    x = np.concatenate([nota(880, 0.09), np.zeros(int(TAXA_SAIDA * 0.02)), nota(1318.5, 0.12)])
    return (x * 32767).astype(np.int16).tobytes()


def caminho_sinal() -> str:
    base = os.path.expandvars("%LOCALAPPDATA%")
    if "%" in base or not base:
        base = os.path.expanduser("~/AppData/Local")
    return os.path.join(base, "dervs", "sons", "sinal_feito.wav")


def carregar_sinal(caminho=None) -> bytes:
    """PCM do sinal, do WAV em cache (gerado na primeira vez)."""
    caminho = caminho or caminho_sinal()
    try:
        with wave.open(caminho) as w:
            if w.getframerate() == TAXA_SAIDA and w.getsampwidth() == 2:
                return w.readframes(w.getnframes())
    except (OSError, wave.Error, EOFError):
        pass
    pcm = sinal_feito_pcm()
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with wave.open(caminho, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(TAXA_SAIDA)
            w.writeframes(pcm)
    except OSError:
        pass
    return pcm


class CancelaEco:
    """AEC do WebRTC via `livekit` (opcional). Só a thread do microfone usa o módulo; o
    player só deixa a referência numa fila."""

    def __init__(self, apm, rtc):
        self._apm, self._rtc = apm, rtc
        self._ref = collections.deque(maxlen=200)

    @classmethod
    def criar(cls):
        try:
            from livekit import rtc
            apm = rtc.AudioProcessingModule(echo_cancellation=True, noise_suppression=False,
                                            high_pass_filter=True, auto_gain_control=False)
            return cls(apm, rtc)
        except Exception:
            return None

    def referencia(self, bloco_24k: np.ndarray):
        self._ref.append(np.asarray(bloco_24k))

    def _frame(self, a):
        return self._rtc.AudioFrame(np.asarray(a).astype(np.int16).tobytes(), TAXA, 1, len(a))

    def limpar(self, quadro: bytes) -> bytes:
        try:
            while self._ref:
                r = reamostrar(self._ref.popleft(), TAXA_SAIDA, TAXA)
                for i in range(0, len(r) - 159, 160):
                    self._apm.process_reverse_stream(self._frame(r[i:i + 160]))
            x = np.frombuffer(quadro, np.int16)
            saida = []
            for i in range(0, len(x), 160):
                f = self._frame(x[i:i + 160])
                self._apm.process_stream(f)
                saida.append(bytes(f.data))
            return b"".join(saida)
        except Exception:
            return quadro


class PlayerFluxo:
    """Toca PCM int16 conforme chega (sounddevice OutputStream com callback, 24 kHz).

    Sem arquivo temporário e sem acelerar (o WSOLA era o 'robótico'). O ganho muda em
    rampa dentro de um bloco de 20 ms: abaixar/restaurar não estalam e valem na hora.
    """

    BLOCO = 480                                  # 20 ms a 24 kHz

    def __init__(self, taxa=TAXA_SAIDA, eco=None, stream_fabrica=None):
        self.taxa = taxa
        self._eco = eco
        self._fabrica = stream_fabrica
        self._fila = collections.deque()
        self._resto = np.zeros(0, np.int16)
        self._ganho = 1.0
        self._alvo = 1.0
        self._trava = threading.Lock()
        self._stream = None

    def _abrir(self):
        if self._fabrica is not None:
            return self._fabrica(self._callback)
        import sounddevice as sd
        s = sd.RawOutputStream(samplerate=self.taxa, blocksize=self.BLOCO, channels=1,
                               dtype="int16", latency="low", callback=self._callback)
        s.start()
        return s

    def tocar(self, pcm: bytes, taxa: int = TAXA_SAIDA):
        x = np.frombuffer(pcm, np.int16)
        if taxa != self.taxa:
            x = np.clip(reamostrar(x, taxa, self.taxa), -32768, 32767).astype(np.int16)
        with self._trava:
            self._fila.append(x)
            precisa_abrir = self._stream is None
        if precisa_abrir:
            s = self._abrir()
            with self._trava:
                if self._stream is None:
                    self._stream, s = s, None
            if s is not None:                     # outra thread abriu antes: fecha o meu
                s.abort()
                s.close()

    def _puxar(self, n):
        partes, falta = [], n
        while falta > 0:
            if len(self._resto) == 0:
                if not self._fila:
                    break
                self._resto = self._fila.popleft()
            p, self._resto = self._resto[:falta], self._resto[falta:]
            partes.append(p)
            falta -= len(p)
        bloco = np.concatenate(partes) if partes else np.zeros(0, np.int16)
        if len(bloco) < n:
            bloco = np.concatenate([bloco, np.zeros(n - len(bloco), np.int16)])
        return bloco

    def _callback(self, outdata, frames, _tempo, _status):
        with self._trava:
            bloco = self._puxar(frames).astype(np.float64)
            rampa = np.linspace(self._ganho, self._alvo, frames)
            self._ganho = self._alvo
        saida = np.clip(bloco * rampa, -32768, 32767).astype(np.int16)
        outdata[:] = saida.tobytes()
        if self._eco is not None:
            self._eco.referencia(saida)

    def abaixar(self, frac=ABAIXAR):
        with self._trava:
            self._alvo = float(frac)

    def restaurar(self):
        self.abaixar(1.0)

    def parar(self):
        with self._trava:
            self._fila.clear()
            self._resto = np.zeros(0, np.int16)
            self._alvo = 1.0

    def tocando(self) -> bool:
        with self._trava:
            return bool(self._fila) or len(self._resto) > 0

    def fechar(self):
        """Tomar, abortar, fechar: só uma thread sai daqui com o stream na mão."""
        with self._trava:
            s, self._stream = self._stream, None
            self._fila.clear()
            self._resto = np.zeros(0, np.int16)
        if s is not None:
            try:
                s.abort()
                s.close()
            except Exception:
                pass


class Gravador:
    """Junta ~30 s do microfone para cadastrar um perfil (o áudio fica só na memória)."""

    def __init__(self, segundos=30.0, progresso=None):
        self._alvo = max(1, int(round(segundos / QUADRO_S)))
        self._quadros = []
        self._progresso = progresso
        self.pronto = threading.Event()

    def quadro(self, pcm: bytes) -> bool:
        if self.pronto.is_set():
            return False
        self._quadros.append(pcm)
        n = len(self._quadros)
        if self._progresso and (n % 33 == 0 or n >= self._alvo):
            try:
                self._progresso(min(1.0, n / self._alvo))
            except Exception:
                pass
        if n >= self._alvo:
            self.pronto.set()
        return True

    def audio(self) -> np.ndarray:
        bruto, self._quadros = b"".join(self._quadros), []
        return np.frombuffer(bruto, np.int16).astype(np.float32) / 32768.0


class Vozes:
    """API dos perfis para o painel (sem Qt). `conversa()` devolve a `ConversaNatural`
    ligada agora (ou None); `gravar_audio(segundos, progresso) -> float32 16 kHz`."""

    def __init__(self, perfis, conversa=lambda: None, gravar_audio=None, conf=None):
        self.perfis = perfis
        self._conversa = conversa
        self._gravar_audio = gravar_audio
        self._conf = conf or {}

    @staticmethod
    def _dict(p):
        return {"nome": p.nome, "papel": p.papel, "ativo": p.ativo}

    def listar(self):
        return [self._dict(p) for p in self.perfis.listar()]

    def _depois(self):
        cn = self._conversa()
        if cn is not None:
            cn.atualizar_trava()

    def gravar(self, nome, papel, progresso=None, segundos=30.0):
        """Novo DONO só a partir de uma conversa já confirmada como dono, ou no 1º cadastro."""
        import dervs_locutor
        if papel not in dervs_locutor.PAPEIS:
            return {"ok": False, "erro": "O papel é 'dono' ou 'convidado'."}
        if papel == "dono" and any(p.papel == "dono" for p in self.perfis.listar()):
            cn = self._conversa()
            if cn is None or not cn.dono_confirmado_recente():
                return {"ok": False, "erro": "Para cadastrar outro dono, fale comigo antes com a "
                                             "voz de um dono já cadastrado e tente de novo."}
        if self._gravar_audio is None:
            return {"ok": False, "erro": "Microfone indisponível para gravar."}
        try:
            p = self.perfis.gravar(nome, papel, self._gravar_audio(segundos, progresso))
        except dervs_locutor.ErroLocutor as e:
            return {"ok": False, "erro": str(e)}
        except Exception as e:
            return {"ok": False, "erro": "Não consegui gravar (%s)." % type(e).__name__}
        self._depois()
        return {"ok": True, "perfil": self._dict(p)}

    def ativar(self, nome, ativo):
        import dervs_locutor
        try:
            p = self.perfis.ativar(nome, bool(ativo))
        except dervs_locutor.ErroLocutor as e:
            return {"ok": False, "erro": str(e)}
        self._depois()
        return {"ok": True, "perfil": self._dict(p)}

    def apagar(self, nome):
        import dervs_locutor
        try:
            apagou = self.perfis.apagar(nome)
        except dervs_locutor.ErroLocutor as e:
            return {"ok": False, "erro": str(e)}
        self._depois()
        return {"ok": True} if apagou else {"ok": False, "erro": "Esse perfil não existe."}

    def estado(self):
        cn = self._conversa()
        if cn is not None:
            return cn.estado()
        lista = self.perfis.listar()
        ligada = self._conf.get("locutor_ligado", True) is not False
        return {"motor_ativo": None, "motor_nome": None, "locutor_ativo": bool(lista) and ligada,
                "perfis_ativos": [p.nome for p in lista if p.ativo],
                "locutor_aviso": _aviso_da_trava(("ligada" if lista else "sem_perfis")
                                                 if ligada else "desligada",
                                                 any(p.ativo for p in lista)),
                "dono_confirmado": False}


def _aviso_da_trava(trava, tem_ativo):
    if trava == "sem_perfis":
        return "grave sua voz"
    if trava == "desligada":
        return "trava de voz desligada"
    return None if tem_ativo else "nenhum perfil ativo"


# --- o orquestrador ---------------------------------------------------------------

class _Lote:
    __slots__ = ("quadros", "voz", "status", "perfil")

    def __init__(self, quadros, voz):
        self.quadros, self.voz, self.status, self.perfil = quadros, voz, None, None


def _em_thread(funcao):
    threading.Thread(target=funcao, name="dervs-conversa-natural", daemon=True).start()


class ConversaNatural:
    """Ver o cabeçalho do módulo. Os métodos públicos são seguros entre threads."""

    def __init__(self, conf, player, perfis, arbitro, conversa_factory, executar_acao, avisar,
                 ao_cair=None, ao_turno=None, ao_feito=None, eco=None, em_fundo=None,
                 relogio=time.monotonic, segurar_s=SEGURAR_S, sinal=None):
        """`executar_acao(pedido, papel, confirmado) -> {"tipo": ...}` (ver `acao_por_texto`);
        `avisar(texto)` aviso curto; `ao_cair(motivo)` a conversa caiu: volte ao caminho antigo;
        `em_fundo(f)` roda o `quem_fala` e as ferramentas fora da thread do microfone."""
        self.conf = conf
        self.player = player
        self.perfis = perfis
        self.arbitro = arbitro
        self._fabrica = conversa_factory
        self._executar = executar_acao
        self._avisar = avisar
        self._ao_cair = ao_cair or (lambda motivo: None)
        self._ao_turno = ao_turno or (lambda: None)
        self._ao_feito = ao_feito or (lambda: None)
        self._eco = eco
        self._em_fundo = em_fundo or _em_thread
        self._relogio = relogio
        self.segurar_s = segurar_s
        self._sinal = sinal
        self._trava_estado = threading.RLock()
        self.conversa = None
        self.falhou = False
        self.trava = "sem_perfis"
        self._ativos = []
        self._avisou_trava = False
        self._limiar_original = getattr(arbitro, "limiar_fala", None)
        self._ultimo_dono = None
        self._n = 0
        self._pre = collections.deque(maxlen=PRE_ROLL)
        self._ignorando = False
        # a fala da pessoa
        self._em_fala = False
        self._atual, self._atual_voz = [], []
        self._lotes = []
        self._ctx = np.zeros(0, np.float32)
        self._houve_ok = False
        self._fim_pendente = False
        self._perfil_turno = None
        # a resposta do DERVS
        self._aguardando = False
        self._retido = []
        self._t_fim = -1e9
        self._ultima_voz = -1e9
        self._quadro_em = None            # relógio do último quadro do microfone
        self._descartar = False
        self._mudo = False
        self._interrupcao = None          # instante em que alguém começou a falar por cima
        # ferramentas
        self._turnos = 0
        self._entrada = []
        self._desde_ferramenta = False
        self._pendente = None

    # ---- ciclo de vida ----
    def atualizar_trava(self):
        """Relê os perfis: trava ligada, aberta (zero perfis) ou desligada na config."""
        try:
            lista = self.perfis.listar() if self.perfis is not None else []
        except Exception:
            lista = None                     # erro de disco também fecha
        with self._trava_estado:
            if self.perfis is None or self.conf.get("locutor_ligado") is False:
                self.trava = "desligada"
            elif lista == []:
                self.trava = "sem_perfis"
            else:
                self.trava = "ligada"
            self._ativos = [p.nome for p in (lista or []) if p.ativo]

    def iniciar(self) -> bool:
        self.atualizar_trava()
        try:
            self.conversa = self._fabrica(self._evento)
            self.conversa.iniciar(SISTEMA, FERRAMENTAS)
        except Exception:
            log.exception("a conversa natural não subiu")
            self._cair("não subiu")
            return False
        return not self.falhou

    def encerrar(self):
        with self._trava_estado:
            c, self.conversa = self.conversa, None
        if c is not None:
            try:
                c.encerrar()
            except Exception:
                pass
        self.player.parar()

    def _cair(self, motivo):
        with self._trava_estado:
            if self.falhou:
                return
            self.falhou = True
        self.encerrar()
        self._avisar(AVISO_CAIU)
        self._ao_cair(motivo)

    def calar(self):
        """Interrupção explícita (o atalho apertado): a resposta em curso para na hora."""
        with self._trava_estado:
            if self._resposta_em_curso():
                self._interromper()

    def tique(self):
        """Chamado pelo relógio do app: solta a resposta retida quando o microfone parou de
        mandar quadros (o modo Atalho fecha o microfone logo depois da fala)."""
        with self._trava_estado:
            self._relogio_interno()

    def estado(self) -> dict:
        with self._trava_estado:
            motor = getattr(self.conversa, "motor_ativo", None) if self.conversa else None
            return {"motor_ativo": motor, "motor_nome": NOMES_DOS_MOTORES.get(motor),
                    "locutor_ativo": self.trava == "ligada",
                    "perfis_ativos": list(self._ativos),
                    "locutor_aviso": _aviso_da_trava(self.trava, bool(self._ativos)),
                    "dono_confirmado": self.dono_confirmado_recente()}

    def ocupado(self) -> bool:
        with self._trava_estado:
            return (self._em_fala or self._aguardando or bool(self._retido)
                    or self.player.tocando())

    def dono_confirmado_recente(self, janela_s=DONO_RECENTE_S) -> bool:
        with self._trava_estado:
            return self._ultimo_dono is not None and self._relogio() - self._ultimo_dono <= janela_s

    @property
    def _t(self):
        return self._n * QUADRO_S

    # ---- entrada: microfone ----
    def quadro(self, pcm: bytes) -> bool:
        """Um quadro de 30 ms (PCM int16 16 kHz). True: o quadro foi tratado aqui."""
        if self.falhou or self.conversa is None:
            return False
        if self._eco is not None:
            pcm = self._eco.limpar(pcm)
        with self._trava_estado:
            self._n += 1
            self._quadro_em = self._relogio()
            tocando = self.player.tocando()
            if self.trava != "ligada" and tocando:
                if not self._ignorando:      # sem trava não há interrupção: surdo enquanto fala
                    self._ignorando = True
                    self._resetar_arbitro()
                return True
            self._ignorando = False
            self._ajustar_vad(tocando)
            self._pre.append(pcm)
            if _rms(pcm) >= LIMIAR_VOZ:
                self._ultima_voz = self._t          # voz de novo: segura a resposta na hora
            iniciou = False
            for ev in self.arbitro.processar(pcm):
                if isinstance(ev, dt.InicioFala):
                    self._inicio_fala(tocando)
                    iniciou = True
                elif isinstance(ev, dt.FimDeVez):
                    self._fim_fala()
            if self._em_fala and not iniciou:
                self._acumular(pcm)
            self._relogio_interno()
        return True

    def turno_gravado(self, pcm: bytes):
        """Uma frase inteira já gravada (a que acordou o DERVS): passa pela trava e vira a vez."""
        with self._trava_estado:
            if self.falhou or self.conversa is None:
                return
            self._inicio_fala(False, pre=False)
            for i in range(0, len(pcm) - QUADRO_BYTES + 1, QUADRO_BYTES):
                self._acumular(pcm[i:i + QUADRO_BYTES])
            self._fim_fala()

    def _resetar_arbitro(self):
        if hasattr(self.arbitro, "reset"):
            self.arbitro.reset()
        self._em_fala = False
        self._atual, self._atual_voz, self._lotes = [], [], []

    def _ajustar_vad(self, tocando):
        if self._limiar_original is None or self.trava != "ligada" or self._eco is not None:
            return
        self.arbitro.limiar_fala = (max(self._limiar_original, LIMIAR_VAD_TOCANDO) if tocando
                                    else self._limiar_original)

    def _inicio_fala(self, tocando, pre=True):
        self._em_fala = True
        self._houve_ok = False
        self._fim_pendente = False
        self._ctx = np.zeros(0, np.float32)
        self._atual, self._atual_voz = [], []
        if tocando and self.trava == "ligada":
            self.player.abaixar(ABAIXAR)            # na hora: o árbitro marca a fala em ~90 ms
            self._interrupcao = self._t
        if self.trava != "ligada" and self._resposta_em_curso():
            self._interromper()                     # retomou a fala antes de ele soar: calado
        if pre:
            for q in self._pre:
                self._acumular(q)

    def _acumular(self, pcm):
        self._atual.append(pcm)
        if _rms(pcm) >= LIMIAR_VOZ:
            self._atual_voz.append(pcm)
        if self.trava != "ligada":
            self._houve_ok = True
            self._enviar(b"".join(self._atual))
            self._atual, self._atual_voz = [], []
            return
        limite = JANELA_INTERRUPCAO_S if self._interrupcao is not None else JANELA_S
        if len(self._atual_voz) * QUADRO_S >= limite - 1e-9:
            self._fechar_lote()

    def _fim_fala(self):
        if not self._em_fala:
            return
        self._em_fala = False
        if self.trava == "ligada" and self._atual:
            self._fechar_lote()
        self._fim_pendente = True
        self._aplicar_lotes()

    # ---- trava de voz ----
    def _fechar_lote(self):
        voz = (np.frombuffer(b"".join(self._atual_voz), np.int16).astype(np.float32) / 32768.0
               if self._atual_voz else np.zeros(0, np.float32))
        lote = _Lote(self._atual, voz)
        self._atual, self._atual_voz = [], []
        self._lotes.append(lote)
        if len(voz) < FALA_MINIMA_S * TAXA:
            lote.status = "silencio"
            return
        sobra = int(CONTEXTO_MAX_S * TAXA) - len(voz)
        amostra = np.concatenate([self._ctx[-sobra:] if sobra > 0 else self._ctx[:0], voz])
        self._em_fundo(lambda: self._checar(lote, amostra))

    def _checar(self, lote, amostra):
        try:
            if not self.perfis.disponivel() or not any(p.ativo for p in self.perfis.listar()):
                status, perfil = "erro", None
            else:
                perfil, _score = self.perfis.quem_fala(amostra)
                status = "ok" if perfil is not None and perfil.ativo else "nao"
        except Exception:
            status, perfil = "erro", None
        with self._trava_estado:
            lote.perfil, lote.status = perfil, status
            self._ctx = lote.voz if status == "ok" else np.zeros(0, np.float32)
            self._aplicar_lotes()

    def _aplicar_lotes(self):
        """Na ordem: janela confirmada vai ao motor; as outras viram silêncio (ou nada)."""
        while self._lotes and self._lotes[0].status is not None:
            lote = self._lotes.pop(0)
            bruto = b"".join(lote.quadros)
            if lote.status == "ok":
                if self._resposta_em_curso():
                    self._interromper()             # falou por cima, ou retomou: ele cala
                self._houve_ok = True
                self._perfil_turno = lote.perfil
                if lote.perfil.papel == "dono":
                    self._ultimo_dono = self._relogio()
                self._enviar(bruto)
            elif self._houve_ok:
                self._enviar(bytes(len(bruto)))     # janela de outra pessoa no meio: silêncio
            elif lote.status == "erro" and not self._avisou_trava:
                self._avisou_trava = True
                self._avisar(AVISO_SEM_ATIVO if not self._ativos else AVISO_TRAVA)
        if self._fim_pendente and not self._lotes and not self._em_fala:
            self._fim_pendente = False
            if self._interrupcao is not None and not self._houve_ok:
                self.player.restaurar()             # não era perfil ativo: o volume volta
            self._interrupcao = None
            if self._houve_ok:
                self._vez()

    def _vez(self):
        self._turnos += 1
        self._entrada = []
        self._desde_ferramenta = False
        self._descartar = False
        self._mudo = False
        self._aguardando = True
        self._t_fim = self._t
        c = self.conversa
        if c is not None:
            c.fim_da_vez()
        self._ao_turno()

    def _enviar(self, pcm):
        c = self.conversa
        if c is not None and pcm:
            c.enviar_audio(pcm)

    def _resposta_em_curso(self):
        return self._aguardando or bool(self._retido) or self.player.tocando()

    def _interromper(self):
        self._retido = []
        self._aguardando = False
        self._descartar = True
        self._interrupcao = None
        self.player.parar()
        c = self.conversa
        if c is not None:
            c.interromper()

    def _pode_tocar(self):
        if self._em_fala:
            return False
        if self._quadro_em is None or self._relogio() - self._quadro_em > 0.5:
            return True                             # microfone parado: não há o que esperar
        return (self._t - self._ultima_voz >= self.segurar_s - 1e-9
                or self._t - self._t_fim >= SEGURAR_MAX_S - 1e-9)

    def _relogio_interno(self):
        if self._interrupcao is not None and self._t - self._interrupcao >= ESPERA_CONFIRMAR_S:
            self._interrupcao = None
            self.player.restaurar()
        if self._retido and self._pode_tocar():
            retido, self._retido = self._retido, []
            for pcm, taxa in retido:
                self.player.tocar(pcm, taxa)
            self._aguardando = False

    # ---- saída: eventos do motor (thread de rede) ----
    def _evento(self, ev):
        try:
            self._tratar_evento(ev)
        except Exception:
            log.exception("evento da conversa natural falhou")

    def _tratar_evento(self, ev):
        if isinstance(ev, dc.AudioSaida):
            with self._trava_estado:
                if self._descartar or self._mudo:
                    return
                if self.player.tocando() or (not self._retido and self._pode_tocar()):
                    self.player.tocar(ev.pcm, ev.taxa)
                    self._aguardando = False
                else:
                    self._retido.append((ev.pcm, ev.taxa))
        elif isinstance(ev, dc.FimResposta):
            with self._trava_estado:
                self._mudo = False
                if not self._retido:
                    self._aguardando = False
        elif isinstance(ev, dc.TextoEntrada):
            with self._trava_estado:
                self._entrada.append(ev.texto)
        elif isinstance(ev, dc.ChamadaFerramenta):
            with self._trava_estado:
                # o motor marca origem="ferramenta" (pedida logo após um resultado); a nossa
                # própria conta (resposta de ferramenta desde a última vez do dono) vale também
                origem = self._desde_ferramenta or getattr(ev, "origem", "modelo") != "modelo"
                ctx = {"origem_ferramenta": origem, "turno": self._turnos,
                       "papel": self._papel()}
            self._em_fundo(lambda: self._ferramenta(ev, ctx))
        elif isinstance(ev, dc.Troca):
            self._avisar("Mudei a voz para o modo %s." % NOMES_DOS_MOTORES.get(ev.para, ev.para))
        elif isinstance(ev, dc.Erro):
            self._cair(ev.tipo)

    def _papel(self):
        """O papel é o que o PC decidiu pela voz, nunca o que o modelo diz."""
        if self.trava != "ligada":
            return "dono"                            # sem perfis ou trava desligada: como hoje
        return self._perfil_turno.papel if self._perfil_turno is not None else None

    # ---- ferramentas ----
    def _ferramenta(self, ev, ctx):
        try:
            resultado = self._decidir_ferramenta(ev, ctx)
        except Exception:
            log.exception("ferramenta falhou")
            resultado = {"ok": False, "diga": "Não consegui fazer isso agora."}
        sinal = resultado.pop("_sinal", False)
        with self._trava_estado:
            if resultado.get("silencioso") is True:
                self._mudo = True                     # nada do que ele falar depois toca
            self._desde_ferramenta = True
            c = self.conversa
        if c is not None:
            c.responder_ferramenta(ev.id, resultado)
        if sinal:
            if self._sinal:
                self.player.tocar(self._sinal, TAXA_SAIDA)
            self._ao_feito()

    def _decidir_ferramenta(self, ev, ctx):
        ok = validar_ferramenta(ev.nome, ev.args)
        if ok is None:
            return {"ok": False, "erro": "ferramenta ou argumentos inválidos; nada foi feito"}
        nome, args = ok
        papel = ctx["papel"]
        if nome == "confirmar":
            return self._confirmar(args["resposta"], ctx)
        if nome == "fazer" and args["clareza"] != "clara":
            return {"ok": False, "feito": False, "diga": "Pergunte o que falta; nada foi feito."}
        if papel not in ("dono", "convidado"):
            return {"ok": False, "recusado": True, "diga": RECUSA_CONVIDADO}
        pedido = pedido_da_ferramenta(nome, args)
        if ctx["origem_ferramenta"]:                  # pedido gerado por resultado de ferramenta
            return self._pedir_confirmacao(pedido, papel, ctx)
        return self._traduzir(self._executar(pedido, papel, False), pedido, papel, ctx)

    def _pedir_confirmacao(self, pedido, papel, ctx, fala=None):
        if papel != "dono":
            return {"ok": False, "recusado": True, "diga": RECUSA_CONVIDADO}
        with self._trava_estado:
            self._pendente = {"pedido": pedido, "turno": ctx["turno"]}
        return {"ok": True, "feito": False, "precisa_confirmacao": True,
                "diga": fala or "Quer que eu faça isto: %s?" % pedido}

    def _confirmar(self, resposta, ctx):
        """Só vale o sim do dono, numa vez NOVA dele, e que a transcrição também diga sim."""
        import dervs_atalhos
        with self._trava_estado:
            pend, self._pendente = self._pendente, None
            dito = " ".join(self._entrada)
            turno = self._turnos
        if pend is None:
            return {"ok": False, "diga": "Não tenho nada esperando o seu sim."}
        ouvi = dervs_atalhos.eh_confirmacao(dito) if dito.strip() else None
        if resposta == "nao" or ouvi == "nao":
            return {"ok": True, "feito": False, "diga": "Beleza, não fiz nada."}
        if (ctx["papel"] != "dono" or ctx["origem_ferramenta"] or turno <= pend["turno"]
                or ouvi != "sim"):
            return {"ok": False, "feito": False, "diga": "Não fiz nada: preciso ouvir um sim seu."}
        return self._traduzir(self._executar(pend["pedido"], "dono", True), pend["pedido"],
                              "dono", ctx)

    def _traduzir(self, r, pedido, papel, ctx):
        r = r if isinstance(r, dict) else {}
        tipo = r.get("tipo")
        if papel == "convidado" and tipo not in ("facil", "resposta"):
            return {"ok": False, "recusado": True, "diga": RECUSA_CONVIDADO}
        if tipo == "facil":
            return {"ok": True, "silencioso": True, "_sinal": True}
        if tipo == "resposta":
            return {"ok": True, "diga": r.get("fala") or ""}
        if tipo == "confirmar":
            return self._pedir_confirmacao(pedido, papel, ctx, r.get("fala"))
        if tipo == "grave":
            return {"ok": True, "feito": False, "aguardando_clique": True,
                    "diga": "Coloquei o plano na tela; confirma no botão."}
        if tipo == "delegado":
            return {"ok": True, "silencioso": True, "encaminhado": True}
        if tipo == "recusado":
            return {"ok": False, "recusado": True, "diga": RECUSA_CONVIDADO}
        return {"ok": False, "diga": r.get("fala") or "Não consegui fazer isso agora."}


def ler_pcm_wav(caminho):
    """PCM int16 16 kHz mono de um .wav da escuta (None se não for isso)."""
    try:
        with wave.open(caminho) as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (TAXA, 1, 2):
                return None
            return w.readframes(w.getnframes())
    except (OSError, wave.Error, EOFError, TypeError):
        return None


def baixar_modelos_em_fundo():
    """Baixa (uma vez, SHA-256 conferido) os modelos do árbitro e do locutor, sem travar nada:
    a sessão de agora segue com o que há; a próxima já usa os modelos."""
    def corpo():
        try:
            import dervs_locutor
            for nome in dt.MODELOS:
                dt.garantir_modelo(nome)
            dervs_locutor.caminho_modelo()
        except Exception:
            log.exception("baixar modelos da conversa natural")
    threading.Thread(target=corpo, name="dervs-modelos-conversa", daemon=True).start()


def criar_padrao(conf, executar_acao, avisar, arbitro=None, **kw):
    """A `ConversaNatural` de produção: Perfis, árbitro, Conversa e player de verdade."""
    import dervs_locutor
    eco = CancelaEco.criar()
    return ConversaNatural(
        conf, PlayerFluxo(eco=eco), dervs_locutor.Perfis(), arbitro or dt.criar(conf, baixar=False),
        lambda cb: dc.Conversa(cb, conf=conf), executar_acao, avisar, eco=eco,
        sinal=carregar_sinal(), **kw)
