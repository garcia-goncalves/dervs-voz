#!/usr/bin/env python3
"""DERVS — a voz (falar em português, offline).

Dois motores:
  - "piper" → PADRÃO. Voz sintética, mas rápida: um daemon (dervs_piper_daemon.py,
              na venv tts-venv) carrega o modelo .onnx uma vez só e fica vivo; cada
              fala paga só o tempo de síntese (dezenas de ms por frase), não o
              recarregamento do modelo (~0,7 s). O texto é falado FRASE POR FRASE —
              a primeira frase começa a tocar enquanto o daemon ainda gera a
              segunda — para o "tempo até o primeiro som" ficar bem abaixo de 1 s.
  - "xtts"  → voz humana (Coqui XTTS v2), via daemon próprio (dervs_tts_daemon.py,
              na venv xtts-venv). Muito mais natural, porém ~7 s por frase — o dono
              decidiu que isso é lento demais para conversar, então deixou de ser o
              padrão. Continua disponível para quem preferir naturalidade a velocidade.

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
import json

import dervs_config
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

# Motor padrão: Kokoro — humano E rápido no CPU (~0,6 s até o 1º som quente),
# o meio-termo que faltava entre Piper (robótico) e XTTS (lento). Cai no Piper
# sozinho se o Kokoro não estiver instalado/falhar.
MOTOR_PADRAO = "kokoro"


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
        self.voz_velocidade = (voz_velocidade if voz_velocidade is not None
                                else dervs_config.carregar()["voz_velocidade"])
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

    def _kokoro_disponivel(self):
        return self._kokoro_instalado() and not self._kokoro_morto

    def disponivel(self) -> bool:
        """Tem como falar por ALGUM motor?"""
        return (self._kokoro_disponivel() or self._piper_disponivel()
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
        if not texto or not self.ligada or not self.disponivel():
            return
        self.calar()
        threading.Thread(target=self._falar_bloqueante, args=(texto,), daemon=True).start()

    def _falar_bloqueante(self, texto: str):
        evento = threading.Event()
        self._evento_atual = evento
        self._gerando = True
        try:
            # 1) Kokoro (padrão): humano E rápido, frase a frase. Se falhar, Piper.
            if self.motor == "kokoro" and self._kokoro_disponivel():
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
        play.wait()


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
