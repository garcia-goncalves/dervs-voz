#!/usr/bin/env python3
"""DERVS — o Claude Code de verdade dentro do painel (onda B da central do PC).

Há DUAS peças de Claude no DERVS, de propósito:
  1. o planejador de voz (`dervs_brain.py`), isolado (`--setting-sources ""`),
     que só devolve uma ficha JSON curta; e
  2. ESTA: a sessão do Claude Code, pela ASSINATURA (OAuth do CLI; nenhuma chave
     de API passa por aqui), com DOIS perfis (decisão do dono, 15/10/2026):
       - `dervs` (o padrão: caixa do painel e voz): o CÉREBRO PRÓPRIO do DERVS.
         `CLAUDE_CONFIG_DIR` = `%APPDATA%\\dervs\\cerebro` (CLAUDE.md com a persona,
         settings sem ganchos, skills/agentes só dele, memória e login próprios),
         `setting_sources=["user"]` (o "user" agora é essa pasta), MCP só o `dervs`
         (`strict_mcp_config`) e a pasta de trabalho `%APPDATA%\\dervs\\area`, que
         não é repositório nem tem CLAUDE.md de projeto. Nada do `~/.claude` de
         desenvolvedor do dono entra aqui (antes entrava: o recado de handoff e o
         CLAUDE.md de dev faziam "abre a calculadora" virar conversa de branch).
       - `projeto` (emprestado): o Claude Code completo do dono (`~/.claude`,
         user+project+local), SÓ quando ele pede trabalho num projeto nomeado, e
         rodando DENTRO da pasta desse projeto. Sem pasta de projeto, não abre.
     O cérebro próprio precisa entrar com a assinatura uma vez
     (`scripts\\entrar-cerebro.ps1`); sem isso o painel e a voz dizem `FALTA_LOGIN`.

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
  - O gancho vale para TODA ferramenta e devolve `ask` para o que não é leitura
    pura: as regras `allow` do settings do dono rodam DEPOIS dele, e sem isso
    `Bash(git push:*)` executava sem nunca chegar ao painel.
  - O servidor MCP `dervs` não tem ferramenta "executar": `propor_acao` só entrega
    a proposta à `Fachada` da onda C (analisar/status); aprovar e executar são
    clique do dono, no painel, e o Motor nunca chega aqui.
  - Tudo que o Claude escreve é DADO, nunca ordem: a tela só usa `textContent`.

Só o que é puro (frase de voz, resumo para fala, nível de risco, caminho
protegido) roda sem o SDK; sem ele instalado o módulo carrega e `perguntar`
responde com um erro claro em vez de derrubar o DERVS.
"""
import asyncio
import datetime
import functools
import json
import os
import re
import sys
import threading
import time
import unicodedata
import uuid
import warnings

import dervs_config
import dervs_gasto
import dervs_permissoes as perm
import dervs_processos
import dervs_safety as seg

try:
    import claude_agent_sdk as sdk
except ImportError:                       # o DERVS abre mesmo assim, sem a sessão
    sdk = None
else:
    # O SDK avisa que `can_use_tool` não é consultado para as 2 ferramentas do
    # servidor `dervs` (estão em `allowed_tools`). É de propósito: nenhuma executa
    # nada, e o gancho PreToolUse continua valendo antes delas.
    warnings.filterwarnings("ignore", category=sdk.CanUseToolShadowedWarning)

# --- as travas ---------------------------------------------------------------
PERMISSION_MODE = "default"
MODOS_PROIBIDOS = ("bypassPermissions", "acceptEdits", "auto")

PERFIL_PADRAO = "dervs"
# dervs: só o cérebro próprio (o "user" é a pasta dele, ver `pasta_cerebro`).
# projeto/dono: o ~/.claude do dono inteiro, emprestado dentro de um projeto ("dono"
# é o nome antigo da config). equipe: só o harness do projeto, para as regras
# valerem iguais em qualquer PC (onda E). Perfil desconhecido = o menor.
SETTING_SOURCES = {"dervs": ("user",), "projeto": ("user", "project", "local"),
                   "dono": ("user", "project", "local"), "equipe": ("project",)}
FALTA_LOGIN = "Falta entrar com a sua assinatura no cérebro do DERVS: clique em Entrar."
FALTA_LOGIN_PROJETO = ("O Claude Code do seu computador está sem a assinatura entrada; "
                       "abra o Claude Code e entre de novo.")

LIMITE_PERGUNTA = 8000          # caracteres que a caixa de texto aceita
TIMEOUT_PEDIDO_S = 300          # sem resposta do dono em 5 min: NEGA
ESPERA_INTERRUPT_S = 5          # depois disto, mata a árvore de processos
LIMITE_RESUMO = 500             # o comando/caminho aparece INTEIRO até aqui; acima, o gancho nega
LIMITE_ENTRADA = 1000           # o resto dos parâmetros; o corte é contado e avisado na tela

FERRAMENTAS_DE_COMANDO = ("Bash", "PowerShell")
FERRAMENTAS_DE_ESCRITA = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_SO_LEITURA = ("Read", "Glob", "Grep", "LS", "TodoWrite", "NotebookRead")
# Só o que funciona: `central_coletar` (stub que sempre dizia "não instalado") saiu em
# 15/10; a leitura da máquina usa as ferramentas normais, e a Central tem o painel dela.
FERRAMENTAS_DERVS = ("mcp__dervs__propor_acao", "mcp__dervs__status_aprovacao")
# A pasta do código do DERVS. NÃO é a pasta de trabalho de nenhuma sessão (o perfil
# `dervs` roda em `pasta_area()`, o emprestado na pasta do projeto); fica só como uma
# das bases contra as quais um caminho relativo é conferido na leitura.
PASTA_HARNESS = os.path.dirname(os.path.abspath(__file__))

LIMITE_ITENS_PROPOSTA = 50
ETIQUETA_GASTO = "assinatura (equivalente)"     # medida, não cobrança


# --- caminhos protegidos (onda C) ---------------------------------------------
# A lista de verdade é a da onda C (`dervs_caminhos_protegidos`): normaliza o
# caminho, resolve 8.3/`\\?\`/junção/atalho e sabe do arquivo do dono
# (`caminhos_protegidos.json`). O import é OBRIGATÓRIO e falha FECHADA: sem o
# módulo, ou com resposta fora do formato `(bool, motivo)`, TUDO é protegido.
# (Antes havia um "piso interno" que deixava passar `\\?\C:\Windows\x`, nomes
# 8.3, `~\.claude.json` e a própria pasta do DERVS.)
#
# A C protege "dentro de repositório": o cérebro do DERVS não edita código de
# projeto. A exceção é o perfil `projeto` (`protegido_no_projeto`): só a pasta do
# projeto que o dono nomeou fica editável, sob as permissões do painel (cartão).
try:
    import dervs_caminhos_protegidos as _cp
