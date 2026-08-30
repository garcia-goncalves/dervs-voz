#!/usr/bin/env python3
"""Grimoire — atalhos locais para o trivial.

Algumas perguntas não precisam do cérebro (o Claude): que horas são, que dia é
hoje, abrir um app. O cérebro custa ~2,7 s por turno; aqui a resposta sai em
milissegundos, sem rede. É o único ganho de velocidade que ainda sobrava depois
que a transcrição bateu no piso físico.

CONTRATO: `tentar(fala)` devolve uma FICHA no MESMO formato de brain.pensar()
  — {"modo": ..., "fala": ..., "passos": [...]} — quando reconhece a frase, ou
  None quando não reconhece. None faz o fluxo cair no cérebro, como antes.

REGRA DE OURO: na dúvida, devolve None. Um atalho é uma OTIMIZAÇÃO, nunca uma
fonte de erro — melhor o cérebro pensar 2,7 s do que o atalho responder errado.
Por isso o casamento é conservador e a lista de apps é curada (só o que existe
nesta máquina e abre solto pelo grimoire_exec).
"""
import re
import shutil
import unicodedata
from datetime import datetime


def _norm(texto: str) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados — para casar a
    fala transcrita sem depender de vírgula, acento ou caixa."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# Hora e data por extenso — a resposta é LIDA em voz alta, então soa natural.
# ---------------------------------------------------------------------------
# Grafia COM acento de propósito: este texto é lido em voz alta pelo Piper, e
# "três" sem acento sai com a pronúncia errada. (O _norm só tira acento da
# ENTRADA, para casar a fala transcrita — nunca da saída.)
_UNID = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete",
         "oito", "nove", "dez", "onze", "doze", "treze", "quatorze", "quinze",
         "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZ = {2: "vinte", 3: "trinta", 4: "quarenta", 5: "cinquenta"}
# Horas no feminino ("uma hora", "duas horas"); o resto usa a forma comum.
_HORAS_FEM = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco",
              6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez",
              11: "onze", 12: "doze"}


def _num_falado(n: int) -> str:
    """Inteiro de 0 a 59 por extenso (para os minutos)."""
    if n < 20:
        return _UNID[n]
    d, u = divmod(n, 10)
    return _DEZ[d] + (" e " + _UNID[u] if u else "")


def hora_falada(agora: datetime) -> str:
    """A hora como uma pessoa diria: 'São três e meia da tarde.'"""
    h, m = agora.hour, agora.minute
    if h == 0:
        base, verbo, periodo = "meia-noite", "É", ""
    elif h == 12:
        base, verbo, periodo = "meio-dia", "É", ""
    else:
        h12 = h % 12 or 12
        base = _HORAS_FEM[h12]
        verbo = "É" if h12 == 1 else "São"
        if 0 <= h < 5:
            periodo = "da madrugada"
        elif h < 12:
            periodo = "da manhã"
        elif h < 18:
            periodo = "da tarde"
        else:
            periodo = "da noite"
    sp = f" {periodo}" if periodo else ""
    if m == 0:
        return f"{verbo} {base}{sp}."
    if m == 30:
        return f"{verbo} {base} e meia{sp}."
    return f"{verbo} {base} e {_num_falado(m)}{sp}."


_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo"]
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_falada(agora: datetime) -> str:
    """A data como uma pessoa diria: 'Hoje é sexta-feira, 30 de agosto.'"""
    return f"Hoje é {_DIAS[agora.weekday()]}, {agora.day} de {_MESES[agora.month - 1]}."


# ---------------------------------------------------------------------------
# Casamento das frases.
# ---------------------------------------------------------------------------
# Hora: "que horas são", "me diz as horas", "que hora é", "tem horas"...
_RE_HORA = re.compile(
    r"\b(que horas?( sao| e| eh)?|me (diz|diga|fala) (as )?horas?|"
    r"tem horas?|horas? agora|qual (a )?hora)\b")
