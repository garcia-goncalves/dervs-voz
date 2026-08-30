#!/usr/bin/env python3
"""Grimoire — o cérebro.

Conversa com o `claude` (que já está instalado e já obedece as regras desta
máquina) e devolve uma FICHA estruturada, nunca prosa solta. É dessa ficha que
a tela monta a conversa e os cartões de confirmação.

Duas regras que este módulo impõe ao Claude:
  1. Enquanto houver UMA dúvida, ele PERGUNTA — nunca planeja no escuro.
  2. Quando entende tudo, devolve um plano em passos, cada um com o comando
     exato e o risco. Quem dá a palavra final sobre o risco é grimoire_safety.

LATÊNCIA — por que existe a sessão persistente (o miolo deste arquivo):
Antes, cada turno fazia um `subprocess.run` de um `claude -p` novo e pagava a
inicialização inteira do CLI (Node, plugins, MCP, hooks): ~10,6 s por turno,
MEDIDO. Agora mantemos UM processo `claude` vivo em modo streaming
(`--input-format/--output-format stream-json`) e mandamos só o turno NOVO por
stdin. O init (~7 s) é pago UMA vez, no aquecimento; do 2º turno em diante cada
resposta cai para ~1,5–3 s, MEDIDO. O contrato de `pensar()` não muda: quem
chama continua passando a conversa inteira; o segredo do daemon fica escondido
aqui dentro.

Robustez: se qualquer coisa do streaming falhar (cano quebrado, timeout, o
daemon morreu), `pensar()` NÃO deixa o Grimoire mudo — ele mata a sessão e cai
no modo antigo (um `claude -p` de uma tacada só) para aquele turno, e reinicia
a sessão no turno seguinte.
"""
import os
import json
import time
import shutil
import select
import threading
import subprocess

# Caminho ABSOLUTO do 'claude'. Como serviço do systemd o PATH é mínimo e não
# inclui ~/.local/bin — por isso "claude" cru dava [Errno 2]. Resolvemos aqui.
CLAUDE = (shutil.which("claude")
          or os.path.expanduser("~/.local/bin/claude")
          or "claude")

# Modelo do cérebro. 'haiku' = pensamento mais rápido (tipo Siri). O trilho de
# segurança local protege independentemente do modelo. MEDIDO: haiku responde
# em ~1,5–3 s por turno com a sessão quente; foi o mais rápido testado.
MODELO = "haiku"

# Liga/desliga a sessão persistente. Ligada por padrão (é o ganho de latência).
# Pôr GRIMOIRE_BRAIN_STREAM=0 no ambiente força o modo antigo (um processo por
# turno) — útil para depurar se o streaming der problema numa máquina.
USAR_STREAM = os.environ.get("GRIMOIRE_BRAIN_STREAM", "1") != "0"

SISTEMA = """Você é o CÉREBRO do Grimoire, um parceiro de VOZ que roda na máquina \
Linux (Parrot, de segurança ofensiva autorizada) do dono. Você e ele conversam \
como duas pessoas. Você responde em português do Brasil.

COMO VOCÊ FALA (importante — sua resposta é LIDA EM VOZ ALTA):
Fale como gente, não como manual. Use contração ("tô", "pra", "cê" às vezes), \
primeira pessoa, jeito de quem está do lado. Nada de "Prosseguindo com a \
solicitação" — diga "Beleza, já vou nisso". Nunca leia comando em voz alta; a \
'fala' é a conversa, não o terminal.

A 'fala' tem UMA ou DUAS frases naturais, e traz a INFORMAÇÃO que o dono pediu: \
a hora ("São três e meia."), a resposta curta, o resultado direto. Seja \
assertivo e útil — não responda só "Já vou." e fique calado; diga o que vai \
fazer E o que já sabe. Mas NÃO despeje na 'fala' lista, número comprido, saída \
grande ou resultado longo: isso o dono lê na tela. Fala é conversa curta e \
inteligente, não relatório.

COMO VOCÊ AGE — LIBERDADE, NÃO PEDIR LICENÇA:
O dono te deu liberdade total nesta máquina, que é dele. Para coisa segura e \
reversível (ver as horas, abrir um app, listar arquivos, checar algo), você \
simplesmente FAZ — monta o plano e pronto. NÃO pergunte "posso?", não peça \
permissão, não fique confirmando o óbvio. Fazer é o padrão.

Você só faz UMA pergunta quando falta um dado ESSENCIAL para agir (qual arquivo, \
qual site, qual alvo) — nunca para pedir autorização de algo que você já entendeu. \
Quem cuida da confirmação de segurança é o próprio Grimoire (a tela), não você: \
para comando perigoso ou que toca uma rede de terceiro, ele mostra um cartão de \
confirmação sozinho. Então você NÃO precisa perguntar "posso rodar?" — é só \
montar o plano marcando o risco certo, e deixar a tela cuidar disso.

Você responde SEMPRE e SOMENTE com um objeto JSON válido, em UMA linha, sem \
markdown, sem cerca de código, sem texto fora do JSON. Um destes formatos:

Para agir (o caso comum — aja sem pedir licença):
{"modo":"planejar",
 "fala":"<o que você vai fazer + o que já sabe, em voz, 1-2 frases naturais>",
 "passos":[
   {"descricao":"<o que este passo faz, em português simples>",
    "comando":"<o comando EXATO de terminal>",
    "risco":"reversivel|muda_estado|destrutivo",
    "reversivel":true|false,
    "toca_alvo":true|false}
 ]}

Para conversar/responder sem rodar nada:
{"modo":"conversar","fala":"<resposta curta e natural, em voz, 1-2 frases>"}

Só quando falta um dado essencial para agir:
{"modo":"perguntar","fala":"<pergunta curta e natural>","pergunta":"<a pergunta>"}

Marque 'risco' com honestidade: 'reversivel' abre/lista/lê; 'muda_estado' \
instala/edita/cria; 'destrutivo' apaga/formata. Marque 'toca_alvo' true para \
qualquer coisa que fale com uma máquina/rede de fora. Prefira ferramentas já \
instaladas. Um comando por passo. Se um passo depende do resultado do anterior, \
pare ali e diga na 'fala' que continua depois de ver a saída."""


