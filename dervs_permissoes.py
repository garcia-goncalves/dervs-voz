#!/usr/bin/env python3
"""Política de permissões do DERVS — o que o dono libera, trava ou manda perguntar.

Princípio: esta camada só REDUZ poder. O teto continua sendo o `dervs_safety` e
os bloqueios de `dervs_claude_code.motivo_de_bloqueio` (que rodam ANTES). Aqui
só se escolhe, dentro do que já era permitido: negar, perguntar ao dono ou
deixar passar sozinho.

Três níveis por categoria: `analisa` (só olha, não age) < `pergunta` (cartão no
painel) < `sozinho`. Cada categoria tem os níveis que fazem sentido para ela, e
`apagar` e `servidor` NUNCA chegam a `sozinho` — nem por config editada à mão.

**"Sozinho" é uma lista POSITIVA.** A categoria diz só o que o dono quis liberar;
quem decide se ESTA ação específica passa sem cartão é `_reconhecida_por_inteiro`:
só entra o que é reconhecido por completo (escrever arquivo dentro de uma pasta de
projeto, abrir um programa simples, instalar um pacote simples, navegar). Comando
de shell em geral, ferramenta desconhecida e qualquer coisa estranha vão sempre ao
cartão — mesmo com a categoria em `sozinho`. (Achado da revisão de segurança de
02/10/2026: com lista de bloqueio, comando disfarçado escapava.)
"""
import json
import os
import re
import time

CATEGORIAS = ("ler", "abrir", "instalar", "alterar_projeto", "apagar",
              "internet", "servidor", "gastar_api")
NIVEIS = ("analisa", "pergunta", "sozinho")

# Os níveis que cada categoria aceita. `ler`: olhar é analisar, então não há
# "só analisa". `gastar_api`: não dá para perguntar a cada chamada de voz; o freio
# dela é o teto diário (dervs_gasto). `apagar`/`servidor`: teto duro, nunca sozinho.
PERMITIDOS = {
    "ler": ("pergunta", "sozinho"),
    "abrir": NIVEIS,
    "instalar": NIVEIS,
    "alterar_projeto": NIVEIS,
    "apagar": ("analisa", "pergunta"),
    "internet": NIVEIS,
    "servidor": ("analisa", "pergunta"),
    "gastar_api": ("analisa", "sozinho"),
}

PADRAO_PERMISSOES = {
    "ler": "sozinho", "abrir": "pergunta", "instalar": "pergunta",
    "alterar_projeto": "pergunta", "apagar": "pergunta", "internet": "pergunta",
    "servidor": "pergunta", "gastar_api": "sozinho",
}

ROTULOS = {
    "ler": "Ler arquivos e olhar o computador",
    "abrir": "Abrir programas e janelas",
    "instalar": "Instalar pacotes (roda o instalador do pacote)",
    "alterar_projeto": "Criar e alterar arquivos nas suas pastas de projeto",
    "apagar": "Apagar (vai para uma lixeira segura)",
    "internet": "Pesquisar na internet (abrir uma página pede o seu sim)",
    "servidor": "Mexer em servidor (acesso remoto)",
    "gastar_api": "Gastar com serviços pagos de IA (até o teto diário)",
}

_COMANDOS = ("Bash", "PowerShell")
_ESCRITA = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_NAVEGACAO = ("WebFetch", "WebSearch")

_SERVIDOR = re.compile(
    r"(?i)(?:^|[\s;&|\"'(`])(?:ssh|scp|sftp|rsync|plink|pscp|psftp)(?:\.exe)?\b"
    r"|\b(?:invoke-command|enter-pssession|new-pssession)\b")
_INSTALAR = re.compile(r"(?i)\b(?:pip3?|npm|pnpm|yarn|winget|choco|scoop|apt(?:-get)?)\b"
                       r"[^|;&]*\b(?:install|upgrade|add)\b|\bmsiexec\b")
_ABRIR = re.compile(r"(?i)(?:^|[\s;&|])(?:start|start-process|explorer|invoke-item)\b")

# --- o que é "reconhecido por inteiro" -------------------------------------------------
# Nome de pacote simples: sem '/', '\', ':' (nada de URL, VCS ou caminho), sem
# metacaractere de shell. Flags só de uma lista curta (nada de -r, -i, --index-url).
_PACOTE = r"[A-Za-z0-9][A-Za-z0-9._\-\[\],=~@]*"
_INST_PIP_NPM = re.compile(
    r"^(?:pip3?|python3? -m pip|npm|pnpm|yarn) (?:install|add)"
    rf"(?: (?:-U|-q|-g|-D|--upgrade|--quiet|--user|--global|--save-dev|{_PACOTE}))+$")
