#!/usr/bin/env python3
"""Política de permissões do DERVS — o que o dono libera, trava ou manda perguntar.

Princípio: esta camada só REDUZ poder. O teto continua sendo o `dervs_safety` e
os bloqueios de `dervs_claude_code.motivo_de_bloqueio` (que rodam ANTES). Aqui
só se escolhe, dentro do que já era permitido: negar, perguntar ao dono ou
deixar passar sozinho.

Três níveis por categoria: `analisa` (só olha, não age) < `pergunta` (cartão no
painel) < `sozinho`. Cada categoria tem os níveis que fazem sentido para ela, e
`apagar` e `servidor` NUNCA chegam a `sozinho` — nem por config editada à mão.
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
    "instalar": "Instalar programas e pacotes",
    "alterar_projeto": "Criar e alterar arquivos de projetos",
    "apagar": "Apagar (sempre vai para a quarentena)",
    "internet": "Usar a internet",
    "servidor": "Mexer em servidor (ssh)",
    "gastar_api": "Gastar com API paga (até o teto diário)",
}

_COMANDOS = ("Bash", "PowerShell")
_ESCRITA = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_SERVIDOR = re.compile(r"(?i)(?:^|[\s;&|])(?:ssh|scp|sftp|rsync)\b")
_INSTALAR = re.compile(r"(?i)\b(?:pip3?|npm|pnpm|yarn|winget|choco|scoop|apt(?:-get)?)\b"
                       r"[^|;&]*\b(?:install|upgrade)\b|\bmsiexec\b")
_ABRIR = re.compile(r"(?i)(?:^|[\s;&|])(?:start|start-process|explorer|invoke-item)\b")


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
    entrada = entrada if isinstance(entrada, dict) else {}
    comando = str(entrada.get("command", "")) if nome in _COMANDOS else ""
    if comando and _SERVIDOR.search(comando):
        return "servidor"
    if comando and _INSTALAR.search(comando):
        return "instalar"
    if risco.get("nivel") == "destrutivo":
        return "apagar"
    if nome in ("WebFetch", "WebSearch") or risco.get("rede"):
        return "internet"
    if comando and _ABRIR.search(comando):
        return "abrir"
    if nome in _ESCRITA or risco.get("nivel") == "muda_estado":
        return "alterar_projeto"
    return "ler"


def decidir(nome: str, entrada, risco: dict, niveis) -> dict:
    """`{"acao": negar|perguntar|permitir, "categoria", "motivo"}`.

    `permitir` só sai para ação que o teto já deixava passar (nunca destrutiva,
    nunca apagar/servidor) e só se o dono pôs a categoria em `sozinho`. Estado
    ilegível => `perguntar`."""
    cat = categoria_da_acao(nome, entrada, risco)
    if not isinstance(niveis, dict):
        return {"acao": "perguntar", "categoria": cat, "motivo": "política ilegível"}
    nivel = niveis.get(cat)
    if nivel == "analisa" and cat != "ler":
        return {"acao": "negar", "categoria": cat,
                "motivo": f"Você deixou '{ROTULOS[cat]}' só em análise: o DERVS olha, mas não age."}
    pode_sozinho = (nivel == "sozinho" and risco.get("nivel") != "destrutivo"
                    and cat not in ("apagar", "servidor"))
    if pode_sozinho:
        return {"acao": "permitir", "categoria": cat, "motivo": f"liberado por você: {ROTULOS[cat]}"}
    return {"acao": "perguntar", "categoria": cat, "motivo": "pede a confirmação do dono"}


# --- registro do que foi feito sozinho (para o dono poder auditar) ----------------

def _arquivo_log() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "dervs", "permissoes.jsonl")


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
                                "ferramenta": nome, "resumo": (resumo or "")[:200]},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass
