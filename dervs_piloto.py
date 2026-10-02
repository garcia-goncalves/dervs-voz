#!/usr/bin/env python3
"""Piloto automático: o DERVS caiu, entende por quê, conta ao dono e (se ele
liberou) prepara o conserto numa cópia isolada.

Regras que não se negociam:
* NUNCA mescla, NUNCA dá push, NUNCA mexe na árvore principal: o conserto
  vive num `git worktree` em branch `piloto/<slug>`; quem decide é o dono.
* NUNCA aprova nada nem simula clique (não toca o Motor de aprovação).
* `git` roda sem shell, com argumentos em lista.
* O diagnóstico não carrega segredo: a mensagem passa por um redator.
"""
import os
import re
import shutil
import subprocess

import dervs_config as cfg

NAO_ENTENDI = "Não consegui entender a queda."
_PROTEGIDOS = ("main", "master")

_RE_QUADRO = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
_RE_ERRO = re.compile(r"^([A-Za-z_][\w.]*)(?::\s*(.*))?$")
_RE_ORIGEM = re.compile(r"^origem:\s*(.*)$", re.M)

_EXPLICACAO = {
    "AttributeError": "algo que devia existir estava vazio ou não tinha o que se esperava",
    "KeyError": "faltou um dado que o programa esperava encontrar",
    "TypeError": "um valor de tipo errado foi usado",
    "ValueError": "um valor chegou num formato inválido",
    "ImportError": "não consegui carregar uma peça do programa",
    "ModuleNotFoundError": "uma peça do programa não está instalada",
    "FileNotFoundError": "um arquivo necessário não foi encontrado",
    "PermissionError": "o Windows negou acesso a um arquivo",
    "OSError": "o sistema operacional recusou uma operação",
    "RuntimeError": "o programa encontrou uma situação que não sabia tratar",
    "IndexError": "o programa procurou um item que não existe na lista",
    "ZeroDivisionError": "houve uma divisão por zero",
}


def _redigir(texto: str) -> str:
    """Tira segredo e caminho de usuário do que vai ser falado ou mostrado."""
    texto = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[segredo]", texto)
    texto = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "[segredo]", texto)
    texto = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+", "~", texto, flags=re.I)
    texto = re.sub(r"/(?:home|Users)/[^/\s]+", "~", texto)
    return texto[:300]


def diagnosticar(texto) -> dict:
    """Lê o traceback guardado e devolve o diagnóstico. Nunca levanta."""
    vazio = {"origem": "", "arquivo": "", "linha": 0, "funcao": "", "tipo": "",
             "mensagem": "", "resumo": NAO_ENTENDI}
    try:
        texto = texto or ""
        quadros = _RE_QUADRO.findall(texto)
        if "Traceback" not in texto or not quadros:
            return vazio
        caminho, linha, funcao = quadros[-1]
        arquivo = re.split(r"[\\/]", caminho)[-1]
        ultima = [l for l in texto.strip().splitlines() if l.strip()][-1].strip()
        m = _RE_ERRO.match(ultima)
        tipo, msg = (m.group(1), m.group(2) or "") if m else ("", "")
        if not tipo or ultima.startswith("File "):
            return vazio
        origem = _RE_ORIGEM.search(texto)
        porque = _EXPLICACAO.get(tipo, "ocorreu um erro inesperado")
        return {
            "origem": origem.group(1).strip() if origem else "",
            "arquivo": arquivo, "linha": int(linha), "funcao": funcao,
            "tipo": tipo, "mensagem": _redigir(msg),
            "resumo": "O DERVS caiu em %s, linha %s (função %s): %s — %s."
                      % (arquivo, linha, funcao, tipo, porque),
        }
    except Exception:
        return vazio


def decidir_acao(nivel_alterar_projeto) -> str:
    return {"analisa": "so_relatorio", "pergunta": "propor",
            "sozinho": "aplicar"}.get(nivel_alterar_projeto, "so_relatorio")


def anunciar(diag: dict, acao: str) -> str:
    """A frase que o motor fala ao dono."""
    resumo = (diag or {}).get("resumo") or NAO_ENTENDI
    if acao == "aplicar":
        return "%s Estou preparando o conserto numa cópia segura." % resumo
    if acao == "propor":
        return ("%s Quer que eu prepare o conserto numa cópia segura? "
                "Diga 'conserta'." % resumo)
    return resumo


def _slug(texto) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", str(texto or "").lower()).strip("-")[:40].strip("-")
    return s or "queda"


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True, timeout=60)


def preparar_worktree(repo, slug, base_dir=None, git=_git, prefixo_branch="piloto"):
    """Cria `<base_dir>/<slug>` num branch novo `piloto/<slug>` a partir do HEAD.

    Devolve (caminho, branch). Recusa main/master. Não faz checkout, commit,
    merge nem push na árvore principal.
    """
    slug = _slug(slug)
    prefixo = re.sub(r"[^a-z0-9/-]+", "-", str(prefixo_branch).lower()).strip("/-")
    branch = "%s/%s" % (prefixo, slug) if prefixo else slug
    if prefixo in _PROTEGIDOS or branch in _PROTEGIDOS:
        raise ValueError("o piloto nunca mexe em %s" % branch)
    base = os.path.abspath(base_dir or os.path.join(cfg.CONFIG_DIR, "piloto"))
    os.makedirs(base, exist_ok=True)
    caminho = os.path.join(base, slug)
    git(repo, "worktree", "add", "-b", branch, caminho, "HEAD")
    return caminho, branch


def _limpar(repo, caminho, branch, git=_git):
    for args in (("worktree", "remove", "--force", caminho), ("branch", "-D", branch)):
        try:
            git(repo, *args)
        except Exception:
            pass
    shutil.rmtree(caminho, ignore_errors=True)


def _prompt(diag) -> str:
    return (
        "O DERVS caiu. Diagnóstico: %s\n"
        "Arquivo: %s, linha %s, função %s. Erro: %s: %s\n"
        "Corrija SOMENTE a causa desta queda, com a menor mudança possível, e "
        "escreva um teste novo que falhava antes e passa depois. Não mexa em "
        "mais nada, não faça merge nem push."
        % (diag.get("resumo"), diag.get("arquivo"), diag.get("linha"),
           diag.get("funcao"), diag.get("tipo"), diag.get("mensagem")))


def aplicar_conserto(diag, repo, agente, rodar_testes, base_dir=None,
                     prefixo_branch="piloto", git=_git):
    """Prepara o conserto numa cópia isolada. NUNCA mescla nem dá push.

    `agente(prompt, cwd=...)` e `rodar_testes(cwd) -> (ok, saida)` são injetados.
    Testes vermelhos ou qualquer exceção: remove a cópia e o branch.
    """
    diag = diag or {}
    slug = "%s-%s" % (str(diag.get("arquivo", "")).replace(".py", ""), diag.get("linha", ""))
    try:
        caminho, branch = preparar_worktree(repo, slug, base_dir, git, prefixo_branch)
    except Exception as e:
        return {"ok": False, "motivo": "não consegui preparar a cópia: %s" % _redigir(str(e))}
    try:
        agente(_prompt(diag), cwd=caminho)
        ok, saida = rodar_testes(caminho)
    except Exception as e:
        _limpar(repo, caminho, branch, git)
        return {"ok": False, "motivo": "o conserto falhou: %s" % _redigir(str(e))}
    if not ok:
        _limpar(repo, caminho, branch, git)
        return {"ok": False, "motivo": "os testes não passaram: %s" % _redigir(str(saida)[-200:])}
    return {"ok": True, "branch": branch, "caminho": caminho}