_INST_WINGET = re.compile(
    r"^winget (?:install|upgrade)"
    rf"(?: (?:--id|-e|--exact|--silent|--accept-package-agreements|--accept-source-agreements|{_PACOTE}))+$")
# Para CLASSIFICAR (qual botão do painel vale): qualquer "start <uma palavra>".
_ABRIR_SIMPLES = re.compile(r"(?i)^(?:start|start-process|explorer)(?:\.exe)? [\"']?[A-Za-z0-9._-]+[\"']?$")
# Para LIBERAR sem cartão: só programas conhecidos e inofensivos. Nada que execute por
# associação de arquivo (.bat/.hta/.lnk/.py), nada de logoff, cmd, powershell, mshta.
_PROGRAMAS_LIVRES = ("notepad", "calc", "mspaint", "wordpad", "write", "charmap", "taskmgr",
                     "snippingtool", "chrome", "msedge", "firefox", "winword", "excel",
                     "powerpnt", "code", "outlook", "spotify", "teams", "whatsapp")
_ABRIR_LIBERADO = re.compile(
    r"(?i)^(?:(?:start|start-process)(?:\.exe)? [\"']?(?:" + "|".join(_PROGRAMAS_LIVRES)
    + r")(?:\.exe)?[\"']?|explorer(?:\.exe)?)$")

# Onde escrever pode fazer algo rodar sozinho depois (login, shell, git, editor, SSH):
# nunca "sozinho", mesmo dentro de uma pasta de projeto.
_PASTAS_DE_AUTOEXECUCAO = {"startup", "windowspowershell", "powershell", ".ssh", ".git",
                           ".claude", ".vscode", ".config"}
_ARQUIVOS_DE_AUTOEXECUCAO = re.compile(
    r"(?i)^(?:\..*|autorun\.inf|pip\.ini|sitecustomize\.py|usercustomize\.py|"
    r"microsoft\.powershell_profile\.ps1|profile\.ps1|desktop\.ini|.*\.(?:lnk|pth|url|hta|scr|scf|library-ms|searchconnector-ms|"
    r"website|settingcontent-ms|appref-ms|cpl|inf))$")


_SEPARADORES = chr(92) + "/"


