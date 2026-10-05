#!/usr/bin/env python3
"""DERVS — pedidos de infraestrutura por voz (Ondas B, C e D da esteira dervs-jarvis).

Entra ANTES do roteador e do cérebro: `interpretar(fala, apelidos)` reconhece só frases
claras e devolve uma intenção; qualquer dúvida devolve None e a fala segue o caminho de
sempre. Quem executa é `AcoesVoz`, com tudo de fora (terminal SSH, config, processos)
injetado, para o teste provar cada trava sem tocar servidor, GitHub nem disco do dono.

Travas que não saem daqui:
  - Servidor: leitura roda; o que muda servidor vira cartão na tela (o terminal SSH decide).
    "Pergunta pro Claude da VPS" NUNCA é leitura: sempre cartão.
  - Projeto: só abre pasta achada DENTRO das pastas de projeto; o Claude do conserto roda em
    git worktree isolado, num branch `dervs/...`, e este módulo nunca mexe na `main`.
  - GitHub: commit e push só em branch próprio, só depois do "confirma" dito pelo dono, e sem
    arquivo de segredo na lista. Não existe aqui `--force`, repositório público nem apagar
    branch remoto: pedir isso por voz só ganha uma recusa.
  - Configuração: só as chaves da LISTA_FIXA mudam por voz; permissões, teto de gasto e pastas
    de projeto exigem clique no painel.
"""
import difflib
import os
import re
import subprocess
import threading
import time
import unicodedata


LISTA_FIXA = ("voz_openai_tempo", "voz_velocidade", "voz_openai", "confirmar_plano")
VOZES_OPENAI = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage",
                "shimmer", "verse", "marin", "cedar")
_APELIDOS_DE_VOZ = {"onix": "onyx", "onics": "onyx", "sedar": "cedar", "cedro": "cedar",
                    "marim": "marin", "eco": "echo"}
TEMPO_OPENAI = (1.0, 1.6, 0.15)        # mínimo, máximo, passo
VELOCIDADE_KOKORO = (0.5, 2.0, 0.1)
VALIDADE_CONFIRMACAO_S = 120
MAX_PERGUNTA = 300
_SEGREDO = re.compile(
    r"(?i)(?:^|[/\\])(?:\.env[\w.\-]*|[\w.\-]*\.env|id_[\w.\-]*|"
    r"[\w.\-]*\.(?:pem|key|ppk|pfx|p12|kdbx|jks|ovpn|sqlite3?|db|sql|bak|dump|tfstate(?:\.backup)?)|"
    r"credentials[\w.\-]*|[\w.\-]*credentials[\w.\-]*\.json|secrets?[\w.\-]*|service-account[\w.\-]*|"
    r"appsettings\.[\w.\-]+\.json|wp-config\.php|kubeconfig|\.htpasswd|"
    r"\.npmrc|\.pypirc|\.netrc|\.pgpass|\.git-credentials)$")

_TOPICOS = (  # (regex na fala normalizada, comando de leitura do terminal SSH)
    (r"\b(?:disco|espaco)\b", "df -h"),
    (r"\b(?:memoria|ram)\b", "free -m"),
    (r"\b(?:uptime|ha quanto tempo|tempo ligado|tempo no ar)\b", "uptime"),
    (r"\b(?:containers?|conteineres?|docker)\b", "docker ps"),
)
_UNIDADE = r"(?!(?:servidor|vps|disco|espaco|memoria|ram|docker|container|containers)(?![\w.@-]))([a-z0-9][a-z0-9@._-]{0,63})"


def _norm(texto) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^\w\s@./:-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _tira_vocativo(t: str) -> str:
    t = re.sub(r"^(?:(?:ei|oi|ola)\s+)?dervs\s+", "", t)
    return re.sub(r"^(?:por favor|pode|poderia|bora)\s+", "", t).strip()


# ------------------------------------------------------------ servidor

