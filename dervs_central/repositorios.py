"""Repositórios com commit sem push. Nunca faz `fetch`: nada de rede."""
import os
import subprocess

import dervs_processos as processos
from dervs_central.base import falha, resultado

PROFUNDIDADE = 2
_IGNORAR = ("node_modules", ".claude", "dervs-venv", ".venv")


def rodar_git(repo: str) -> str:
    p = subprocess.run(["git", "-C", repo, "status", "--porcelain=v2", "--branch"],
                       capture_output=True, timeout=20, **processos.sem_janela())
    if p.returncode != 0:
        raise OSError("git recusou")
    return p.stdout.decode("utf-8", "replace")


def interpretar(saida: str) -> dict:
    r = {"branch": "", "ahead": 0, "behind": 0, "sujo": False, "sem_upstream": True}
    for linha in saida.splitlines():
        if linha.startswith("# branch.head "):
            r["branch"] = linha.split(" ", 2)[2]
        elif linha.startswith("# branch.upstream"):
            r["sem_upstream"] = False
        elif linha.startswith("# branch.ab "):
            _, _, a, b = linha.split()
            r["ahead"], r["behind"] = int(a.lstrip("+")), abs(int(b))
        elif not linha.startswith("#") and linha.strip():
            r["sujo"] = True
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
                if dados["ahead"] or dados["sujo"] or (dados["sem_upstream"] and dados["branch"]):
                    itens.append(dict(dados, repo=repo, nome=os.path.basename(repo)))
    except OSError as erro:
        return falha(erro)
    return resultado(itens)
