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

_VERBO = r"(?:pergunta|pergunte|perguntar|pede|peca|pedir|manda|mande|mandar|usa|use|usar)"
_ALVO = r"(?:pro|pra|para o|para|ao|o|com o)"
_PEDIDO_DIRETO = re.compile(rf"^{_VERBO}\s+{_ALVO}\s+codex\b[\s,:;-]*(?:(?:para|pra|que)\s+)?(?P<p>.+)$", re.DOTALL)
_PEDIDO_NO_PROJETO = re.compile(
    rf"^(?:no|do|na|da|em)\s+projeto\s+(?:do\s+|da\s+|de\s+)?(?P<n>.+?)[\s,:;-]+{_VERBO}\s+{_ALVO}\s+codex\b"
    r"[\s,:;-]*(?:(?:para|pra|que)\s+)?(?P<p>.+)$", re.DOTALL)
_PROJETO_NO_FIM = re.compile(
    r"^(?P<antes>.+?)[\s,]+(?P<prep>no|do|na|da|em|o)\s+projeto\s+(?:do\s+|da\s+|de\s+)?(?P<n>[a-z0-9][\w .-]{0,60})$")
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
    projeto = None
    m = _PEDIDO_NO_PROJETO.match(t)
    if m:
        projeto = original[m.start("n"):m.end("n")].strip(_BORDAS)
        pedido = original[m.start("p"):m.end("p")].strip(_BORDAS)
    else:
        m = _PEDIDO_DIRETO.match(t)
        if not m:
            return None
        bruto = original[m.start("p"):m.end("p")]
        pedido = bruto.strip(_BORDAS)
        mp = _PROJETO_NO_FIM.match(t[m.start("p"):m.end("p")])
        if mp:
            projeto = bruto[mp.start("n"):mp.end("n")].strip(_BORDAS)
            if mp.group("prep") != "o":              # "analisa o projeto X": a frase inteira vale
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
    return {"tipo": "codex_escrita" if escrita else "codex_leitura", "pedido": pedido, "projeto": projeto}


class AcoesCodex:
    """Executa uma intenção do Codex e devolve a frase que o DERVS fala. Nunca levanta."""

    def __init__(self, *, codex, raizes_fn, mostrar_texto=None, git=voz_infra._git,
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

    # -- confirmação por voz (escrita)
    def tem_pendencia(self) -> bool:
        p = self._pendente
        if p and self._relogio() > p["expira"]:
            self._pendente = None
        return self._pendente is not None

    def responder_pendencia(self, sim: bool) -> str:
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
        if i.get("projeto"):
            pasta, empate = voz_infra.achar_projeto(i["projeto"], self._raizes())
            if pasta is None:
                if empate:
                    return "Achei mais de um projeto parecido: " + ", ".join(empate) + ". Qual deles?"
                return f"Não achei o projeto {i['projeto']} nas suas pastas de projeto."
        if tipo == "codex_escrita":
            return self._preparar_escrita(pasta, i["pedido"])
        if pasta is None:
            os.makedirs(self._pasta_neutra, exist_ok=True)       # sem projeto: pasta vazia, sem nada para ler
            pasta = self._pasta_neutra
        r = self._codex.perguntar(i["pedido"], pasta, "leitura")
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
        self._pendente = {"pasta": pasta, "pedido": pedido, "expira": self._relogio() + VALIDADE_CONFIRMACAO_S}
        return (f"Vou pedir ao Codex, numa cópia isolada do {os.path.basename(pasta)}: {pedido}. "
                "Ele não vai poder mandar nada ao GitHub. Diga confirma para eu começar.")

    def _rodar_escrita(self, p):
        pasta, pedido = p["pasta"], p["pedido"]
        if self._codex.ocupado:
            return "Ainda estou com um pedido ao Codex. Diga para se quiser interromper."
        hora = time.strftime("%H%M%S")
        branch = f"dervs/codex-{voz_infra._slug(pedido)}-{hora[:4]}"
        destino = os.path.join(self._pasta_wt, f"{voz_infra._slug(os.path.basename(pasta))}-codex-{hora}")
        os.makedirs(self._pasta_wt, exist_ok=True)
        if self._git(pasta, "worktree", "add", "-b", branch, destino).returncode != 0:
            return "Não consegui criar a cópia isolada do projeto. Nada foi feito."
        r = self._codex.perguntar(pedido, destino, "escrita")
        mudou = self._git(destino, "status", "--porcelain=v1", "--untracked-files=all")
        n = len([x for x in (mudou.stdout or "").splitlines() if x.strip()]) if mudou.returncode == 0 else 0
        resumo = (f"Mudou {n} arquivo{'s' if n != 1 else ''} no branch {branch}, na cópia isolada, sem commit "
                  "e sem enviar nada ao GitHub. ")
        if not r["ok"]:
            return (resumo if n else "") + r["motivo"]
        return self._falar(r, os.path.basename(pasta), prefixo=resumo)
