#!/usr/bin/env python3
"""DERVS — o Claude Code de verdade dentro do painel (onda B da central do PC).

Há DUAS peças de Claude no DERVS, de propósito:
  1. o planejador de voz (`dervs_brain.py`), isolado (`--setting-sources ""`),
     que só devolve uma ficha JSON curta; e
  2. ESTA: a sessão do Claude Code, "o mesmo Claude" do terminal do dono — com o
     `~/.claude` dele (CLAUDE.md, skills, agentes, MCPs, plugins), pela ASSINATURA
     (OAuth já logado no CLI; nenhuma chave de API passa por aqui).

Usa o SDK oficial (`claude-agent-sdk`), que já fala o protocolo de controle do
stream-json (pedido de permissão, interrupt, ganchos em processo) — a parte
perigosa de errar à mão. O `ClaudeSDKClient` vive numa thread própria, com laço
asyncio, e TODA chamada a ele sai de UMA tarefa (o "trabalhador"): o cliente
abre um grupo de tarefas do anyio no `connect()` e exige fechar na mesma tarefa.

TRAVAS (cada uma tem teste que quebra se alguém mexer):
  - `PERMISSION_MODE = "default"`. Nunca `bypassPermissions`, `acceptEdits` ou
    `auto`: todo pedido que uma regra não resolva chega ao painel do DERVS.
  - Gancho `PreToolUse` EM PROCESSO em Bash/PowerShell/Edit/Write: roda ANTES de
    qualquer regra, e o "negar" dele vale até em bypassPermissions. Comando
    destrutivo (`dervs_safety.decidir_risco`) e caminho protegido são negados com
    a instrução de usar `mcp__dervs__propor_acao`.
  - `can_use_tool` vira o verbo `claude_pedido`; sem resposta em 5 minutos, NEGA.
    Voz nunca aprova nível `muda_estado`/`destrutivo` (voz não é senha — ver
    `test_dervs_voz_nao_e_senha.py`).
  - O servidor MCP `dervs` não tem ferramenta "executar": `propor_acao` só
    REGISTRA o pedido; executar é clique do dono, numa onda futura (C).
  - Tudo que o Claude escreve é DADO, nunca ordem: a tela só usa `textContent`.

Só o que é puro (frase de voz, resumo para fala, nível de risco, caminho
protegido) roda sem o SDK; sem ele instalado o módulo carrega e `perguntar`
responde com um erro claro em vez de derrubar o DERVS.
"""
import asyncio
import datetime
import json
import os
import re
import sys
import threading
import time
import unicodedata
import uuid
import warnings

import dervs_gasto
import dervs_processos
import dervs_safety as seg

try:
    import claude_agent_sdk as sdk
except ImportError:                       # o DERVS abre mesmo assim, sem a sessão
    sdk = None
else:
    # O SDK avisa que `can_use_tool` não é consultado para as 3 ferramentas do
    # servidor `dervs` (estão em `allowed_tools`). É de propósito: nenhuma executa
    # nada, e o gancho PreToolUse continua valendo antes delas.
    warnings.filterwarnings("ignore", category=sdk.CanUseToolShadowedWarning)

# --- as travas ---------------------------------------------------------------
PERMISSION_MODE = "default"
MODOS_PROIBIDOS = ("bypassPermissions", "acceptEdits", "auto")

PERFIL_PADRAO = "dono"
# dono: o ~/.claude dele inteiro vale. equipe: só o harness do projeto, para as
# regras valerem iguais em qualquer PC (onda E). Perfil desconhecido = o menor.
SETTING_SOURCES = {"dono": ("user", "project", "local"), "equipe": ("project",)}

LIMITE_PERGUNTA = 8000          # caracteres que a caixa de texto aceita
TIMEOUT_PEDIDO_S = 300          # sem resposta do dono em 5 min: NEGA
ESPERA_INTERRUPT_S = 5          # depois disto, mata a árvore de processos
LIMITE_RESUMO = 200
LIMITE_ENTRADA = 600

FERRAMENTAS_DE_COMANDO = ("Bash", "PowerShell")
FERRAMENTAS_DE_ESCRITA = ("Edit", "Write", "MultiEdit", "NotebookEdit")
MATCHER_DO_GANCHO = "|".join(FERRAMENTAS_DE_COMANDO + FERRAMENTAS_DE_ESCRITA)
_SO_LEITURA = ("Read", "Glob", "Grep", "LS", "TodoWrite", "NotebookRead")
FERRAMENTAS_DERVS = ("mcp__dervs__central_coletar", "mcp__dervs__propor_acao",
                     "mcp__dervs__status_aprovacao")
# A "pasta do harness" (onda E) ainda não existe: até lá, a própria pasta do DERVS.
PASTA_HARNESS = os.path.dirname(os.path.abspath(__file__))

ETIQUETA_GASTO = "assinatura (equivalente)"     # medida, não cobrança


# --- caminhos protegidos -----------------------------------------------------
# TODO(onda C): o módulo `dervs_caminhos_protegidos` (com `esta_protegido`) é da
# onda C e ainda não existe nesta branch. Este piso interno cobre o mínimo e
# SEMPRE vale; se o módulo da C aparecer, o veredito dele soma-se ao daqui
# (protegido se QUALQUER um disser que é). Não inventar aquele módulo neste arquivo.
try:
    from dervs_caminhos_protegidos import esta_protegido as _protegido_da_onda_c
except ImportError:
    _protegido_da_onda_c = None

_PASTAS_DE_SISTEMA = re.compile(r"^[a-z]:\\(?:windows|program files[^\\]*)(?:\\|$)")


def _protegido_interno(caminho) -> bool:
    """Piso mínimo: C:\\Windows, C:\\Program Files*, qualquer `.git`, `.claude` ou
    `.ssh` no caminho."""
    try:
        p = os.path.normcase(os.path.normpath(
            os.path.expandvars(os.path.expanduser(str(caminho)))))
    except (TypeError, ValueError):
        return True               # não deu para entender o caminho: na dúvida, protege
    partes = [x for x in re.split(r"[\\/]+", p) if x]
    if ".git" in partes or ".claude" in partes or ".ssh" in partes:
        return True
    if _PASTAS_DE_SISTEMA.match(p.replace("/", "\\")):
        return True
    raiz = os.path.normcase(os.environ.get("SystemRoot") or r"C:\Windows")
    if p == raiz or p.startswith(raiz + os.sep):
        return True
    return False


def esta_protegido(caminho) -> bool:
    if _protegido_interno(caminho):
        return True
    if _protegido_da_onda_c is not None:
        try:
            return bool(_protegido_da_onda_c(caminho))
        except Exception:
            return True           # o motor da C quebrou: fecha, não abre
    return False


# --- risco e resumo de uma ferramenta -----------------------------------------

def nivel_da_ferramenta(nome: str, entrada: dict) -> str:
    """`reversivel` | `muda_estado` | `destrutivo` — o mesmo vocabulário da casa."""
    if nome in FERRAMENTAS_DE_COMANDO:
        return seg.decidir_risco(str((entrada or {}).get("command", "")))["nivel"]
    if nome in _SO_LEITURA or nome in FERRAMENTAS_DERVS:
        return "reversivel"
    return "muda_estado"          # escrever, rede, desconhecido: no mínimo um clique


def resumo_da_ferramenta(nome: str, entrada: dict) -> str:
    entrada = entrada if isinstance(entrada, dict) else {}
    for chave in ("command", "file_path", "notebook_path", "path", "pattern",
                  "url", "query"):
        if isinstance(entrada.get(chave), str) and entrada[chave]:
            return entrada[chave][:LIMITE_RESUMO]
    return json.dumps(entrada, ensure_ascii=False, default=str)[:LIMITE_RESUMO]


def entrada_cortada(entrada) -> str:
    return json.dumps(entrada, ensure_ascii=False, default=str)[:LIMITE_ENTRADA]


# --- o gancho PreToolUse -------------------------------------------------------
_TOKEN = re.compile(r"[^\s\"'|;&<>()]+")


def _caminhos_no_comando(comando: str):
    """Pedaços do comando que parecem caminho (têm barra, começam com `.` ou `~`,
    ou têm letra de unidade). É heurística: o objetivo é não deixar um comando
    que MUDA algo passar por cima de pasta protegida."""
    for t in _TOKEN.findall(comando or ""):
        if "\\" in t or "/" in t or t.startswith((".", "~")) or re.match(r"^[A-Za-z]:", t):
            yield t