except ImportError:
    _cp = None


def protegido_com_motivo(caminho, **kw):
    """`(protegido, motivo)`. Qualquer dúvida é `True`."""
    if _cp is None:
        return True, "o motor de caminhos protegidos (onda C) não está disponível"
    try:
        r = _cp.esta_protegido(caminho, **kw)
    except Exception as e:
        return True, f"erro ao consultar os caminhos protegidos ({type(e).__name__})"
    if isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], bool):
        return r[0], str(r[1])
    return True, "resposta inesperada do motor de caminhos protegidos"


def esta_protegido(caminho) -> bool:
    return protegido_com_motivo(caminho)[0]


def protegido_no_projeto(caminho, projeto, protegido=esta_protegido) -> bool:
    """Perfil `projeto`: a pasta do projeto pedido é editável (a onda C protege todo
    repositório, e sem isto o Claude emprestado nunca editava o que o dono pediu).
    Dentro dela seguem protegidos o `.git`, segredo e o próprio DERVS (repositório e
    %APPDATA%\\dervs), que só se libera quando o projeto pedido É o dervs-voz. Fora
    dela, a régua de sempre. Editável não é sem cartão: o gancho ainda pergunta.
    Na dúvida, protegido."""
    try:
        if _cp is None or not isinstance(caminho, str) or not caminho:
            return True
        raiz = _cp.normalizar(projeto) if isinstance(projeto, str) and projeto else None
        lexico = _cp._lexico(_para_windows(caminho))
        real = _cp.normalizar(lexico) if lexico else None
        if raiz is None or real is None:
            return protegido(caminho)
        if _cp.link_no_caminho(lexico) or _cp.link_no_caminho(real):
            return True
        c, r = _cp._chave(real), _cp._chave(raiz)
        # O próprio DERVS (código e %APPDATA%\dervs), dentro ou fora do projeto, a não ser
        # que o projeto pedido esteja dentro dele (é o dervs-voz).
        for pasta_do_dervs in (PASTA_HARNESS, dervs_config.CONFIG_DIR):
            d = _cp.normalizar(pasta_do_dervs) or _cp._lexico(pasta_do_dervs)
            if d is None:
                return True
            d = _cp._chave(d)
            if _cp._dentro(c, d) and not _cp._dentro(r, d):
                return True
        if not _cp._dentro(c, r):
            return protegido(caminho)
        if any(p.lower() == ".git" for p in re.split(r"[\\/]", os.path.relpath(real, raiz))):
            return True
        if _parece_segredo(caminho) or _parece_segredo(real):
            return True
        return False
    except Exception:
        return True


# Perfis de navegador (cookies, senhas salvas, histórico) e o ~/.claude.json (MCPs,
# tokens de conectores) não se leem, em nenhum perfil.
_AREA_SENSIVEL = re.compile(
    r"\.claude\.json\b|[\\/]User Data(?:[\\/]|$)|Mozilla[\\/]Firefox[\\/]Profiles|"
    r"BraveSoftware|Opera Software|[\\/]Chromium[\\/]", re.IGNORECASE)


def _nome_longo(caminho: str):
    """`GetLongPathNameW`: o nome completo de um caminho que EXISTE, ou `None`."""
    if os.name != "nt":
        return None
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetLongPathNameW(caminho, buf, 32768)
    return buf.value if 0 < n < 32768 else None


def _expandir_83(texto: str) -> str:
    """`ENV~1` é o `.env` e `SSH~1\\ID_ED2~1` é a chave SSH: a regex só vê o texto, então
    o nome curto (8.3) é expandido antes dela. Caminho que não existe fica como está."""
    if "~" not in texto:
        return texto
    try:
        return _nome_longo(texto) or texto
    except Exception:
        return texto


def _parece_segredo(texto: str) -> bool:
    return any(re.search(p, t, re.IGNORECASE) for t in {texto, _expandir_83(texto)}
               for p in seg._SEGREDOS)


def _para_windows(texto: str) -> str:
    """`~`, `%VAR%`, `$env:VAR` e o `/c/...` do Git Bash viram caminho do Windows."""
    t = texto.strip()
    m = re.match(r"^\$env:(\w+)(.*)$", t, re.IGNORECASE)
    if m:
        t = os.environ.get(m.group(1), "") + m.group(2)
    if t.startswith("~"):
        t = os.path.expanduser(t)
    if "%" in t:
        t = os.path.expandvars(t)
    m = re.match(r"^/([A-Za-z])(?:/(.*))?$", t)
    if m:
        t = m.group(1).upper() + ":\\" + (m.group(2) or "").replace("/", "\\")
    return t


_CURINGA_DE_BUSCA = re.compile(r"[*?\[]")
_TEM_UNIDADE_OU_RAIZ = re.compile(r"^(?:[A-Za-z]:|[\\/])")


def _chaves_de_leitura(texto: str, busca: bool):
    """`(chaves, motivo)`: as formas (escrita e real) do caminho, já como chave de
    comparação, ou o motivo de não dar para resolver (aí a leitura fecha). Numa
    busca, o curinga fica de fora: vale a pasta literal antes dele."""
    t = _para_windows(texto)
    if busca:
        m = _CURINGA_DE_BUSCA.search(t)
        if m:
            t = t[:m.start()]
            t = t[:max(t.rfind("\\"), t.rfind("/")) + 1]
    if not t or not _TEM_UNIDADE_OU_RAIZ.match(t):
        bases = (PASTA_HARNESS, os.getcwd())          # relativo: a pasta da sessão
        candidatos = [os.path.join(b, t) for b in bases]
    else:
        candidatos = [t]
    chaves = []
    for c in candidatos:
        lexico = _cp._lexico(c)
        real = _cp.normalizar(lexico) if lexico else None
        if lexico is None or real is None:
            return None, "não deu para resolver o caminho (relativo, de rede, disfarçado)"
        if _cp.link_no_caminho(lexico) or _cp.link_no_caminho(real):
            return None, "passa por uma junção ou atalho — o destino pode ser trocado"
        chaves += [_cp._chave(lexico), _cp._chave(real)]
    return chaves, ""


