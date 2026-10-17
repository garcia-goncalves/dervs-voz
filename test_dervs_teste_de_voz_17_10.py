#!/usr/bin/env python3
"""O teste por voz do dono em 17/10/2026, 15:13–15:16: cada defeito vira um teste.

O que ele relatou: aviso vermelho "Não chegou som nenhum" enquanto falava; só respondia
quando ouvia "DERVS", às vezes nem assim; dizia que não pode programar; repetia e inventava.
O que os diários e o código mostraram:
  1. O microfone dele é baixo: 43% dos quadros de 30 ms numa sala quieta têm pico <= 30 (medido),
     e o limite de "mudo" era 30. Oito segundos de sala quieta viravam "microfone desconectado".
  2. O vermelho só saía quando o porteiro decidia uma frase; com a conversa natural no
     microfone o porteiro não roda, então o aviso ficava preso com ele falando.
  3. A conversa natural dormia calada: o teto de 90 s contava da chamada e não se renovava
     com a conversa, e a queda não deixava linha no diário.
  4. Quando o motor caía, o motivo ia para o nada: nenhuma linha em execucao.log.
  5. A instrução não dizia que programar/projeto/servidor é pedido de 'fazer', então o
     modelo respondia que não sabe programar.
  6. O Whisper do motor econômico devolve frase de legenda ("Obrigado por assistir") em
     ruído, e o DERVS respondia a isso: a "alucinação".

Rodar: python -m pytest test_dervs_teste_de_voz_17_10.py -q
"""
import array
import logging
import types

import pytest

import dervs_conversa as dc
import dervs_conversa_natural as cn
from dervs_listen import (FRAME_AMOSTRAS, FRAME_MS, PICO_SILENCIO, VigiaDeSilencio,
                          esta_mudo)


def _quadro(pico):
    return array.array("h", [pico if i % 2 else -pico for i in range(FRAME_AMOSTRAS)]).tobytes()


# ---- 1. sala quieta com microfone baixo não é microfone mudo ------------------------------

def test_chiado_baixo_de_microfone_ligado_nao_e_mudo():
    # pico 12: o chiado medido no microfone do dono em sala quieta (17/10)
    assert esta_mudo(_quadro(12)) is False


def test_cabo_fora_continua_sendo_mudo():
    # pico 1: o que o cabo fora da entrada rosa entregava (02/09)
    assert esta_mudo(_quadro(1)) is True
    assert esta_mudo(_quadro(0)) is True
    assert PICO_SILENCIO < 12


# ---- 2. o aviso vermelho sai quando o som volta, mesmo sem o porteiro ----------------------

def test_vigia_diz_que_esta_avisando_e_quando_o_som_volta():
    vigia = VigiaDeSilencio(segundos=FRAME_MS * 3 / 1000)
    assert vigia.avisando is False
    avisou = [vigia.ver(_quadro(0)) for _ in range(3)]
    assert avisou == [False, False, True]
    assert vigia.avisando is True
    assert vigia.ver(_quadro(500)) is False
    assert vigia.avisando is False, "o som voltou e o vigia continuou dizendo que está mudo"


# ---- 3. a conversa natural não dorme no meio da conversa, e não dorme calada ---------------

def test_turno_da_conversa_natural_renova_o_teto():
    pytest.importorskip("PyQt6")
    import dervs
    chamadas = []
    pop = types.SimpleNamespace(
        _acordar=lambda novo=False, renovar_teto=False: chamadas.append((novo, renovar_teto)))
    dervs.PopUp._cn_tratar(pop, "turno", None)
    assert chamadas == [(False, True)], "turno de conversa não renovou o teto: dormia aos 90 s"


def test_conversa_natural_que_dorme_deixa_linha_no_diario(capsys):
    pytest.importorskip("PyQt6")
    import dervs
    desligou = []
    cn_atual = types.SimpleNamespace(tique=lambda: None, ocupado=lambda: False)
    pop = types.SimpleNamespace(
        _cn=cn_atual, escuta=object(), _esta_desperto=lambda: False,
        _cn_desligar=lambda: desligou.append(True), _desperto_ate=0.0)
    dervs.PopUp._cn_vigiar(pop)
    assert desligou == [True]
    assert "conversa natural dormiu" in capsys.readouterr().err


# ---- 4. o motivo da queda do motor vai para o diário --------------------------------------

def test_queda_do_motor_registra_o_motivo(caplog):
    emitidos = []
    motor = types.SimpleNamespace(_encerrado=False, nome="gemini_live",
                                  _emitir=emitidos.append, encerrar=lambda: None)
    with caplog.at_level(logging.WARNING, logger="dervs.conversa"):
        dc._MotorWS._falhar(motor, ConnectionResetError("conexão fechada pelo servidor"))
    assert emitidos and isinstance(emitidos[0], dc.Erro)
    assert "gemini_live" in caplog.text and "ConnectionResetError" in caplog.text


# ---- 5. programar é pedido de ação, não "não sei fazer" -----------------------------------