def montar_prompt(conversa: list) -> str:
    """Renderiza o transcript inteiro num texto para o Claude ler.

    'conversa' é uma lista de dicts {"papel","texto"} onde papel é um de:
    'dono' (o que a pessoa falou), 'grimoire' (o que o cérebro respondeu),
    'resultado' (a saída de um comando que já rodou)."""
    linhas = ["CONVERSA ATÉ AGORA:"]
    for msg in conversa:
        linhas.append(_rotular(msg))
    linhas.append("")
    linhas.append("Responda AGORA com o próximo JSON, seguindo a regra de ouro.")
    return "\n".join(linhas)


_ROTULOS = {"dono": "[dono]", "grimoire": "[grimoire]",
            "resultado": "[resultado de um comando]"}


def _rotular(msg: dict) -> str:
    """Uma mensagem da conversa vira uma linha rotulada, como o modelo espera."""
    rot = _ROTULOS.get(msg.get("papel", ""), "[?]")
    return f"{rot} {msg.get('texto', '')}"


def _extrair_json(bruto: str) -> dict:
    """Puxa o objeto JSON de dentro da resposta, tolerando cercas de código ou
    texto em volta. Pega do primeiro '{' ao último '}'."""
    if not bruto:
        raise ValueError("resposta vazia do cérebro")
    ini = bruto.find("{")
    fim = bruto.rfind("}")
    if ini == -1 or fim == -1 or fim < ini:
        raise ValueError("nenhum JSON encontrado na resposta")
    return json.loads(bruto[ini:fim + 1])


def _normalizar(ficha: dict) -> dict:
    """Garante que a ficha tem os campos que a tela espera, sem quebrar se o
    cérebro esquecer algum."""
    modo = ficha.get("modo", "conversar")
    ficha.setdefault("fala", "")
    if modo == "planejar":
        passos = ficha.get("passos") or []
        for p in passos:
            p.setdefault("descricao", "")
            p.setdefault("comando", "")
            p.setdefault("risco", "reversivel")
            p.setdefault("reversivel", True)
            p.setdefault("toca_alvo", False)
        ficha["passos"] = passos
    return ficha


# ---------------------------------------------------------------------------
# Sessão persistente do CLI. UM processo `claude` vivo; cada turno é um bloco
# de texto mandado por stdin. É onde mora o ganho de latência.
# ---------------------------------------------------------------------------

