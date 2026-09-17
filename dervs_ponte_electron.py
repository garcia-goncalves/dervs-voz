#!/usr/bin/env python3
"""DERVS — a ponte com a cara nova: o Electron, subido como processo filho.

O Python continua dono de tudo (microfone, cérebro, trilhos de risco); o
Electron só desenha. A conversa entre os dois é a mais simples que resolve:
uma mensagem por linha, JSON UTF-8, terminada em quebra de linha — o mesmo
espírito de protocolo dos daemons (`dervs_stt_daemon.py`, cabeçalho) e das três
escutas do `QProcess` do STT (`dervs.py`, saída/erro/morte): sem as três,
volta o "DERVS surdo e calado".

Electron fala com o Python pelo `stdout` do filho — essa direção funciona
sem problema. Python fala com o Electron por um SOQUETE TCP local (só
`127.0.0.1`, porta escolhida pelo sistema, passada ao Electron como
argumento de linha de comando), **não** pelo `stdin` do filho.

Por quê: um app Electron (sem console, como todo app gráfico do Windows)
recebe um "fim de stdin" FALSO quase na hora, mesmo com o processo pai
vivo e escrevendo — é uma limitação do Chromium/Electron no Windows, não
um jeito errado de escrever. Confirmado em bancada em 17/09/2026: um
Electron mínimo, sem nenhuma linha do DERVS, reproduz o mesmo "fim falso"
ao ler `stdin` herdado de um `subprocess.Popen` do Python; rodando o
MESMO binário como Node puro (`ELECTRON_RUN_AS_NODE=1`, que tem console)
o problema some. Depois do "fim falso", o `stdin` também para de entregar
dado novo — não dá para só ignorar o evento e seguir lendo. Daí o soquete:
mesmo padrão (`127.0.0.1`, nunca a rede) já comprovado em
`dervs_instancia.py` para a trava de instância única.

O `stderr` do filho é lido aqui e reescrito no `sys.stderr` deste processo,
com o prefixo `electron:` — falha nunca é engolida.

Verbos Python → Electron (só estes cinco):
  estado  {"valor", "texto", "apoio"} — só quando o estado muda.
  volume  {"valor"}                   — 0.0 a 1.0, estrangulado (ver abaixo).
  fala    {"papel", "texto"}          — uma linha nova de conversa.
  plano   {"passos", "nivel", "pergunta", "cartao_id"} — lista vazia limpa
            o cartão. Cada passo em `passos` traz `rotulo`/`nivel` (contrato
            original); um cartão de PASSO ÚNICO (risco de um passo
            destrutivo dentro do plano, não o plano inteiro) também traz,
            por extensão do protocolo: `comando` (texto do comando),
            `precisa_autorizacao` (bool — toca rede de fora ou lê arquivo
            de segredo), `texto_autorizacao` (a frase certa para a caixa) e
            `dupla_confirmacao` (bool — exige dois "confirmar" seguidos).
            `cartao_id` é extensão do protocolo (correção de concorrência):
            identifica de forma única o cartão que espera resposta — sem
            ele, duas mensagens de resposta em trânsito não dá para saber a
            qual cartão cada uma se refere (ver `_confirmar_do_electron` em
            `dervs_electron.py`). Ausente/`None` para cartões que não
            esperam resposta (ex.: a lista vazia que limpa a tela).
            Consumidor que só lê `rotulo`/`nivel` continua funcionando sem
            mudar nada.
  mostrar {}                          — traz a janela para frente.

Verbos Electron → Python (o mínimo que o comportamento de hoje já faz):
  pronto  — a janela carregou. Antes disso, `estado` e `volume` ficam
            guardados (só o último de cada) e são despachados quando ele
            chega — o mesmo padrão do `READY` dos daemons.
  sair    — "Sair do DERVS" da bandeja.
  plano   {"resposta": "confirmar" | "cancelar", "autorizado": bool,
            "cartao_id"} — botão do cartão de plano. `autorizado` é
            extensão do protocolo: reflete a caixa "Tenho autorização"
            marcada ou não quando o cartão em tela é um passo com
            `precisa_autorizacao`; qualquer valor que não seja o booleano
            `True` vira `False` (checagem estrita — string "false" ou
            outro valor truthy do JSON não destrava nada). `cartao_id` é
            extensão do protocolo: ecoa o id do cartão a que esta resposta
            se refere — quem decide se ainda vale é `dervs_electron.py`.

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
import socket
import subprocess
import sys
import threading
import time

WINDOWS = sys.platform == "win32"

_LIMITE_LINHA = 64 * 1024      # 64 KiB — linha maior que isso é descartada
_LIMITE_TEXTO = 4000           # texto livre é cortado antes de ser enviado
_LIMITE_PLANO = 60000          # caracteres — teto abaixo de _LIMITE_LINHA,
                                # para sobrar folga para o resto do JSON
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
        """`ao_plano` é chamado como `ao_plano(resposta, autorizado, cartao_id)`."""
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
        self._servidor = None       # soquete que escuta a conexão do Electron
        self._conexao = None        # soquete aceito, já conversando com o Electron
        self._canal_saida = None    # onde `_escrever` escreve de verdade
                                     # (o objeto do soquete, via makefile) —
                                     # `None` nos testes com dublê, que
                                     # continuam escrevendo em `processo.stdin`

    # ---- subir o filho -----------------------------------------------

    def abrir(self, caminho_app, executavel=None):
        """Sobe o Electron apontando para `caminho_app` (a pasta com o
        `package.json`/`main.js`). Levanta `FileNotFoundError` se o Electron
        não estiver instalado — nunca sobe um DERVS invisível calado.

        Antes de subir o filho, abre o soquete de escuta (só `127.0.0.1`)
        que vai carregar a direção Python → Electron (ver o cabeçalho do
        arquivo para o porquê de não ser o `stdin`) e passa a porta como
        último argumento de linha de comando."""
        executavel = executavel or _EXECUTAVEL_PADRAO
        if not os.path.isfile(executavel):
            raise FileNotFoundError(
                f"o Electron não está instalado ({executavel}) — rode "
                f"'npm install' dentro da pasta 'electron/' e tente de novo")
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        porta = servidor.getsockname()[1]
        self._servidor = servidor
        threading.Thread(target=self._aceitar_conexao, daemon=True).start()
        kwargs = {}
        if WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        processo = subprocess.Popen(
            [executavel, caminho_app, str(porta)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **kwargs)
        self._iniciar(processo)

    def _aceitar_conexao(self):
        """Espera o Electron conectar no soquete de escuta.

        15 s é folgado de propósito: o Electron só conecta depois de subir o
        runtime do Chromium, que em máquina carregada pode não ser instantâneo.
        Endereço de origem é conferido por segurança em profundidade — o
        soquete já só escuta em `127.0.0.1`, mas nunca custa checar de novo
        quem está do outro lado antes de tratar a conexão como o Electron."""
        servidor = self._servidor
        try:
            servidor.settimeout(15.0)
            conexao, endereco = servidor.accept()
        except OSError:
            return
        if endereco[0] != "127.0.0.1":
            sys.stderr.write(f"ponte: conexão recusada de {endereco!r} (não é loopback)\n")
            conexao.close()
            return
        canal = conexao.makefile("wb")
        with self._lock:
            if self._fechado:
                canal.close()
                conexao.close()
                return
            self._conexao = conexao
            self._canal_saida = canal

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
            # `autorizado` é extensão do protocolo (ver cabeçalho, verbo
            # `plano` Electron → Python): a caixa "Tenho autorização"
            # marcada ou não. Checagem ESTRITA — só o booleano `True` de
            # verdade destrava; `bool("false")` é `True` em Python, então
            # qualquer outro valor truthy do JSON (string, lista não-vazia)
            # não pode passar por essa porta.
            autorizado = dado.get("autorizado") is True
            # `cartao_id` é extensão do protocolo (correção de concorrência,
            # ver cabeçalho): identifica a qual cartão esta resposta se
            # refere. Repassado como veio (string ou número) — quem decide
            # se ainda vale é `dervs_electron.py`.
            cartao_id = dado.get("cartao_id")
            self._chamar(self._ao_plano, resposta, autorizado, cartao_id)
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

    def enviar_plano(self, passos, nivel, pergunta, cartao_id=None):
        msg = {"verbo": "plano", "passos": list(passos), "nivel": nivel,
               "pergunta": _cortar(pergunta)}
        if cartao_id is not None:
            msg["cartao_id"] = cartao_id
        # Teto de tamanho: sem isto, um plano grande o bastante estoura o
        # `_LIMITE_LINHA` de 64 KiB (linha inteira descartada do lado do
        # Electron, ver `_processar_linha`), reintroduzindo por outra porta
        # o mesmo sintoma "cartão nunca aparece" que a `_cortar` de `pergunta`
        # já resolve para o texto livre. Corta a lista de passos, mantendo
        # os primeiros que couberem — nunca deixa a linha estourar em
        # silêncio sem alternativa nenhuma chegando à tela.
        total_original = len(msg["passos"])
        while msg["passos"] and len(json.dumps(msg, ensure_ascii=False)) > _LIMITE_PLANO:
            msg["passos"].pop()
        if len(msg["passos"]) < total_original:
            sys.stderr.write(
                f"ponte: plano com {total_original} passos estourava "
                f"{_LIMITE_PLANO} caracteres — cortado para "
                f"{len(msg['passos'])} passo(s)\n")
        self._escrever(msg)

    def enviar_mostrar(self):
        self._escrever({"verbo": "mostrar"})

    def _escrever(self, msg: dict):
        linha = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            # Caminho real: o soquete aceito de `_aceitar_conexao`. Caminho
            # de teste: nenhum soquete foi aberto (ninguém chamou `abrir()`
            # de verdade), então cai no `processo.stdin` do dublê — é assim
            # que a suíte inteira de testes desta ponte continua funcionando
            # sem precisar subir soquete nenhum.
            canal = self._canal_saida
            if canal is None:
                processo = self._processo
                canal = processo.stdin if processo is not None else None
            if canal is None:
                return
            try:
                canal.write(linha)
                canal.flush()
            except (BrokenPipeError, OSError, ValueError) as e:
                sys.stderr.write(f"ponte: falha ao escrever para o Electron: {e}\n")

    # ---- encerrar -------------------------------------------------------

    def fechar(self, espera: float = 3.0):
        """Fecha o canal de escrita (soquete ou `stdin` do dublê), o soquete
        de escuta, espera, `terminate()`, espera de novo, `kill()`.
        Seguro chamar duas vezes."""
        with self._lock:
            if self._fechado:
                return
            self._fechado = True
            processo = self._processo
            canal = self._canal_saida
            conexao = self._conexao
            servidor = self._servidor
            if canal is not None:
                try:
                    canal.close()
                except (OSError, ValueError):
                    pass
            if conexao is not None:
                try:
                    conexao.close()
                except OSError:
                    pass
            if servidor is not None:
                try:
                    servidor.close()
                except OSError:
                    pass
            if canal is None and processo is not None:
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
