"""Roteador: o dono fala e o DERVS decide quem atende, sem ele escolher cérebro.

Conservador de propósito: um falso positivo manda o pedido ao Claude Code (mais
lento, gasta a assinatura); então só pedido CLARO de desenvolvimento ou de
análise vai para lá. O resto continua no planejador rápido de sempre."""
import json

import pytest

import dervs_roteador as r


@pytest.mark.parametrize("fala", [
    "cria um site para a minha clínica",
    "Dervs, conserta o bug do login",
    "desenvolve um aplicativo de agenda",
    "implementa a tela de cadastro",
    "refatora essa função",
    "escreve um script para renomear as fotos",
    "corrige o teste que está falhando",
    "faz uma API de pacientes",
    "Olá dervs, cria um site",
    "faça um site para mim",
    "corrija o bug do login",
    "desenvolva um sistema de agenda",
    "quero que você crie um aplicativo",
    "pode criar um site pra mim",
    "preciso que você conserte o bug",
])
def test_pedido_de_desenvolvimento_vai_para_o_claude_code(fala):
    d = r.rotear(fala)
    assert d["executor"] == "claude_code"
    assert d["intencao"] == "desenvolver"
    assert d["pedido"]
    assert d["motivo"]


@pytest.mark.parametrize("fala", [
    "pede pro Claude olhar a minha agenda",
    "analisa o meu disco",
    "verifica meu pc",
])
def test_pedido_explicito_de_trabalho_continua_indo_ao_claude_code(fala):
    d = r.rotear(fala)
    assert d["executor"] == "claude_code"
    assert d["intencao"] == "trabalho"


@pytest.mark.parametrize("fala", [
    "que horas são",
    "abre o chrome",
    "cria um lembrete para amanhã às nove",
    "faz um café",
    "conserta a impressora",
    "",
    "   ",
    "o site está lento hoje",
    "Dervs, faz um teste do microfone",
    "cria um lembrete na tela",
    "faz um programa de televisão",
    "quero um café",
])
def test_o_resto_fica_no_planejador_rapido(fala):
    d = r.rotear(fala)
    assert d["executor"] == "planejador"
    assert d["pedido"] is None


def test_o_pedido_enviado_e_o_texto_original_sem_o_vocativo():
    assert r.rotear("Dervs, cria um site simples")["pedido"].lower().endswith("cria um site simples")


def test_registra_o_motivo_e_lista_os_recentes(tmp_path, monkeypatch):
    log = tmp_path / "roteamento.jsonl"
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(log))
    r.registrar(r.rotear("cria um site"), "cria um site")
    r.registrar(r.rotear("que horas são"), "que horas são")
    linhas = log.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2 and json.loads(linhas[0])["executor"] == "claude_code"
    rec = r.recentes(5)
    assert [x["executor"] for x in rec] == ["planejador", "claude_code"]   # mais novo primeiro


def test_log_nao_guarda_o_texto_inteiro_nem_derruba(tmp_path, monkeypatch):
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(tmp_path / "x" / "y.jsonl"))
    r.registrar(r.rotear("cria um site " + "a" * 5000), "cria um site " + "a" * 5000)
    assert len(r.recentes(1)[0]["fala"]) <= 80
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(tmp_path))      # é uma pasta: não pode levantar
    r.registrar(r.rotear("cria um site"), "cria um site")
