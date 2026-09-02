#!/usr/bin/env python3
"""DERVS — atalhos locais para o trivial.

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
nesta máquina e abre solto pelo dervs_exec).
"""
import os
import re
import shutil
import sys
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
# Valor: (comando, nome amigável). Duas tabelas — Linux (a máquina original,
# Parrot/KDE) e Windows — escolhidas em tempo de execução por sys.platform.
# As FRASES em português são as mesmas nas duas; só o binário muda.
_APPS_LINUX = {
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
_APPS_WINDOWS = {
    "firefox": ("firefox.exe", "o Firefox"),
    "navegador": ("chrome.exe", "o navegador"),
    "chrome": ("chrome.exe", "o Chrome"),
    "google chrome": ("chrome.exe", "o Chrome"),
    "edge": ("msedge.exe", "o Edge"),
    "terminal": ("wt.exe", "o terminal"),
    "prompt": ("wt.exe", "o terminal"),
    "powershell": ("wt.exe", "o terminal"),
    "arquivos": ("explorer.exe", "os arquivos"),
    "explorador": ("explorer.exe", "o explorador de arquivos"),
    "gerenciador de arquivos": ("explorer.exe", "os arquivos"),
    "calculadora": ("calc.exe", "a calculadora"),
    "editor": ("notepad.exe", "o editor de texto"),
    "editor de texto": ("notepad.exe", "o editor de texto"),
    "bloco de notas": ("notepad.exe", "o bloco de notas"),
    "configuracoes": ("explorer.exe ms-settings:", "as configurações"),
    "painel de controle": ("explorer.exe ms-settings:", "as configurações"),
}
_APPS = _APPS_WINDOWS if sys.platform == "win32" else _APPS_LINUX


def _via_registro(nome: str) -> str | None:
    """Procura o executável na chave 'App Paths' do registro do Windows — é o
    jeito oficial de achar Chrome/Firefox/etc, que raramente ficam no PATH."""
    try:
        import winreg
    except ImportError:
        return None  # não é Windows
    subchave = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{nome}"
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(raiz, subchave) as chave:
                valor, _ = winreg.QueryValueEx(chave, None)
                if valor and os.path.exists(valor):
                    return valor
        except OSError:
            continue
    return None


# Caminhos conhecidos de instalação — último recurso, quando nem o PATH nem o
# registro acham o programa.
_CAMINHOS_CONHECIDOS = {
    "chrome.exe": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "firefox.exe": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "msedge.exe": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "wt.exe": [
        os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"),
    ],
}


def _via_caminhos_conhecidos(nome: str) -> str | None:
    for caminho in _CAMINHOS_CONHECIDOS.get(nome, []):
        if os.path.exists(caminho):
            return caminho
    return None


def _resolver_programa(nome: str) -> str | None:
    """Acha o executável de verdade para 'nome' (ex.: 'chrome.exe'), tentando
    nesta ordem: PATH, registro do Windows, caminhos conhecidos de instalação.

    REGRA DE OURO: se não achar em lugar nenhum, devolve None — quem chama
    decide se deixa o cérebro tentar outro caminho."""
    achado = shutil.which(nome)
    if achado:
        return achado
    achado = _via_registro(nome)
    if achado:
        return achado
    return _via_caminhos_conhecidos(nome)


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
        # "local": este plano já resolve tudo aqui — o DERVS NÃO precisa
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
    primeiro = comando.split()[0]
    if _resolver_programa(primeiro) is None:
        return None  # app não instalado: deixa o cérebro achar outro caminho
    return _ficha_abrir(comando, nome)


# ---------------------------------------------------------------------------
# Confirmação por voz — quando um plano está esperando o OK do dono.
# ---------------------------------------------------------------------------
_AFIRMA = {
    "ok", "okay", "oquei", "okei", "sim", "pode", "faz", "faca", "manda",
    "vai", "isso", "confirma", "confirmado", "confirmar", "positivo", "beleza",
    "blz", "fechou", "bora", "vamos", "claro", "perfeito", "exato", "aham",
    "certo", "correto", "roda", "executa", "manda ver", "pode ser", "pode sim",
    "isso ai", "isso mesmo", "ta bom", "tá bom", "com certeza", "vai la", "manda bala",
}
_NEGA = {
    "nao", "cancela", "cancelar", "cancelado", "deixa", "para", "pare", "esquece",
    "negativo", "nem", "para nao", "melhor nao", "deixa pra la", "deixa quieto",
    "nao precisa", "cancela isso", "para tudo",
}


def eh_confirmacao(texto: str) -> str | None:
    """Numa frase CURTA, diz se o dono confirmou ('sim'), recusou ('nao') ou
    nenhum dos dois (None → é uma correção/novo pedido, vai para o cérebro).

    Conservador de propósito: só decide em frase curta (até 4 palavras). "Não,
    faz no Firefox" tem mais de 4 palavras → None → o cérebro re-planeja."""
    n = _norm(texto)
    if not n:
        return None
    if n in _AFIRMA:
        return "sim"
    if n in _NEGA:
        return "nao"
    palavras = n.split()
    if len(palavras) > 4:
        return None  # frase longa = correção/instrução nova, não um simples ok
    # começa com palavra de negação ("não", "cancela ...") pesa como recusa
    if palavras[0] in {"nao", "cancela", "cancelar", "para", "pare", "esquece", "negativo"}:
        return "nao"
    if palavras[0] in _AFIRMA or n in _AFIRMA:
        return "sim"
    return None


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