def leitura_proibida(caminho, busca: bool = False):
    """Motivo pelo qual o Claude NÃO pode LER este caminho (segredo, ou pasta que
    o dono marcou como protegida — dado de paciente), ou `None`. Vale para
    qualquer perfil: o perfil `equipe` não tem regra de `deny` de Read.

    `busca=True` (Grep/Glob/LS): a raiz da busca também não pode CONTER uma pasta
    protegida — `Grep` em `C:\\` varre a pasta do paciente. A decisão é por contenção
    contra as pastas do dono, já resolvidas; NÃO se pergunta ao motor de protegidos
    (ele já negava a raiz do disco por outro motivo, e isso liberava a leitura)."""
    if not isinstance(caminho, str) or not caminho:
        return None
    if _parece_segredo(caminho):
        return "parece um arquivo de segredo (chave, senha, credencial)"
    if any(_AREA_SENSIVEL.search(t) for t in {caminho, _expandir_83(caminho)}):
        return "é área de login do dono (perfil de navegador ou ~/.claude.json)"
    if _cp is None:
        return "o motor de caminhos protegidos (onda C) não está disponível"
    try:
        extras = _cp.carregar_extras(_cp.arquivo_extras())
    except Exception:
        return "a lista de pastas protegidas está ilegível — nada é lido até consertar"
    if not extras:
        return None
    try:
        pastas = []
        for extra in extras:
            resolvido = _cp.normalizar(extra) or _cp._lexico(extra)
            if resolvido is None:
                return "um caminho da lista de pastas protegidas é inválido — nada é lido"
            pastas.append(_cp._chave(resolvido))
        chaves, erro = _chaves_de_leitura(caminho, busca)
        if chaves is None:
            return f"{erro} — com pasta protegida configurada, a leitura fecha"
        for c in chaves:
            for p in pastas:
                if _cp._dentro(c, p):
                    return "fica numa pasta que o dono marcou como protegida"
                if busca and _cp._dentro(p, c):
                    return "a busca abrangeria uma pasta que o dono marcou como protegida"
    except Exception as e:
        return f"erro ao conferir as pastas protegidas ({type(e).__name__}) — a leitura fecha"
    return None


# --- risco e resumo de uma ferramenta -----------------------------------------
# A lista de "leitura de verdade" é PRÓPRIA e curta. A do `dervs_safety` foi feita
# para o planejador de VOZ e aceita `chrome`, `explorer`, `code`... só pelo prefixo:
# um Claude induzido por conteúdo hostil abria o navegador com dado da conversa na
# URL e o gancho devolvia `{}`. Aqui, tudo fora da lista é `ask`.
# `git -C pasta push`, `git -c x=y push`, `git --git-dir=... push`: a opção antes do verbo
# não pode esconder o envio (revisão 15/10). Na dúvida (a palavra aparece depois de
# `git`), é rede: o pior caso é um cartão a mais.
_REDE = re.compile(
    r"\b(?:git\b[^;&|\r\n]*?\s(?:push|remote|clone|fetch|pull|ls-remote|submodule)\b|gh|curl|wget|"
    r"Invoke-WebRequest|iwr|Invoke-RestMethod|irm|Start-BitsTransfer|bitsadmin|scp|sftp|"
    r"ssh|ftp|telnet|nc|ncat|socat|npm\s+publish|Test-NetConnection|tnc)\b", re.IGNORECASE)
# Abre navegador, editor, programa ou URL: leva o dado da conversa para fora do PC.
_ABRE_ALGO = re.compile(
    r"(?<![\w-])(?:chrome|msedge|firefox|brave|iexplore|opera|vivaldi|explorer|code|"
    r"xdg-open|open|start|start-process|saps|ii|invoke-item|mshta|rundll32|regsvr32|"
    r"wscript|cscript|msiexec)(?![\w-])", re.IGNORECASE)
# Qualquer URL (`https://`, `ftp://`, `file://`...) ou caminho de rede (`\\host`).
_URL_OU_UNC = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://|\\\\[^\\\s]")
_GIT_LEITURA = re.compile(
    r"^\s*git\s+(?:status|log|diff|show)(?:\s+[^\s;&|`$<>()\"']+)*\s*$", re.IGNORECASE)
_GIT_BRANCH_LISTA = re.compile(
    r"^\s*git\s+branch(?:\s+(?:-a|-r|-v|-vv|--list|--all|--remotes))*\s*$", re.IGNORECASE)
_GIT_PERIGO = re.compile(
    r"--output|--ext-diff|--textconv|--exec|--upload-pack|--receive-pack|--git-dir|"
    r"--work-tree|--open-files-in-pager|--no-index|(?:^|\s)-c(?:\s|$)", re.IGNORECASE)
# Sem argumento: `date`/`whoami /all`/`hostname -x` mudam ou despejam coisa em alguns shells.
_LEITURA_SEM_ARGUMENTO = re.compile(
    r"^\s*(?:pwd|whoami|hostname|get-location|get-date|date(?:\s+/t)?)\s*$", re.IGNORECASE)
_LEITURA_COM_ARGUMENTO = re.compile(
    r"^\s*(?:dir|ls|get-childitem|gci|get-process|test-path|echo)(?:\s+(?P<args>.*))?$",
    re.IGNORECASE | re.DOTALL)
# Argumento limpo: só letras, números, espaço e `. _ - \ / : ~ * ? ' " ,`. Fora
# `$ ; & | > < ` % ^ = @ { } ( ) [ ]` (expansão, encadeamento, redirecionamento,
# variável e subexpressão do PowerShell: `echo ([IO.File]::Delete(...))` executa).
_ARGUMENTO_LIMPO = re.compile(r"^[\w\s.\\/:~*?'\",-]*$")
# `Env:`, `HKCU:`, `Cert:`, `Variable:` despejam segredo/registro; só unidade de uma letra.
_UNIDADE_ESTRANHA = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9_]{2,}:")
_NOME_DE_REDE = re.compile(r"fetch|http|browser|navigate|web|url|download|request|search",
                           re.IGNORECASE)


def _git_e_leitura(comando: str) -> bool:
    if _GIT_PERIGO.search(comando):
        return False
    return bool(_GIT_LEITURA.match(comando) or _GIT_BRANCH_LISTA.match(comando))


def _leitura_de_verdade(comando: str) -> bool:
    """Só o que a lista curta reconhece INTEIRO. `cat`/`type`/`Get-Content` ficam de
    fora de propósito: para ler arquivo existe a ferramenta Read (com o filtro de
    segredos); `env`, `set`, `history`, `find -exec/-delete`, `systeminfo` também."""
    if _URL_OU_UNC.search(comando) or _ABRE_ALGO.search(comando):
        return False
    if _git_e_leitura(comando) or _LEITURA_SEM_ARGUMENTO.match(comando):
        return True
    m = _LEITURA_COM_ARGUMENTO.match(comando)
    if not m:
        return False
    args = m.group("args") or ""
    return bool(_ARGUMENTO_LIMPO.match(args) and not _UNIDADE_ESTRANHA.search(args))


def classificar(nome: str, entrada: dict) -> dict:
    """`{"nivel": reversivel|muda_estado|destrutivo, "rede": bool}` — a mesma
    régua serve para o gancho, para o diálogo e para a regra "voz não aprova"."""
    entrada = entrada if isinstance(entrada, dict) else {}
    if nome in _SO_LEITURA or nome in FERRAMENTAS_DERVS:
        return {"nivel": "reversivel", "rede": False}
    if nome in FERRAMENTAS_DE_COMANDO:
        comando = str(entrada.get("command", ""))
        d = seg.decidir_risco(comando)
        rede = bool(d["toca_alvo"] or _REDE.search(comando) or _ABRE_ALGO.search(comando)
                    or _URL_OU_UNC.search(comando))
        nivel = d["nivel"]
        if rede or (nivel == "reversivel" and not _leitura_de_verdade(comando)):
            nivel = seg._nivel_max(nivel, "muda_estado")
        return {"nivel": nivel, "rede": rede}
    rede = nome in ("WebFetch", "WebSearch") or (
        nome.startswith("mcp__") and bool(_NOME_DE_REDE.search(nome)))
    return {"nivel": "muda_estado", "rede": rede}


def nivel_da_ferramenta(nome: str, entrada: dict) -> str:
    return classificar(nome, entrada)["nivel"]


def _campo_do_resumo(nome: str, entrada: dict) -> str:
    entrada = entrada if isinstance(entrada, dict) else {}
    for chave in ("command", "file_path", "notebook_path", "path", "pattern",
                  "url", "query"):
        if isinstance(entrada.get(chave), str) and entrada[chave]:
            return entrada[chave]
    return json.dumps(entrada, ensure_ascii=False, default=str)


def resumo_da_ferramenta(nome: str, entrada: dict) -> str:
    return _campo_do_resumo(nome, entrada)[:LIMITE_RESUMO]


def para_a_tela(nome: str, entrada: dict):
    """`(resumo, entrada_cortada, escondidos)` do que o diálogo mostra. O comando
    de Bash/PowerShell aparece INTEIRO no resumo (o gancho nega o que não cabe),
    então sai do JSON; qualquer outro corte é contado em `escondidos`."""
    campo = _campo_do_resumo(nome, entrada)
    resto = dict(entrada) if isinstance(entrada, dict) else {}
    if nome in FERRAMENTAS_DE_COMANDO:
        resto.pop("command", None)
    completo = json.dumps(resto, ensure_ascii=False, default=str)
    escondidos = max(0, len(campo) - LIMITE_RESUMO) + max(0, len(completo) - LIMITE_ENTRADA)
    return campo[:LIMITE_RESUMO], completo[:LIMITE_ENTRADA], escondidos


# --- o gancho PreToolUse -------------------------------------------------------
_TOKEN = re.compile(r"[^\s\"'|;&<>()]+")
_FERRAMENTAS_DE_LEITURA_COM_CAMINHO = ("Read", "Glob", "Grep", "LS", "NotebookRead")


_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
# `/x/...` é o caminho do Git Bash (`/c/Users/...`); `/s` ou `/t` sozinho é opção.
_ABSOLUTO = re.compile(r"^(?:[A-Za-z]:|\\|/[^\\/]+[\\/]|~|%|\$env:)", re.IGNORECASE)
_NOME_CURTO_83 = re.compile(r"(?:^|[\\/])[^\\/]{1,8}~\d")
_PEDACO_SENSIVEL = re.compile(r"(?:^|[\\/])\.(?:git|claude|ssh)(?:[\\/]|$)", re.IGNORECASE)


def _caminhos_no_comando(comando: str):
    """Pedaços do comando que parecem caminho ABSOLUTO (unidade, UNC, `~`, `%VAR%`,
    `$env:`), mais qualquer pedaço com `.git`/`.claude`/`.ssh` no meio. URL não é
    caminho. Caminho relativo qualquer não dá para resolver sem o diretório do
    comando (a onda C o trata como inválido), então só entra se tiver esses nomes.
    É heurística: o objetivo é não deixar um comando que MUDA algo passar por
    cima de pasta protegida."""
    for t in _TOKEN.findall(comando or ""):
        if _URL.match(t):
            continue
        if _ABSOLUTO.match(t) or _PEDACO_SENSIVEL.search(t) or _NOME_CURTO_83.search(t):
            yield t


def motivo_de_bloqueio(nome: str, entrada: dict, protegido=esta_protegido,
                       leitura=leitura_proibida):
    """Devolve o motivo (texto para o Claude ler) se a ferramenta deve ser
    NEGADA antes de qualquer regra; `None` deixa seguir."""
    entrada = entrada if isinstance(entrada, dict) else {}
    proposta = "Use a ferramenta mcp__dervs__propor_acao: o dono decide no painel."
    if nome in FERRAMENTAS_DE_COMANDO:
        comando = str(entrada.get("command", ""))
        if len(comando) > LIMITE_RESUMO or "\n" in comando or "\r" in comando:
            return ("O DERVS bloqueou: o comando é longo demais ou tem quebra de linha, e o "
                    "painel só mostra ao dono uma linha curta. Divida em passos menores "
                    "(um comando curto de cada vez).")
        d = seg.decidir_risco(comando)
        if d["nivel"] == "destrutivo":
            porque = "; ".join(d["motivos"]) or "destrutivo"
            return f"O DERVS bloqueou este comando ({porque}). {proposta}"
        # Segredo e pasta do dono valem para QUALQUER nível: "reversível" é só o que o
        # `dervs_safety` reconhece, e ele não sabe quais pastas o dono protegeu.
        # `protegido` (escrita) só onde o comando muda algo: listar `C:\Windows` é liberado.
        for c in _caminhos_no_comando(comando):
            if d["nivel"] != "reversivel" and protegido(c):
                return f"O DERVS bloqueou: o comando mexe em caminho protegido ({c}). {proposta}"
            porque = leitura(c)
            if porque:
                return f"O DERVS bloqueou: o comando toca {c[:120]} e {porque}. {proposta}"
        return None
    if nome in FERRAMENTAS_DE_ESCRITA:
        caminho = (entrada.get("file_path") or entrada.get("notebook_path")
                   or entrada.get("path"))
        if not isinstance(caminho, str) or not caminho:
            return f"O DERVS bloqueou: a escrita veio sem caminho legível. {proposta}"
        if protegido(caminho):
            return f"O DERVS bloqueou: {caminho} é um caminho protegido. {proposta}"
        return None
    if nome in _FERRAMENTAS_DE_LEITURA_COM_CAMINHO:
        for chave in ("file_path", "path", "notebook_path", "pattern", "glob"):
            valor = entrada.get(chave)
            if not isinstance(valor, str) or not valor:
                continue
            # `pattern` do Grep é o TEXTO procurado, não um caminho.
            if chave == "pattern" and nome == "Grep":
                continue
            motivo = leitura(valor, busca=nome not in ("Read", "NotebookRead"))
            if motivo:
                return f"O DERVS não deixa o Claude ler {valor[:120]}: {motivo}."
    return None


