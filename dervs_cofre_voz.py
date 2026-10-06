#!/usr/bin/env python3
"""DERVS — o cofre por voz: "anota que…", "o que eu sei sobre…", "abre o cofre".

Funções puras de interpretar e executar, no mesmo molde de `dervs_voz_infra`: `interpretar`
devolve uma intenção (dict com "tipo") ou None, e frase que não casa INTEIRA no padrão segue
para o roteador e o cérebro como sempre. "me lembra em 10 minutos…" é do módulo de lembretes
e nunca entra aqui (o padrão exige "lembra que", sem o "me").

Duas travas de privacidade, porque a voz de resposta pode ser de nuvem:
* nota privada nunca tem título nem trecho lidos em voz alta — só "uma nota privada";
* o que parece segredo (senha, chave) não é anotado e não é lido.
"""
import re

import dervs_cofre as cofre

_VOCATIVO = re.compile(r"^\s*(?:(?:ei|oi|ol[áa])\s+)?dervs\b[\s,:;.!-]*", re.IGNORECASE)
_EDUCACAO = re.compile(r"^(?:por\s+favor|pode|poderia)\s+", re.IGNORECASE)

_ANOTA = re.compile(
    r"^(?:anota|anote|anotar)\b(?:\s+(?:a[ií]|isso|uma\s+nota|uma\s+ideia))?"
    r"(?:\s+(?:em\s+|como\s+)?(?P<priv>privado|privada|segredo|sigilo))?"
    r"\s*[:,\-]?\s*(?:que\s+)?(?P<t>.+)$", re.IGNORECASE | re.DOTALL)
_LEMBRA = re.compile(
    r"^(?:lembra|lembre|n[ãa]o\s+esquece|n[ãa]o\s+esque[cç]a|memoriza|memorize)\s+que\s+(?P<t>.+)$",
    re.IGNORECASE | re.DOTALL)
_SEI = re.compile(
    r"^o\s+que\s+(?:eu\s+|a\s+gente\s+|n[óo]s\s+)?(?:sei|anotei|decidi|guardei|escrevi|combinei|tenho\s+anotado)"
    r"\s+(?:(?:sobre|a\s+respeito\s+de|de|do|da|dos|das)\s+)?(?P<c>.+)$", re.IGNORECASE)
_PROCURA = re.compile(
    r"^(?:procura|procure|busca|busque|pesquisa|pesquise|acha|ache)(?:\s+para\s+mim)?"
    r"\s+(?:na|nas|no|nos|em)\s+(?:minhas?\s+|meus?\s+)?(?:notas|anota[çc][õo]es|cofre|segundo\s+c[ée]rebro)"
    r"\s*(?:(?:sobre|por|a\s+respeito\s+de)\s+)?(?P<c>.+)$", re.IGNORECASE)
_ABRIR = re.compile(r"^abr(?:e|ir|iu)\s+(?:o\s+|as\s+|meu\s+|minhas?\s+)?(?:cofre|notas|segundo\s+c[ée]rebro)$", re.IGNORECASE)


def _limpa(fala) -> str:
    t = _VOCATIVO.sub("", str(fala or "")).strip()
    return _EDUCACAO.sub("", t).strip()


_SEM_CONTEUDO = {"que", "isso", "ai", "aí", "uma nota", "uma ideia"}


def _tem_conteudo(texto: str) -> bool:
    miolo = re.sub(r"[\W_]+", " ", texto).strip().lower()
    return len(miolo) >= 3 and miolo not in _SEM_CONTEUDO


def interpretar(fala):
    """Intenção do cofre ou None. Conservador: na dúvida, deixa para o cérebro."""
    if not isinstance(fala, str):
        return None
    t = _limpa(fala)
    if not t:
        return None
    sem_ponto = t.rstrip(" .!?")
    if _ABRIR.match(sem_ponto):
        return {"tipo": "cofre_abrir"}
    for padrao in (_SEI, _PROCURA):
        m = padrao.match(sem_ponto)
        if m and _tem_conteudo(m.group("c")):
            return {"tipo": "cofre_buscar", "consulta": m.group("c").strip()}
    if t.rstrip().endswith("?"):
        return None                 # pergunta ("lembra que horas são?") não é nota: vai ao cérebro
    m = _ANOTA.match(t)
    if m and _tem_conteudo(m.group("t")):
        return {"tipo": "cofre_anotar", "texto": m.group("t").strip(), "privado": bool(m.group("priv"))}
    m = _LEMBRA.match(t)
    if m and _tem_conteudo(m.group("t")):
        return {"tipo": "cofre_anotar", "texto": m.group("t").strip(), "privado": False}
    return None


def _titulo(texto: str) -> str:
    palavras = re.sub(r"[\s]+", " ", texto).strip().split(" ")[:8]
    titulo = " ".join(palavras).strip(" .,;:!?-")[:60].strip()
    return (titulo[:1].upper() + titulo[1:]) or "Nota"


def _trecho(bruto: str) -> str:
    t = re.sub(r"\s+", " ", bruto.replace("[", "").replace("]", "")).strip()
    return t if len(t) <= 140 else t[:139].rstrip() + "…"


def executar(intencao, cv, abrir_pasta=None):
    """Faz o que a intenção pede e devolve a frase a falar (None se a intenção não é do cofre)."""
    tipo = (intencao or {}).get("tipo")
    if tipo == "cofre_anotar":
        texto = intencao["texto"]
        if cofre.parece_segredo(texto):
            return "Não anotei: isso parece um segredo, como senha ou chave. Segredo não vai para o cofre."
        privado = bool(intencao.get("privado"))
        rel = cv.escrever(_titulo(texto), texto, pasta=cofre.PASTA_PRIVADA if privado else "entrada", origem="voz")
        cv.indexar_nota(rel)
        return "Anotei em privado." if privado else "Anotei."
    if tipo == "cofre_buscar":
        consulta = intencao["consulta"]
        cv.reindexar_se_velho()
        achados = cv.buscar_hibrido(consulta, limite=6)
        publicas = [a for a in achados if not a["privado"]][:3]
        privadas = sum(1 for a in achados if a["privado"])
        if not achados:
            return f"Não achei nada nas suas notas sobre {consulta}."
        sufixo = ""
        if privadas:
            sufixo = f" Há {privadas} nota{'s' if privadas > 1 else ''} privada{'s' if privadas > 1 else ''}; abra o cofre para ler."
        if not publicas:
            return ("Achei uma nota privada sobre isso. Abra o cofre para ler." if privadas == 1
                    else f"Achei {privadas} notas privadas sobre isso. Abra o cofre para ler.")
        nomes = " e ".join(a["titulo"] for a in publicas) if len(publicas) <= 2 else \
            ", ".join(a["titulo"] for a in publicas[:-1]) + " e " + publicas[-1]["titulo"]
        fala = f"Achei {len(publicas)} nota{'s' if len(publicas) > 1 else ''}: {nomes}."
        trecho = _trecho(publicas[0]["trecho"])
        if trecho and not cofre.parece_segredo(trecho):
            fala += f" Em {publicas[0]['titulo']}: {trecho}"
        return fala + sufixo
    if tipo == "cofre_abrir":
        if abrir_pasta is not None:
            abrir_pasta(str(cv.raiz))
        return "Abri o cofre."
    return None
