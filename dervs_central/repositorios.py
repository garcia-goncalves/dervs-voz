"""Repositórios com commit sem push. Nunca faz `fetch`: nada de rede."""
import os
import re
import subprocess

import dervs_processos as processos
from dervs_central.base import falha, resultado

PROFUNDIDADE = 2
_IGNORAR = ("node_modules", ".claude", "dervs-venv", ".venv")


def _git(repo: str, *args) -> str:
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=20,
                       **processos.sem_janela())
    if p.returncode != 0:
        raise OSError("git recusou")
    return p.stdout.decode("utf-8", "replace")


def rodar_git(repo: str) -> str:
    """Lê SÓ as referências (branch atual e quanto está à frente do remoto).
    Nunca `git status`: ele lê a árvore de trabalho e executa o que o `.git/config`
    do projeto mandar (fsmonitor, filtros) — uma pasta copiada de fora rodaria
    código do autor dela dentro do DERVS. `for-each-ref` e `symbolic-ref` não."""
    atual = _git(repo, "symbolic-ref", "--short", "-q", "HEAD").strip()
    refs = _git(repo, "for-each-ref", "--format=%(refname:short)%09%(upstream:short)%09%(upstream:track)",
                "refs/heads")
    return f"HEAD{chr(9)}{atual}{chr(10)}{refs}"


def interpretar(saida: str) -> dict:
    """`saida` é o que `rodar_git` devolve: 'HEAD<TAB>branch' e uma linha por branch
    local 'nome<TAB>upstream<TAB>[ahead N, behind M]'."""
    r = {"branch": "", "ahead": 0, "behind": 0, "sujo": False, "sem_upstream": True}
    linhas = saida.splitlines()
    if linhas and linhas[0].startswith("HEAD" + chr(9)):
        r["branch"] = linhas[0].split(chr(9), 1)[1].strip()
    for linha in linhas[1:]:
        campos = linha.split(chr(9))
        if campos[0] != r["branch"]:
            continue
        if len(campos) > 1 and campos[1]:
            r["sem_upstream"] = False
        track = campos[2] if len(campos) > 2 else ""
        for chave in ("ahead", "behind"):
            m = re.search(chave + " (" + chr(92) + "d+)", track)
            if m:
                r[chave] = int(m.group(1))
    return r


def _achar(raiz: str, nivel: int = 0):
    if os.path.isdir(os.path.join(raiz, ".git")):
        yield raiz
        return
    if nivel >= PROFUNDIDADE:
        return
    try:
        with os.scandir(raiz) as it:
            for e in sorted(it, key=lambda x: x.name):
                if e.is_dir(follow_symlinks=False) and e.name not in _IGNORAR:
                    yield from _achar(e.path, nivel + 1)
    except OSError:
        return


def coletar(raizes=None, rodar_git_fn=None) -> dict:
    if raizes is None:
        raizes = [os.path.join(os.path.expanduser("~"), "source", "repos")]
    lendo = rodar_git_fn or rodar_git
    itens = []
    try:
        for raiz in raizes:
            for repo in _achar(raiz):
                try:
                    dados = interpretar(lendo(repo))
                except (OSError, subprocess.SubprocessError, ValueError):
                    continue
                if dados["ahead"] or (dados["sem_upstream"] and dados["branch"]):
                    itens.append(dict(dados, repo=repo, nome=os.path.basename(repo)))
    except OSError as erro:
        return falha(erro)
    return resultado(itens)