def decisao_do_gancho(nome, entrada, protegido=esta_protegido, leitura=leitura_proibida,
                      niveis=None, raizes=None):
    """`("deny", motivo)`, `("ask", motivo)` ou `(None, None)`.

    `ask` faz o pedido cair SEMPRE no `can_use_tool` (o diálogo do painel), mesmo
    que uma regra `allow` do settings do dono o liberasse: o gancho roda antes das
    regras. Só passa direto a leitura pura, as 2 ferramentas do servidor `dervs`
    e o comando que o `dervs_safety` classifica como reversível (sem rede)."""
    motivo = motivo_de_bloqueio(nome, entrada, protegido, leitura)
    if motivo:
        return "deny", motivo
    if niveis is not None:
        # Política do dono (painel "O que o DERVS pode fazer"): roda DEPOIS dos
        # bloqueios acima, então só reduz poder. `permitir` devolve (None, None) e o
        # `_can_use_tool` aprova sem cartão; destrutivo/servidor nunca chegam a isso.
        d = perm.decidir(nome, entrada, classificar(nome, entrada), niveis, raizes or ())
        if d["acao"] == "negar":
            return "deny", d["motivo"]
        if d["acao"] == "permitir":
            return None, None
        return "ask", "O DERVS pede a confirmação do dono no painel."
    if nome in _SO_LEITURA or nome in FERRAMENTAS_DERVS:
        return None, None
    if nome in FERRAMENTAS_DE_COMANDO and classificar(nome, entrada)["nivel"] == "reversivel":
        return None, None
    return "ask", "O DERVS pede a confirmação do dono no painel."


def criar_gancho(protegido=esta_protegido, leitura=leitura_proibida, niveis_fn=None,
                 raizes_fn=None):
    """O callback `PreToolUse` do SDK, registrado SEM filtro de ferramenta.
    Falha FECHADA: se o próprio gancho quebrar, nega."""
    async def gancho(entrada, tool_use_id, contexto):
        try:
            acao, motivo = decisao_do_gancho(entrada.get("tool_name", ""),
                                             entrada.get("tool_input") or {}, protegido, leitura,
                                             niveis_fn() if niveis_fn else None,
                                             raizes_fn() if raizes_fn else None)
        except Exception as e:
            acao = "deny"
            motivo = f"O DERVS não conseguiu avaliar a ferramenta ({type(e).__name__}); negada."
        if acao is None:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": acao,
                                       "permissionDecisionReason": motivo}}
    return gancho


# --- opções da sessão ----------------------------------------------------------

def _unidades_para_leitura():
    if sys.platform != "win32":
        return []
    return [(os.environ.get("SystemDrive") or "C:") + "\\"]


def pasta_cerebro() -> str:
    """O `CLAUDE_CONFIG_DIR` do cérebro próprio: `%APPDATA%\\dervs\\cerebro`."""
    return os.path.join(dervs_config.CONFIG_DIR, "cerebro")


def pasta_area() -> str:
    """A pasta de trabalho do perfil `dervs`: neutra, sem git e sem CLAUDE.md de projeto."""
    return os.path.join(dervs_config.CONFIG_DIR, "area")


PERSONA = """\
# DERVS

Você é o DERVS, o assistente pessoal do dono deste computador, no estilo do JARVIS:
educado, direto, prestativo e com um toque de humor discreto.

## Como falar
- Sempre em português do Brasil, simples, sem jargão técnico.
- Respostas curtas, boas de ouvir em voz alta: uma ou duas frases. Detalhe só se ele pedir.
- O dono não é técnico. Explique o que vai fazer em palavras do dia a dia.
- Sem listas longas, tabelas ou blocos de código, a não ser que ele peça.

## Como agir
- Coisa fácil e segura (abrir um programa, ver uma informação, responder uma dúvida): faça direto.
- Na dúvida sobre o que ele quer, pergunte uma coisa só, com a sua sugestão.
- Para mudar qualquer coisa no computador, o painel do DERVS pede o OK dele. Nunca tente contornar.
- Para limpar, desinstalar ou desativar, proponha com a ferramenta mcp__dervs__propor_acao.

## O que não fazer
- Não fale do seu próprio código, de branches, commits ou do processo de desenvolvimento
  do DERVS, a não ser que ele pergunte.
- Trabalho de programação num projeto não é com você: diga a ele para pedir
  "no projeto tal, ..." que o DERVS chama o Claude Code dentro daquele projeto.
"""

_SETTINGS_CEREBRO = {
    # Sem "hooks": nenhum gancho de terminal roda aqui. O único gancho é o PreToolUse
    # em processo (`criar_gancho`), que o DERVS passa pelas opções do SDK.
    "permissions": {"defaultMode": PERMISSION_MODE, "allow": [], "deny": []},
}

_LEIA_ME = {
    "skills": "Skills do DERVS. Só valem para o cérebro próprio do DERVS, nunca para o "
              "Claude Code de desenvolvimento do dono (que mora em ~/.claude).\n",
    "agents": "Agentes do DERVS. Só valem para o cérebro próprio do DERVS, nunca para o "
              "Claude Code de desenvolvimento do dono (que mora em ~/.claude).\n",
}


def _escrever_se_faltar(caminho: str, conteudo: str):
    """Grava só se o arquivo NÃO existe: o que o dono editou nunca é sobrescrito."""
    try:
        with open(caminho, "x", encoding="utf-8", newline="\n") as f:
            f.write(conteudo)
    except FileExistsError:
        pass


