"""Testes do tratador local dos recados do painel web (dervs_ponte_tratador)."""
import json
import os

import pytest

import dervs_ponte_tratador as t


@pytest.fixture
def repos(tmp_path):
    raiz = tmp_path / "repos"
    for nome in ("alfa", "beta"):
        (raiz / nome / ".git").mkdir(parents=True)
    return str(raiz)


SAIDA = "HEAD\tmain\nmain\torigin/main\t[ahead 2]\n"


def _tr(repos, tmp_path, **kw):
    return t.TratadorLocal(raizes=[repos], arquivo_propostas=str(tmp_path / "p.jsonl"),
                           git_fn=lambda repo: SAIDA, **kw)


def test_status_resume_o_estado(repos, tmp_path):
    tr = _tr(repos, tmp_path, estado_fn=lambda: {"cerebro_ativo": "claude_code", "gasto_dia_usd": 0.12})
    estado, resumo, custo = tr.leitura({"tipo": "status"})
    assert estado == "feito" and "claude_code" in resumo and "0,12" in resumo and custo == 0.0


def test_analisar_projeto_le_so_referencias(repos, tmp_path):
    estado, resumo, _ = _tr(repos, tmp_path).leitura({"tipo": "analisar", "alvo": "alfa"})
    assert estado == "feito" and "main" in resumo and "2" in resumo


def test_analisar_projeto_que_nao_existe(repos, tmp_path):
    estado, resumo, _ = _tr(repos, tmp_path).leitura({"tipo": "analisar", "alvo": "zeta"})
    assert estado == "feito" and "não achei" in resumo.lower()


def test_analisar_sem_alvo_lista_os_com_commit_sem_push(repos, tmp_path):
    estado, resumo, _ = _tr(repos, tmp_path).leitura({"tipo": "analisar"})
    assert estado == "feito" and "alfa" in resumo and "beta" in resumo


def test_nome_nunca_vira_caminho(repos, tmp_path):
    estado, resumo, _ = _tr(repos, tmp_path).leitura({"tipo": "analisar", "alvo": ".."})
    assert "não achei" in resumo.lower()


def test_propor_so_guarda_e_nao_executa(repos, tmp_path):
    tr = _tr(repos, tmp_path)
    msg = tr.propor({"id": "r-1", "tipo": "propor", "alvo": "alfa", "texto": "apagar tudo",
                     "nivel": "muda_estado"})
    assert "clique" in msg
    p = tr.pendentes()
    assert len(p) == 1 and p[0]["id"] == "r-1" and p[0]["estado"] == "pendente"
    assert os.path.isdir(os.path.join(repos, "alfa"))


def test_fila_de_propostas_tem_teto(repos, tmp_path):
    tr = _tr(repos, tmp_path)
    for i in range(t.MAX_PENDENTES + 5):
        msg = tr.propor({"id": "r-%d" % i, "tipo": "propor", "texto": "x"})
    assert len(tr.pendentes()) == t.MAX_PENDENTES
    assert "cheia" in msg


def test_proposta_nao_guarda_segredo(repos, tmp_path):
    tr = _tr(repos, tmp_path)
    tr.propor({"id": "r-1", "tipo": "propor", "texto": "use sk-ABCDEFGH12345678 aqui"})
    assert "sk-ABCDEFGH" not in (tmp_path / "p.jsonl").read_text(encoding="utf-8")


def test_arquivo_estragado_nao_derruba(repos, tmp_path):
    (tmp_path / "p.jsonl").write_text(
        "{lixo\n" + json.dumps({"id": "a", "estado": "pendente"}) + "\n", encoding="utf-8")
    assert [p["id"] for p in _tr(repos, tmp_path).pendentes()] == ["a"]
