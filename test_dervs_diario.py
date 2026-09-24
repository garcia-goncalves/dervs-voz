#!/usr/bin/env python3
"""Testa o cartão do diário do porteiro (`dervs_diario.py`): a contagem do dia
a partir do `porteiro.jsonl` e o laço que manda o resultado pela ponte.

Rodar: python -m pytest test_dervs_diario.py -q
"""
import datetime
import json
import threading

import dervs_diario as diario

HOJE = datetime.date(2026, 9, 23)


def _linha(quando, acordou, **extra):
    d = {"quando": quando, "acordou": acordou, "palavras": 3, "duracao_s": 1.2}
    d.update(extra)
    return json.dumps(d) + "\n"


def test_conta_ouvidas_e_acordadas_so_de_hoje(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    arq.write_text(
        _linha("2026-09-22T23:59:59", True)          # ontem: fora
        + _linha("2026-09-23T08:00:00", False)
        + _linha("2026-09-23T09:30:00", True)
        + _linha("2026-09-23T10:00:00", False),
        encoding="utf-8")
    assert diario.resumo_do_dia(str(arq), HOJE) == {"ouvidas": 3, "acordou": 1}


def test_arquivo_ausente_devolve_zeros(tmp_path):
    assert diario.resumo_do_dia(str(tmp_path / "nao_existe.jsonl"), HOJE) == {
        "ouvidas": 0, "acordou": 0}


def test_ignora_linhas_invalidas(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    arq.write_text(
        "isto nao e json\n"
        + "\n"
        + "[1, 2, 3]\n"                                       # JSON, mas nao objeto
        + json.dumps({"quando": 5, "acordou": True}) + "\n"  # quando torto
        + json.dumps({"acordou": True}) + "\n"               # sem quando
        + _linha("2026-09-23T08:00:00", True),
        encoding="utf-8")
    assert diario.resumo_do_dia(str(arq), HOJE) == {"ouvidas": 1, "acordou": 1}


def test_acordou_so_conta_o_booleano_verdadeiro(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    arq.write_text(
        json.dumps({"quando": "2026-09-23T08:00:00", "acordou": "true"}) + "\n"
        + json.dumps({"quando": "2026-09-23T08:01:00", "acordou": 1}) + "\n",
        encoding="utf-8")
    assert diario.resumo_do_dia(str(arq), HOJE) == {"ouvidas": 2, "acordou": 0}


def test_junta_a_rotacao_ponto_1(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    (tmp_path / "porteiro.jsonl.1").write_text(
        _linha("2026-09-23T07:00:00", True) + _linha("2026-09-23T07:10:00", False),
        encoding="utf-8")
    arq.write_text(_linha("2026-09-23T11:00:00", True), encoding="utf-8")
    assert diario.resumo_do_dia(str(arq), HOJE) == {"ouvidas": 3, "acordou": 2}


def test_so_a_rotacao_existe(tmp_path):
    (tmp_path / "porteiro.jsonl.1").write_text(
        _linha("2026-09-23T07:00:00", True), encoding="utf-8")
    assert diario.resumo_do_dia(str(tmp_path / "porteiro.jsonl"), HOJE) == {
        "ouvidas": 1, "acordou": 1}


def test_nunca_devolve_o_texto(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    arq.write_text(_linha("2026-09-23T08:00:00", True, texto="segredo de familia"),
                   encoding="utf-8")
    saida = diario.resumo_do_dia(str(arq), HOJE)
    assert "segredo" not in json.dumps(saida)
    assert set(saida) == {"ouvidas", "acordou"}


def test_hoje_aceita_string_iso(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    arq.write_text(_linha("2026-09-23T08:00:00", True), encoding="utf-8")
    assert diario.resumo_do_dia(str(arq), "2026-09-23") == {"ouvidas": 1, "acordou": 1}


def test_bytes_invalidos_no_arquivo_nao_derrubam(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    arq.write_bytes(b"\xff\xfe lixo\n" + _linha("2026-09-23T08:00:00", False).encode())
    assert diario.resumo_do_dia(str(arq), HOJE) == {"ouvidas": 1, "acordou": 0}


class PonteFalsa:
    def __init__(self):
        self.enviados = []

    def enviar_diario(self, ouvidas, acordou):
        self.enviados.append((ouvidas, acordou))


def test_um_passo_manda_o_resumo_pela_ponte(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    arq.write_text(_linha("2026-09-23T08:00:00", True), encoding="utf-8")
    ponte = PonteFalsa()
    diario._um_passo(ponte, str(arq), hoje=lambda: HOJE)
    assert ponte.enviados == [(1, 1)]


def test_laco_manda_e_para_com_o_evento(tmp_path):
    ponte = PonteFalsa()
    parar = threading.Event()
    primeira = threading.Event()

    class PonteAviso(PonteFalsa):
        def enviar_diario(self, ouvidas, acordou):
            super().enviar_diario(ouvidas, acordou)
            primeira.set()

    ponte = PonteAviso()
    t = diario.iniciar_loop_diario(ponte, parar, intervalo=0.01,
                                   caminho=str(tmp_path / "x.jsonl"))
    assert primeira.wait(2.0)
    parar.set()
    t.join(2.0)
    assert not t.is_alive()
    assert ponte.enviados[0] == (0, 0)
