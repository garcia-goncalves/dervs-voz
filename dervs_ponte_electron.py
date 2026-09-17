#!/usr/bin/env python3
"""DERVS — a ponte com a cara nova: o Electron, subido como processo filho.

O Python continua dono de tudo (microfone, cérebro, trilhos de risco); o
Electron só desenha. A conversa entre os dois é a mais simples que resolve:
uma mensagem por linha, JSON UTF-8, terminada em quebra de linha — o mesmo
espírito de protocolo dos daemons (`dervs_stt_daemon.py`, cabeçalho) e das três
escutas do `QProcess` do STT (`dervs.py`, saída/erro/morte): sem as três,
volta o "DERVS surdo e calado".

Python fala com o Electron pelo `stdin` do filho; o Electron fala de volta
pelo `stdout`. O `stderr` do filho é lido aqui e reescrito no `sys.stderr`
deste processo, com o prefixo `electron:` — falha nunca é engolida.

Verbos Python → Electron (só estes cinco):
  estado  {"valor", "texto", "apoio"} — só quando o estado muda.
  volume  {"valor"}                   — 0.0 a 1.0, estrangulado (ver abaixo).
  fala    {"papel", "texto"}          — uma linha nova de conversa.
  plano   {"passos", "nivel", "pergunta"} — lista vazia limpa o cartão.
  mostrar {}                          — traz a janela para frente.

Verbos Electron → Python (o mínimo que o comportamento de hoje já faz):
  pronto  — a janela carregou. Antes disso, `estado` e `volume` ficam
            guardados (só o último de cada) e são despachados quando ele
            chega — o mesmo padrão do `READY` dos daemons.
  sair    — "Sair do DERVS" da bandeja.
  plano   {"resposta": "confirmar" | "cancelar"} — botão do cartão de plano.

Regras duras (valem para os dois lados da ponte, e este arquivo cumpre a
parte do Python):
  - linha que não é JSON válido, verbo desconhecido ou campo faltando é
    ignorada e vira uma linha no stderr — nunca derruba o processo;
  - linha maior que 64 KiB é descartada (mesmo espírito do `_LIMITE_LINHA`
    de `dervs_instancia.py`); texto de conversa é cortado a 4000 caracteres;
  - `volume` é estrangulado a no máximo 20 mensagens por segundo (50 ms),
    arredondado em 2 casas, e valor repetido não é reenviado — a `Escuta`
    produz ~33 quadros por segundo (`dervs_listen.py`), e sem estrangular a
    régua de CPU é queimada só com JSON;
  - a escrita é thread-safe: quem manda mensagem são a thread da tela, a
    thread do Qt vinda da `Escuta` e a thread de fala do `dervs_tts` — três
    donos do mesmo `stdin`;
  - o filho sobe com `CREATE_NO_WINDOW` no Windows — sem isso volta a "janela
    preta" já corrigida.
"""
import json
import os
import subprocess
import sys
import threading
import time

WINDOWS = sys.platform == "win32"

_LIMITE_LINHA = 64 * 1024      # 64 KiB — linha maior que isso é descartada
_LIMITE_TEXTO = 4000           # texto livre é cortado antes de ser enviado
_ESTRANGULA_SEG = 0.05         # 50 ms = no máximo 20 mensagens de volume/s

_EXECUTAVEL_PADRAO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "electron", "node_modules", "electron", "dist", "electron.exe")


def _cortar(texto: str) -> str:
    """Texto livre nunca atravessa a ponte sem limite — é conteúdo hostil
    por definição (transcrição, resposta do cérebro, saída de comando)."""
    return (texto or "")[:_LIMITE_TEXTO]


