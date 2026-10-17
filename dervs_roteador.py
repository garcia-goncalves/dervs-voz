#!/usr/bin/env python3
"""Roteador do DERVS — decide quem atende o pedido, sem o dono escolher cérebro.

Dois destinos:
  - `claude_code`: pedido de DESENVOLVER (criar/consertar/refatorar código) ou de
    TRABALHO explícito ("pede pro Claude…", "analisa…", "verifica meu PC"). Roda na
    sessão do Claude Code (assinatura do dono, no PC dele), sob as permissões do
    painel: com o cérebro do DERVS, ou com o Claude Code do dono emprestado DENTRO da
    pasta do projeto quando a frase nomeia um (`destino`).
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
import dervs_voz_infra

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
               r"componente|banco de dados|automacao|programacao)")
_ALVO_SOLTO = r"(?:tela|teste|testes|pagina|rotina|projeto|classe|modulo|programa)"
# "cria um arquivo de teste no projeto dervs-voz" (17/10): o lugar diz que é código
# — mas só com objeto de código antes: "cria uma pasta no projeto" é do planejador (revisão)
_OBJ_CODIGO = r"(?:arquivo|teste|testes|funcao|script|classe|modulo|tela|pagina|componente)"
_NUM_PROJETO = (rf"{_OBJ_CODIGO}\b[^.?!]{{0,40}}?\b"
                r"(?:no|do|pro|para o|dentro do) (?:projeto|repositorio|repo)")
_DESENVOLVER = re.compile(
    rf"^(?:{_VERBO_GERAL}\b[^.?!]{{0,60}}?\b(?:{_ALVO_FORTE}|{_NUM_PROJETO})\b"
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
                "motivo": "pedido explícito de trabalho/análise", "pedido": trabalho,
                "claude_citado": dervs_claude_code.cita_o_claude(original)}
    t = _VOCATIVO.sub("", _norm(original), count=1)
    t = _PEDIDO_EDUCADO.sub("", t, count=1).strip()
    if _DESENVOLVER.match(t):
        return {"executor": "claude_code", "intencao": "desenvolver",
                "motivo": "pedido de desenvolvimento (verbo de construir + coisa de software)",
                "pedido": original}
    return {"executor": "planejador", "intencao": "rapido",
            "motivo": "comando ou conversa curta: planejador rápido", "pedido": None}


# --- qual cérebro: o do DERVS ou o Claude Code do dono emprestado num projeto ---------
# Decisão do dono (15/10/2026): o DERVS responde com o cérebro próprio; o Claude Code
# de desenvolvimento dele só é emprestado quando ele pede TRABALHO num projeto NOMEADO,
# e roda dentro da pasta desse projeto (`dervs_claude_code`, perfil `projeto`).
DIGA_O_PROJETO = "Em qual projeto? Diga, por exemplo: no projeto tal, conserta isso."
_PREP = r"(?:no|do|na|da|em)\s+projeto\s+(?:d[oae]\s+)?"
_PROJETO_NO_COMECO = re.compile(rf"^{_PREP}(?P<n>[^,:;]+?)\s*[,:;]\s*(?P<p>.+)$")
_PROJETO_NO_COMECO_SEM_VIRGULA = re.compile(rf"^{_PREP}(?P<n>\S+)\s+(?P<p>.+)$")
_PROJETO_NO_FIM = re.compile(
    r"^(?P<p>.+?)[\s,]+(?P<prep>no|do|na|da|em|o)\s+projeto\s+(?:d[oae]\s+)?"
    r"(?P<n>[a-z0-9][\w .-]{0,60})$")


def _projeto_citado(texto: str):
    """`(nome, pedido)` quando a frase cita um projeto, ou None. O pedido é o que sobra
    sem o projeto — é nele que se mede a intenção ("no projeto X, corrige o bug")."""
    t = _norm(texto).rstrip(" .!?")
    t = _PEDIDO_EDUCADO.sub("", _VOCATIVO.sub("", t, count=1), count=1).strip()
    for padrao in (_PROJETO_NO_COMECO, _PROJETO_NO_COMECO_SEM_VIRGULA):
        m = padrao.match(t)
        if m:
            return m.group("n").strip(" .-"), m.group("p")
    m = _PROJETO_NO_FIM.match(t)
    if m:
        # "analisa o projeto X": o projeto É o objeto do verbo, a frase inteira vale.
        return m.group("n").strip(" .-"), (t if m.group("prep") == "o" else m.group("p"))
    return None


def destino(texto: str, raizes) -> dict:
    """`rotear` mais o cérebro: `perfil` (`dervs` ou `projeto`), `projeto` (a pasta) e,
    quando o DERVS só responde, `executor="falar"` com a `fala`. Nunca levanta."""
    rota = {**rotear(texto), "perfil": "dervs", "projeto": None}
    citado = _projeto_citado(texto)
    if citado is None:
        if rota["intencao"] == "desenvolver":
            return {**rota, "executor": "falar", "fala": DIGA_O_PROJETO}
        return rota
    nome, pedido = citado
    rota_projeto = rotear(pedido)
    if rota_projeto["executor"] != "claude_code":
        return rota                      # cita um projeto mas não pede trabalho: fica com o DERVS
    try:
        pasta, empate = dervs_voz_infra.achar_projeto(nome, raizes or [])
    except Exception:
        pasta, empate = None, []
    if pasta:
        return {**rota_projeto, "perfil": "projeto", "projeto": pasta,
                "pedido": (texto or "").strip(),
                "motivo": rota_projeto["motivo"] + "; no projeto " + os.path.basename(pasta)}
    fala = ("Achei mais de um projeto parecido: " + ", ".join(empate) + ". Qual deles?"
            if empate else f"Não achei o projeto {nome} nas suas pastas de projeto.")
    return {**rota_projeto, "executor": "falar", "fala": fala, "perfil": "dervs", "projeto": None}


# --- Codex como reserva do Claude ocupado ------------------------------------------

DECISAO_RESERVA = {"executor": "codex", "intencao": "trabalho",
                   "motivo": "claude ocupado: reserva automática"}
AVISO_RESERVA = "O Claude está ocupado; passei para o Codex, só para leitura."


def reserva_codex(rota, *, claude_ocupado: bool, codex_pronto: bool, ligado: bool):
    """Intenção `codex_leitura` para `dervs_codex_voz.AcoesCodex.executar`, ou None.
    Só ANÁLISE desvia: pedido de desenvolver nunca vai ao Codex sem o dono citá-lo
    (lá a escrita exige projeto e "confirma"), e quem chamou o Claude pelo nome
    escolheu quem atende. E só com PROJETO na frase: sem projeto o Codex roda numa
    pasta neutra de onde o somente-leitura enxerga o disco todo ("verifica meu PC",
    "analisa meus documentos"), e o que ele lê vai à OpenAI sem o dono ter escolhido."""
    if not (ligado and claude_ocupado and codex_pronto) or not isinstance(rota, dict):
        return None
    if (rota.get("executor") != "claude_code" or rota.get("intencao") != "trabalho"
            or rota.get("claude_citado") or not rota.get("pedido")):
        return None
    import dervs_codex_voz      # aqui dentro: o roteador não carrega o Codex só para rotear
    i = dervs_codex_voz.interpretar("pede pro Codex " + rota["pedido"])
    if not i or i.get("tipo") != "codex_leitura" or not i.get("projeto"):
        return None
    # sem `pedido_inteiro`: projeto que não existir vira "não achei", nunca pergunta solta
    return {"tipo": "codex_leitura", "pedido": i["pedido"], "projeto": i["projeto"]}


def dica_codex(rota, *, ligado: bool) -> str:
    """Complemento do "ainda estou trabalhando" quando o Claude ocupado recusa um
    pedido de desenvolver: o Codex só escreve se o dono pedir, então o DERVS ensina como."""
    if ligado and isinstance(rota, dict) and rota.get("intencao") == "desenvolver":
        return " Ou diga: no projeto tal, pede pro Codex fazer isso."
    return ""


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
                                         if decisao.get("executor") in ("claude_code", "codex")
                                         else "")},
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
