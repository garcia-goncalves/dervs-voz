#!/usr/bin/env python3
"""DERVS — o Codex por voz: "pergunta pro Codex…", "pede pro Codex…", "no projeto X pede pro Codex…".

Mesmo molde de `dervs_cofre_voz` e `dervs_voz_infra`: `interpretar` devolve uma intenção (dict com
"tipo") ou None, e frase que não casa INTEIRA no padrão segue para o roteador e o cérebro como
sempre. Quem executa é `AcoesCodex`, com tudo de fora injetado para o teste.

Travas:
  - Leitura ("analisa", "explica", "o que…") roda em somente leitura, na pasta do projeto.
  - Escrita ("faz", "corrige", "cria"…) exige projeto, só roda depois do "confirma" dito pelo dono, numa
    cópia git worktree em branch `dervs/codex-…` (nunca a main), sem rede e sem credencial: o Codex não
    tem como mandar nada ao GitHub, e este módulo nunca faz commit nem push.
  - Pedido que parece segredo (senha, chave) não vai ao Codex, que é de um terceiro.
"""
import os
import re
import secrets
import subprocess
import threading
import time
import unicodedata

import dervs_cofre as cofre
import dervs_codex as codex_mod
import dervs_voz_infra as voz_infra

MAX_PEDIDO = 1500
VALIDADE_CONFIRMACAO_S = 120
_BORDAS = " \t\r\n,;:-"
_VERBOS_ESCRITA = {
    "faz", "faca", "fazer", "corrige", "corrija", "corrigir", "conserta", "conserte", "consertar",
    "implementa", "implemente", "implementar", "cria", "crie", "criar", "escreve", "escreva", "escrever",
    "refatora", "refatore", "refatorar", "arruma", "arrume", "arrumar", "adiciona", "adicione",
    "adicionar", "altera", "altere", "alterar", "muda", "mude", "mudar", "remove", "remova", "remover",
    "atualiza", "atualize", "atualizar", "ajusta", "ajuste", "ajustar", "troca", "troque", "trocar",
    "apaga", "apague", "apagar", "renomeia", "renomeie", "renomear",
}

_VERBO = r"(?P<v>pergunta|pergunte|perguntar|pede|peca|pedir|manda|mande|mandar|usa|use|usar)"
_VERBOS_FORTES = {"pergunta", "pergunte", "perguntar", "pede", "peca", "pedir", "manda", "mande", "mandar"}
_ALVO = r"(?:pro|pra|para o|para|ao|o|com o)"
# o reconhecedor de voz troca o nome ("cloud" no lugar de "Claude"): aceita as trocas mais comuns. As
# variantes fracas (palavras que existem de verdade: codec, codes, kodak) só valem com verbo forte e
# nunca com "usa" ("usa o codec h264" não pode ser roubado).
_NOME = r"(?P<nome>codex|codice|kodex|codecs?|kodak|code x|codes)"
_NOMES_FRACOS = {"codec", "codecs", "codes", "kodak", "code x"}
_PEDIDO_DIRETO = re.compile(rf"^{_VERBO}\s+{_ALVO}\s+{_NOME}\b[\s,:;-]*(?:(?:para|pra|que)\s+)?(?P<p>.+)$", re.DOTALL)
_PEDIDO_NO_PROJETO = re.compile(
    rf"^(?:no|do|na|da|em)\s+projeto\s+(?:do\s+|da\s+|de\s+)?(?P<n>.+?)[\s,:;-]+{_VERBO}\s+{_ALVO}\s+{_NOME}\b"
    r"[\s,:;-]*(?:(?:para|pra|que)\s+)?(?P<p>.+)$", re.DOTALL)
_PROJETO_NO_FIM = re.compile(
    r"^(?P<antes>.+?)[\s,]+(?P<prep>no|do|na|da|em|o)\s+projeto\s+(?:do\s+|da\s+|de\s+)?(?P<n>[a-z0-9][\w .-]{0,60})$")
# sem projeto, a leitura NÃO é isolada: o somente-leitura enxerga o disco todo. Por isso o pedido que
# cita caminho absoluto ou segredo, sem projeto, é recusado.
_SENSIVEL = re.compile(r"\b[a-z]:[\\/]|(?:^|\s)/[\w.]|\.env\b|\bsenhas?\b|\bchaves?\b|\btokens?\b|\bsegredos?\b|"
                       r"auth\.json|id_rsa")
_VOCATIVO = re.compile(r"^(?:(?:ei|oi|ola)\s+)?dervs\b[\s,:;.!-]*")
_EDUCACAO = re.compile(r"^(?:por favor|pode|poderia|bora)[\s,]+")


def _sem_acento(texto: str) -> str:
    """Minúsculas sem acento, caractere a caractere: o tamanho não muda, então uma posição achada
    aqui serve para fatiar a fala ORIGINAL (o Codex recebe o texto com acento)."""
    return "".join(unicodedata.normalize("NFD", c.lower()[:1] or c)[0] for c in str(texto))