@pytest.mark.parametrize("instrucao", [cn.SISTEMA, dc.PROMPT_CASCATA])
def test_instrucao_manda_programar_para_a_ferramenta(instrucao):
    t = instrucao.lower()
    assert "código" in t and "nunca diga que não" in t


def test_ferramenta_fazer_cobre_programar_e_servidor():
    desc = next(f for f in cn.FERRAMENTAS if f["name"] == "fazer")["description"].lower()
    for palavra in ("código", "projeto", "servidor", "terminal"):
        assert palavra in desc


# ---- 6. frase de legenda inventada pelo Whisper não vira pedido ---------------------------

@pytest.mark.parametrize("texto", [
    "Obrigado por assistir!", "Legendas pela comunidade Amara.org", "Inscreva-se no canal.",
    "  obrigado.  ", "...", "Tchau, tchau.", "Legenda Adriana Zanotto",
])
def test_alucinacao_do_whisper_e_descartada(texto):
    assert dc.eh_alucinacao_stt(texto) is True


@pytest.mark.parametrize("texto", [
    "Obrigado, DERVS, pode abrir o Chrome.", "Abre a calculadora.", "Que horas são?",
    "Assiste comigo o vídeo do canal",
])
def test_fala_de_verdade_passa(texto):
    assert dc.eh_alucinacao_stt(texto) is False


def test_cascata_nao_responde_a_alucinacao():
    eventos = []
    m = dc.MotorCascata(eventos.append, conf={})
    m._transcrever = lambda pcm: "Legendas pela comunidade Amara.org"
    m._responder = lambda *a, **k: pytest.fail("respondeu a uma legenda inventada")
    m._turno_interno(b"\1\0" * 16000, m._geracao)
    assert [type(e).__name__ for e in eventos] == ["FimResposta"]


# ==== 2º teste por voz, 17/10 15:36 ===========================================================
# Pediu "cria um arquivo de teste no projeto dervs-voz": a conversa dormiu 20 s depois da fala
# dele, logo que terminou de responder (a janela contava da fala, não do fim da resposta), e o
# pedido foi ao planejador rápido em vez do Claude Code (o roteador não conhecia "no projeto").

def test_conversa_ocupada_empurra_a_janela_e_nao_dorme():
    pytest.importorskip("PyQt6")
    import dervs
    acordou, desligou = [], []
    cn_atual = types.SimpleNamespace(tique=lambda: None, ocupado=lambda: True)
    pop = types.SimpleNamespace(
        _cn=cn_atual, escuta=object(), _esta_desperto=lambda: bool(acordou),
        _cn_desligar=lambda: desligou.append(True), _acordar=lambda novo=False: acordou.append(novo))
    dervs.PopUp._cn_vigiar(pop)
    assert acordou and not desligou, "falando/trabalhando, a janela tem de contar do fim"


def test_motor_preso_em_ocupado_nao_segura_o_microfone_depois_do_teto():
    pytest.importorskip("PyQt6")
    import dervs
    desligou = []
    cn_atual = types.SimpleNamespace(tique=lambda: None, ocupado=lambda: True)
    pop = types.SimpleNamespace(   # teto estourado: _acordar não renova, segue dormindo
        _cn=cn_atual, escuta=object(), _esta_desperto=lambda: False,
        _cn_desligar=lambda: desligou.append(True), _acordar=lambda novo=False: None)
    dervs.PopUp._cn_vigiar(pop)
    assert desligou, "motor travado em ocupado deixou o microfone aberto para sempre"


def _pop_teto(agora, conversa_desde, desperto_desde):
    pytest.importorskip("PyQt6")
    import dervs
    pop = types.SimpleNamespace(
        _auto=types.SimpleNamespace(tocar=lambda: None), _desperto=True,
        _desperto_desde=desperto_desde, _desperto_ate=0.0, _conversa_desde=conversa_desde,
        TETO_DESPERTO=90.0, TETO_CONVERSA=600.0, JANELA_DESPERTO=20)
    return dervs, pop


def test_turno_renova_o_teto_dentro_da_conversa(monkeypatch):
    dervs, pop = _pop_teto(1000.0, conversa_desde=900.0, desperto_desde=905.0)
    monkeypatch.setattr(dervs.time, "time", lambda: 1000.0)
    dervs.PopUp._acordar(pop, renovar_teto=True)
    assert pop._desperto_desde == 1000.0 and pop._desperto_ate == 1020.0


def test_teto_da_conversa_ninguem_renova(monkeypatch):
    # 11 min depois do nome, com fala a cada 20 s: o teto de 90 s não renova mais e ele dorme
    dervs, pop = _pop_teto(1000.0, conversa_desde=340.0, desperto_desde=905.0)
    monkeypatch.setattr(dervs.time, "time", lambda: 1000.0)
    dervs.PopUp._acordar(pop, renovar_teto=True)
    assert pop._desperto_desde == 905.0 and pop._desperto_ate == 0.0,         "a sala ia para a nuvem sem limite: o teto da conversa foi renovado"


