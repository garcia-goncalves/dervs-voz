#!/usr/bin/env python3
"""Grimoire — a voz (falar em português, offline).

Dois motores:
  - "piper" → PADRÃO. Voz sintética, mas rápida: um daemon (grimoire_piper_daemon.py,
              na venv tts-venv) carrega o modelo .onnx uma vez só e fica vivo; cada
              fala paga só o tempo de síntese (dezenas de ms por frase), não o
              recarregamento do modelo (~0,7 s). O texto é falado FRASE POR FRASE —
              a primeira frase começa a tocar enquanto o daemon ainda gera a
              segunda — para o "tempo até o primeiro som" ficar bem abaixo de 1 s.
  - "xtts"  → voz humana (Coqui XTTS v2), via daemon próprio (grimoire_tts_daemon.py,
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
import tempfile
import threading
import json

HOME = os.path.expanduser("~")
VOICE_DIR = f"{HOME}/voice"

# --- Piper (rápido, padrão) ---
PIPER_PY = f"{VOICE_DIR}/tts-venv/bin/python"
PIPER_DAEMON = f"{VOICE_DIR}/grimoire_piper_daemon.py"
VOZES_DIR = f"{VOICE_DIR}/piper-voices"
VOZ_PADRAO = "jeff"             # faber / cadu / jeff — ver escolha no relatório da tarefa
# length_scale < 1 fala mais rápido (1.0 = padrão do modelo). 0.95 deixa a
# conversa mais ágil sem soar robótico (testado até 0.85 antes de comprometer
# a naturalidade das sílabas).
LENGTH_SCALE = 0.95
NOISE_W = 0.9
SILENCIO_FRASE = "0.35"          # só usado no modo de reserva (sem daemon)

# --- Kokoro (humano E rápido, padrão novo) ---
KOKORO_PY = f"{VOICE_DIR}/kokoro-venv/bin/python"
KOKORO_DAEMON = f"{VOICE_DIR}/grimoire_kokoro_daemon.py"
KOKORO_MODELO = f"{VOICE_DIR}/kokoro-model/kokoro-v1.0.onnx"
VOZ_KOKORO_PADRAO = "pm_santa"   # masculina grave (feiticeiro)
KOKORO_SPEED = 1.15              # 1.0 = natural; 1.15 = mais ágil, ainda claro (pedido do dono)
KOKORO_LANG = "pt-br"

# --- XTTS (humano, opcional) ---
XTTS_PY = f"{VOICE_DIR}/xtts-venv/bin/python"
XTTS_DAEMON = f"{VOICE_DIR}/grimoire_tts_daemon.py"

# Motor padrão: Kokoro — humano E rápido no CPU (~0,6 s até o 1º som quente),
# o meio-termo que faltava entre Piper (robótico) e XTTS (lento). Cai no Piper
# sozinho se o Kokoro não estiver instalado/falhar.
MOTOR_PADRAO = "kokoro"


def caminho_voz(nome: str) -> str:
    return f"{VOZES_DIR}/pt_BR-{nome}-medium.onnx"


MODELO_VOZ = caminho_voz(VOZ_PADRAO)   # compatibilidade


def _player():
    for p in ("pw-play", "paplay", "aplay"):
        if shutil.which(p):
            return p
    return None


class Voz:
    """Fala frases, uma de cada vez. Ligada/desligada por um interruptor."""

    def __init__(self, ligada: bool = False, motor: str = MOTOR_PADRAO,
                 voz: str = VOZ_PADRAO, voz_kokoro: str = VOZ_KOKORO_PADRAO):
        self.ligada = ligada
        self.motor = motor
        self.modelo = caminho_voz(voz)    # voz do Piper
        self.voz_kokoro = voz_kokoro      # voz do Kokoro
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
                and _player() is not None)

    def _piper_daemon_instalado(self):
        return os.path.exists(PIPER_DAEMON) and self._piper_disponivel()

    def _xtts_instalado(self):
        return os.path.exists(XTTS_PY) and os.path.exists(XTTS_DAEMON)

    def _kokoro_instalado(self):
        return (os.path.exists(KOKORO_PY) and os.path.exists(KOKORO_DAEMON)
                and os.path.exists(KOKORO_MODELO) and _player() is not None)

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
        """Encerra tudo, inclusive os daemons (ao fechar o app)."""
        self.calar()
        with self._lock:
            for nome in ("_daemon", "_piper_daemon", "_kokoro_daemon"):
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
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
                    "speed": KOKORO_SPEED, "lang": KOKORO_LANG,
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
        tmp = tempfile.NamedTemporaryFile(prefix="grimoire_voz_", suffix=".wav", delete=False)
        wav = tmp.name; tmp.close()
        with self._lock:
            self._synth = subprocess.Popen(
                [PIPER_PY, "-m", "piper", "-m", self.modelo,
                 "--length-scale", str(LENGTH_SCALE), "--noise-w-scale", str(NOISE_W),
                 "--sentence-silence", SILENCIO_FRASE, "-f", wav],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
        player = _player()
        if not player:
            return
        with self._lock:
            self._play = subprocess.Popen(
                [player, wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play = self._play
        play.wait()


if __name__ == "__main__":
    import sys, time
    motor = sys.argv[2] if len(sys.argv) > 2 else MOTOR_PADRAO
    v = Voz(ligada=True, motor=motor)
    if not v.disponivel():
        print("voz indisponível"); sys.exit(1)
    frase = sys.argv[1] if len(sys.argv) > 1 else "Olá, eu sou o Grimoire. Estou aqui pra te ajudar."
    print(f"motor={motor} — falando: {frase!r}")
    t = time.time()
    v._falar_bloqueante(frase)
    print(f"levou {time.time()-t:.1f}s")
    v.desligar()