def interpretar(fala):
    """Intenção do Codex ou None. Conservador: na dúvida, deixa para o cérebro."""
    if not isinstance(fala, str):
        return None
    original = fala.strip().rstrip(" .!")
    t = _sem_acento(original)
    for padrao in (_VOCATIVO, _EDUCACAO):
        m = padrao.match(t)
        if m:
            original, t = original[m.end():], t[m.end():]
    if not t.strip():
        return None
    projeto = inteiro = None
    m = _PEDIDO_NO_PROJETO.match(t)
    if m:
        if m.group("nome") in _NOMES_FRACOS and m.group("v") not in _VERBOS_FORTES:
            return None
        projeto = original[m.start("n"):m.end("n")].strip(_BORDAS)
        pedido = original[m.start("p"):m.end("p")].strip(_BORDAS)
    else:
        m = _PEDIDO_DIRETO.match(t)
        if not m or (m.group("nome") in _NOMES_FRACOS and m.group("v") not in _VERBOS_FORTES):
            return None
        bruto = original[m.start("p"):m.end("p")]
        pedido = bruto.strip(_BORDAS)
        mp = _PROJETO_NO_FIM.match(t[m.start("p"):m.end("p")])
        if mp:
            projeto = bruto[mp.start("n"):mp.end("n")].strip(_BORDAS)
            if mp.group("prep") != "o":              # "analisa o projeto X": a frase inteira vale
                inteiro = pedido                     # projeto que não existir: a frase inteira vira pergunta solta
                pedido = bruto[mp.start("antes"):mp.end("antes")].strip(_BORDAS)
    if not pedido or len(re.sub(r"[\W_]+", "", pedido)) < 3:
        return None
    if projeto is not None and not re.sub(r"[\W_]+", "", projeto):
        return None
    if len(pedido) > MAX_PEDIDO:
        return {"tipo": "falar", "fala": "Esse pedido ficou longo demais para mandar ao Codex."}
    primeira = _sem_acento(pedido).split()[0].strip(",.:;")
    escrita = primeira in _VERBOS_ESCRITA
    if escrita and not projeto:
        return {"tipo": "falar", "fala": "Para o Codex mexer em código eu preciso saber o projeto. "
                                         "Diga: no projeto tal, pede pro Codex fazer isso."}
    i = {"tipo": "codex_escrita" if escrita else "codex_leitura", "pedido": pedido, "projeto": projeto}
    if inteiro and not escrita:
        i["pedido_inteiro"] = inteiro
    return i


def _git_seguro(pasta, *args, rodar=subprocess.run):
    """`git -C pasta ...` sem shell, sem credencial, sem hook e sem fsmonitor: a worktree compartilha
    `.git/hooks` do repositório principal, e um hook plantado rodaria no primeiro `git status`."""
    return rodar(["git", "-C", pasta, "-c", "core.hooksPath=NUL", "-c", "core.fsmonitor=false", *args],
                 capture_output=True, text=True, timeout=60, env=codex_mod._ambiente(True),
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class AcoesCodex:
    """Executa uma intenção do Codex e devolve a frase que o DERVS fala. Nunca levanta."""

    def __init__(self, *, codex, raizes_fn, mostrar_texto=None, git=_git_seguro,
                 relogio=time.monotonic, pasta_worktrees=None, pasta_neutra=None):
        self._codex = codex
        self._raizes = raizes_fn
        self._mostrar = mostrar_texto or (lambda texto: None)
        self._git = git
        self._relogio = relogio
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        self._pasta_wt = pasta_worktrees or os.path.join(base, "dervs", "worktrees")
        self._pasta_neutra = pasta_neutra or os.path.join(base, "dervs", "codex-vazio")
        self._pendente = None
        self._trava = threading.RLock()      # `_pendente` é tocado pela thread da tela e pelas de trabalho

    # -- confirmação por voz (escrita)
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
            return "Certo, cancelei. O Codex não mexeu em nada."
        try:
            return self._rodar_escrita(p)
        except Exception as erro:
            return f"Algo falhou por dentro ({type(erro).__name__}). Nada foi enviado."

    def executar(self, i: dict) -> str:
        try:
            return self._despachar(i)
        except Exception as erro:
            return f"Algo falhou por dentro ({type(erro).__name__}). Nada foi feito."

    def _despachar(self, i):
        tipo = i["tipo"]
        if tipo == "falar":
            return i["fala"]
        if tipo not in ("codex_leitura", "codex_escrita"):
            return "Não entendi o que fazer."
        if cofre.parece_segredo(i["pedido"]):
            return "Não mandei ao Codex: o pedido parece conter um segredo, como senha ou chave."
        if self._codex.ocupado:
            return "Ainda estou com um pedido ao Codex. Diga para se quiser interromper."
        pasta = None
        pedido = i["pedido"]
        if i.get("projeto"):
            pasta, empate = voz_infra.achar_projeto(i["projeto"], self._raizes())
            if pasta is None:
                if empate:
                    return "Achei mais de um projeto parecido: " + ", ".join(empate) + ". Qual deles?"
                if tipo == "codex_leitura" and i.get("pedido_inteiro"):
                    pedido = i["pedido_inteiro"]             # "no projeto" era parte da pergunta, não um projeto
                else:
                    return f"Não achei o projeto {i['projeto']} nas suas pastas de projeto."
        if pasta is None and tipo == "codex_leitura" and _SENSIVEL.search(_sem_acento(pedido)):
            return ("Sem um projeto escolhido o Codex enxerga o computador todo, então não mando pedido com "
                    "caminho, senha, chave ou segredo. Escolha um projeto: no projeto tal, pede pro Codex isso.")
        if tipo == "codex_escrita":
            return self._preparar_escrita(pasta, i["pedido"])
        if pasta is None:
            # sem projeto o Codex começa numa pasta vazia, mas ISSO NÃO ISOLA a leitura (o somente-leitura
            # enxerga o disco todo): quem barra pedido sobre caminho ou segredo é o `_SENSIVEL` acima
            os.makedirs(self._pasta_neutra, exist_ok=True)
            pasta = self._pasta_neutra
        r = self._codex.perguntar(pedido, pasta, "leitura")
        return self._falar(r, os.path.basename(pasta))

    def _falar(self, r: dict, rotulo: str, prefixo: str = "") -> str:
        if not r["ok"]:
            if r["motivo"] == "ocupado":
                return "Ainda estou com um pedido ao Codex. Diga para se quiser interromper."
            return r["motivo"]
        self._mostrar(f"Codex ({rotulo}):\n{r['texto']}")           # o texto completo fica na conversa
        fala = codex_mod.fala_curta(r["texto"])
        return prefixo + (fala or "O Codex respondeu. A resposta completa está na conversa.")

    # -- escrita: cópia isolada + "confirma"
    def _preparar_escrita(self, pasta, pedido):
        if self._git(pasta, "rev-parse", "--is-inside-work-tree").returncode != 0:
            return "Essa pasta não é um repositório git; não pedi nada ao Codex."
        with self._trava:
            self._pendente = {"pasta": pasta, "pedido": pedido, "expira": self._relogio() + VALIDADE_CONFIRMACAO_S}
        return (f"Vou pedir ao Codex, numa cópia isolada do {os.path.basename(pasta)}: {pedido}. "
                "Ele não vai poder mandar nada ao GitHub. Diga confirma para eu começar.")

    def _remover_worktree(self, pasta, destino, branch):
        self._git(pasta, "worktree", "remove", "--force", destino)
        self._git(pasta, "branch", "-D", branch)

    def _rodar_escrita(self, p):
        pasta, pedido = p["pasta"], p["pedido"]
        if not self._codex.reservar():                  # o slot é tomado ANTES de criar a cópia isolada
            return "Ainda estou com um pedido ao Codex. Diga para se quiser interromper."
        entregue = False
        try:
            sufixo = secrets.token_hex(2)
            branch = f"dervs/codex-{voz_infra._slug(pedido)}-{sufixo}"
            destino = os.path.join(self._pasta_wt, f"{voz_infra._slug(os.path.basename(pasta))}-codex-{sufixo}")
            os.makedirs(self._pasta_wt, exist_ok=True)
            if self._git(pasta, "worktree", "add", "-b", branch, destino).returncode != 0:
                return "Não consegui criar a cópia isolada do projeto. Nada foi feito."
            entregue = True                             # a partir daqui `perguntar` libera o slot
            r = self._codex.perguntar(pedido, destino, "escrita", reservado=True)
        finally:
            if not entregue:
                self._codex.liberar()
        if not r["ok"] and r["motivo"] == "ocupado":
            self._remover_worktree(pasta, destino, branch)
            return "Ainda estou com um pedido ao Codex. Diga para se quiser interromper."
        if not os.path.isfile(os.path.join(destino, ".git")):
            # o `.git` da worktree é um ARQUIVO; virou pasta = o Codex mexeu onde não devia (git rodaria hook)
            return (f"Parei: a cópia isolada em {destino} mudou de forma (o .git virou pasta). "
                    "Não rodei git nela. Confira essa pasta antes de usar.")
        mudou = self._git(destino, "status", "--porcelain=v1", "--untracked-files=all")
        n = len([x for x in (mudou.stdout or "").splitlines() if x.strip()]) if mudou.returncode == 0 else 0
        resumo = (f"Mudou {n} arquivo{'s' if n != 1 else ''} no branch {branch}, na cópia isolada, sem commit "
                  "e sem enviar nada ao GitHub. ")
        if not r["ok"]:
            return (resumo if n else "") + r["motivo"]
        return self._falar(r, os.path.basename(pasta), prefixo=resumo)