def _fichas_de_servidor(t: str, apelidos) -> list:
    """Apelidos que a fala cita: todos os pedaços do apelido (VPS-OVH = vps + ovh) aparecem nela;
    ganham os que casam mais pedaços. Só 'vps'/'servidor' solto: quem tem 'vps' no nome."""
    palavras = set(re.split(r"[^\w]+", t))
    pontos = []
    for a in apelidos or ():
        pedacos = [p for p in re.split(r"[-._]+", a.lower()) if p]
        if pedacos and all(p in palavras for p in pedacos):
            pontos.append((len(pedacos), a))
    if pontos:
        melhor = max(p for p, _ in pontos)
        return sorted(a for p, a in pontos if p == melhor)
    if "vps" in palavras:
        com_vps = [a for a in apelidos or () if "vps" in a.lower()]
        return sorted(com_vps or (apelidos or ()))
    if "servidor" in palavras:                 # "servidor" solto não adivinha: pergunta qual
        return sorted(apelidos or ())
    return []


def _servidor_ou_pergunta(t, apelidos):
    achados = _fichas_de_servidor(t, apelidos)
    if len(achados) == 1:
        return achados[0], None
    if not achados:
        return None, ("Não tenho nenhum servidor cadastrado." if not apelidos else
                      "Qual servidor? Tenho: " + ", ".join(sorted(apelidos)) + ".")
    return None, "Qual deles: " + " ou ".join(achados) + "?"


_SERVIDOR = r"(?:vps|servidor|[a-z0-9][a-z0-9 ._-]{0,40})"


def _ssh(t: str, apelidos):
    m = re.match(r"(?:pergunta|pergunte|fala|fale|pede|peca|manda|mande)\s+(?:pro|para o|pra|ao|com o)\s+"
                 r"claude\s+(?:da|na|do|no)\s+(.+)$", t)
    if m:
        palavras = m.group(1).split()
        for k in (3, 2, 1):                       # o servidor são as primeiras k palavras
            cabeca, resto = " ".join(palavras[:k]), " ".join(palavras[k:])
            if len(palavras) <= k or not _fichas_de_servidor(cabeca, apelidos):
                continue
            pecas = {x for x in re.split(r"[^\w]+", palavras[k - 1]) if x}
            conhecidas = {"vps", "servidor"}.union(
                *(re.split(r"[-._]+", a.lower()) for a in apelidos or ()))
            if pecas & conhecidas:
                break
        else:
            return None
        resto = re.sub(r"^(?:que|:)\s+", "", resto)
        apelido, duvida = _servidor_ou_pergunta(cabeca, apelidos)
        if apelido is None:
            return {"tipo": "falar", "fala": duvida}
        if len(resto) > MAX_PERGUNTA:
            return {"tipo": "falar", "fala": "Essa pergunta ficou longa demais para mandar ao servidor."}
        # quem monta o `claude -p '...'` é a tela Integração (o único módulo que conhece o SSH)
        return {"tipo": "ssh", "apelido": apelido, "comando": None, "pergunta": resto, "claude": True}
    m = re.match(r"(?:roda|rode|executa|execute)\s+(.+)\s+(?:na|no|em)\s+(?:a |o )?((?:\S+ ){0,2}\S+)$", t)
    if m and _fichas_de_servidor(m.group(2), apelidos):
        apelido, duvida = _servidor_ou_pergunta(m.group(2), apelidos)
        if apelido is None:
            return {"tipo": "falar", "fala": duvida}
        return {"tipo": "ssh", "apelido": apelido, "comando": m.group(1), "claude": False}
    if not re.search(r"\b(?:na|no|da|do|em)\s+(?:a |o )?(?:vps|servidor)\b", t) and not (
            apelidos and _fichas_de_servidor(t, [a for a in apelidos if "-" in a or "." in a or "_" in a])):
        return None
    comando = None
    m = re.search(rf"\bstatus (?:do|da|de) {_UNIDADE}\b", t)
    if m:
        comando = f"systemctl status {m.group(1)}"
    else:
        m = re.search(rf"\blogs? (?:do|da|de) {_UNIDADE}\b", t)
        if m:
            comando = f"journalctl -u {m.group(1)} -n 50 --no-pager"
    if comando is None:
        for padrao, cmd in _TOPICOS:
            if re.search(padrao, t):
                comando = cmd
                break
    if comando is None:
        return None
    apelido, duvida = _servidor_ou_pergunta(t, apelidos)
    if apelido is None:
        return {"tipo": "falar", "fala": duvida}
    return {"tipo": "ssh", "apelido": apelido, "comando": comando, "claude": False}


# ------------------------------------------------------------ projetos e GitHub

