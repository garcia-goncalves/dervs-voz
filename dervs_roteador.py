#!/usr/bin/env python3
"""Roteador do DERVS — decide quem atende o pedido, sem o dono escolher cérebro.

Dois destinos:
  - `claude_code`: pedido de DESENVOLVER (criar/consertar/refatorar código) ou de
    TRABALHO explícito ("pede pro Claude…", "analisa…", "verifica meu PC"). Roda na
    sessão do Claude Code (assinatura do dono, no PC dele), sob as permissões do
    painel.
  - `planejador`: todo o resto — o fluxo rápido de sempre (comando, hora, abrir app).

É heurística transparente, não modelo: um falso positivo manda o pedido ao
Claude Code (mais lento, gasta assinatura), então só entra o que é claro. Cada
decisão fica em `roteamento.jsonl` com o motivo, para o dono conferir em
"Avançado". O Claude Code continua passando pelo gancho de permissões.
"""
import json
import os
import re
import time
import unicodedata

import dervs_claude_code

# Tudo é comparado JÁ normalizado (sem acento, minúsculo): "Olá", "faça" e "corrija"
# chegam como "ola", "faca" e "corrija".
_VOCATIVO = re.compile(r"^\W*(?:(?:ei|oi|ola)\W+)?dervs\W+")
_PEDIDO_EDUCADO = re.compile(r"^(?:(?:por favor|pode|poderia|vamos|bora)\s+)+"
                             r"|^(?:eu )?(?:quero|preciso|gostaria) que (?:voce|vc|o dervs) ")
# Verbo de construir × coisa claramente de software.
_VERBO_GERAL = (r"(?:cri(?:a|e|ar)|desenvolv(?:a|e|er)|implement(?:a|e|ar)|constr(?:oi|ua|uir)|"
                r"program(?:a|e|ar)|escrev(?:a|e|er)|fa(?:z|ca|zer)|mont(?:a|e|ar))")
# Verbo técnico: aceita também coisas mais soltas (tela, teste), porque quem
# "corrige o teste" ou "refatora a rotina" só pode estar falando de código.
_VERBO_TECNICO = (r"(?:consert(?:a|e|ar)|corrij(?:a|o)|corrig(?:e|ir)|refator(?:a|e|ar)|"
                  r"implement(?:a|e|ar)|desenvolv(?:a|e|er))")
_ALVO_FORTE = (r"(?:site|app|aplicativo|sistema|funcao|codigo|script|bug|api|"
               r"programa de computador|backend|frontend|landing page|endpoint|"
               r"componente|banco de dados|automacao)")
_ALVO_SOLTO = r"(?:tela|teste|testes|pagina|rotina|projeto|classe|modulo|programa)"
_DESENVOLVER = re.compile(
    rf"^(?:{_VERBO_GERAL}\b[^.?!]{{0,60}}?\b{_ALVO_FORTE}\b"
    rf"|{_VERBO_TECNICO}\b[^.?!]{{0,60}}?\b(?:{_ALVO_FORTE}|{_ALVO_SOLTO})\b)")


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def rotear(texto: str) -> dict:
    """`{executor, intencao, motivo, pedido}`. `pedido` é o texto a mandar ao
    Claude Code (ou None quando o planejador atende)."""
    original = (texto or "").strip()
    if not original:
        return {"executor": "planejador", "intencao": "vazio",
                "motivo": "sem fala", "pedido": None}
    trabalho = dervs_claude_code.frase_de_trabalho(original)
    if trabalho:
        return {"executor": "claude_code", "intencao": "trabalho",
                "motivo": "pedido explícito de trabalho/análise", "pedido": trabalho}
    t = _VOCATIVO.sub("", _norm(original), count=1)
    t = _PEDIDO_EDUCADO.sub("", t, count=1).strip()
    if _DESENVOLVER.match(t):
        return {"executor": "claude_code", "intencao": "desenvolver",
                "motivo": "pedido de desenvolvimento (verbo de construir + coisa de software)",
                "pedido": original}
    return {"executor": "planejador", "intencao": "rapido",
            "motivo": "comando ou conversa curta: planejador rápido", "pedido": None}


# --- registro (para o dono auditar em "Avançado") --------------------------------

def _arquivo_log() -> str:
    forcado = os.environ.get("DERVS_ROTEAMENTO_LOG")
    if forcado:
        return forcado
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "dervs", "roteamento.jsonl")


def registrar(decisao: dict, fala: str) -> None:
    """Uma linha por decisão. A fala só é guardada (80 caracteres) quando vai ao
    Claude Code; o que vai ao planejador rápido não deixa a frase no disco, porque
    pode ser dado falado em voz alta. Nunca levanta."""
    try:
        caminho = _arquivo_log()
        if not caminho:
            return
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "executor": decisao.get("executor"),
                                "intencao": decisao.get("intencao"),
                                "motivo": decisao.get("motivo"),
                                "fala": ((fala or "")[:80]
                                         if decisao.get("executor") == "claude_code" else "")},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def recentes(n: int = 10) -> list:
    """As últimas `n` decisões, a mais nova primeiro. Nunca levanta."""
    try:
        caminho = _arquivo_log()
        if not caminho or not os.path.exists(caminho):
            return []
        with open(caminho, "rb") as f:
            f.seek(0, os.SEEK_END)
            tam = f.tell()
            f.seek(max(0, tam - 64 * 1024))
            linhas = f.read().decode("utf-8", errors="replace").splitlines()
        saida = []
        for linha in reversed(linhas):
            try:
                saida.append(json.loads(linha))
            except ValueError:
                continue
            if len(saida) >= n:
                break
        return saida
    except Exception:
        return []