def preparar_cerebro(base=None, area=None):
    """Monta (idempotente) a pasta do cérebro próprio e a pasta de trabalho neutra."""
    base = base or pasta_cerebro()
    area = area or pasta_area()
    for pasta in (base, area, os.path.join(base, "skills"), os.path.join(base, "agents")):
        os.makedirs(pasta, exist_ok=True)
    _escrever_se_faltar(os.path.join(base, "CLAUDE.md"), PERSONA)
    _escrever_se_faltar(os.path.join(base, "settings.json"),
                        json.dumps(_SETTINGS_CEREBRO, ensure_ascii=False, indent=2) + "\n")
    for sub, texto in _LEIA_ME.items():
        _escrever_se_faltar(os.path.join(base, sub, "README.md"), texto)


_SEM_LOGIN = re.compile(r"not logged in|run /login|invalid api key|oauth token has expired|"
                        r"authentication_failed", re.IGNORECASE)


def falta_login(texto) -> bool:
    """O erro do CLI é de assinatura não entrada (ou vencida)?"""
    return isinstance(texto, str) and bool(_SEM_LOGIN.search(texto))


def montar_opcoes(perfil, *, can_use_tool, gancho, servidor_mcp, resume=None,
                  cwd=None, cli_path=None):
    if sdk is None:
        raise RuntimeError("o pacote claude-agent-sdk não está instalado "
                           "(rode: pip install -r requirements.txt)")
    if perfil == "dervs":
        # Cérebro próprio: nem um `cwd` pedido de fora o leva para um repositório.
        preparar_cerebro()
        cwd, ambiente, so_o_dervs = pasta_area(), {"CLAUDE_CONFIG_DIR": pasta_cerebro()}, True
    elif not cwd:
        raise ValueError("o Claude Code do dono só é emprestado dentro da pasta de um projeto")
    else:
        ambiente, so_o_dervs = {}, False
    if cli_path is None:
        import dervs_brain
        cli_path = dervs_brain._resolver_claude()
    fontes = SETTING_SOURCES.get(perfil, SETTING_SOURCES["equipe"])
    return sdk.ClaudeAgentOptions(
        permission_mode=PERMISSION_MODE,
        setting_sources=list(fontes),
        cwd=cwd,
        env=ambiente,                           # o SDK soma ao ambiente herdado
        strict_mcp_config=so_o_dervs,           # no cérebro próprio, MCP só o `dervs`
        cli_path=cli_path,
        add_dirs=_unidades_para_leitura(),      # leitura da máquina inteira
        include_partial_messages=True,          # streaming palavra a palavra
        can_use_tool=can_use_tool,
        # SEM filtro de ferramenta (`matcher=None`): as regras `allow` do settings do
        # dono são resolvidas DEPOIS do gancho, e um filtro deixava as demais
        # ferramentas (ex.: `Bash(git push:*)`) executarem sem chegar ao painel.
        hooks={"PreToolUse": [sdk.HookMatcher(matcher=None, hooks=[gancho])]},
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


def cita_o_claude(texto: str) -> bool:
    """O dono citou o Claude ("pede pro Claude…", "Claude, …", "analisa X com o Claude"): ele
    escolheu quem atende, e nenhuma reserva automática troca o executor."""
    return re.search(r"\bclaude\b", texto or "", re.IGNORECASE) is not None


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


def _pids_filhos():
    """PIDs dos filhos diretos DESTE processo (para achar o `claude` sem depender
    de atributo privado do SDK)."""
    try:
        import psutil
        return {c.pid for c in psutil.Process().children()}
    except Exception:
        return set()


def _marca_do_pid(pid):
    try:
        import psutil
        return psutil.Process(pid).create_time()
    except Exception:
        return None


def _pid_confere(pid, marca) -> bool:
    """O PID ainda é o mesmo processo de quando o registramos (PID reaproveitado
    pelo Windows não pode ser morto por engano)."""
    if pid is None or marca is None:
        return False
    return _marca_do_pid(pid) == marca


class _ProcessoPorPid:
    """A cara de `Popen` para `encerrar_arvore` quando só se conhece o PID."""

    def __init__(self, pid):
        self.pid = pid

    def poll(self):
        try:
            import psutil
            return None if psutil.Process(self.pid).is_running() else 0
        except Exception:
            return 0

    def kill(self):
        import psutil
        psutil.Process(self.pid).kill()

    def wait(self, timeout=None):
        limite = time.time() + (timeout or 0)
        while self.poll() is None and time.time() < limite:
            time.sleep(0.05)


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
                 fachada_fabrica=None, cwd=None, protegido=esta_protegido,
                 timeout_pedido=TIMEOUT_PEDIDO_S, espera_interrupt=ESPERA_INTERRUPT_S,
                 encerrar_arvore=dervs_processos.encerrar_arvore, niveis_fn=None,
                 raizes_fn=None, perfil_projeto="projeto"):
        # `niveis_fn()` devolve a matriz de permissões do dono, lida na hora (o painel
        # vale sem reiniciar). Sem ela, tudo vai ao cartão como antes.
        self._niveis_fn = niveis_fn
        self._raizes_fn = raizes_fn      # pastas de projeto onde escrever sozinho vale
        self._ao_evento = ao_evento
        self._ao_texto_final = ao_texto_final
        self._ao_aviso = ao_aviso
        self.perfil = perfil if perfil in SETTING_SOURCES else PERFIL_PADRAO
        # O harness emprestado quando o pedido é num projeto (config `claude_perfil`).
        self._perfil_projeto = (perfil_projeto if perfil_projeto in SETTING_SOURCES
                                and perfil_projeto != "dervs" else "projeto")
        self._alvo_base = (self.perfil, cwd)
        self._alvo = self._alvo_base          # (perfil, cwd) do cliente atual
        self._sessoes = {}                    # session_id de cada alvo já usado
        self._sem_login = False
        self._fabrica = fabrica_cliente or self._fabrica_padrao
        self._arquivo_sessao = caminho_sessao() if arquivo_sessao == "padrao" else arquivo_sessao
        # A ÚNICA porta para o motor de aprovação (onda C): a `Fachada` (só
        # `analisar` e `status`). O Motor, o cartão e a senha de uso NUNCA chegam aqui.
        self._fachada_fabrica = fachada_fabrica
        self._fachada = None
        self._cwd = cwd
        self._protegido = protegido
        self._protegido_atual = protegido     # no projeto emprestado, a pasta dele é editável
        self._timeout_pedido = timeout_pedido
        self._espera_interrupt = espera_interrupt
        self._encerrar_arvore = encerrar_arvore

        self._trava = threading.Lock()
        self._laco = None
        self._comandos = None
        self._cliente = None                  # só o trabalhador mexe
        self._pedidos = _Pedidos()
        self._pid = None                      # o `claude` que o SDK abriu, se soubermos
        self._pid_marca = None
        self._ocupado = False
        self._interrompido = False
        self._fim_do_turno = threading.Event()
        self._fim_do_turno.set()
        self._session_id = None
        self._custo_acumulado = 0.0
        self._geracao = 0                     # sobe a cada nova_conversa
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

    def perguntar(self, texto: str, origem: str = "painel", projeto=None) -> bool:
        """`projeto` (pasta) empresta o Claude Code do dono DENTRO dela; sem ele,
        responde o cérebro próprio do DERVS."""
        texto = (texto or "").strip()
        if not texto or len(texto) > LIMITE_PERGUNTA or self._encerrada:
            return False
        if projeto is not None and not (isinstance(projeto, str) and os.path.isdir(projeto)):
            return False
        with self._trava:
            if self._ocupado:
                return False
            self._ocupado = True
            self._interrompido = False
            self._fim_do_turno = threading.Event()
        laco = self._garantir_laco()
        laco.call_soon_threadsafe(self._comandos.put_nowait, ("turno", (texto, origem, projeto)))
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
        self._geracao += 1            # o resultado de um turno anterior fica velho
        self._session_id = None
        self._sessoes.clear()
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
                falha = None
                try:
                    if tipo == "turno":
                        await self._turno(*arg)
                    elif tipo == "reiniciar":
                        await self._descartar_cliente()
                    else:
                        await self._descartar_cliente()
                        break
                except Exception as e:
                    falha = f"{type(e).__name__}: {str(e)[:200]}"
                    sys.stderr.write(f"claude_code: comando {tipo} falhou: {falha}" + chr(10))
                finally:
                    if tipo == "turno" and self._ocupado:
                        self._liberar_turno(falha)
        finally:
            self._trabalhador_parou.set()

    def _liberar_turno(self, falha):
        """O turno acabou sem passar pelo fim normal (exceção fora do `try` do
        `_turno`): solta o painel, senão ele fica ocupado para sempre."""
        self._pedidos.negar_todos()
        with self._trava:
            self._ocupado = False
            fim = self._fim_do_turno
        self._emitir("claude_fim", {"ok": False, "custo": 0.0,
                                    "erro": falha or "o turno terminou sem resultado"})
        fim.set()

    def _fabrica_padrao(self, opcoes):
        return sdk.ClaudeSDKClient(options=opcoes)

    async def _mirar(self, projeto):
        """Troca de cérebro entre turnos: pedido num projeto usa o harness emprestado,
        na pasta dele; o resto volta ao do DERVS. Cada um retoma a PRÓPRIA conversa."""
        alvo = (self._perfil_projeto, projeto) if projeto else self._alvo_base
        if alvo == self._alvo:
            return
        await self._descartar_cliente()
        if self._session_id:
            self._sessoes[self._alvo] = self._session_id
        self._alvo = alvo
        self._session_id = self._sessoes.get(alvo)
        self._protegido_atual = (self._protegido if alvo == self._alvo_base else
                                 functools.partial(protegido_no_projeto, projeto=alvo[1],
                                                   protegido=self._protegido))

    async def _conectar(self):
        if self._cliente is not None:
            return
        base = self._alvo == self._alvo_base
        if self._session_id is None and self._arquivo_sessao and base:
            self._session_id = ler_sessao(self._arquivo_sessao, self.perfil)
        servidor = criar_servidor_dervs(self)[0]
        perfil, cwd = self._alvo
        opcoes = montar_opcoes(
            perfil, can_use_tool=self._can_use_tool,
            gancho=criar_gancho(self._protegido_atual, niveis_fn=self._niveis_fn,
                                raizes_fn=self._raizes_fn), servidor_mcp=servidor,
            resume=self._session_id, cwd=cwd)
        cliente = self._fabrica(opcoes)
        antes = _pids_filhos()
        try:
            await cliente.connect()
        except Exception:
            if self._session_id:            # não deu para retomar: a próxima começa limpa
                self._session_id = None
                if base:
                    apagar_sessao(self._arquivo_sessao)
            raise
        self._cliente = cliente
        self._custo_acumulado = 0.0
        self._registrar_pid(antes)

    def _registrar_pid(self, antes):
        """Guarda o PID do `claude` (com a hora de criação, contra PID reaproveitado).
        Vem do SDK se o atributo existir; senão, é o filho novo deste processo."""
        pid = getattr(self._processo_do_cliente(), "pid", None)
        if pid is None:
            novos = _pids_filhos() - antes
            pid = min(novos) if novos else None
        self._pid = pid
        self._pid_marca = _marca_do_pid(pid) if pid is not None else None

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
        # `_transport._process` é atributo PRIVADO do SDK: pode sumir numa versão
        # nova. Por isso tudo é getattr, e `_matar_processo` tem o PID guardado.
        transporte = getattr(self._cliente, "_transport", None)
        return getattr(transporte, "_process", None)

    def _matar_processo(self):
        proc = self._processo_do_cliente()
        if proc is not None:
            alvo = _ProcessoAnyio(proc)
        elif self._pid is not None and _pid_confere(self._pid, self._pid_marca):
            alvo = _ProcessoPorPid(self._pid)
        else:
            sys.stderr.write("claude_code: não sei qual processo encerrar (o SDK mudou?)\n")
            return
        try:
            self._encerrar_arvore(alvo)
        except Exception:
            pass

    # ---- um turno ---------------------------------------------------------------
    def _emitir(self, verbo, dados):
        try:
            self._ao_evento(verbo, dados)
        except Exception as e:
            sys.stderr.write(f"claude_code: falha ao avisar o painel: {e}\n")

    async def _turno(self, texto, origem, projeto=None):
        self._texto_emitido = False
        self._separar = False
        self._streamou = False
        self._partes = []
        self._sem_login = False
        erro = None
        resultado = None
        geracao = self._geracao
        await self._mirar(projeto)            # antes do custo: trocar de cliente o zera
        base_custo = self._custo_acumulado
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
        custo, texto_final = self._fechar_resultado(resultado, geracao, base_custo)
        ok = erro is None and resultado is not None and not resultado.is_error
        if self._interrompido:
            ok, erro = False, "interrompido"
        elif erro is None and resultado is None:
            ok, erro = False, "o Claude não devolveu resultado"
        elif erro is None and resultado.is_error:
            detalhe = resultado.result or "; ".join(resultado.errors or []) or resultado.subtype
            erro = str(detalhe)[:300]
        if not ok and not self._interrompido and (self._sem_login or falta_login(erro)):
            # Erro genérico do CLI não diz nada ao dono: diga o que falta e onde clicar.
            erro = FALTA_LOGIN if self._alvo == self._alvo_base else FALTA_LOGIN_PROJETO
            if self._ao_aviso:
                try:
                    self._ao_aviso(erro)
                except Exception:
                    pass
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

    def _fechar_resultado(self, resultado, geracao=None, base_custo=0.0):
        """Grava o `session_id` e o custo do `ResultMessage`; devolve (custo do
        turno, texto final). O `total_cost_usd` do SDK é ACUMULADO na sessão, então
        o que se registra é a diferença."""
        if resultado is None:
            return 0.0, "".join(self._partes)
        velho = geracao is not None and geracao != self._geracao
        if velho:
            pass    # turno anterior à nova_conversa: não ressuscita a sessão apagada
        elif resultado.session_id and resultado.session_id != self._session_id:
            self._session_id = resultado.session_id
            if self._alvo == self._alvo_base:     # a do projeto emprestado não vai ao disco
                gravar_sessao(self._arquivo_sessao, self._session_id, self.perfil)
        custo = 0.0
        total = resultado.total_cost_usd
        if isinstance(total, (int, float)) and total >= 0:
            ref = base_custo if velho else self._custo_acumulado
            custo = total - ref if total >= ref else total
            if not velho:
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
            if getattr(msg, "error", None) == "authentication_failed":
                self._sem_login = True
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
        risco = classificar(nome, entrada)
        nivel = risco["nivel"]
        if self._niveis_fn is not None and nivel != "destrutivo":
            try:
                d = perm.decidir(nome, entrada, risco, self._niveis_fn(),
                                self._raizes_fn() if self._raizes_fn else ())
                livre = (d["acao"] == "permitir"
                         and not motivo_de_bloqueio(nome, entrada, self._protegido_atual,
                                                    leitura_proibida))
            except Exception:
                livre = False          # política ilegível: cai no cartão, nunca no "sim"
            if livre:
                perm.registrar(d, nome, resumo_da_ferramenta(nome, entrada))
                return sdk.PermissionResultAllow()
        id_, futuro = self._pedidos.abrir(asyncio.get_running_loop(), nivel)
        resumo, cortada, escondidos = para_a_tela(nome, entrada)
        self._emitir("claude_pedido", {
            "id": id_, "ferramenta": nome, "resumo": resumo,
            "entrada_cortada": cortada, "escondidos": escondidos, "nivel": nivel,
            "rede": risco["rede"], "expira_s": int(self._timeout_pedido)})
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
    def obter_fachada(self):
        """A `Fachada` da onda C, criada na primeira vez que alguém a pede (o Motor
        cria pasta e arquivos em %LOCALAPPDATA%\\dervs)."""
        if self._fachada is None and self._fachada_fabrica is not None:
            try:
                self._fachada = self._fachada_fabrica()
            except Exception as e:
                sys.stderr.write(f"claude_code: motor de aprovação indisponível ({type(e).__name__})\n")
        return self._fachada