def _cmd_stream() -> list:
    """Monta a linha de comando do daemon. Corta tudo que o cérebro NÃO usa —
    config da máquina, MCP, ferramentas de arquivo/rede, slash-commands — porque
    cada um pesa no init, no contexto e no CUSTO de cada turno.

    A parte mais importante é `--setting-sources ""`: sem isso, o `claude` carrega
    o CLAUDE.md global (o perfil de segurança gigante), as memórias e as skills a
    CADA frase. MEDIDO: isso somava ~40 mil tokens de contexto, custava US$ 0,03
    por frase, subia o tempo até responder para ~8,5 s E SEQUESTRAVA o modelo — em
    vez do JSON que o Grimoire espera, ele respondia prosa (o Grimoire ficava
    mudo, 'nenhum JSON encontrado'). Com o contexto isolado: ~1,7 s, US$ 0,0075,
    e o JSON volta a sair certo. O cérebro tem o próprio `--system-prompt`; não
    precisa de NADA da config da máquina."""
    return [
        CLAUDE, "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",  # obrigatório junto de stream-json na saída
        "--system-prompt", SISTEMA,
        "--model", MODELO,
        # Contexto isolado: não carrega CLAUDE.md, memória, skills, hooks, plugins.
        "--setting-sources", "",
        # Sem servidores MCP: o cérebro não fala com nenhum.
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        # Sem ferramentas: o cérebro só PLANEJA comando em texto, não executa.
        "--disallowedTools",
        "Bash,Edit,Read,Write,Glob,Grep,WebFetch,WebSearch,Task,TodoWrite,"
        "NotebookEdit,MultiEdit",
        "--disable-slash-commands",
    ]


