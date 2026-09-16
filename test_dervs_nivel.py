#!/usr/bin/env python3
"""Testes do nível de áudio que a onda desenha (sem Qt, sem microfone).

Rodar: python -m pytest test_dervs_nivel.py -q
"""
import array
import struct
import wave

from dervs_nivel import TETO_NIVEL, envelope_do_wav, nivel_do_frame


def _frame_com_amplitude(amplitude: int, n_amostras: int = 480) -> bytes:
    a = array.array("h", [amplitude] * n_amostras)
    return a.tobytes()


def _escreve_wav(caminho, amostras, taxa=16000, sampwidth=2):
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(sampwidth)
        w.setframerate(taxa)
        w.writeframes(struct.pack(f"<{len(amostras)}h", *amostras))


def test_silencio_absoluto_da_zero():
    frame = _frame_com_amplitude(0)
    assert nivel_do_frame(frame) == 0.0


def test_audio_alto_da_perto_de_um_e_nunca_acima():
    frame = _frame_com_amplitude(32767)
    nivel = nivel_do_frame(frame)
    assert nivel <= 1.0
    assert nivel > 0.9


def test_quadro_vazio_nao_explode():
    assert nivel_do_frame(b"") == 0.0


def test_quadro_de_tamanho_impar_nao_explode():
    assert nivel_do_frame(b"\x01") == 0.0


def test_monotonicidade_audio_mais_alto_nunca_da_nivel_menor():
    baixo = nivel_do_frame(_frame_com_amplitude(100))
    medio = nivel_do_frame(_frame_com_amplitude(3000))
    alto = nivel_do_frame(_frame_com_amplitude(30000))
    assert baixo <= medio <= alto


def test_teto_e_o_parafuso_de_ajuste():
    # rms de uma onda constante de amplitude A é A. No teto, o nível bate em 1.0.
    frame = _frame_com_amplitude(int(TETO_NIVEL))
    assert nivel_do_frame(frame) == 1.0


def test_envelope_de_wav_alto_tem_media_maior_que_silencio(tmp_path):
    caminho_silencio = tmp_path / "silencio.wav"
    caminho_alto = tmp_path / "alto.wav"
    _escreve_wav(caminho_silencio, [0] * 16000)
    _escreve_wav(caminho_alto, [30000, -30000] * 8000)

    niveis_silencio = envelope_do_wav(str(caminho_silencio))
    niveis_alto = envelope_do_wav(str(caminho_alto))

    assert niveis_silencio
    assert niveis_alto
    assert sum(niveis_silencio) / len(niveis_silencio) == 0.0
    assert sum(niveis_alto) / len(niveis_alto) > sum(niveis_silencio) / len(niveis_silencio)


def test_wav_inexistente_devolve_lista_vazia():
    assert envelope_do_wav("nao-existe-de-verdade.wav") == []


def test_wav_que_nao_e_pcm_16_bits_devolve_lista_vazia(tmp_path):
    caminho = tmp_path / "8bits.wav"
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(16000)
        w.writeframes(bytes([128] * 16000))

    assert envelope_do_wav(str(caminho)) == []