def test_nome_dito_de_novo_abre_conversa_nova(monkeypatch):
    dervs, pop = _pop_teto(1000.0, conversa_desde=340.0, desperto_desde=905.0)
    monkeypatch.setattr(dervs.time, "time", lambda: 1000.0)
    dervs.PopUp._acordar(pop, novo=True)
    assert pop._conversa_desde == 1000.0


@pytest.mark.parametrize("tipo, dado", [("feito", None), ("aviso", "pronto"),
                                        ("pedido", "x"), ("plano", {})])
def test_resposta_ou_acao_do_dervs_renova_a_janela(tipo, dado):
    pytest.importorskip("PyQt6")
    import dervs
    acordou = []
    pop = types.SimpleNamespace(
        _acordar=lambda novo=False: acordou.append(novo), _diz=lambda *a, **k: None,
        _toast=lambda *a: None, _cn=None, _cerebro_respondeu=lambda f: None,
        voz=types.SimpleNamespace(ligada=False))
    dervs.PopUp._cn_tratar(pop, tipo, dado)
    assert acordou, "%s não renovou a janela: dormia antes de ele responder" % tipo


@pytest.mark.parametrize("texto", [
    "cria um arquivo de teste no projeto dervs-voz",
    "Cria um arquivo de teste no projeto Dervs Voss.",
    "faz algo de programação pra mim",
    "escreve um teste no repositório do grimoire",
])
def test_roteador_manda_programacao_ao_claude_code(texto):
    import dervs_roteador
    assert dervs_roteador.rotear(texto)["executor"] == "claude_code"


@pytest.mark.parametrize("texto", [
    "abre a calculadora", "que horas são", "cria uma pasta na área de trabalho",
    "faz um café pra mim", "cria uma pasta no projeto", "faz um resumo do projeto",
])
def test_roteador_nao_manda_comando_simples_ao_claude_code(texto):
    import dervs_roteador
    assert dervs_roteador.rotear(texto)["executor"] == "planejador"


def test_legenda_de_verdade_passa():
    assert dc.eh_alucinacao_stt("legenda esse vídeo pra mim") is False


def test_queda_do_motor_nao_grava_chave(caplog):
    motor = types.SimpleNamespace(_encerrado=False, nome="gemini_live",
                                  _emitir=lambda ev: None, encerrar=lambda: None)
    with caplog.at_level(logging.WARNING, logger="dervs.conversa"):
        dc._MotorWS._falhar(motor, RuntimeError(
            "403 header x-goog-api-key: AIzaSEGREDO123 Authorization: Bearer sk-SEGREDO456"))
    assert "SEGREDO" not in caplog.text


# ---- 4o teste (17/10 17:58): sem o texto da conversa no diário, depurar era às cegas ----

def _cn_texto(registrar):
    return cn.ConversaNatural({"porteiro_registrar_texto": registrar}, types.SimpleNamespace(),
                              None, None, None, lambda *a: None, lambda t: None,
                              em_fundo=lambda f: None)


def test_com_registro_ligado_o_diario_guarda_o_que_ouviu_disse_e_pediu(caplog):
    x = _cn_texto(True)
    with caplog.at_level(logging.INFO, logger="dervs.conversa_natural"):
        for ev in (dc.TextoEntrada("cria um arquivo "), dc.TextoEntrada("de teste"),
                   dc.TextoSaida("Quer que eu "), dc.TextoSaida("faça isto?"),
                   dc.ChamadaFerramenta("1", "fazer", {"pedido": "criar arquivo"}),
                   dc.FimResposta()):
            x._tratar_evento(ev)
    assert "ouvi: cria um arquivo de teste" in caplog.text
    assert "disse: Quer que eu faça isto?" in caplog.text
    assert "ferramenta fazer" in caplog.text and "criar arquivo" in caplog.text


def test_com_registro_desligado_nada_do_que_foi_dito_vai_ao_diario(caplog):
    x = _cn_texto(False)
    with caplog.at_level(logging.INFO, logger="dervs.conversa_natural"):
        for ev in (dc.TextoEntrada("segredo falado"), dc.TextoSaida("resposta"),
                   dc.ChamadaFerramenta("1", "fazer", {"pedido": "segredo falado"}),
                   dc.FimResposta()):
            x._tratar_evento(ev)
    assert "segredo falado" not in caplog.text and "resposta" not in caplog.text


# ---- 5o teste (17/10 18:20): a voz leu em voz alta "Diga em tom natural e ágil" ----

def test_voz_do_gemini_manda_so_a_frase_sem_instrucao_que_ela_le_em_voz_alta(monkeypatch):
    import json as _json
    import dervs_tts as tts
    corpos = []

    def urlopen(req, timeout):
        corpos.append(_json.loads(req.data))
        raise TimeoutError()
    monkeypatch.setattr(tts.urllib.request, "urlopen", urlopen)
    tts.sintetizar_gemini("Tô ligado.", "Charon", "k")
    assert corpos and all(c["contents"][0]["parts"][0]["text"] == "Tô ligado." for c in corpos)


def test_cascata_nao_tem_instrucao_de_tom_na_frase():
    assert not getattr(dc, "INSTRUCAO_TTS_GEMINI", "")