_PROIBIDO_GIT = re.compile(
    r"\b(?:force|forca|forcado|forcar)\b|\bpublic[oa]s?\b|"
    r"\b(?:apaga|apague|deleta|delete|remove|remova|exclui|exclua)\b.*\b(?:branch|ramo|tag|repositorio)\b")
_FALA_GIT = re.compile(r"\b(?:commit|commita|commite|push|github|branch|repositorio)\b")


def _projeto(t: str):
    if _FALA_GIT.search(t) and _PROIBIDO_GIT.search(t):
        return {"tipo": "falar", "fala": "Isso eu não faço por voz: forçar envio, tornar repositório "
                                         "público ou apagar branch ou tag no GitHub só com você mesmo, "
                                         "no terminal."}
    m = re.match(r"(?:abre|abra|abrir)\s+(?:o\s+)?(?:projeto|repo|repositorio)\s+(?:do |da |de )?(.+?)"
                 r"(?:\s+no\s+(?:vs ?code|visual studio code|codigo))?$", t)
    if m:
        return {"tipo": "projeto_abrir", "nome": m.group(1)}
    m = re.match(r"(?:pede|peca|pedir|manda|mande)\s+(?:pro|para o|ao)\s+claude\s+(.+?)\s+"
                 r"(?:no|do|na|da|em)\s+projeto\s+(?:do |da |de )?(.+)$", t)
    if m:
        return {"tipo": "projeto_claude", "pedido": m.group(1), "nome": m.group(2)}
    m = re.match(r"(?:no|do|na|da|em)\s+projeto\s+(?:do |da |de )?(.+?),?\s+(?:pede|peca)\s+(?:pro|para o|ao)\s+"
                 r"claude\s+(.+)$", t)
    if m:
        return {"tipo": "projeto_claude", "pedido": m.group(2), "nome": m.group(1)}
    m = re.match(r"(?:faz|faca|manda|mande|sobe|suba|envia|envie)\s+(?:o\s+)?(?:commit|push)?.*?"
                 r"\b(?:projeto)\s+(?:do |da |de )?(.+?)(?:\s+(?:pro|pra|para o|para|no)\s+github)?$", t)
    if m and re.search(r"\b(?:commit|commita|push|github)\b", t):
        return {"tipo": "git_enviar", "nome": m.group(1)}
    return None


# ------------------------------------------------------------ configuração por voz

_VERBO_MUDAR = (r"\b(?:muda|mude|altera|altere|aumenta|aumente|libera|libere|troca|troque|define|defina|"
                r"ativa|ative|desativa|desative|tira|tire|zera|zere|aumentar|mudar|trocar)\b")
_PROTEGIDO = re.compile(r"\b(?:permissao|permissoes|teto|gasto|limite|pastas? de projeto|chave|senha|token)\b")


def _config(t: str):
    if re.search(_VERBO_MUDAR, t) and _PROTEGIDO.search(t):
        return {"tipo": "config_protegida"}
    m = (re.match(r"(?:fala|fale)\s+(?:um pouco |bem )?mais\s+(rapido|depressa|devagar|lento)\b", t)
         or re.match(r"(acelera|desacelera)\s+(?:a )?voz\b", t))
    if m:
        mais_rapido = m.group(1) in ("rapido", "depressa", "acelera")
        return {"tipo": "config_ritmo", "sentido": 1 if mais_rapido else -1}
    m = re.match(r"(?:troca|troque|muda|mude|coloca|ponha)\s+(?:a )?voz\s+(?:para|pra|pro|do|de)\s+(?:a |o )?(\w+)$", t)
    if m:
        nome = _APELIDOS_DE_VOZ.get(m.group(1), m.group(1))
        if nome in VOZES_OPENAI:
            return {"tipo": "config", "chave": "voz_openai", "valor": nome}
        return {"tipo": "falar", "fala": "Não conheço essa voz. As que tenho: " + ", ".join(VOZES_OPENAI) + "."}
    if re.search(r"\b(?:desativa|desative|desliga|desligue|tira|tire)\s+(?:o\s+)?modo\s+sempre\s+confirmar\b", t) or \
            re.search(r"\bso confirma(?:r)? (?:o )?grave\b", t):
        return {"tipo": "config", "chave": "confirmar_plano", "valor": "grave"}
    if re.search(r"\b(?:ativa|ative|liga|ligue)\s+(?:o\s+)?modo\s+sempre\s+confirmar\b", t):
        return {"tipo": "config", "chave": "confirmar_plano", "valor": "sempre"}
    return None