def criar_servidor_dervs(sessao: SessaoClaudeCode):
    """O servidor MCP em processo `dervs`. Devolve (config para as opções,
    {nome: ferramenta}). NÃO existe ferramenta que execute: executar é clique."""
    if sdk is None:
        raise RuntimeError("claude-agent-sdk não instalado")

    @sdk.tool("propor_acao",
              "Propõe ao dono uma lista de ações (limpar, desinstalar, desativar...). "
              "NÃO executa nada: o motor de aprovação confere cada item no disco e monta "
              "um relatório que o dono lê e aprova no painel. Cada item: acao, alvo, "
              "por_que_seguro (obrigatório), explicacao, o_que_muda.",
              {"type": "object", "required": ["itens"],
               "properties": {"itens": {"type": "array", "items": {"type": "object"}}}})
    async def propor_acao(args):
        itens = args.get("itens") if isinstance(args, dict) else None
        if (not isinstance(itens, list) or not 1 <= len(itens) <= LIMITE_ITENS_PROPOSTA
                or not all(isinstance(i, dict) for i in itens)):
            return _texto_mcp(f"itens precisa ser uma lista de 1 a {LIMITE_ITENS_PROPOSTA} "
                              "objetos.", erro=True)
        fachada = await asyncio.to_thread(sessao.obter_fachada)
        if fachada is None:
            return _texto_mcp("O motor de aprovação está indisponível agora; nada foi feito.",
                              erro=True)
        try:
            rel = await asyncio.to_thread(fachada.analisar, itens)
        except Exception as e:                       # sem a mensagem: pode ter segredo
            return _texto_mcp(f"Não consegui montar o relatório ({type(e).__name__}).", erro=True)
        id_ = str(rel.get("id", ""))[:64]
        recusados = rel.get("recusados") or []
        linhas = [f"Relatório {id_}: {len(rel.get('itens') or [])} item(ns) aceito(s), "
                  f"{len(recusados)} recusado(s). NADA foi executado: o dono decide no "
                  "painel do DERVS."]
        for r in recusados[:10]:
            linhas.append(f"- recusado: {str(r.get('alvo', ''))[:80]} — "
                          f"{str(r.get('motivo', ''))[:200]}")
        sessao._emitir("claude_ferramenta", {
            "nome": "propor_acao",
            "resumo": f"relatório {id_}: {len(rel.get('itens') or [])} aceito(s), "
                      f"{len(recusados)} recusado(s) — aguarda o dono; nada foi executado"})
        return _texto_mcp("\n".join(linhas))

    @sdk.tool("status_aprovacao", "Diz em que pé está um relatório feito com propor_acao.",
              {"relatorio_id": str})
    async def status_aprovacao(args):
        fachada = sessao.obter_fachada()
        if fachada is None:
            return _texto_mcp("O motor de aprovação está indisponível agora.", erro=True)
        id_ = str((args or {}).get("relatorio_id", ""))[:64]
        try:
            st = fachada.status(id_)
        except Exception as e:
            return _texto_mcp(f"Não consegui consultar ({type(e).__name__}).", erro=True)
        if st is None:
            return _texto_mcp("Não conheço esse relatório.")
        linhas = [f"Relatório {id_}:" + (" vencido" if st.get("vencido") else "")]
        for i in (st.get("itens") or [])[:50]:
            linhas.append(f"- {i.get('id')}: {i.get('estado')} "
                          f"({i.get('acao')}, risco {i.get('risco')})")
        return _texto_mcp("\n".join(linhas))

    ferramentas = {t.name: t for t in (propor_acao, status_aprovacao)}
    return (sdk.create_sdk_mcp_server("dervs", tools=list(ferramentas.values())),
            ferramentas)