def motivo_de_bloqueio(nome: str, entrada: dict, protegido=esta_protegido):
    """Devolve o motivo (texto para o Claude ler) se a ferramenta deve ser
    NEGADA antes de qualquer regra; `None` deixa o fluxo normal seguir."""
    entrada = entrada if isinstance(entrada, dict) else {}
    proposta = "Use a ferramenta mcp__dervs__propor_acao: o dono decide no painel."
    if nome in FERRAMENTAS_DE_COMANDO:
        comando = str(entrada.get("command", ""))
        d = seg.decidir_risco(comando)
        if d["nivel"] == "destrutivo":
            porque = "; ".join(d["motivos"]) or "destrutivo"
            return f"O DERVS bloqueou este comando ({porque}). {proposta}"
        if d["nivel"] != "reversivel":
            for c in _caminhos_no_comando(comando):
                if protegido(c):
                    return f"O DERVS bloqueou: o comando mexe em caminho protegido ({c}). {proposta}"
        return None
    if nome in FERRAMENTAS_DE_ESCRITA:
        caminho = (entrada.get("file_path") or entrada.get("notebook_path")
                   or entrada.get("path"))
        if not isinstance(caminho, str) or not caminho:
            return f"O DERVS bloqueou: a escrita veio sem caminho legível. {proposta}"
        if protegido(caminho):
            return f"O DERVS bloqueou: {caminho} é um caminho protegido. {proposta}"
    return None


def criar_gancho(protegido=esta_protegido):
    """O callback `PreToolUse` do SDK. Falha FECHADA: se o próprio gancho
    quebrar, nega."""
    async def gancho(entrada, tool_use_id, contexto):
        try:
            motivo = motivo_de_bloqueio(entrada.get("tool_name", ""),
                                        entrada.get("tool_input") or {}, protegido)
        except Exception as e:
            motivo = f"O DERVS não conseguiu avaliar a ferramenta ({type(e).__name__}); negada."
        if motivo is None:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": motivo}}
    return gancho


# --- opções da sessão ----------------------------------------------------------

def _unidades_para_leitura():
    if sys.platform != "win32":
        return []
    return [(os.environ.get("SystemDrive") or "C:") + "\\"]


def montar_opcoes(perfil, *, can_use_tool, gancho, servidor_mcp, resume=None,
                  cwd=None, cli_path=None):
    if sdk is None:
        raise RuntimeError("o pacote claude-agent-sdk não está instalado "
                           "(rode: pip install -r requirements.txt)")
    if cli_path is None:
        import dervs_brain
        cli_path = dervs_brain._resolver_claude()
    fontes = SETTING_SOURCES.get(perfil, SETTING_SOURCES["equipe"])
    return sdk.ClaudeAgentOptions(
        permission_mode=PERMISSION_MODE,
        setting_sources=list(fontes),
        cwd=cwd or PASTA_HARNESS,
        cli_path=cli_path,
        add_dirs=_unidades_para_leitura(),      # leitura da máquina inteira
        include_partial_messages=True,          # streaming palavra a palavra
        can_use_tool=can_use_tool,
        hooks={"PreToolUse": [sdk.HookMatcher(matcher=MATCHER_DO_GANCHO, hooks=[gancho])]},
        mcp_servers={"dervs": servidor_mcp},
        allowed_tools=list(FERRAMENTAS_DERVS),  # o gancho ainda roda antes delas
        resume=resume,
    )


# --- sessão em disco -----------------------------------------------------------
_ID_DE_SESSAO = re.compile(r"^[0-9A-Za-z-]{8,80}$")


def _pasta_local():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        return os.path.join(base, "dervs")
    return os.path.expanduser("~/.local/state/dervs")


def _caminho(nome_env: str, arquivo: str):
    """Como o `dervs_gasto`: a variável manda; sob pytest sem ela, `None` (o
    teste não pode sujar os arquivos reais do dono)."""
    forcado = os.environ.get(nome_env)
    if forcado:
        return forcado
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    return os.path.join(_pasta_local(), arquivo)


def caminho_sessao():
    return _caminho("DERVS_CLAUDE_SESSAO", "claude_sessao.json")


def caminho_propostas():
    return _caminho("DERVS_CLAUDE_PROPOSTAS", "claude_propostas.jsonl")


