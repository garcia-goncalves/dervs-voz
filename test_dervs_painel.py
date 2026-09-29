#!/usr/bin/env python3
"""Painel grande (JARVIS): mensagens novas da ponte e os dados que as alimentam.

Rodar: python -m pytest test_dervs_painel.py -q
"""
import datetime
import json
import threading

import pytest

import dervs_diario as diario
import dervs_lembretes as lembretes
import dervs_painel as painel
import dervs_sistema as sistema
from test_dervs_ponte_electron import _nova_ponte, _linhas_escritas


def _ultima(processo):
    return json.loads(_linhas_escritas(processo)[-1])


# ---- ponte: verbos novos ----------------------------------------------------

def test_sistema_com_rede_leva_os_dois_campos():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_sistema(cpu=1.0, ram=2.0, disco_livre_gb=3.0, disco_total_gb=4.0,
                     rede_baixa_kbs=12.5, rede_sobe_kbs=3.0)
    d = _ultima(processo)
    assert d["rede_baixa_kbs"] == 12.5 and d["rede_sobe_kbs"] == 3.0


def test_sistema_sem_rede_nao_leva_campo_de_rede():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_sistema(cpu=1.0, ram=2.0, disco_livre_gb=3.0, disco_total_gb=4.0)
    assert "rede_baixa_kbs" not in _ultima(processo)


def test_enviar_gasto_manda_valores_arredondados():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_gasto({"total": 0.123456789, "tts": 0.1, "stt": 0.02, "cerebro": 0.003456789})
    assert _ultima(processo) == {"verbo": "gasto", "total": 0.123457, "tts": 0.1,
                                 "stt": 0.02, "cerebro": 0.003457}


def test_gasto_repetido_nao_e_reenviado_e_antes_de_pronto_nao_manda():
    p, processo = _nova_ponte()
    g = {"total": 1.0, "tts": 1.0, "stt": 0.0, "cerebro": 0.0}
    p.enviar_gasto(g)
    assert _linhas_escritas(processo) == []
    p._despachar_guardado()
    p.enviar_gasto(g)
    p.enviar_gasto(g)
    assert len(_linhas_escritas(processo)) == 1


def test_enviar_agenda_manda_lista():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    itens = [{"quando": "2026-09-28T15:30:00", "quando_txt": "às 15h30", "texto": "ligar"}]
    p.enviar_agenda(itens)
    assert _ultima(processo) == {"verbo": "agenda", "itens": itens}


def test_agenda_vazia_tambem_e_enviada():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_agenda([])
    assert _ultima(processo) == {"verbo": "agenda", "itens": []}


def test_texto_da_agenda_e_cortado():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_agenda([{"quando": "x", "quando_txt": "y", "texto": "a" * 9000}])
    assert len(_ultima(processo)["itens"][0]["texto"]) <= 200


def test_enviar_diario_entradas():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    e = [{"hora": "09:30", "acordou": True, "palavras": 3, "duracao_s": 1.2}]
    p.enviar_diario_entradas(e)
    assert _ultima(processo) == {"verbo": "diario_entradas", "entradas": e}


def test_enviar_voz_so_aceita_nuvem_ou_local():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_voz("nuvem")
    assert _ultima(processo) == {"verbo": "voz", "motor": "nuvem"}
    p.enviar_voz("qualquer coisa")
    assert _ultima(processo) == {"verbo": "voz", "motor": "local"}


def test_enviar_acao_corta_texto():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_acao("resultado", "x" * 9000)
    d = _ultima(processo)
    assert d["verbo"] == "acao" and d["papel"] == "resultado" and len(d["texto"]) <= 4000


# ---- dados: agenda, diário, rede -------------------------------------------

def test_montar_agenda_le_lembretes_reais(tmp_path):
    caminho = tmp_path / "lembretes.json"
    agora = datetime.datetime(2026, 9, 28, 10, 0, 0)
    ag = lembretes.Agenda(str(caminho), relogio=lambda: agora)
    ag.adicionar(datetime.datetime(2026, 9, 28, 15, 30), "ligar para o contador")
    ag.adicionar(datetime.datetime(2026, 9, 29, 9, 0), "reunião")
    itens = painel.montar_agenda(ag)
    assert [i["texto"] for i in itens] == ["ligar para o contador", "reunião"]
    assert itens[0]["quando_txt"] == "às 15h30"
    assert itens[1]["quando_txt"] == "amanhã às 9h"


def test_montar_agenda_vazia(tmp_path):
    ag = lembretes.Agenda(str(tmp_path / "nada.json"))
    assert painel.montar_agenda(ag) == []


