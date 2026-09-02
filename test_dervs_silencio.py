#!/usr/bin/env python3
"""Testes do "não entrou som nenhum" — o defeito de 02/09/2026.

Por que existe: o dono apertou Gravar, falou 4,71 s, e o DERVS devolveu texto
vazio sem uma palavra de explicação. O microfone dele não estava conectado (as
duas entradas rosa do gabinete apareciam como DESCONECTADO no Windows) e o
arquivo gravado era silêncio digital puro — pico 1 numa escala de 32.767.

Silêncio não é falha de transcrição: é falha de ENTRADA, e o DERVS tem de
dizer isso em vez de mandar silêncio para a nuvem (que ainda por cima é pago) e
mostrar um campo vazio.

Rodar: python -m pytest test_dervs_silencio.py -q
"""
import array
import math
import wave

import pytest

from dervs_listen import (PICO_SILENCIO, esta_mudo, motivo_do_silencio, pico,
                          salvar_wav, TAXA)


def _pcm(amostras) -> bytes:
    return array.array("h", amostras).tobytes()


def _fala(segundos=1.0, amplitude=8000) -> bytes:
    """Um tom — serve de 'som de verdade' sem precisar de microfone."""
    n = int(TAXA * segundos)
    return _pcm(int(amplitude * math.sin(2 * math.pi * 440 * i / TAXA))
                for i in range(n))


# ---- pico: a medida crua ------------------------------------------------

def test_pico_de_silencio_absoluto_e_zero():
    assert pico(_pcm([0] * 1000)) == 0


def test_pico_ignora_o_sinal_da_amostra():
    assert pico(_pcm([0, -5000, 300])) == 5000


def test_pico_de_pcm_vazio_e_zero():
    assert pico(b"") == 0


def test_pico_aguenta_byte_solto_no_fim():
    """Meia amostra no fim não pode derrubar a medição."""
    assert pico(_pcm([0, -4000]) + b"\x01") == 4000


# ---- esta_mudo: a decisão ----------------------------------------------

def test_silencio_digital_puro_e_mudo():
    assert esta_mudo(_pcm([0] * TAXA)) is True


def test_o_caso_real_do_dono_e_mudo():
    """Pico 1 em 4,71 s — exatamente o dervs_rec.wav de 02/09/2026 19:59."""
    amostras = [0] * int(TAXA * 4.71)
    amostras[100] = 1
    assert esta_mudo(_pcm(amostras)) is True


def test_fala_de_verdade_nao_e_mudo():
    assert esta_mudo(_fala()) is False


def test_chiado_bem_baixo_ainda_conta_como_som():
    """Microfone ligado num quarto silencioso tem ruído de fundo: não é mudo."""
    assert esta_mudo(_fala(0.5, amplitude=PICO_SILENCIO * 4)) is False


def test_gravacao_vazia_e_muda():
    assert esta_mudo(b"") is True


# ---- o caminho do arquivo, ponta a ponta -------------------------------

def test_wav_de_silencio_gravado_e_lido_como_mudo(tmp_path):
    destino = str(tmp_path / "mudo.wav")
    salvar_wav(_pcm([0] * TAXA), destino)
    with wave.open(destino) as w:
        assert esta_mudo(w.readframes(w.getnframes())) is True


def test_wav_com_fala_nao_e_mudo(tmp_path):
    destino = str(tmp_path / "fala.wav")
    salvar_wav(_fala(), destino)
    with wave.open(destino) as w:
        assert esta_mudo(w.readframes(w.getnframes())) is False


# ---- o recado ao dono ---------------------------------------------------

def test_motivo_diz_que_nao_ha_microfone_quando_nao_ha(monkeypatch):
    monkeypatch.setattr("dervs_listen._entradas_do_sistema", lambda: [])
    recado = motivo_do_silencio()
    assert "nenhum microfone" in recado.lower()


def test_motivo_aponta_mudo_ou_desconectado_quando_ha_entrada(monkeypatch):
    monkeypatch.setattr("dervs_listen._entradas_do_sistema",
                        lambda: ["Microfone (Realtek(R) Audio)"])
    recado = motivo_do_silencio().lower()
    assert "mudo" in recado or "desconectado" in recado


def test_motivo_nunca_estoura_mesmo_sem_a_biblioteca(monkeypatch):
    def explode():
        raise RuntimeError("sounddevice não instalado")
    monkeypatch.setattr("dervs_listen._entradas_do_sistema", explode)
    assert isinstance(motivo_do_silencio(), str)
    assert motivo_do_silencio() != ""


def test_motivo_e_uma_frase_curta_para_caber_na_tela(monkeypatch):
    monkeypatch.setattr("dervs_listen._entradas_do_sistema",
                        lambda: ["Microfone (Realtek(R) Audio)"])
    assert len(motivo_do_silencio()) <= 120


@pytest.mark.parametrize("entradas", [[], ["Microfone"], ["A", "B"]])
def test_motivo_sempre_em_portugues_sem_jargao(monkeypatch, entradas):
    monkeypatch.setattr("dervs_listen._entradas_do_sistema", lambda: entradas)
    recado = motivo_do_silencio().lower()
    for jargao in ("stream", "device", "portaudio", "input", "error"):
        assert jargao not in recado