_CONFIRMA_ENVIO = {"confirma", "confirmado", "confirmar", "confirma o envio", "sim confirma"}
_RECUSA_ENVIO = {"nao", "cancela", "cancelar", "cancele", "para", "deixa", "nao envia", "nao manda"}


def resposta_de_envio(fala) -> str | None:
    """"sim", "nao" ou None. O envio ao GitHub é mais exigente que o "ok" do dia a dia: um
    "beleza" solto (de uma TV, de uma conversa ao lado) não confirma; só a palavra do pedido."""
    t = re.sub(r"^(?:(?:ei|oi|ola)\s+)?dervs\s+", "", _norm(fala))   # sem tirar o "pode" de "pode enviar"
    if t in _CONFIRMA_ENVIO:
        return "sim"
    if t in _RECUSA_ENVIO:
        return "nao"
    return None


def interpretar(fala, apelidos=()):
    """Intenção (dict com "tipo") ou None. Conservador: frase que não casa inteira vai ao cérebro."""
    t = _tira_vocativo(_norm(fala))
    if not t:
        return None
    protegida = _config(t)
    if protegida and protegida["tipo"] == "config_protegida":     # recusar vem antes de tudo
        return protegida
    return _ssh(t, apelidos) or _projeto(t) or protegida or _config(t)


# ------------------------------------------------------------ projetos: achar a pasta

def achar_projeto(nome: str, raizes) -> tuple[str | None, list]:
    """(pasta, candidatos). Pasta só quando há um vencedor claro; senão None e a lista de empate."""
    alvo = _norm(nome).replace("-", " ").replace("_", " ")
    ranque = []
    for raiz in raizes:
        try:
            filhos = [e for e in os.scandir(raiz) if e.is_dir() and not e.name.startswith(".")]
        except OSError:
            continue
        for e in filhos:
            n = _norm(e.name).replace("-", " ").replace("_", " ")
            ponto = 1.0 if n == alvo else difflib.SequenceMatcher(None, alvo, n).ratio()
            if alvo and (alvo in n or n in alvo) and min(len(alvo), len(n)) >= 4:
                ponto = max(ponto, 0.85)
            ranque.append((ponto, e.name, e.path))
    ranque.sort(reverse=True)
    if not ranque or ranque[0][0] < 0.6:
        return None, []
    if ranque[0][0] >= 0.99 or len(ranque) == 1 or ranque[0][0] - ranque[1][0] >= 0.1:
        return ranque[0][2], []
    return None, [nome_ for _, nome_, _ in ranque[:3]]


def localizar_vscode() -> str | None:
    for base, resto in ((os.environ.get("LOCALAPPDATA"), r"Programs\Microsoft VS Code\Code.exe"),
                        (os.environ.get("ProgramFiles"), r"Microsoft VS Code\Code.exe")):
        if base and os.path.isfile(os.path.join(base, resto)):
            return os.path.join(base, resto)
    return None


