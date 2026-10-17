#!/usr/bin/env python3
"""DERVS — a voz (falar em português).

O motor padrão NÃO é definido aqui: a fonte única é `dervs_config.PADRAO["motor"]`
(hoje "openai", a voz de nuvem; `MOTOR_PADRAO` abaixo só a repete). Os motores:
  - "openai" → voz de nuvem, a mais natural; precisa de internet e de chave, e custa
              centavos por fala. Cai no Kokoro se a nuvem falhar.
  - "kokoro" → voz humana offline e rápida (~0,6 s até o 1º som), a RESERVA da nuvem.
  - "piper"  → voz sintética e instantânea: um daemon (dervs_piper_daemon.py, na venv
              tts-venv) carrega o modelo .onnx uma vez só e fica vivo. O texto é falado
              FRASE POR FRASE — a primeira começa a tocar enquanto o daemon gera a
              segunda — para o "tempo até o primeiro som" ficar bem abaixo de 1 s.
  - "xtts"   → voz humana (Coqui XTTS v2), via daemon próprio (dervs_tts_daemon.py,
              na venv xtts-venv). Muito natural, porém ~7 s por frase: lento demais
              para conversar.

Regras de projeto:
  - Nunca quebra: se o motor escolhido falhar, cai no outro; se nenhum houver,
    fica mudo e a pessoa lê pela tela.
  - Dá para CALAR na hora (barge-in) — para a reprodução, sem matar o daemon,
    mesmo no meio de uma fala com várias frases em fila.
  - Nunca bloqueia a tela: síntese e reprodução rodam em thread separada.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
import hashlib
import io
import json
import random
import queue
import re
import urllib.request

import numpy as np

import dervs_config
import dervs_gasto
import dervs_nivel
import dervs_processos as processos

HOME = os.path.expanduser("~")
VOICE_DIR = f"{HOME}/voice"


def _venv_python(venv_dir: str) -> str:
    """Caminho do python de dentro de um venv: Scripts\\python.exe no Windows,
    bin/python em Linux — mesma venv, layout diferente por plataforma."""
    if sys.platform == "win32":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def _dir_modelos_kokoro() -> str:
    """Onde ficam os modelos do Kokoro. DERVS_MODELOS sobrepõe tudo; senão,
    no Windows é %LOCALAPPDATA%\\dervs\\modelos (onde já foram baixados nesta
    máquina); em Linux continua ~/voice/kokoro-model."""
    if os.environ.get("DERVS_MODELOS"):
        return os.environ["DERVS_MODELOS"]
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        return os.path.join(base, "dervs", "modelos")
    return f"{VOICE_DIR}/kokoro-model"


def _dir_daemons() -> str:
    """Pasta onde moram os scripts dos daemons de voz.

    No Linux o projeto irmão instala tudo em `~/voice`. No Windows essa pasta
    NÃO existe: os daemons vêm junto com o repositório, ao lado deste arquivo.
    Com o caminho do Linux fixo aqui, `Voz.disponivel()` respondia False e o
    DERVS ficava mudo na máquina do dono — com o modelo já baixado."""
    if sys.platform == "win32":
        return os.path.dirname(os.path.abspath(__file__))
    return VOICE_DIR


def _py_do_motor(venv_linux: str) -> str:
    """Python que roda um daemon de voz.

    No Linux cada motor tem seu ambiente isolado dentro de `~/voice`. No
    Windows não há essa separação: tudo foi instalado no `dervs-venv` do
    próprio projeto — e se ele não estiver lá, serve o mesmo Python que roda o
    app, que é onde as bibliotecas necessariamente estão."""
    if sys.platform != "win32":
        return _venv_python(f"{VOICE_DIR}/{venv_linux}")
    proprio = _venv_python(os.path.join(_dir_daemons(), "dervs-venv"))
    escolhido = proprio if os.path.exists(proprio) else sys.executable
    # `pythonw` em vez de `python`: mesma linguagem, sem janela de terminal.
    # A voz do DERVS deixava uma janela preta aberta (02/09/2026).
    return processos.python_sem_console(escolhido)


# --- Piper (rápido, padrão) ---
PIPER_PY = _py_do_motor("tts-venv")
PIPER_DAEMON = os.path.join(_dir_daemons(), "dervs_piper_daemon.py")
VOZES_DIR = f"{VOICE_DIR}/piper-voices"
VOZ_PADRAO = "jeff"             # faber / cadu / jeff — ver escolha no relatório da tarefa
# length_scale < 1 fala mais rápido (1.0 = padrão do modelo). 0.95 deixa a
# conversa mais ágil sem soar robótico (testado até 0.85 antes de comprometer
# a naturalidade das sílabas).
LENGTH_SCALE = 0.95
NOISE_W = 0.9
SILENCIO_FRASE = "0.35"          # só usado no modo de reserva (sem daemon)

# --- Kokoro (humano E rápido, padrão novo) ---
KOKORO_PY = _py_do_motor("kokoro-venv")
KOKORO_DAEMON = os.path.join(_dir_daemons(), "dervs_kokoro_daemon.py")
KOKORO_MODELO = os.path.join(_dir_modelos_kokoro(), "kokoro-v1.0.onnx")
VOZ_KOKORO_PADRAO = "pm_santa"   # masculina grave (feiticeiro)
KOKORO_LANG = "pt-br"

# --- XTTS (humano, opcional) ---
XTTS_PY = _py_do_motor("xtts-venv")
XTTS_DAEMON = os.path.join(_dir_daemons(), "dervs_tts_daemon.py")

# Motor padrão: o da config (fonte única). Se a nuvem não puder falar, cai no Kokoro e,
# sem ele, no Piper.
MOTOR_PADRAO = dervs_config.PADRAO["motor"]

# --- Voz de nuvem (OpenAI): a mais natural, e a única que aceita instrução de
# sotaque. O Kokoro local fica de reserva, para quando a internet cair. ---
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
OPENAI_TTS_TIMEOUT_S = 20
OPENAI_DESCANSO_S = 60      # depois de uma falha, não insiste na nuvem por 1 min
INSTRUCOES_VOZ_BR = (
    "Voz: homem adulto, timbre grave e suave, calmo, culto e elegante, como um assistente "
    "de IA sofisticado (estilo JARVIS) falando português do Brasil. Confiante e preciso; "
    "nunca locutor de rádio, nunca atendente de call center.\n"
    "Sotaque: português do Brasil, natural e claro, neutro com leve toque paulistano. "
    "Pronuncie como brasileiro de verdade: 'r' e 'rr' do jeito daqui, 'ão', 'lh', vogais "
    "finais reduzidas ('pode', 'leite').\n"
    "Ritmo: ágil e fluido, resposta pronta, sem pausas longas, sem arrastar vogais nem "
    "sílabas finais. Rápido sem atropelar, com a calma de quem tem tudo sob controle.\n"
    "Entonação: firme e decidida. Final de frase seguro, nunca caindo mole; pergunta "
    "sobe de forma natural. Ênfase leve nas palavras importantes.\n"
    "Emoção: presença tranquila, um traço discreto de humor seco quando cabe. "
    "Naturalidade acima de tudo. Nunca monótono, nunca robótico, nunca sotaque estrangeiro."
)
# Respostas imediatas: ditas na hora, de um áudio já guardado em disco, enquanto o
# cérebro pensa e a frase de verdade é gerada na nuvem (~2 s). Curtas e neutras.
ACUSES = ("Certo.", "Entendido.", "Pois não.", "Um instante.")

# Frases do jeito JARVIS que saem na hora (esteira dervs-jeito-jarvis, 17/10/2026): gravadas uma
# vez na voz única e tocadas do disco. Antes, "DERVS" sozinho pedia "Oi! Pode falar." à nuvem
# (~3,4 s, e às vezes 20 s calado quando o Google não respondia).
FRASE_CHAMADO = "Pois não, senhor?"
FRASE_PRESENTE = "À sua disposição, senhor."
FRASE_LIGADO = "Online, senhor. Basta me chamar."
FRASES_PRONTAS = (FRASE_CHAMADO, FRASE_PRESENTE, FRASE_LIGADO)
_FIM_FRASE = re.compile(r"(?<=[.!?;:])\s+")
_FIM_DA_FILA = object()


def _frases_da_fala(texto: str):
    """Quebra em frases para tocar a 1ª enquanto a 2ª ainda é gerada."""
    partes = [p.strip() for p in _FIM_FRASE.split(texto.strip()) if p.strip()]
    return partes or ([texto.strip()] if texto.strip() else [])


def pedido_openai(texto: str, voz: str, modelo: str, instrucoes: str) -> dict:
    return {"model": modelo, "voice": voz, "input": texto,
            "instructions": instrucoes, "response_format": "wav"}


def consertar_cabecalho_wav(dados: bytes) -> bytes:
    """A nuvem manda o wav com o tamanho do bloco de áudio como 0xFFFFFFFF
    ("não sei ainda"). O `wave` do Python então lê 89 mil segundos e o player e
    o medidor de onda se perdem. Reescreve os dois tamanhos com o valor real."""
    i = dados.find(b"data")
    if not dados.startswith(b"RIFF") or i < 0:
        return dados
    real = len(dados) - (i + 8)
    return (dados[:4] + (len(dados) - 8).to_bytes(4, "little") + dados[8:i + 4]
            + real.to_bytes(4, "little") + dados[i + 8:])


def acelerar_wav(dados: bytes, fator: float) -> bytes:
    """Acelera um wav mono de 16 bits SEM mudar o tom (WSOLA, só numpy): a voz fica
    mais ágil sem ficar fina. Entrada que não dá para tratar (não é wav, estéreo,
    curta demais) volta intacta — acelerar nunca pode derrubar a fala."""
    try:
        if not fator or fator <= 1.0:
            return dados
        with wave.open(io.BytesIO(dados), "rb") as w:
            canais, largura, taxa = w.getnchannels(), w.getsampwidth(), w.getframerate()
            bruto = w.readframes(w.getnframes())
        if canais != 1 or largura != 2:
            return dados
        x = np.frombuffer(bruto, dtype="<i2").astype(np.float32) / 32768.0
        n = int(taxa * 0.032) // 2 * 2                      # janela de ~32 ms, par
        if len(x) < n * 6:
            return dados
        y = _wsola(x, float(fator), n, int(taxa * 0.010))
        pcm = (np.clip(y, -1.0, 1.0) * 32767.0).astype("<i2")
        saida = io.BytesIO()
        with wave.open(saida, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(pcm.tobytes())
        return saida.getvalue()
    except Exception:
        return dados


def _wsola(x, fator: float, n: int, folga: int):
    """Sobrepõe janelas de Hann escolhendo, perto do ponto nominal, o trecho que
    melhor continua o anterior (maior correlação): é isso que evita o "chiado" de
    uma colagem ingênua."""
    hs = n // 2                                             # passo de síntese
    ha = hs * fator                                         # passo de análise (maior)
    janela = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)).astype(np.float32)
    x = np.concatenate([x, np.zeros(n * 3 + folga * 2, dtype=np.float32)])
    quadros = int((len(x) - n * 3 - folga * 2) / ha)
    saida = np.zeros(quadros * hs + n, dtype=np.float32)
    peso = np.zeros_like(saida)
    saida[:n] += x[:n] * janela
    peso[:n] += janela
    anterior = 0
    for k in range(1, quadros):
        alvo = int(round(k * ha))
        ref = x[anterior + hs:anterior + hs + n]            # continuação natural
        lo = max(0, alvo - folga)
        hi = alvo + folga
        candidatos = np.lib.stride_tricks.sliding_window_view(x[lo:hi + n], n)
        melhor = lo + int(np.argmax(candidatos @ ref))
        ini = k * hs
        saida[ini:ini + n] += x[melhor:melhor + n] * janela
        peso[ini:ini + n] += janela
        anterior = melhor
    return saida / np.maximum(peso, 1e-3)


def sintetizar_openai(texto: str, voz: str, modelo: str, instrucoes: str, chave: str,
                      tempo: float = 1.0):
    """Gera UMA frase na nuvem e devolve o caminho de um wav temporário, ou None
    se algo falhou. `tempo` > 1 acelera o áudio sem mudar o tom. Nunca escreve a
    chave (nem o erro cru, que pode citá-la)."""
    try:
        req = urllib.request.Request(
            OPENAI_TTS_URL,
            data=json.dumps(pedido_openai(texto, voz, modelo, instrucoes)).encode("utf-8"),
            headers={"Authorization": "Bearer " + chave,
                     "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=OPENAI_TTS_TIMEOUT_S) as r:
            dados = r.read()
        if not dados.startswith(b"RIFF"):
            return None
        dados = consertar_cabecalho_wav(dados)
        dervs_gasto.registrar_voz(dados, modelo)    # mede DEPOIS de consertar o tamanho
        dados = acelerar_wav(dados, tempo)          # o custo é do áudio gerado, não do tocado
        tmp =tempfile.NamedTemporaryFile(prefix="dervs_openai_", suffix=".wav", delete=False)
        try:
            tmp.write(dados)
        finally:
            tmp.close()
        return tmp.name
    except Exception as erro:
        sys.stderr.write("dervs_tts: voz de nuvem falhou (%s)\n" % type(erro).__name__)
        return None


GEMINI_TTS_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
                  "gemini-3.8-flash-lite-tts:generateContent")
GEMINI_TTS_TIMEOUT_S = 8
GEMINI_TTS_TAXA = 24000


def aparar_silencio(pcm: bytes, limiar: int = 300, folga_s: float = 0.12) -> bytes:
    """Tira o silêncio do começo e do fim (PCM 16 bits, 24 kHz), deixando uma folga curta: o
    Gemini devolve meio segundo mudo que soa como hesitação."""
    x = np.frombuffer(pcm, np.int16)
    alto = np.flatnonzero(np.abs(x.astype(np.int32)) > limiar)
    if alto.size == 0:
        return b""
    folga = int(GEMINI_TTS_TAXA * folga_s)
    return x[max(0, alto[0] - folga):alto[-1] + folga].tobytes()


def sintetizar_gemini(texto: str, voz: str, chave: str):
    """A MESMA voz da conversa natural (Gemini TTS, faixa grátis) para o caminho antigo: uma voz só
    no DERVS inteiro (16/10/2026). A resposta inteira vai numa ida só — a faixa grátis dá 429 a
    poucos pedidos por minuto, e frase a frase estouraria. Devolve o wav temporário ou None; nunca
    escreve a chave nem o erro cru."""
    import base64
    import wave
    try:
        corpo = json.dumps({
            # só a frase: com instrução de tom antes, o modelo às vezes a lia em voz alta (17/10)
            "contents": [{"parts": [{"text": texto}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}},
        }).encode("utf-8")
        req = urllib.request.Request(GEMINI_TTS_URL, data=corpo, method="POST", headers={
            "x-goog-api-key": chave, "Content-Type": "application/json"})
        for tentativa in (1, 2):
            # leva ~3,4 s; às vezes o Google não responde, e esperar 20 s calado era o
            # "travou" do teste de 17/10. Espera curta e uma segunda tentativa só no tempo esgotado.
            try:
                with urllib.request.urlopen(req, timeout=GEMINI_TTS_TIMEOUT_S) as r:
                    d = json.loads(r.read())
                break
            except (TimeoutError, urllib.error.URLError) as erro:
                esgotou = isinstance(erro, TimeoutError) or isinstance(
                    getattr(erro, "reason", None), TimeoutError)
                if tentativa == 2 or isinstance(erro, urllib.error.HTTPError) or not esgotou:
                    raise
        pcm = b"".join(base64.b64decode((p.get("inlineData") or {}).get("data") or "")
                       for c in d.get("candidates", [])
                       for p in (c.get("content") or {}).get("parts", []))
        pcm = aparar_silencio(pcm[:len(pcm) // 2 * 2])
        if len(pcm) < 2:
            return None
        tmp = tempfile.NamedTemporaryFile(prefix="dervs_gemini_", suffix=".wav", delete=False)
        tmp.close()
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(GEMINI_TTS_TAXA)
            w.writeframes(pcm[:len(pcm) // 2 * 2])
        return tmp.name
    except Exception as erro:
        sys.stderr.write("dervs_tts: voz do Gemini falhou (%s)\n" % type(erro).__name__)
        return None


def caminho_voz(nome: str) -> str:
    return f"{VOZES_DIR}/pt_BR-{nome}-medium.onnx"


MODELO_VOZ = caminho_voz(VOZ_PADRAO)   # compatibilidade


def _player_linux():
    for p in ("pw-play", "paplay", "aplay"):
        if shutil.which(p):
            return p
    return None


def _reproducao_disponivel() -> bool:
    """Tem como tocar áudio nesta máquina? No Windows sempre tem — sounddevice
    se estiver instalado, senão winsound (biblioteca padrão, sempre presente)."""
    if sys.platform == "win32":
        return True
    return _player_linux() is not None


class _ReprodutorSD:
    """Toca um wav com sounddevice e imita a interface mínima de
    subprocess.Popen (poll/terminate/wait) que o resto de Voz já usa para
    _play — assim calar() (barge-in) funciona igual em Windows e Linux."""

    def __init__(self, wav: str):
        import sounddevice as sd
        import soundfile as sf
        self._sd = sd
        dados, taxa = sf.read(wav, dtype="float32")
        sd.play(dados, taxa)

    def poll(self):
        try:
            fluxo = self._sd.get_stream()
        except Exception:
            return 0
        if fluxo is not None and fluxo.active:
            return None      # ainda tocando (igual Popen.poll() == None)
        return 0

    def terminate(self):
        try:
            self._sd.stop()
        except Exception:
            pass

    def wait(self):
        try:
            self._sd.wait()
        except Exception:
            pass


class _ReprodutorWinsound:
    """Reserva quando sounddevice não está instalado: winsound é da biblioteca
    padrão do Windows, então nunca falta. Assíncrono, para o barge-in
    (calar()) conseguir cortar no meio — SND_PURGE derruba o que estiver
    tocando na hora."""

    def __init__(self, wav: str):
        import winsound
        self._winsound = winsound
        self._parado = False
        with wave.open(wav, "rb") as w:
            self._duracao = w.getnframes() / float(w.getframerate() or 1)
        self._inicio = time.monotonic()
        winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC)

    def poll(self):
        if self._parado:
            return 0
        return None if (time.monotonic() - self._inicio) < self._duracao else 0

    def terminate(self):
        self._parado = True
        try:
            self._winsound.PlaySound(None, self._winsound.SND_PURGE)
        except Exception:
            pass

    def wait(self):
        while self.poll() is None:
            time.sleep(0.02)


def criar_reprodutor(wav: str):
    """Devolve um objeto com poll()/terminate()/wait() tocando `wav` — mesmo
    contrato do subprocess.Popen usado no Linux, para calar() e falando()
    valerem para os dois sistemas sem precisar saber qual está tocando.
    Devolve None se não há como tocar nada."""
    if sys.platform == "win32":
        try:
            return _ReprodutorSD(wav)
        except Exception as erro:
            sys.stderr.write(f"dervs_tts: sounddevice indisponível ({erro}), usando winsound\n")
            try:
                return _ReprodutorWinsound(wav)
            except Exception as erro2:
                sys.stderr.write(f"dervs_tts: winsound também falhou ({erro2})\n")
                return None
    player = _player_linux()
    if not player:
        return None
    return subprocess.Popen([player, wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Voz:
    """Fala frases, uma de cada vez. Ligada/desligada por um interruptor."""

    def __init__(self, ligada: bool = False, motor: str = MOTOR_PADRAO,
                 voz: str = VOZ_PADRAO, voz_kokoro: str = VOZ_KOKORO_PADRAO,
                 voz_velocidade: float | None = None):
        self.ligada = ligada
        self.motor = motor
        self.modelo = caminho_voz(voz)    # voz do Piper
        self.voz_kokoro = voz_kokoro      # voz do Kokoro
        # velocidade do Kokoro: vem da config (voz_velocidade), a menos que
        # quem chamou passe um valor explícito.
        _conf = dervs_config.carregar()
        self.voz_velocidade = (voz_velocidade if voz_velocidade is not None
                                else _conf["voz_velocidade"])
        self.voz_openai = _conf["voz_openai"]
        self.modelo_openai = _conf["voz_openai_modelo"]
        self.tempo_openai = _conf["voz_openai_tempo"]     # aceleração sem mudar o tom
        self.voz_gemini = _conf.get("voz_gemini") or "Charon"
        self.silenciada = False            # a conversa natural está falando: esta voz não abre a boca
        self._openai_descansa_ate = 0.0    # monotonic: até quando a nuvem descansa
        self._synth = None                 # processo de síntese "de reserva" (sem daemon)
        self._play = None                  # processo do player
        self._daemon = None                # processo do daemon XTTS (persistente)
        self._xtts_ready = False
        self._xtts_morto = False           # daemon XTTS falhou → usa Piper
        self._piper_daemon = None          # processo do daemon Piper (persistente)
        self._piper_pronto = False
        self._piper_daemon_morto = False   # daemon Piper falhou → usa Piper "de reserva"
        self._kokoro_daemon = None         # processo do daemon Kokoro (persistente)
        self._kokoro_pronto = False
        self._kokoro_morto = False         # daemon Kokoro falhou → cai no Piper
        self._gerando = False              # true enquanto sintetiza, mesmo sem processo próprio
        self._evento_atual = None          # threading.Event da fala em andamento (p/ calar())
        self.ao_nivel = None                # quem quiser ver a onda enquanto o DERVS fala liga isto aqui
        self._lock = threading.Lock()          # guarda _play/_synth (calar() precisa ser instantâneo)
        self._lock_piper = threading.Lock()    # serializa a conversa com o daemon do Piper
        self._lock_kokoro = threading.Lock()   # serializa a conversa com o daemon do Kokoro
        # já sobe o daemon do motor escolhido, para o modelo estar quente na 1a fala
        if self.motor == "kokoro" and self._kokoro_instalado():
            self._garantir_kokoro_daemon()
        elif self.motor == "xtts" and self._xtts_instalado():
            self._garantir_daemon()
        elif self.motor == "piper" and self._piper_daemon_instalado():
            self._garantir_piper_daemon()

    # ---- disponibilidade ----
    def _piper_disponivel(self):
        return (os.path.exists(PIPER_PY) and os.path.exists(self.modelo)
                and _reproducao_disponivel())

    def _piper_daemon_instalado(self):
        return os.path.exists(PIPER_DAEMON) and self._piper_disponivel()

    def _xtts_instalado(self):
        return os.path.exists(XTTS_PY) and os.path.exists(XTTS_DAEMON)

    def _kokoro_instalado(self):
        return (os.path.exists(KOKORO_PY) and os.path.exists(KOKORO_DAEMON)
                and os.path.exists(KOKORO_MODELO) and _reproducao_disponivel())

    def _chave_openai(self):
        try:
            return dervs_config.segredo("OPENAI_API_KEY")
        except Exception:
            return None

    def _chave_gemini(self):
        try:
            return dervs_config.segredo("GEMINI_API_KEY")
        except Exception:
            return None

    def _gemini_disponivel(self):
        return self.motor == "gemini" and _reproducao_disponivel() and bool(self._chave_gemini())

    def _openai_disponivel(self):
        return (self.motor == "openai" and _reproducao_disponivel()
                and time.monotonic() >= self._openai_descansa_ate
                and bool(self._chave_openai())
                and dervs_gasto.pode_gastar()[0])      # teto diário e "só analisa"

    def _kokoro_disponivel(self):
        return self._kokoro_instalado() and not self._kokoro_morto

    def disponivel(self) -> bool:
        """Tem como falar por ALGUM motor?"""
        if self.motor == "gemini":
            return self._gemini_disponivel()        # voz única: sem reserva em outra voz
        return (self._openai_disponivel() or self._kokoro_disponivel()
                or self._piper_disponivel()
                or (self._xtts_instalado() and not self._xtts_morto))

    def trocar_voz(self, nome: str):
        alvo = caminho_voz(nome)
        if os.path.exists(alvo):
            self.modelo = alvo
            # o daemon do Piper carrega modelo por caminho e faz cache sozinho;
            # só derruba o daemon se ele não existir mais (troca rara, sem custo aqui)
            return True
        return False

    def falando(self) -> bool:
        """Está falando/gerando agora? (a escuta contínua pausa enquanto isso)."""
        if self._gerando:
            return True
        with self._lock:
            for proc in (self._play, self._synth):
                if proc and proc.poll() is None:
                    return True
        return False

    def calar(self):
        """Para a fala em andamento — na hora. NÃO mata os daemons (persistem).

        Se a fala atual for do Piper em várias frases, sinaliza a thread que
        está gerando para parar de tocar mais frases — mas ela continua
        drenando a resposta do daemon até o fim por baixo dos panos, senão a
        próxima fala se confundiria com o restante desta.
        """
        if self._evento_atual is not None:
            self._evento_atual.set()
        with self._lock:
            for proc in (self._play, self._synth):
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            self._play = self._synth = None

    def desligar(self):
        """Encerra tudo, inclusive os daemons (ao fechar o app).

        Cada daemon é encerrado sob O MESMO lock que serializa a conversa com
        ele. Antes os três saíam sob `self._lock`, enquanto `_pedir_piper` e
        `_pedir_kokoro` — que rodam na thread de fundo criada por `falar()` —
        usavam `_lock_piper` e `_lock_kokoro`. Locks diferentes sobre o mesmo
        dado não excluem nada: fechar o app no meio de uma fala derrubava o
        processo do daemon com a thread ainda escrevendo no `stdin` dele. O
        `except` genérico lá dentro engolia o erro, então a fala morria pelo
        meio sem uma linha de aviso em lugar nenhum.
        """
        self.calar()
        for nome, trava in (("_daemon", self._lock),
                            ("_piper_daemon", self._lock_piper),
                            ("_kokoro_daemon", self._lock_kokoro)):
            with trava:
                proc = getattr(self, nome)
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                setattr(self, nome, None)

    def falar(self, texto: str):
        """Fala a frase (sem travar a tela)."""
        texto = (texto or "").strip()
        if not texto or not self.ligada or self.silenciada or not self.disponivel():
            return
        self.calar()
        threading.Thread(target=self._falar_bloqueante, args=(texto,), daemon=True).start()

    def _falar_bloqueante(self, texto: str):
        evento = threading.Event()
        self._evento_atual = evento
        self._gerando = True
        try:
            if self.motor == "gemini":
                # voz única (a mesma da conversa natural). Falhou: fica calado — o texto já está na
                # tela — em vez de trocar para uma segunda voz no meio da conversa.
                pronto = self._arquivo_pronto(texto)
                if pronto and os.path.isfile(pronto) and os.path.getsize(pronto) > 0:
                    if not evento.is_set():
                        self._tocar(pronto)             # do disco, na hora; não apaga
                    return
                wav = (sintetizar_gemini(texto, self.voz_gemini, self._chave_gemini())
                       if self._gemini_disponivel() and not evento.is_set() else None)
                if wav is not None and pronto:
                    self._guardar_pronto(wav, pronto)
                if wav is not None and not evento.is_set():
                    self._tocar_e_apagar(wav)
                return
            # 0) Nuvem (padrão): voz humana com sotaque brasileiro. Se a internet
            #    ou a chave falharem, cai no Kokoro (offline) — nunca fica mudo.
            if self.motor == "openai" and self._openai_disponivel():
                if self._falar_openai(texto, evento):
                    return
            # 1) Kokoro: humano E rápido, frase a frase. Se falhar, Piper.
            if self.motor in ("kokoro", "openai") and self._kokoro_disponivel():
                if self._falar_kokoro(texto, evento):
                    return
                # Kokoro falhou nesta fala → cai no Piper abaixo.
            # 2) XTTS (opcional): humano, porém lento.
            if self.motor == "xtts" and self._xtts_instalado() and not self._xtts_morto:
                wav = self._sintetizar_xtts(texto)
                if wav is not None:
                    self._tocar_e_apagar(wav)
                    return
                # XTTS falhou → cai no Piper abaixo.
            # 3) Piper (reserva universal): sintético, mas sempre disponível.
            if self._piper_daemon_instalado() and not self._piper_daemon_morto:
                self._falar_piper(texto, evento)
            elif self._piper_disponivel():
                wav = self._sintetizar_piper_direto(texto)
                self._tocar_e_apagar(wav)
        except Exception:
            pass
        finally:
            self._gerando = False

    def _falar_openai(self, texto: str, evento: threading.Event) -> bool:
        """Fala pela nuvem: gera a próxima frase enquanto a anterior toca.
        Devolve False só se NADA chegou a tocar (o chamador cai no Kokoro)."""
        frases = _frases_da_fala(texto)
        if not frases:
            return True
        chave = self._chave_openai()
        fila = queue.Queue()

        def produzir():
            try:
                for frase in frases:
                    if evento.is_set():
                        break
                    wav = sintetizar_openai(frase, self.voz_openai, self.modelo_openai,
                                            INSTRUCOES_VOZ_BR, chave, self.tempo_openai)
                    fila.put(wav)
                    if wav is None:
                        break
            finally:
                fila.put(_FIM_DA_FILA)

        threading.Thread(target=produzir, daemon=True).start()
        falou = False
        while True:
            wav = fila.get()
            if wav is _FIM_DA_FILA:
                return True
            if wav is None:
                self._openai_descansa_ate = time.monotonic() + OPENAI_DESCANSO_S
                if not falou:
                    return False
                continue
            if evento.is_set():
                try:
                    os.remove(wav)
                except Exception:
                    pass
                continue
            self._tocar_e_apagar(wav)
            falou = True

    # ---- resposta imediata ("Certo.") -------------------------------------------------
    def _dir_acuses(self) -> str:
        forcado = os.environ.get("DERVS_ACUSES_DIR")
        if forcado:
            return forcado
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "dervs", "acuses")

    def _arquivo_acuse(self, frase: str) -> str:
        """O nome muda com a voz, o modelo, a velocidade e o estilo: trocar qualquer
        um deles gera os áudios de novo em vez de tocar a voz velha."""
        chave = "|".join((self.voz_openai, self.modelo_openai, str(self.tempo_openai),
                          INSTRUCOES_VOZ_BR, frase))
        return os.path.join(self._dir_acuses(), hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16] + ".wav")

    def preparar_acuses(self, bloquear: bool = False):
        """Gera, uma única vez, os áudios das respostas imediatas (centavos). Roda em
        segundo plano; só o que falta; respeita o teto de gasto; nunca levanta."""
        def _gerar():
            try:
                if not self.ligada or self.motor != "openai" or not self._chave_openai():
                    return
                os.makedirs(self._dir_acuses(), exist_ok=True)
                for frase in ACUSES:
                    destino = self._arquivo_acuse(frase)
                    if os.path.exists(destino):
                        continue
                    if not dervs_gasto.pode_gastar()[0]:
                        return
                    wav = sintetizar_openai(frase, self.voz_openai, self.modelo_openai,
                                            INSTRUCOES_VOZ_BR, self._chave_openai(), self.tempo_openai)
                    if wav:
                        shutil.move(wav, destino)
            except Exception:
                pass
        if bloquear:
            _gerar()
        else:
            threading.Thread(target=_gerar, daemon=True).start()

    def _arquivo_pronto(self, frase: str):
        """Onde mora o áudio pronto de uma das FRASES_PRONTAS (None para qualquer outra). O nome
        muda com a voz e o modelo: trocar a voz grava de novo em vez de tocar a voz velha."""
        if frase not in FRASES_PRONTAS:
            return None
        chave = "|".join(("gemini", self.voz_gemini, GEMINI_TTS_URL, frase))
        return os.path.join(self._dir_acuses(),
                            "pronta_" + hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16] + ".wav")

    @staticmethod
    def _guardar_pronto(wav, destino):
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            temporario = destino + ".tmp"
            shutil.copyfile(wav, temporario)
            os.replace(temporario, destino)
        except OSError:
            pass

    def preparar_frases_prontas(self, bloquear: bool = False):
        """Grava, uma vez, as FRASES_PRONTAS que faltam (voz do Gemini, faixa grátis). Para no
        primeiro erro (cota 429, sem rede): tenta de novo na próxima abertura. Nunca levanta."""
        def _gerar():
            try:
                if not self.ligada or not self._gemini_disponivel():
                    return
                for frase in FRASES_PRONTAS:
                    destino = self._arquivo_pronto(frase)
                    if os.path.isfile(destino):
                        continue
                    wav = sintetizar_gemini(frase, self.voz_gemini, self._chave_gemini())
                    if wav is None:
                        return
                    self._guardar_pronto(wav, destino)
                    try:
                        os.remove(wav)
                    except OSError:
                        pass
                    time.sleep(2)                       # a faixa grátis aceita poucas por minuto
            except Exception:
                pass
        if bloquear:
            _gerar()
        else:
            threading.Thread(target=_gerar, daemon=True).start()

    def acusar_recebimento(self, bloquear: bool = False):
        """Diz "Certo." na hora. Nunca atrasa nada: se o áudio ainda não existe, fica
        quieto. Toca num player à parte, sem mexer na fila da fala de verdade."""
        def _tocar_acuse():
            try:
                if not self.ligada or self.motor != "openai":
                    return
                arquivo = self._arquivo_acuse(random.choice(ACUSES))
                if os.path.exists(arquivo):
                    criar_reprodutor(arquivo)
            except Exception:
                pass
        if bloquear:
            _tocar_acuse()
        else:
            threading.Thread(target=_tocar_acuse, daemon=True).start()

    def _tocar_e_apagar(self, wav):
        if not wav or not os.path.exists(wav) or os.path.getsize(wav) == 0:
            return
        try:
            self._tocar(wav)
        finally:
            try:
                os.remove(wav)
            except Exception:
                pass

    # ---- síntese Piper via daemon (padrão — frase a frase) ----
    def _garantir_piper_daemon(self):
        if self._piper_daemon is not None and self._piper_daemon.poll() is None:
            return
        try:
            self._piper_daemon = subprocess.Popen(
                [PIPER_PY, PIPER_DAEMON, self.modelo],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, **processos.sem_janela())
            self._piper_pronto = False
        except Exception:
            self._piper_daemon = None
            self._piper_daemon_morto = True

    def _falar_piper(self, texto: str, evento: threading.Event):
        """Consome o daemon do Piper e toca cada frase assim que ela chega."""
        for wav in self._pedir_piper(texto, evento):
            if evento.is_set():
                try:
                    os.remove(wav)
                except Exception:
                    pass
                continue
            self._tocar_e_apagar(wav)

    def _pedir_piper(self, texto: str, evento: threading.Event):
        """Gerador: manda o texto ao daemon e devolve o caminho de cada frase
        pronta, na ordem. Sempre drena a resposta até FIM/ERRO, mesmo se
        `evento` for sinalizado no meio — protege o próximo pedido."""
        with self._lock_piper:
            self._garantir_piper_daemon()
            d = self._piper_daemon
            if d is None or d.stdin is None or d.stdout is None:
                self._piper_daemon_morto = True
                return
            try:
                if not self._piper_pronto:
                    while True:
                        linha = d.stdout.readline()
                        if not linha:                # daemon morreu (ex.: numpy faltando)
                            self._piper_daemon_morto = True
                            return
                        if linha.decode("utf-8", "replace").strip() == "READY":
                            self._piper_pronto = True
                            break
                pedido = json.dumps({
                    "texto": texto, "modelo": self.modelo,
                    "length_scale": LENGTH_SCALE, "noise_w": NOISE_W,
                }) + "\n"
                d.stdin.write(pedido.encode("utf-8"))
                d.stdin.flush()
                while True:
                    linha = d.stdout.readline()
                    if not linha:
                        self._piper_daemon_morto = True
                        return
                    s = linha.decode("utf-8", "replace").strip()
                    if s == "FIM":
                        return
                    if s.startswith("ERRO"):
                        return
                    if s.startswith("WAV "):
                        yield s[4:]
            except Exception:
                self._piper_daemon_morto = True
                return

    # ---- síntese Kokoro via daemon (padrão — humana, frase a frase) ----
    def _garantir_kokoro_daemon(self):
        if self._kokoro_daemon is not None and self._kokoro_daemon.poll() is None:
            return
        try:
            self._kokoro_daemon = subprocess.Popen(
                [KOKORO_PY, KOKORO_DAEMON],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, **processos.sem_janela())
            self._kokoro_pronto = False
        except Exception:
            self._kokoro_daemon = None
            self._kokoro_morto = True

    def _falar_kokoro(self, texto: str, evento: threading.Event) -> bool:
        """Fala pelo Kokoro, tocando cada frase assim que chega. Devolve True se
        tratou a fala; False se o daemon falhou (o chamador cai no Piper)."""
        for wav in self._pedir_kokoro(texto, evento):
            if evento.is_set():
                try:
                    os.remove(wav)
                except Exception:
                    pass
                continue
            self._tocar_e_apagar(wav)
        return not self._kokoro_morto

    def _pedir_kokoro(self, texto: str, evento: threading.Event):
        """Gerador: manda o texto ao daemon do Kokoro e devolve o caminho de cada
        frase pronta, na ordem. Drena até FIM/ERRO mesmo com barge-in, para não
        contaminar o próximo pedido."""
        with self._lock_kokoro:
            self._garantir_kokoro_daemon()
            d = self._kokoro_daemon
            if d is None or d.stdin is None or d.stdout is None:
                self._kokoro_morto = True
                return
            try:
                if not self._kokoro_pronto:
                    while True:
                        linha = d.stdout.readline()
                        if not linha:                # daemon morreu na carga do modelo
                            self._kokoro_morto = True
                            return
                        s = linha.decode("utf-8", "replace").strip()
                        if s == "READY":
                            self._kokoro_pronto = True
                            break
                        if s.startswith("ERRO"):     # falhou ao carregar o modelo
                            self._kokoro_morto = True
                            return
                pedido = json.dumps({
                    "texto": texto, "voz": self.voz_kokoro,
                    "speed": self.voz_velocidade, "lang": KOKORO_LANG,
                }) + "\n"
                d.stdin.write(pedido.encode("utf-8"))
                d.stdin.flush()
                while True:
                    linha = d.stdout.readline()
                    if not linha:
                        self._kokoro_morto = True
                        return
                    s = linha.decode("utf-8", "replace").strip()
                    if s == "FIM":
                        return
                    if s.startswith("ERRO"):
                        return
                    if s.startswith("WAV "):
                        yield s[4:]
            except Exception:
                self._kokoro_morto = True
                return

    # ---- síntese Piper direta (reserva — sem daemon, um processo por fala) ----
    def _sintetizar_piper_direto(self, texto):
        tmp = tempfile.NamedTemporaryFile(prefix="dervs_voz_", suffix=".wav", delete=False)
        wav = tmp.name; tmp.close()
        with self._lock:
            self._synth = subprocess.Popen(
                [PIPER_PY, "-m", "piper", "-m", self.modelo,
                 "--length-scale", str(LENGTH_SCALE), "--noise-w-scale", str(NOISE_W),
                 "--sentence-silence", SILENCIO_FRASE, "-f", wav],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, **processos.sem_janela())
            synth = self._synth
        if synth is None:
            return None
        synth.communicate(input=texto.encode("utf-8"))
        return wav if synth.returncode == 0 else None

    # ---- síntese XTTS (humana, via daemon) ----
    def _garantir_daemon(self):
        if self._daemon is not None and self._daemon.poll() is None:
            return
        try:
            self._daemon = subprocess.Popen(
                [XTTS_PY, XTTS_DAEMON],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, **processos.sem_janela())
            self._xtts_ready = False
        except Exception:
            self._daemon = None
            self._xtts_morto = True

    def _sintetizar_xtts(self, texto):
        with self._lock:
            self._garantir_daemon()
            d = self._daemon
            if d is None or d.stdin is None or d.stdout is None:
                self._xtts_morto = True
                return None
            try:
                # espera o modelo carregar (consome linhas até READY) — só na 1a vez
                if not self._xtts_ready:
                    while True:
                        linha = d.stdout.readline()
                        if not linha:                # daemon morreu (ex.: torch faltando)
                            self._xtts_morto = True
                            return None
                        if linha.decode("utf-8", "replace").strip() == "READY":
                            self._xtts_ready = True
                            break
                # pede a fala
                d.stdin.write((json.dumps(texto) + "\n").encode("utf-8"))
                d.stdin.flush()
                while True:
                    linha = d.stdout.readline()
                    if not linha:
                        self._xtts_morto = True
                        return None
                    s = linha.decode("utf-8", "replace").strip()
                    if s.startswith("WAV "):
                        return s[4:]
                    if s == "ERRO":
                        return None
            except Exception:
                self._xtts_morto = True
                return None

    # ---- tocar ----
    def _tocar(self, wav):
        with self._lock:
            self._play = criar_reprodutor(wav)
            play = self._play
        if play is None:
            return
        if self.ao_nivel is not None:
            self._acompanhar_nivel(wav, play)
        play.wait()

    def _acompanhar_nivel(self, wav, play):
        """Sobe uma thread que alimenta `self.ao_nivel` com o nível da fala
        enquanto `play` toca `wav`, parando assim que `play.poll()` deixar de
        ser None (fim natural ou barge-in via calar()). Envelope vazio (wav
        estranho) não sobe thread nenhuma — comportamento de hoje intacto."""
        niveis = dervs_nivel.envelope_do_wav(wav, passo_ms=30)
        if not niveis:
            return
        ao_nivel = self.ao_nivel
        passo_s = 30 / 1000.0

        def rodar():
            try:
                inicio = time.monotonic()
                for i, nivel in enumerate(niveis):
                    if play.poll() is not None:
                        break
                    alvo = inicio + (i + 1) * passo_s
                    espera = alvo - time.monotonic()
                    if espera > 0:
                        time.sleep(espera)
                    if play.poll() is not None:
                        break
                    ao_nivel(nivel)
            except Exception as erro:
                sys.stderr.write(f"dervs_tts: erro ao acompanhar o nível da fala: {erro}\n")
            finally:
                try:
                    ao_nivel(0.0)
                except Exception as erro:
                    sys.stderr.write(f"dervs_tts: erro ao zerar o nível da fala: {erro}\n")

        threading.Thread(target=rodar, daemon=True).start()


if __name__ == "__main__":
    import sys, time
    motor = sys.argv[2] if len(sys.argv) > 2 else MOTOR_PADRAO
    v = Voz(ligada=True, motor=motor)
    if not v.disponivel():
        print("voz indisponível"); sys.exit(1)
    frase = sys.argv[1] if len(sys.argv) > 1 else "Olá, eu sou o DERVS. Estou aqui pra te ajudar."
    print(f"motor={motor} — falando: {frase!r}")
    t = time.time()
    v._falar_bloqueante(frase)
    print(f"levou {time.time()-t:.1f}s")
    v.desligar()
