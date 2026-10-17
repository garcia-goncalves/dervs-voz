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
    pop = types.SimpleNamespace(_acordar=lambda novo=False: chamadas.append(novo))
    dervs.PopUp._cn_tratar(pop, "turno", None)
    assert chamadas == [True], "turno de conversa não renovou o teto: dormia aos 90 s"


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