class _Sessao:
    """Guarda o processo `claude` vivo e sabe mandar só o turno novo.

    Toda a conversa mora dentro do próprio `claude` (ele lembra os turnos
    anteriores). Aqui a gente só rastreia QUANTO da conversa já foi mandado,
    para não reenviar o que ele já sabe — é isso que torna o 2º turno em diante
    barato."""

    def __init__(self):
        self.proc = None
        # Impressão digital da conversa já entregue ao daemon: lista de
        # (papel, texto). Serve para descobrir o pedaço NOVO a cada chamada.
        self._enviada = []
        self._lock = threading.Lock()

    def _vivo(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _matar(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self._enviada = []

    def _iniciar(self):
        """Sobe um processo `claude` novo e zera o rastro da conversa."""
        self._matar()
        # stderr vai para DEVNULL de propósito: como o daemon vive muito tempo e
        # a gente nunca lê o stderr, deixá-lo em PIPE poderia ENCHER o buffer do
        # cano e TRAVAR o processo. O que interessa (o resultado) vem no stdout.
        self.proc = subprocess.Popen(
            _cmd_stream(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self._enviada = []

    def _mandar(self, texto: str):
        """Escreve um turno do usuário no stdin do daemon (formato stream-json)."""
        msg = {"type": "user",
               "message": {"role": "user",
                           "content": [{"type": "text", "text": texto}]}}
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _ler_resultado(self, timeout: float) -> str:
        """Lê a saída stream-json até o evento 'result' e devolve o texto do
        modelo. Respeita o prazo com select(); se estourar, levanta erro para
        o chamador cair no fallback."""
        deadline = time.time() + timeout
        out = self.proc.stdout
        while True:
            restante = deadline - time.time()
            if restante <= 0:
                raise TimeoutError("o cérebro demorou demais para responder")
            pronto, _, _ = select.select([out], [], [], restante)
            if not pronto:
                raise TimeoutError("o cérebro demorou demais para responder")
            linha = out.readline()
            if linha == "":
                raise RuntimeError("o cérebro fechou a saída (daemon morreu)")
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
            except Exception:
                continue
            if obj.get("type") == "result":
                if obj.get("is_error") or obj.get("subtype") not in (None, "success"):
                    raise RuntimeError(
                        f"o cérebro devolveu erro: {str(obj.get('result'))[:200]}")
                return obj.get("result", "") or ""

    def _delta(self, conversa: list):
        """Descobre o pedaço NOVO da conversa desde a última chamada.

        Devolve (texto_a_mandar, precisa_reiniciar). Se a conversa não é uma
        continuação do que já mandamos (o dono começou outra conversa, ou a
        lista foi editada), pede reinício e manda tudo de novo."""
        atual = [(m.get("papel", ""), m.get("texto", "")) for m in conversa]
        n = len(self._enviada)
        continuacao = atual[:n] == self._enviada
        if not continuacao:
            # Conversa nova/editada: reinicia e manda tudo.
            return montar_prompt(conversa), True
        novos = conversa[n:]
        # Só interessa reenviar o que o daemon ainda não viu: fala do dono e
        # resultado de comando. As respostas do próprio grimoire ele já tem
        # como saída dele mesmo — reenviar seria redundante.
        relevantes = [m for m in novos if m.get("papel") in ("dono", "resultado")]
        if not relevantes:
            # Nada de novo para o modelo pensar em cima (situação estranha):
            # reinicia com a conversa inteira, por segurança.
            return montar_prompt(conversa), True
        linhas = [_rotular(m) for m in relevantes]
        linhas.append("")
        linhas.append("Responda AGORA com o próximo JSON, seguindo a regra de ouro.")
        return "\n".join(linhas), False

    def pensar(self, conversa: list, timeout: float) -> str:
        """Manda o turno novo e devolve o TEXTO cru do modelo. Levanta exceção
        em qualquer falha de streaming — o chamador decide o fallback."""
        with self._lock:
            if not self._vivo():
                self._iniciar()
            texto, reiniciar = self._delta(conversa)
            if reiniciar:
                self._iniciar()
                texto = montar_prompt(conversa)
            try:
                self._mandar(texto)
                bruto = self._ler_resultado(timeout)
            except (BrokenPipeError, TimeoutError, RuntimeError, OSError):
                # Sessão contaminada: mata para o próximo turno recomeçar limpo,
                # e propaga para o fallback deste turno.
                self._matar()
                raise
            # Marca toda a conversa deste turno como já entregue.
            self._enviada = [(m.get("papel", ""), m.get("texto", ""))
                             for m in conversa]
            return bruto

    def aquecer(self, timeout: float = 40.0):
        """Sobe o processo `claude` adiantado (no boot do Grimoire), para o
        interpretador Node já estar carregado quando o dono falar.

        Por que só spawn, sem 'ping' ao modelo: MEDIDO nesta máquina, mandar um
        turno-lixo de aquecimento NÃO adianta o primeiro turno real — o pico de
        latência (7–15 s) é o backoff/throttle da API do haiku, que simplesmente
        pula para a chamada seguinte em vez de sumir. O ping só gastava uma
        chamada à toa. Então aqui só deixamos o processo de pé; o primeiro turno
        real paga o init uma vez (~7–8 s) e todos os seguintes ficam em ~2,5–3 s.
        `timeout` fica na assinatura só por compatibilidade; não é usado."""
        with self._lock:
            if not self._vivo():
                self._iniciar()


# Instância única do daemon para todo o processo do Grimoire.
_sessao = _Sessao()


def aquecer():
    """Atalho público: sobe o daemon do cérebro adiantado (chame no boot)."""
    if USAR_STREAM:
        _sessao.aquecer()


def _pensar_oneshot(conversa: list, timeout: int) -> dict:
    """Modo antigo, de segurança: um `claude -p` por turno. Mais lento (~10 s)
    mas não depende do daemon. É o fallback quando o streaming falha."""
    prompt = montar_prompt(conversa)
    cmd = [CLAUDE, "-p", "--output-format", "json", "--system-prompt", SISTEMA,
           # mesmo isolamento do daemon: sem CLAUDE.md/memória/skills (ver _cmd_stream)
           "--setting-sources", "",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    if MODELO:
        cmd += ["--model", MODELO]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("o cérebro demorou demais para responder")
    if proc.returncode != 0:
        raise RuntimeError(f"o cérebro falhou: {proc.stderr.strip()[:200]}")
    texto = proc.stdout
    try:
        env = json.loads(proc.stdout)
        if isinstance(env, dict) and "result" in env:
            texto = env["result"]
    except Exception:
        pass
    try:
        ficha = _extrair_json(texto)
    except Exception as e:
        raise RuntimeError(f"não entendi a resposta do cérebro ({e})")
    return _normalizar(ficha)


def pensar(conversa: list, timeout: int = 120) -> dict:
    """Manda a conversa ao Claude e devolve a ficha já normalizada.

    Usa a sessão persistente (rápida) e, se ela falhar por qualquer motivo,
    cai sozinha no modo antigo (um processo por turno) para NUNCA deixar o
    Grimoire mudo. Levanta RuntimeError com mensagem em português só se os DOIS
    caminhos falharem."""
    if USAR_STREAM:
        try:
            bruto = _sessao.pensar(conversa, timeout=timeout)
            ficha = _extrair_json(bruto)
            return _normalizar(ficha)
        except Exception:
            # Streaming falhou (daemon morreu, timeout, JSON ilegível...):
            # tenta o modo antigo antes de desistir.
            pass
    return _pensar_oneshot(conversa, timeout)


if __name__ == "__main__":
    # Teste manual: python3 grimoire_brain.py "abre o firefox"
    import sys
    fala = sys.argv[1] if len(sys.argv) > 1 else "abre o firefox pra mim"
    print(json.dumps(pensar([{"papel": "dono", "texto": fala}]),
                     ensure_ascii=False, indent=2))