# Data: "que dia é hoje", "que data é hoje", "que dia da semana", "qual a data"...
_RE_DATA = re.compile(
    r"\b(que dia (e|eh) hoje|que data( e| eh)?( hoje)?|que dia (da semana )?(e|eh)|"
    r"qual (a )?data|hoje (e|eh) que dia|dia de hoje)\b")

# Apps que abrem por atalho. Chave: como a pessoa fala (normalizado, sem acento).
# Valor: (comando, nome amigável). Só entram se o binário existir na máquina.
_APPS = {
    "firefox": ("firefox", "o Firefox"),
    "navegador": ("firefox", "o navegador"),
    "chrome": ("google-chrome", "o Chrome"),
    "google chrome": ("google-chrome", "o Chrome"),
    "chromium": ("chromium", "o Chromium"),
    "konsole": ("konsole", "o terminal"),
    "terminal": ("konsole", "o terminal"),
    "dolphin": ("dolphin", "o gerenciador de arquivos"),
    "arquivos": ("dolphin", "os arquivos"),
    "gerenciador de arquivos": ("dolphin", "os arquivos"),
    "calculadora": ("kcalc", "a calculadora"),
    "kcalc": ("kcalc", "a calculadora"),
    "kate": ("kate", "o editor de texto"),
    "editor": ("kate", "o editor de texto"),
    "editor de texto": ("kate", "o editor de texto"),
}
# "abre o firefox", "abrir firefox", "pode abrir o navegador", "abra a calculadora"
_RE_ABRIR = re.compile(r"\b(abre|abrir|abra|inicia|iniciar|abri)\b\s+(.+)$")
# Artigo no começo do alvo ("o firefox" -> "firefox").
_LIXO_INICIO = re.compile(r"^(o|a|os|as|um|uma)\s+")
# Cortesia no fim ("navegador pra mim" -> "navegador", "firefox por favor" -> "firefox").
_LIXO_FIM = re.compile(r"\s+(pra mim|por favor|pfv|agora|ai|então|entao)$")


def _ficha_conversar(fala: str) -> dict:
    return {"modo": "conversar", "fala": fala}


def _ficha_abrir(comando: str, nome: str) -> dict:
    return {
        "modo": "planejar",
        # "local": este plano já resolve tudo aqui — o Grimoire NÃO precisa
        # chamar o cérebro depois de rodá-lo (economiza ~2,7 s e uma chamada).
        "local": True,
        "fala": f"Beleza, abrindo {nome}.",
        "passos": [{
            "descricao": f"Abrir {nome}",
            "comando": comando,
            "risco": "reversivel",
            "reversivel": True,
            "toca_alvo": False,
        }],
    }


def _casar_abrir(n: str) -> dict | None:
    """Reconhece 'abre o X' só se X é um app conhecido E instalado. Qualquer
    outra coisa (abrir arquivo, abrir site, abrir porta...) vai para o cérebro."""
    m = _RE_ABRIR.search(n)
    if not m:
        return None
    alvo = m.group(2).strip()
    alvo = _LIXO_INICIO.sub("", alvo)
    alvo = _LIXO_FIM.sub("", alvo).strip()
    par = _APPS.get(alvo)
    if not par:
        return None
    comando, nome = par
    if shutil.which(comando.split()[0]) is None:
        return None  # app não instalado: deixa o cérebro achar outro caminho
    return _ficha_abrir(comando, nome)


def tentar(fala: str, agora: datetime | None = None) -> dict | None:
    """Devolve a ficha pronta se a fala é trivial e conhecida; senão None.

    `agora` é injetável para o teste; em produção usa a hora do relógio."""
    n = _norm(fala)
    if not n:
        return None
    agora = agora or datetime.now()
    if _RE_HORA.search(n):
        return _ficha_conversar(hora_falada(agora))
    if _RE_DATA.search(n):
        return _ficha_conversar(data_falada(agora))
    return _casar_abrir(n)


if __name__ == "__main__":
    import sys
    fala = " ".join(sys.argv[1:]) or "que horas são"
    print(tentar(fala))