class PonteElectron:
    """Sobe o Electron como filho e fala com ele em linhas de JSON.

    `ao_sair` é chamado quando o filho pede para sair (verbo `sair`) ou
    quando ele morre sozinho (o `stdout` fecha). `ao_plano` é chamado com
    "confirmar" ou "cancelar" quando o cartão de plano responde. `ao_pronto`
    é chamado quando a janela terminou de carregar.
    """

    def __init__(self, ao_sair, ao_plano, ao_pronto):
        self._ao_sair = ao_sair
        self._ao_plano = ao_plano
        self._ao_pronto = ao_pronto
        self._processo = None
        self._fechado = False
        self._lock = threading.RLock()
        self._pronto = False
        self._ultimo_estado_guardado = None
        self._ultimo_volume_guardado = None
        self._ultimo_volume_enviado = None
        self._ultimo_envio_volume = 0.0
        self._sair_notificado = False

    # ---- subir o filho -----------------------------------------------

    def abrir(self, caminho_app, executavel=None):
        """Sobe o Electron apontando para `caminho_app` (a pasta com o
        `package.json`/`main.js`). Levanta `FileNotFoundError` se o Electron
        não estiver instalado — nunca sobe um DERVS invisível calado."""
        executavel = executavel or _EXECUTAVEL_PADRAO
        if not os.path.isfile(executavel):
            raise FileNotFoundError(
                f"o Electron não está instalado ({executavel}) — rode "
                f"'npm install' dentro da pasta 'electron/' e tente de novo")
        kwargs = {}
        if WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        processo = subprocess.Popen(
            [executavel, caminho_app],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **kwargs)
        self._iniciar(processo)

    def _iniciar(self, processo):
        """Liga as leituras de `stdout` e `stderr` num processo já subido.

        Separado de `abrir()` de propósito: os testes usam um dublê de
        processo aqui (um objeto com `stdin`/`stdout` de pipe), sem precisar
        do Electron instalado.
        """
        self._processo = processo
        threading.Thread(target=self._ler_saida, daemon=True).start()
        threading.Thread(target=self._ler_erro, daemon=True).start()

    # ---- ler o que volta do Electron ----------------------------------

    def _ler_saida(self):
        """O `stdout` fechar é o filho morrendo — o DERVS não pode ficar sem
        cara em silêncio."""
        processo = self._processo
        try:
            for linha in processo.stdout:
                self._processar_linha(linha)
        except (OSError, ValueError):
            pass
        finally:
            self._chamar_ao_sair()

    def _ler_erro(self):
        processo = self._processo
        try:
            for linha in processo.stderr:
                texto = linha.decode("utf-8", "replace")
                sys.stderr.write("electron: " + texto)
                sys.stderr.flush()
        except (OSError, ValueError):
            pass

    def _processar_linha(self, linha: bytes):
        if len(linha) > _LIMITE_LINHA:
            sys.stderr.write("ponte: linha do Electron maior que 64 KiB, descartada\n")
            return
        try:
            texto = linha.decode("utf-8").strip()
            if not texto:
                return
            dado = json.loads(texto)
            verbo = dado["verbo"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            sys.stderr.write(f"ponte: linha inválida vinda do Electron: {linha!r}\n")
            return
        if verbo == "pronto":
            self._despachar_guardado()
        elif verbo == "sair":
            self._chamar_ao_sair()
        elif verbo == "plano":
            resposta = dado.get("resposta")
            if resposta not in ("confirmar", "cancelar"):
                sys.stderr.write(f"ponte: resposta de plano desconhecida: {dado!r}\n")
                return
            self._chamar(self._ao_plano, resposta)
        else:
            sys.stderr.write(f"ponte: verbo desconhecido vindo do Electron: {verbo!r}\n")

    def _chamar(self, callback, *args):
        """Callback do dono explodir não pode derrubar a ponte."""
        try:
            callback(*args)
        except Exception as e:
            sys.stderr.write(f"ponte: callback falhou: {e}\n")

    def _chamar_ao_sair(self):
        """`ao_sair` é o gatilho de encerramento do DERVS — no máximo uma vez
        por instância, mesmo que o verbo `sair` chegue e em seguida o
        `stdout` feche (o mesmo evento de saída, contado duas vezes)."""
        with self._lock:
            if self._sair_notificado:
                return
            self._sair_notificado = True
        self._chamar(self._ao_sair)

    def _despachar_guardado(self):
        with self._lock:
            self._pronto = True
            estado = self._ultimo_estado_guardado
            volume = self._ultimo_volume_guardado
        if estado is not None:
            self._escrever(estado)
        if volume is not None:
            self._escrever(volume)
        self._chamar(self._ao_pronto)

    # ---- mandar mensagem para o Electron -------------------------------

    def enviar_estado(self, valor, texto="", apoio=""):
        msg = {"verbo": "estado", "valor": valor, "texto": _cortar(texto),
               "apoio": _cortar(apoio)}
        with self._lock:
            if not self._pronto:
                self._ultimo_estado_guardado = msg
                return
        self._escrever(msg)

    def enviar_volume(self, x):
        try:
            x = float(x)
        except (TypeError, ValueError):
            return
        x = max(0.0, min(1.0, x))
        valor = round(x, 2)
        msg = {"verbo": "volume", "valor": valor}
        with self._lock:
            if not self._pronto:
                self._ultimo_volume_guardado = msg
                return
            if valor == self._ultimo_volume_enviado:
                return
            agora = time.monotonic()
            if agora - self._ultimo_envio_volume < _ESTRANGULA_SEG:
                return
            self._ultimo_volume_enviado = valor
            self._ultimo_envio_volume = agora
        self._escrever(msg)

    def enviar_fala(self, papel, texto):
        self._escrever({"verbo": "fala", "papel": papel, "texto": _cortar(texto)})

    def enviar_plano(self, passos, nivel, pergunta):
        self._escrever({"verbo": "plano", "passos": passos, "nivel": nivel,
                         "pergunta": _cortar(pergunta)})

    def enviar_mostrar(self):
        self._escrever({"verbo": "mostrar"})

    def _escrever(self, msg: dict):
        linha = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            processo = self._processo
            if processo is None or processo.stdin is None:
                return
            try:
                processo.stdin.write(linha)
                processo.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as e:
                sys.stderr.write(f"ponte: falha ao escrever para o Electron: {e}\n")

    # ---- encerrar -------------------------------------------------------

    def fechar(self, espera: float = 3.0):
        """Fecha o `stdin`, espera, `terminate()`, espera de novo, `kill()`.
        Seguro chamar duas vezes."""
        with self._lock:
            if self._fechado:
                return
            self._fechado = True
            processo = self._processo
            if processo is not None:
                try:
                    if processo.stdin is not None:
                        processo.stdin.close()
                except (OSError, ValueError):
                    pass
        if processo is None:
            return
        try:
            processo.wait(timeout=espera)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            processo.terminate()
            processo.wait(timeout=espera)
            return
        except (subprocess.TimeoutExpired, OSError):
            pass
        try:
            processo.kill()
        except OSError:
            pass