def _git(pasta, *args, rodar=subprocess.run):
    """Roda `git -C pasta ...` sem shell. Nenhum chamador passa --force."""
    return rodar(["git", "-C", pasta, *args], capture_output=True, text=True, timeout=60,
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _slug(texto: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", _norm(texto)).strip("-")[:30]) or "pedido"


# ------------------------------------------------------------ executar

class AcoesVoz:
    """Executa uma intenção e devolve a frase que o DERVS fala. Nunca levanta."""

    def __init__(self, *, terminal_por_voz, raizes_fn, gravar_config, ler_config, aplicar_ao_vivo=None,
                 abrir_vscode=None, abrir_claude=None, git=_git, relogio=time.monotonic,
                 pasta_worktrees=None):
        self._ssh = terminal_por_voz          # (apelido, comando, pergunta) -> frase
        self._raizes = raizes_fn
        self._gravar = gravar_config
        self._ler = ler_config
        self._ao_vivo = aplicar_ao_vivo or (lambda chave, valor: None)
        self._abrir_vscode = abrir_vscode or self._vscode_padrao
        self._abrir_claude = abrir_claude or self._claude_padrao
        self._git = git
        self._relogio = relogio
        self._pasta_wt = pasta_worktrees or os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "dervs", "worktrees")
        self._pendente = None
        self._trava = threading.RLock()       # uma ação por vez: um "confirma" repetido não envia duas vezes

    # -- confirmação por voz (envio ao GitHub e conserto pelo Claude Code)
    def tem_pendencia(self) -> bool:
        with self._trava:
            p = self._pendente
            if p and self._relogio() > p["expira"]:
                self._pendente = None
            return self._pendente is not None

    def responder_pendencia(self, sim: bool) -> str:
        with self._trava:
            p, self._pendente = self._pendente, None
            if not p or self._relogio() > p["expira"]:
                return "Esse pedido já venceu. Peça de novo."
            if not sim:
                return "Certo, cancelei. Nada foi feito."
            if p["tipo"] == "conserto":
                return self._abrir_conserto(p)
            return self._enviar(p)

    def executar(self, i: dict) -> str:
        with self._trava:
            try:
                return self._despachar(i)
            except Exception as erro:
                return f"Algo falhou por dentro ({type(erro).__name__}). Nada foi feito."

    def _despachar(self, i):
        tipo = i["tipo"]
        if tipo == "falar":
            return i["fala"]
        if tipo == "ssh":
            return self._ssh(i["apelido"], i["comando"], i.get("pergunta"))
        if tipo == "config_protegida":
            return ("Isso é configuração de segurança: permissões, teto de gasto e pastas de projeto "
                    "só mudam por clique no painel.")
        if tipo == "config_ritmo":
            return self._ritmo(i["sentido"])
        if tipo == "config":
            return self._config(i["chave"], i["valor"])
        pasta, empate = achar_projeto(i["nome"], self._raizes())
        if pasta is None:
            if empate:
                return "Achei mais de um projeto parecido: " + ", ".join(empate) + ". Qual deles?"
            return f"Não achei o projeto {i['nome']} nas suas pastas de projeto."
        if tipo == "projeto_abrir":
            return self._abrir_vscode(pasta)
        if tipo == "projeto_claude":
            return self._conserto(pasta, i["pedido"])
        if tipo == "git_enviar":
            return self._preparar_envio(pasta)
        return "Não entendi o que fazer."

    # -- Onda D
    def _config(self, chave, valor):
        if chave not in LISTA_FIXA:
            return "Essa chave não muda por voz."
        if not self._gravar(chave, valor):
            return "Não consegui gravar a configuração."
        self._ao_vivo(chave, valor)
        return {"voz_openai": f"Pronto, troquei a voz para {valor}.",
                "confirmar_plano": ("Pronto: agora peço o seu OK em todo plano." if valor == "sempre"
                                    else "Pronto: volto a pedir OK só no que é grave.")}.get(chave, "Pronto.")

    def _ritmo(self, sentido):
        conf = self._ler()
        mudou = []
        for chave, (menor, maior, passo) in (("voz_openai_tempo", TEMPO_OPENAI),
                                             ("voz_velocidade", VELOCIDADE_KOKORO)):
            atual = float(conf.get(chave, menor))
            novo = round(min(maior, max(menor, atual + sentido * passo)), 2)
            if novo != atual and self._gravar(chave, novo):
                self._ao_vivo(chave, novo)
                mudou.append(chave)
        if mudou:
            return "Pronto, falo mais rápido." if sentido > 0 else "Pronto, falo mais devagar."
        return "Já estou no mais rápido que a voz aguenta." if sentido > 0 else "Já estou no mais devagar."

    # -- Onda C
    @staticmethod
    def _vscode_padrao(pasta):
        exe = localizar_vscode()
        if not exe:
            return "Não achei o VS Code instalado."
        subprocess.Popen([exe, pasta], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        return f"Abrindo {os.path.basename(pasta)} no VS Code."

    def _claude_padrao(self, worktree, pedido):
        env = dict(os.environ, DERVS_PEDIDO=pedido)      # o pedido vai por variável: sem aspas, sem shell
        subprocess.Popen(["powershell", "-NoExit", "-Command", "claude --disallowedTools 'Bash(git push:*)' -- $env:DERVS_PEDIDO"],
                         cwd=worktree, env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))

    def _conserto(self, pasta, pedido):
        """O pedido falado vira o PROMPT de um Claude Code: por isso espera o "confirma", como o envio."""
        if self._git(pasta, "rev-parse", "--is-inside-work-tree").returncode != 0:
            return "Essa pasta não é um repositório git; não abri sessão nela."
        self._pendente = {"tipo": "conserto", "pasta": pasta, "pedido": pedido,
                          "expira": self._relogio() + VALIDADE_CONFIRMACAO_S}
        return (f"Vou pedir ao Claude Code, numa cópia isolada do {os.path.basename(pasta)}: {pedido}. "
                "Ele não vai poder mandar nada ao GitHub. Diga confirma para eu abrir.")

    def _abrir_conserto(self, p):
        pasta, pedido = p["pasta"], p["pedido"]
        branch = f"dervs/{_slug(pedido)}-{time.strftime('%H%M')}"
        destino = os.path.join(
            self._pasta_wt, f"{_slug(os.path.basename(pasta))}-{_slug(pedido)}-{time.strftime('%H%M%S')}")
        os.makedirs(self._pasta_wt, exist_ok=True)
        r = self._git(pasta, "worktree", "add", "-b", branch, destino)
        if r.returncode != 0:
            return "Não consegui criar a cópia isolada do projeto. Nada foi feito."
        self._abrir_claude(destino, pedido)
        return (f"Abri o Claude Code numa cópia isolada do {os.path.basename(pasta)}, no branch {branch}. "
                "Ele não tem permissão de mandar nada ao GitHub: o envio só sai por aqui, com o seu confirma.")

    def _arquivos_mudados(self, pasta):
        """Caminhos exatos que mudaram (pasta nova listada arquivo a arquivo), ou None se não é git."""
        r = self._git(pasta, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        if r.returncode != 0:
            return None
        partes, caminhos, i = r.stdout.split("\0"), [], 0
        while i < len(partes):
            e = partes[i]
            i += 1
            if len(e) < 4:
                continue
            caminhos.append(e[3:])
            if e[0] in "RC" and i < len(partes):      # renomeado: o caminho de origem vem em seguida
                caminhos.append(partes[i])
                i += 1
        return caminhos

    def _preparar_envio(self, pasta):
        arquivos = self._arquivos_mudados(pasta)
        if arquivos is None:
            return "Essa pasta não é um repositório git."
        if not arquivos:
            return "Não há nada novo para enviar nesse projeto."
        segredos = [a for a in arquivos if _SEGREDO.search(a)]
        if segredos:
            return "Parei: há arquivo que parece segredo na lista (" + ", ".join(segredos[:3]) + "). Não enviei nada."
        atual = self._git(pasta, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if not atual or atual == "HEAD":
            return "O projeto está sem branch (HEAD solto). Não enviei nada."
        branch = f"dervs/voz-{time.strftime('%Y%m%d-%H%M')}"        # nunca o branch em que o projeto está
        self._pendente = {"tipo": "envio", "pasta": pasta, "branch": branch, "arquivos": arquivos,
                          "n": len(arquivos), "expira": self._relogio() + VALIDADE_CONFIRMACAO_S}
        return (f"Vou salvar {len(arquivos)} arquivo{'s' if len(arquivos) != 1 else ''} do "
                f"{os.path.basename(pasta)} no branch {branch} e mandar ao GitHub. Diga confirma para eu fazer.")

    def _enviar(self, p):
        pasta, branch = p["pasta"], p["branch"]
        agora = self._arquivos_mudados(pasta) or []
        if any(_SEGREDO.search(a) for a in agora):
            return "Apareceu arquivo que parece segredo depois do seu pedido. Não enviei nada."
        lista = [a for a in p["arquivos"] if a in agora]          # só o que foi conferido e ainda mudou
        if not lista:
            return "Nada do que eu tinha conferido mudou mais. Não enviei nada."
        atual = self._git(pasta, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != atual and self._git(pasta, "switch", "-c", branch).returncode != 0:
            return "Não consegui criar o branch. Nada foi enviado."
        if self._git(pasta, "add", "--", *lista).returncode != 0:
            return "Não consegui preparar os arquivos. Nada foi enviado."
        c = self._git(pasta, "commit", "-m", "chore(voz): alterações pedidas por voz", "--", *lista)
        if c.returncode != 0:
            return "O commit não passou (algum aviso do projeto). Nada foi enviado."
        e = self._git(pasta, "push", "-u", "origin", branch)
        if e.returncode != 0:
            return "Salvei no computador, mas o GitHub recusou o envio. Nada foi forçado."
        return f"Pronto: salvei e mandei ao GitHub no branch {branch}. A main não foi tocada."
