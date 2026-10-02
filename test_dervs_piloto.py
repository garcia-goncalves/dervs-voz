"""Piloto automático: entende a queda, explica e prepara o conserto isolado."""
import os
import subprocess

import pytest

import dervs_piloto as p

TB = (
    "quando: 02/10/2026 10:00:00\n"
    "origem: tela\n"
    "\n"
    "Traceback (most recent call last):\n"
    '  File "C:\\Users\\Dono\\dervs\\dervs_electron.py", line 700, in <module>\n'
    "    main()\n"
    '  File "C:\\Users\\Dono\\dervs\\dervs_electron.py", line 778, in main\n'
    "    x.y\n"
    "AttributeError: 'NoneType' object has no attribute 'y'\n"
)


def test_diagnostico_le_o_ultimo_quadro():
    d = p.diagnosticar(TB)
    assert d["arquivo"] == "dervs_electron.py"
    assert d["linha"] == 778 and d["funcao"] == "main"
    assert d["tipo"] == "AttributeError" and d["origem"] == "tela"
    assert "dervs_electron.py, linha 778" in d["resumo"]
    assert "função main" in d["resumo"]


@pytest.mark.parametrize("t", ["", None, "lixo qualquer", "Traceback (most recent call last):"])
def test_queda_ilegivel_e_honesta(t):
    assert "não consegui entender" in p.diagnosticar(t)["resumo"].lower()


def test_redator_corta_segredos_e_caminho():
    t = TB.replace("'NoneType' object has no attribute 'y'",
                   "chave " + "s" + "k-abcdefghijklmnopqrstuvwxyz123456 em C:\\Users\\Dono\\x")
    d = p.diagnosticar(t)
    assert "sk-abc" not in d["mensagem"] and "Dono" not in d["mensagem"]
    assert "~" in d["mensagem"]


def test_decidir_acao():
    assert p.decidir_acao("analisa") == "so_relatorio"
    assert p.decidir_acao("pergunta") == "propor"
    assert p.decidir_acao("sozinho") == "aplicar"
    assert p.decidir_acao("xis") == "so_relatorio"
    assert p.decidir_acao(None) == "so_relatorio"


def test_anunciar():
    d = p.diagnosticar(TB)
    assert "conserta" in p.anunciar(d, "propor")
    assert "conserta" not in p.anunciar(d, "so_relatorio")
    assert "dervs_electron.py" in p.anunciar(d, "so_relatorio")
    assert "preparando o conserto" in p.anunciar(d, "aplicar")


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "main")
    _git(r, "config", "user.email", "a@b.c")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("1")
    _git(r, "add", ".")
    _git(r, "commit", "-m", "i")
    return str(r)


def test_worktree_criada_em_branch_piloto(repo, tmp_path):
    caminho, branch = p.preparar_worktree(repo, "meu conserto", base_dir=str(tmp_path / "wt"))
    assert branch == "piloto/meu-conserto" and os.path.isfile(os.path.join(caminho, "a.txt"))
    assert _git(repo, "branch", "--show-current").strip() == "main"


@pytest.mark.parametrize("slug", ["../x", "a b", "a;b", "$(rm)"])
def test_slug_malicioso_e_sanitizado(repo, tmp_path, slug):
    base = tmp_path / "wt"
    caminho, branch = p.preparar_worktree(repo, slug, base_dir=str(base))
    assert os.path.dirname(os.path.abspath(caminho)) == str(base)
    assert all(c.isalnum() or c in "-/" for c in branch) and ".." not in branch
    assert len(branch) <= len("piloto/") + 40


def test_slug_vazio_cai_num_padrao(repo, tmp_path):
    _, branch = p.preparar_worktree(repo, "../;;", base_dir=str(tmp_path / "wt"))
    assert branch.startswith("piloto/") and len(branch) > len("piloto/")


def test_recusa_main_e_master(repo, tmp_path):
    for ramo in ("main", "master"):
        with pytest.raises(ValueError):
            p.preparar_worktree(repo, "x", base_dir=str(tmp_path / "wt"), prefixo_branch=ramo)


def _diag():
    return p.diagnosticar(TB)


def test_conserto_com_sucesso_deixa_a_copia(repo, tmp_path):
    visto = {}

    def agente(prompt, cwd):
        visto["prompt"], visto["cwd"] = prompt, cwd

    r = p.aplicar_conserto(_diag(), repo, agente, lambda cwd: (True, "ok"),
                           base_dir=str(tmp_path / "wt"))
    assert r["ok"] and r["branch"].startswith("piloto/") and os.path.isdir(r["caminho"])
    assert "dervs_electron.py" in visto["prompt"] and "teste" in visto["prompt"]
    assert visto["cwd"] == r["caminho"]
    assert _git(repo, "branch", "--show-current").strip() == "main"
    assert len(_git(repo, "log", "--oneline", "main").splitlines()) == 1


def test_testes_vermelhos_limpam(repo, tmp_path):
    r = p.aplicar_conserto(_diag(), repo, lambda pr, cwd: None,
                           lambda cwd: (False, "FAILED"), base_dir=str(tmp_path / "wt"))
    assert not r["ok"] and r["motivo"]
    assert "piloto/" not in _git(repo, "branch")
    assert not os.path.exists(str(tmp_path / "wt")) or not os.listdir(str(tmp_path / "wt"))


def test_agente_que_explode_limpa(repo, tmp_path):
    def agente(pr, cwd):
        raise RuntimeError("boom")

    r = p.aplicar_conserto(_diag(), repo, agente, lambda cwd: (True, ""),
                           base_dir=str(tmp_path / "wt"))
    assert not r["ok"] and "piloto/" not in _git(repo, "branch")


def test_testes_que_explodem_limpam(repo, tmp_path):
    def rodar(cwd):
        raise RuntimeError("boom")

    r = p.aplicar_conserto(_diag(), repo, lambda pr, cwd: None, rodar,
                           base_dir=str(tmp_path / "wt"))
    assert not r["ok"] and "piloto/" not in _git(repo, "branch")


def test_tentativa_de_main_recusada_no_conserto(repo, tmp_path):
    r = p.aplicar_conserto(_diag(), repo, lambda pr, cwd: None, lambda cwd: (True, ""),
                           base_dir=str(tmp_path / "wt"), prefixo_branch="main")
    assert not r["ok"]