def test_entradas_recentes_do_diario_so_metadados_e_de_hoje(tmp_path):
    arq = tmp_path / "porteiro.jsonl"
    linhas = [
        {"quando": "2026-09-27T23:00:00", "acordou": True, "palavras": 1, "duracao_s": 1.0},
        {"quando": "2026-09-28T08:00:00", "acordou": False, "palavras": 5, "duracao_s": 2.5,
         "texto": "SEGREDO DA FAMILIA"},
        {"quando": "2026-09-28T09:30:00", "acordou": True, "palavras": 2, "duracao_s": 1.1},
    ]
    arq.write_text("\n".join(json.dumps(x) for x in linhas) + "\nlixo\n", encoding="utf-8")
    r = diario.entradas_recentes(str(arq), datetime.date(2026, 9, 28), limite=10)
    assert [e["hora"] for e in r] == ["09:30", "08:00"]       # mais recente primeiro
    assert r[0]["acordou"] is True and r[1]["palavras"] == 5
    assert "SEGREDO" not in json.dumps(r) and all("texto" not in e for e in r)


def test_entradas_recentes_arquivo_ausente(tmp_path):
    assert diario.entradas_recentes(str(tmp_path / "x.jsonl"), datetime.date(2026, 9, 28)) == []


def test_kbs_de_rede_a_partir_de_dois_contadores():
    est = sistema.EstadoRede()
    assert est.kbs(1_000_000, 500_000, 10.0) == (None, None)      # 1a leitura: sem base
    baixa, sobe = est.kbs(1_000_000 + 20_480, 500_000 + 10_240, 12.0)
    assert baixa == pytest.approx(10.0) and sobe == pytest.approx(5.0)


def test_kbs_nunca_negativo_se_contador_reinicia():
    est = sistema.EstadoRede()
    est.kbs(5_000_000, 5_000_000, 0.0)
    assert est.kbs(100, 100, 2.0) == (0.0, 0.0)


def test_motor_de_voz_nuvem_ou_local():
    class V:
        motor = "openai"

        def _openai_disponivel(self):
            return True
    assert painel.motor_de_voz(V()) == "nuvem"
    V.motor = "kokoro"
    assert painel.motor_de_voz(V()) == "local"
    v = V()
    v.motor = "openai"
    v._openai_disponivel = lambda: False      # descansando/sem chave: cai no local
    assert painel.motor_de_voz(v) == "local"
    assert painel.motor_de_voz(None) == "local"


def test_um_passo_do_painel_manda_tudo(tmp_path, monkeypatch):
    monkeypatch.setenv("DERVS_GASTO_ARQUIVO", str(tmp_path / "g.jsonl"))
    import dervs_gasto
    dervs_gasto.registrar("tts", 0.05)
    p, processo = _nova_ponte()
    p._despachar_guardado()
    ag = lembretes.Agenda(str(tmp_path / "l.json"))
    painel.um_passo(p, agenda=ag, voz=None, caminho_diario=str(tmp_path / "d.jsonl"))
    verbos = [json.loads(l)["verbo"] for l in _linhas_escritas(processo)]
    assert set(verbos) == {"gasto", "agenda", "diario_entradas", "voz"}
    gasto = [json.loads(l) for l in _linhas_escritas(processo)
             if json.loads(l)["verbo"] == "gasto"][0]
    assert gasto["total"] == pytest.approx(0.05)


def test_laco_para_quando_o_evento_e_marcado(tmp_path):
    p, _ = _nova_ponte()
    parar = threading.Event()
    parar.set()
    t = painel.iniciar_loop_painel(p, parar, agenda=lembretes.Agenda(str(tmp_path / "l.json")),
                                   voz=None, caminho_diario=str(tmp_path / "d.jsonl"))
    t.join(2)
    assert not t.is_alive()


def test_agenda_nao_pisca_vazia_quando_a_troca_do_arquivo_atrapalha_uma_leitura():
    import datetime
    import dervs_painel

    agora = datetime.datetime(2026, 9, 28, 10, 0, 0)

    class AgendaTrocandoArquivo:
        def __init__(self):
            self.chamadas = 0

        def agora(self):
            return agora

        def listar(self):
            self.chamadas += 1
            if self.chamadas == 2:            # a leitura que cai na troca do arquivo
                return []
            return [{"quando": agora + datetime.timedelta(minutes=5), "texto": "beber água"}]

    ag = AgendaTrocandoArquivo()
    assert len(dervs_painel.montar_agenda(ag)) == 1
    assert len(dervs_painel.montar_agenda(ag)) == 1, "a agenda piscou vazia"