def ler_sessao(caminho, perfil):
    """`session_id` a retomar, ou `None` (sem arquivo, torto, ou de outro perfil)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
        sid = d.get("session_id")
        if d.get("perfil") == perfil and isinstance(sid, str) and _ID_DE_SESSAO.match(sid):
            return sid
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


def gravar_sessao(caminho, session_id, perfil):
    if not caminho or not isinstance(session_id, str) or not _ID_DE_SESSAO.match(session_id):
        return False
    try:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        temporario = caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump({"session_id": session_id, "perfil": perfil,
                       "quando": datetime.datetime.now().isoformat(timespec="seconds")}, f)
        os.replace(temporario, caminho)
        return True
    except OSError:
        return False


def apagar_sessao(caminho):
    try:
        if caminho:
            os.remove(caminho)
    except OSError:
        pass


# --- voz: o que vira trabalho para o Claude ------------------------------------

def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


_PEDE_AO_CLAUDE = re.compile(
    r"^\W*(?:(?:ei|oi|ola)\s+)?(?:dervs\W+)?"
    r"(?:pede|pe[cç]a|pergunta|manda|fala|chama)\s+(?:pr[oa]|para\s+o|ao|a\s+o|com\s+o|o)\s+claude"
    r"\W*(?:(?:que|pra|para)\s+)?(.+)$", re.IGNORECASE | re.DOTALL)
_CLAUDE_VIRGULA = re.compile(r"^\W*(?:dervs\W+)?claude\s*[,:]\s*(.+)$",
                             re.IGNORECASE | re.DOTALL)
_VERBO_DE_TRABALHO = re.compile(
    r"^(?:(?:ei )?dervs )?(?:analis[ae]|investig[ae]|diagnostic[ae]|audit[ae]) \w+")
_VERIFICA_A_MAQUINA = re.compile(
    r"^(?:(?:ei )?dervs )?verific[ae] (?:o |a |todo o |toda a )?(?:meu |minha )?"
    r"(?:pc|computador|maquina|windows|disco|sistema|notebook)\b")


def frase_de_trabalho(texto: str):
    """Devolve o texto a mandar ao Claude Code quando a frase PEDE TRABALHO
    ("pede pro Claude…", "analisa…", "verifica meu PC"), ou `None`. Conservador
    de propósito: rodando antes dos atalhos e do planejador, um falso positivo
    gasta assinatura e tempo do dono à toa."""
    original = (texto or "").strip()
    if not original:
        return None
    m = _PEDE_AO_CLAUDE.match(original) or _CLAUDE_VIRGULA.match(original)
    if m and m.group(1).strip():
        return m.group(1).strip()
    n = _norm(original)
    if _VERBO_DE_TRABALHO.match(n) or _VERIFICA_A_MAQUINA.match(n):
        return original
    return None


_PARAR = {"para", "parar", "pare", "para ai", "para tudo", "para com isso",
          "cancela", "cancela isso", "chega", "interrompe", "interrompe isso"}


def eh_comando_parar(texto: str) -> bool:
    n = _norm(texto)
    if n.startswith("dervs "):
        n = n[6:]
    return n in _PARAR


def resumir_para_fala(texto: str, max_frases: int = 2, max_chars: int = 240) -> str:
    """A resposta inteira fica no painel; a voz lê no máximo duas frases, sem
    marcação de markdown."""
    t = texto or ""
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"(?m)^\s*(?:[-*+>]|#{1,6}|\d+[.)])\s+", "", t)
    t = re.sub(r"[`*]{1,3}|__", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    frases = re.split(r"(?<=[.!?])\s+", t)
    fala = " ".join(frases[:max_frases])
    if len(fala) > max_chars:
        fala = fala[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return fala


# --- pedidos de permissão ------------------------------------------------------

class _Pedidos:
    """Os pedidos de permissão em aberto. `abrir` roda na thread do laço; `responder`
    vem de outra thread (a leitora da ponte). Cada id vale UMA vez: resposta
    duplicada, atrasada ou de id desconhecido é ignorada em silêncio."""

    def __init__(self):
        self._abertos = {}
        self._trava = threading.Lock()

    def abrir(self, laco, nivel):
        id_ = uuid.uuid4().hex[:12]
        futuro = laco.create_future()
        with self._trava:
            self._abertos[id_] = (futuro, nivel, laco)
        return id_, futuro

    def fechar(self, id_):
        with self._trava:
            self._abertos.pop(id_, None)

    def responder(self, id_, permitir, cartao_id=None, origem="clique") -> bool:
        with self._trava:
            item = self._abertos.get(id_)
            if item is None:
                return False
            futuro, nivel, laco = item
            if cartao_id is not None and cartao_id != id_:
                return False
            # VOZ NÃO É SENHA: por voz só se aprova o que é reversível. Negar por
            # voz sempre vale (é o lado seguro).
            if origem == "voz" and permitir and nivel != "reversivel":
                return False
            del self._abertos[id_]
        laco.call_soon_threadsafe(lambda: futuro.done() or futuro.set_result(bool(permitir)))
        return True

    def negar_todos(self):
        with self._trava:
            itens = list(self._abertos.values())
            self._abertos.clear()
        for futuro, _nivel, laco in itens:
            laco.call_soon_threadsafe(lambda f=futuro: f.done() or f.set_result(False))

    def quantos(self) -> int:
        with self._trava:
            return len(self._abertos)


class _ProcessoAnyio:
    """Empresta a um `anyio.Process` a cara de `subprocess.Popen` que
    `dervs_processos.encerrar_arvore` espera."""

    def __init__(self, processo):
        self._p = processo
        self.pid = processo.pid

    def poll(self):
        return self._p.returncode

    def kill(self):
        self._p.kill()

    def wait(self, timeout=None):
        limite = time.time() + (timeout or 0)
        while self._p.returncode is None and time.time() < limite:
            time.sleep(0.05)


def _texto_mcp(texto, erro=False):
    r = {"content": [{"type": "text", "text": texto}]}
    if erro:
        r["is_error"] = True
    return r


def _redigir(texto: str) -> str:
    """Não grava no log o que parece segredo (mesmos padrões do `dervs_safety`)."""
    if any(re.search(p, texto, re.IGNORECASE) for p in seg._SEGREDOS):
        return "[redigido: parece conter segredo]"
    return texto


# --- a sessão --------------------------------------------------------------------

class SessaoClaudeCode:
    """Uma conversa contínua com o Claude Code. Os métodos públicos são seguros de
    chamar de qualquer thread (a Qt, a leitora da ponte, a de voz).

    `ao_evento(verbo, dados)` recebe os verbos que vão ao painel: `claude_delta
    {texto}`, `claude_ferramenta {nome, resumo}`, `claude_pedido {...}` e
    `claude_fim {ok, custo, erro}`. `ao_texto_final(texto, origem)` recebe a
    resposta final (a voz resume). `ao_aviso(texto)` recebe avisos de limite."""

    def __init__(self, ao_evento, ao_texto_final=None, ao_aviso=None,
                 perfil=PERFIL_PADRAO, fabrica_cliente=None, arquivo_sessao="padrao",
                 arquivo_propostas="padrao", cwd=None, protegido=esta_protegido,
                 timeout_pedido=TIMEOUT_PEDIDO_S, espera_interrupt=ESPERA_INTERRUPT_S,
                 encerrar_arvore=dervs_processos.encerrar_arvore):
        self._ao_evento = ao_evento
        self._ao_texto_final = ao_texto_final
        self._ao_aviso = ao_aviso
        self.perfil = perfil if perfil in SETTING_SOURCES else PERFIL_PADRAO
        self._fabrica = fabrica_cliente or self._fabrica_padrao
        self._arquivo_sessao = caminho_sessao() if arquivo_sessao == "padrao" else arquivo_sessao
        self._arquivo_propostas = (caminho_propostas() if arquivo_propostas == "padrao"
                                   else arquivo_propostas)
        self._cwd = cwd
        self._protegido = protegido
        self._timeout_pedido = timeout_pedido
        self._espera_interrupt = espera_interrupt
        self._encerrar_arvore = encerrar_arvore

        self._trava = threading.Lock()
        self._laco = None
        self._comandos = None
        self._cliente = None                  # só o trabalhador mexe
        self._pedidos = _Pedidos()
        self._propostas = {}
        self._ocupado = False
        self._interrompido = False
        self._fim_do_turno = threading.Event()
        self._fim_do_turno.set()
        self._session_id = None
        self._custo_acumulado = 0.0
        self._encerrada = False
        self._trabalhador_parou = threading.Event()
        # estado de UM turno (só o trabalhador mexe)
        self._texto_emitido = False
        self._separar = False
        self._streamou = False
        self._partes = []

    # ---- API pública (qualquer thread) ---------------------------------------
    @property
    def ocupado(self) -> bool:
        return self._ocupado

    def perguntar(self, texto: str, origem: str = "painel") -> bool:
        texto = (texto or "").strip()
        if not texto or len(texto) > LIMITE_PERGUNTA or self._encerrada:
            return False
        with self._trava:
            if self._ocupado:
                return False
            self._ocupado = True
            self._interrompido = False
            self._fim_do_turno = threading.Event()
        laco = self._garantir_laco()
        laco.call_soon_threadsafe(self._comandos.put_nowait, ("turno", (texto, origem)))
        return True

    def parar(self) -> bool:
        """Interrompe o turno em andamento. Se o Claude não obedecer em
        `espera_interrupt` s, mata a árvore de processos DELE (pelo PID que o SDK
        abriu — nunca por padrão de linha de comando)."""
        with self._trava:
            if not self._ocupado:
                return False
            self._interrompido = True
            fim = self._fim_do_turno
        self._pedidos.negar_todos()
        self._agendar(self._interromper())
        threading.Thread(target=self._vigiar_interrupcao, args=(fim,), daemon=True).start()
        return True

    def nova_conversa(self):
        """Esquece a conversa: para o que estiver rodando, apaga o `session_id` e
        derruba o cliente (o próximo `perguntar` abre um limpo)."""
        self.parar()
        self._session_id = None
        self._custo_acumulado = 0.0
        apagar_sessao(self._arquivo_sessao)
        if self._laco is not None:
            self._laco.call_soon_threadsafe(self._comandos.put_nowait, ("reiniciar", None))

    def responder(self, id_, permitir, cartao_id=None, origem="clique") -> bool:
        return self._pedidos.responder(id_, permitir is True, cartao_id, origem)

    def aguardar_ocioso(self, timeout=10.0) -> bool:
        """Espera o turno atual (e o que estiver na fila do trabalhador) acabar."""
        fim = time.time() + timeout
        while time.time() < fim:
            if not self._ocupado and (self._comandos is None or self._comandos.empty()):
                return True
            time.sleep(0.02)
        return False

    def encerrar(self):
        """Fim do DERVS: derruba o cliente e o laço. Não deixa `claude` órfão."""
        self._encerrada = True
        self._pedidos.negar_todos()
        laco = self._laco
        if laco is None:
            return
        if self._ocupado:
            self._matar_processo()          # o app está fechando: sem esperar 5 s
        laco.call_soon_threadsafe(self._comandos.put_nowait, ("encerrar", None))
        if not self._trabalhador_parou.wait(8):
            self._matar_processo()
        laco.call_soon_threadsafe(laco.stop)

    # ---- laço e trabalhador ----------------------------------------------------
    def _garantir_laco(self):
        with self._trava:
            if self._laco is None:
                laco = asyncio.new_event_loop()
                self._comandos = asyncio.Queue()
                threading.Thread(target=self._rodar_laco, args=(laco,), daemon=True,
                                 name="claude-code").start()
                laco.call_soon_threadsafe(lambda: laco.create_task(self._trabalhador()))
                self._laco = laco
            return self._laco

    @staticmethod
    def _rodar_laco(laco):
        asyncio.set_event_loop(laco)
        laco.run_forever()

    def _agendar(self, corrotina):
        if self._laco is None:
            corrotina.close()
            return
        asyncio.run_coroutine_threadsafe(corrotina, self._laco)

    async def _trabalhador(self):
        try:
            while True:
                tipo, arg = await self._comandos.get()
                if tipo == "turno":
                    await self._turno(*arg)
                elif tipo == "reiniciar":
                    await self._descartar_cliente()
                else:
                    await self._descartar_cliente()
                    break
        finally:
            self._trabalhador_parou.set()

    def _fabrica_padrao(self, opcoes):
        return sdk.ClaudeSDKClient(options=opcoes)

    async def _conectar(self):
        if self._cliente is not None:
            return
        if self._session_id is None and self._arquivo_sessao:
            self._session_id = ler_sessao(self._arquivo_sessao, self.perfil)
        servidor = criar_servidor_dervs(self)[0]
        opcoes = montar_opcoes(
            self.perfil, can_use_tool=self._can_use_tool,
            gancho=criar_gancho(self._protegido), servidor_mcp=servidor,
            resume=self._session_id, cwd=self._cwd)
        cliente = self._fabrica(opcoes)
        try:
            await cliente.connect()
        except Exception:
            if self._session_id:            # não deu para retomar: a próxima começa limpa
                self._session_id = None
                apagar_sessao(self._arquivo_sessao)
            raise
        self._cliente = cliente
        self._custo_acumulado = 0.0

    async def _descartar_cliente(self):
        cliente, self._cliente = self._cliente, None
        if cliente is None:
            return
        try:
            await asyncio.wait_for(cliente.disconnect(), 10)
        except Exception:
            pass

    async def _interromper(self):
        cliente = self._cliente
        if cliente is None:
            return
        try:
            await cliente.interrupt()
        except Exception:
            pass

    def _vigiar_interrupcao(self, fim):
        if not fim.wait(self._espera_interrupt):
            self._matar_processo()

    def _processo_do_cliente(self):
        transporte = getattr(self._cliente, "_transport", None)
        return getattr(transporte, "_process", None)

    def _matar_processo(self):
        proc = self._processo_do_cliente()
        if proc is not None:
            try:
                self._encerrar_arvore(_ProcessoAnyio(proc))
            except Exception:
                pass

    # ---- um turno ---------------------------------------------------------------
    def _emitir(self, verbo, dados):
        try:
            self._ao_evento(verbo, dados)
        except Exception as e:
            sys.stderr.write(f"claude_code: falha ao avisar o painel: {e}\n")

    async def _turno(self, texto, origem):
        self._texto_emitido = False
        self._separar = False
        self._streamou = False
        self._partes = []
        erro = None
        resultado = None
        try:
            await self._conectar()
            await self._cliente.query(texto)
            async for msg in self._cliente.receive_response():
                r = self._tratar(msg)
                if r is not None:
                    resultado = r
        except Exception as e:
            erro = f"{type(e).__name__}: {str(e)[:200]}"
            await self._descartar_cliente()       # o próximo turno reconecta (resume)
        custo, texto_final = self._fechar_resultado(resultado)
        ok = erro is None and resultado is not None and not resultado.is_error
        if self._interrompido:
            ok, erro = False, "interrompido"
        elif erro is None and resultado is None:
            ok, erro = False, "o Claude não devolveu resultado"
        elif erro is None and resultado.is_error:
            detalhe = resultado.result or "; ".join(resultado.errors or []) or resultado.subtype
            erro = str(detalhe)[:300]
        self._pedidos.negar_todos()
        with self._trava:
            self._ocupado = False
            fim = self._fim_do_turno
        self._emitir("claude_fim", {"ok": ok, "custo": custo, "erro": erro})
        if ok and texto_final and self._ao_texto_final:
            try:
                self._ao_texto_final(texto_final, origem)
            except Exception as e:
                sys.stderr.write(f"claude_code: falha ao entregar a resposta final: {e}\n")
        fim.set()

    def _fechar_resultado(self, resultado):
        """Grava o `session_id` e o custo do `ResultMessage`; devolve (custo do
        turno, texto final). O `total_cost_usd` do SDK é ACUMULADO na sessão, então
        o que se registra é a diferença."""
        if resultado is None:
            return 0.0, "".join(self._partes)
        if resultado.session_id and resultado.session_id != self._session_id:
            self._session_id = resultado.session_id
            gravar_sessao(self._arquivo_sessao, self._session_id, self.perfil)
        custo = 0.0
        total = resultado.total_cost_usd
        if isinstance(total, (int, float)) and total >= 0:
            custo = total - self._custo_acumulado if total >= self._custo_acumulado else total
            self._custo_acumulado = total
            dervs_gasto.registrar("claude", custo, ETIQUETA_GASTO)
        return round(custo, 6), (resultado.result or "\n\n".join(self._partes))

    def _tratar(self, msg):
        if sdk is None:
            return None
        if isinstance(msg, sdk.StreamEvent):
            if msg.parent_tool_use_id is None:
                self._tratar_stream(msg.event or {})
        elif isinstance(msg, sdk.AssistantMessage):
            self._tratar_assistente(msg)
        elif isinstance(msg, sdk.RateLimitEvent):
            self._tratar_limite(msg.rate_limit_info)
        elif isinstance(msg, sdk.ResultMessage):
            return msg
        return None

    def _emitir_texto(self, texto):
        if not texto:
            return
        if self._separar:
            texto = "\n\n" + texto
            self._separar = False
        self._texto_emitido = True
        self._emitir("claude_delta", {"texto": texto})

    def _tratar_stream(self, ev):
        tipo = ev.get("type")
        if tipo == "message_start":
            self._separar = self._texto_emitido
        elif tipo == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta" and isinstance(d.get("text"), str):
                self._streamou = True
                self._emitir_texto(d["text"])

    def _tratar_assistente(self, msg):
        for bloco in msg.content:
            if isinstance(bloco, sdk.TextBlock):
                if msg.parent_tool_use_id is None:
                    self._partes.append(bloco.text)
                    if not self._streamou:
                        self._separar = self._separar or self._texto_emitido
                        self._emitir_texto(bloco.text)
            elif isinstance(bloco, sdk.ToolUseBlock):
                self._emitir("claude_ferramenta", {
                    "nome": bloco.name,
                    "resumo": resumo_da_ferramenta(bloco.name, bloco.input)})
        self._streamou = False

    def _tratar_limite(self, info):
        if info.status == "rejected":
            quando = ""
            if info.resets_at:
                quando = datetime.datetime.fromtimestamp(info.resets_at).strftime("%H:%M")
            texto = ("Atingi o limite do plano" +
                     (f", volta às {quando}." if quando else "."))
        elif info.status == "allowed_warning":
            pct = f" ({round(info.utilization * 100)}%)" if info.utilization else ""
            texto = f"Estou chegando no limite do plano{pct}."
        else:
            return
        if self._ao_aviso:
            try:
                self._ao_aviso(texto)
            except Exception:
                pass

    # ---- permissão -----------------------------------------------------------------
    async def _can_use_tool(self, nome, entrada, contexto):
        nivel = nivel_da_ferramenta(nome, entrada)
        id_, futuro = self._pedidos.abrir(asyncio.get_running_loop(), nivel)
        self._emitir("claude_pedido", {
            "id": id_, "ferramenta": nome, "resumo": resumo_da_ferramenta(nome, entrada),
            "entrada_cortada": entrada_cortada(entrada), "nivel": nivel,
            "expira_s": int(self._timeout_pedido)})
        try:
            permitir = await asyncio.wait_for(futuro, self._timeout_pedido)
        except asyncio.TimeoutError:
            permitir = False
        finally:
            self._pedidos.fechar(id_)
        if permitir:
            return sdk.PermissionResultAllow()
        return sdk.PermissionResultDeny(
            message="O dono negou (ou não respondeu em 5 minutos). Não tente de novo "
                    "sem perguntar a ele.")

    # ---- ferramentas do servidor MCP `dervs` -----------------------------------------
    def registrar_proposta(self, itens) -> str:
        id_ = "p-" + uuid.uuid4().hex[:8]
        limpos = [{str(k)[:40]: _redigir(str(v)[:300]) for k, v in i.items()}
                  for i in itens[:50] if isinstance(i, dict)]
        self._propostas[id_] = {"itens": limpos, "estado": "pendente"}
        if self._arquivo_propostas:
            try:
                os.makedirs(os.path.dirname(self._arquivo_propostas) or ".", exist_ok=True)
                with open(self._arquivo_propostas, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"quando": datetime.datetime.now().isoformat(
                        timespec="seconds"), "id": id_, "itens": limpos},
                        ensure_ascii=False) + "\n")
            except OSError:
                pass
        self._emitir("claude_ferramenta", {
            "nome": "propor_acao",
            "resumo": f"proposta {id_} com {len(limpos)} item(ns) — aguarda o dono; nada foi executado"})
        return id_

    def estado_da_proposta(self, id_):
        p = self._propostas.get(id_)
        return None if p is None else p["estado"]


def criar_servidor_dervs(sessao: SessaoClaudeCode):
    """O servidor MCP em processo `dervs`. Devolve (config para as opções,
    {nome: ferramenta}). NÃO existe ferramenta que execute: executar é clique."""
    if sdk is None:
        raise RuntimeError("claude-agent-sdk não instalado")

    @sdk.tool("central_coletar",
              "Coleta uma leitura da máquina (somente leitura) para a Central do PC.",
              {"coletor": str})
    async def central_coletar(args):
        # A onda D preenche os coletores reais.
        return _texto_mcp("Coletor ainda não instalado: a Central do PC (onda D) "
                          "não chegou. Use as ferramentas normais de leitura.")

    @sdk.tool("propor_acao",
              "Propõe ao dono uma lista de ações (limpar, desinstalar, desativar...). "
              "NÃO executa nada: só registra o pedido e mostra no painel; quem "
              "executa é o clique do dono. Cada item: acao, alvo, o_que_e, "
              "por_que_seguro, como_desfazer.",
              {"type": "object", "required": ["itens"],
               "properties": {"itens": {"type": "array", "items": {"type": "object"}}}})
    async def propor_acao(args):
        itens = args.get("itens") if isinstance(args, dict) else None
        if not isinstance(itens, list) or not itens or not all(isinstance(i, dict) for i in itens):
            return _texto_mcp("itens precisa ser uma lista não vazia de objetos.", erro=True)
        id_ = sessao.registrar_proposta(itens)
        return _texto_mcp(f"Proposta {id_} registrada. NADA foi executado: o dono "
                          "decide no painel do DERVS.")

    @sdk.tool("status_aprovacao", "Diz em que pé está uma proposta feita com propor_acao.",
              {"relatorio_id": str})
    async def status_aprovacao(args):
        estado = sessao.estado_da_proposta(str((args or {}).get("relatorio_id", "")))
        if estado is None:
            return _texto_mcp("Não conheço essa proposta.")
        return _texto_mcp("Proposta pendente: o dono ainda não decidiu. Nada foi executado.")

    ferramentas = {t.name: t for t in (central_coletar, propor_acao, status_aprovacao)}
    return (sdk.create_sdk_mcp_server("dervs", tools=list(ferramentas.values())),
            ferramentas)