def raiz_valida(raiz) -> bool:
    """Uma pasta de projeto não pode ser larga demais: raiz do disco, o perfil do
    usuário, um ancestral dele ou qualquer coisa ligada a AppData deixariam o
    DERVS gravar `.gitconfig`, `.pth`, `pip.ini` e afins sem perguntar."""
    if not isinstance(raiz, str) or not raiz or not os.path.isabs(raiz):
        return False
    if raiz.startswith((chr(92) * 2, "//")):
        return False                                      # UNC e prefixo \?\ de caminho longo
    real = os.path.normcase(os.path.realpath(raiz)).rstrip(_SEPARADORES)
    if not os.path.splitdrive(real)[1].strip(_SEPARADORES):
        return False                                      # raiz do disco
    protegidas = [os.path.expanduser("~"), os.environ.get("USERPROFILE", ""),
                  os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")]
    for outra in protegidas:
        if not outra:
            continue
        o = os.path.normcase(os.path.realpath(outra)).rstrip(_SEPARADORES)
        if real == o or o.startswith(real + os.sep):
            return False                                  # o próprio ou um ancestral
    for appdata in protegidas[2:]:
        if appdata:
            a = os.path.normcase(os.path.realpath(appdata)).rstrip(_SEPARADORES)
            if real.startswith(a + os.sep):
                return False                              # dentro de AppData
    perfil = os.path.normcase(os.path.realpath(os.path.expanduser("~"))).rstrip(_SEPARADORES)
    return not (real.startswith(perfil + os.sep + "appdata"))


def normalizar(valor) -> dict:
    """Matriz completa e válida. Lixo vira o padrão; nível fora do permitido da
    categoria vira o padrão dela; categoria desconhecida é ignorada."""
    base = dict(PADRAO_PERMISSOES)
    if not isinstance(valor, dict):
        return base
    for cat in CATEGORIAS:
        nivel = valor.get(cat)
        if isinstance(nivel, str) and nivel in PERMITIDOS[cat]:
            base[cat] = nivel
    return base


def categoria_da_acao(nome: str, entrada, risco: dict) -> str:
    """Em que categoria a ação cai. Serve para o "só analisa" (negar) e para saber
    qual botão do painel vale; quem libera de verdade é `_reconhecida_por_inteiro`."""
    entrada = entrada if isinstance(entrada, dict) else {}
    comando = str(entrada.get("command", "")) if nome in _COMANDOS else ""
    if comando and _SERVIDOR.search(comando):
        return "servidor"
    if comando and _INSTALAR.search(comando):
        return "instalar"
    if risco.get("nivel") == "destrutivo":
        return "apagar"
    if comando and (_ABRIR_SIMPLES.match(comando.strip()) or _ABRIR_LIBERADO.match(comando.strip())):
        return "abrir"
    if nome in _NAVEGACAO or risco.get("rede"):
        return "internet"
    if comando and _ABRIR.search(comando):
        return "abrir"
    if nome in _ESCRITA or risco.get("nivel") == "muda_estado":
        return "alterar_projeto"
    return "ler"


def _dentro_de_pasta_de_projeto(caminho: str, raizes) -> bool:
    if not isinstance(caminho, str) or not caminho or not os.path.isabs(caminho):
        return False
    real = os.path.normcase(os.path.realpath(caminho))
    partes = {p.lower() for p in re.split(r"[\\/]", real) if p}
    if partes & _PASTAS_DE_AUTOEXECUCAO:
        return False
    if _ARQUIVOS_DE_AUTOEXECUCAO.match(os.path.basename(real)):
        return False
    for raiz in raizes or ():
        if not raiz_valida(raiz):
            continue
        base = os.path.normcase(os.path.realpath(raiz))
        if real == base or real.startswith(base.rstrip("\\/") + os.sep):
            return True
    return False


def _reconhecida_por_inteiro(cat: str, nome: str, entrada, risco: dict, raizes) -> bool:
    """Lista POSITIVA do que pode passar sem cartão quando o dono liberou a categoria."""
    entrada = entrada if isinstance(entrada, dict) else {}
    if risco.get("nivel") == "destrutivo":
        return False
    comando = str(entrada.get("command", "")).strip() if nome in _COMANDOS else ""
    if cat == "ler":
        return risco.get("nivel") == "reversivel" and not risco.get("rede")
    if cat == "alterar_projeto":
        if nome not in _ESCRITA:
            return False
        caminho = entrada.get("file_path") or entrada.get("notebook_path") or ""
        return _dentro_de_pasta_de_projeto(caminho, raizes)
    if cat == "internet":
        # Só PESQUISAR. Abrir uma URL qualquer pode levar dado privado na query
        # (Read + WebFetch = vazamento), então WebFetch sempre vai ao cartão.
        return nome == "WebSearch"
    if cat == "instalar":
        return bool(comando) and bool(_INST_PIP_NPM.match(comando) or _INST_WINGET.match(comando))
    if cat == "abrir":
        return bool(comando) and bool(_ABRIR_LIBERADO.match(comando))
    return False


def decidir(nome: str, entrada, risco: dict, niveis, raizes=()) -> dict:
    """`{"acao": negar|perguntar|permitir, "categoria", "motivo"}`.

    `permitir` só sai se (1) o dono pôs a categoria em `sozinho` E (2) a ação é
    reconhecida por inteiro (lista positiva) E (3) o teto já a deixava passar.
    `raizes` são as pastas de projeto onde escrever sozinho é permitido. Estado
    ilegível => `perguntar`."""
    cat = categoria_da_acao(nome, entrada, risco)
    if not isinstance(niveis, dict):
        return {"acao": "perguntar", "categoria": cat, "motivo": "política ilegível"}
    nivel = niveis.get(cat)
    if nivel == "analisa" and cat != "ler":
        return {"acao": "negar", "categoria": cat,
                "motivo": f"Você deixou '{ROTULOS[cat]}' só em análise: o DERVS olha, mas não age."}
    if (nivel == "sozinho" and cat not in ("apagar", "servidor")
            and _reconhecida_por_inteiro(cat, nome, entrada, risco, raizes)):
        return {"acao": "permitir", "categoria": cat, "motivo": f"liberado por você: {ROTULOS[cat]}"}
    return {"acao": "perguntar", "categoria": cat, "motivo": "pede a confirmação do dono"}


# --- registro do que foi feito sozinho (para o dono poder auditar) ----------------

def _arquivo_log() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "dervs", "permissoes.jsonl")


def _sem_segredo(texto: str) -> str:
    texto = re.sub(r"(?i)\b(?:sk|pk|ghp|gho|xox[bap])[-_][A-Za-z0-9_\-]{8,}", "[segredo]", texto or "")
    return re.sub(r"\b[A-Za-z0-9+/_\-]{32,}\b", "[segredo]", texto)


def registrar(decisao: dict, nome: str, resumo: str = "") -> None:
    """Uma linha por ação feita sem perguntar. Nunca derruba quem chamou."""
    try:
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("DERVS_PERMISSOES_LOG"):
            return
        caminho = os.environ.get("DERVS_PERMISSOES_LOG") or _arquivo_log()
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "acao": decisao.get("acao"), "categoria": decisao.get("categoria"),
                                "ferramenta": nome, "resumo": _sem_segredo(resumo or "")[:160]},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass
