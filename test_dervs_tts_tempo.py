"""Aceleração da voz da nuvem sem mudar o tom (02/10/2026, pedido do dono: "mais rápida").

A OpenAI não tem parâmetro de velocidade para o gpt-4o-mini-tts; o DERVS acelera
o áudio por dentro (WSOLA, só numpy), então funciona em qualquer PC e a voz não
fica fina nem "de esquilo"."""
import io
import time
import wave

import numpy as np
import pytest

import dervs_config
import dervs_tts as tts

TAXA = 24000


def _wav(sinal, taxa=TAXA, canais=1):
    pcm = (np.clip(sinal, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _ler(dados):
    with wave.open(io.BytesIO(dados), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32767, w.getframerate()


def _tom(freq, seg=2.0):
    t = np.arange(int(TAXA * seg)) / TAXA
    return 0.5 * np.sin(2 * np.pi * freq * t)


def _pico(x, taxa):
    espectro = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.argmax(espectro)) * taxa / len(x)


@pytest.mark.parametrize("fator", [1.15, 1.25, 1.5])
def test_encurta_na_proporcao_e_mantem_o_tom(fator):
    original = _wav(_tom(220))
    novo = tts.acelerar_wav(original, fator)
    x, taxa = _ler(novo)
    assert taxa == TAXA
    esperado = 2.0 / fator
    assert abs(len(x) / taxa - esperado) < 0.08                 # duração certa
    assert abs(_pico(x, taxa) - 220) < 4                        # o tom NÃO mudou
    assert np.max(np.abs(x)) <= 1.0 and np.max(np.abs(x)) > 0.2  # sem estourar nem sumir


def test_fator_um_ou_menos_devolve_o_mesmo_audio():
    original = _wav(_tom(220))
    assert tts.acelerar_wav(original, 1.0) == original
    assert tts.acelerar_wav(original, 0.8) == original


def test_entrada_estranha_nunca_derruba():
    assert tts.acelerar_wav(b"nao e wav", 1.25) == b"nao e wav"
    estereo = _wav(np.zeros(TAXA), canais=2)
    assert tts.acelerar_wav(estereo, 1.25) == estereo            # só mono 16 bits
    curtinho = _wav(_tom(220, 0.02))
    assert tts.acelerar_wav(curtinho, 1.25) == curtinho          # curto demais para esticar


def test_e_rapido_o_bastante_para_nao_atrasar_a_fala():
    original = _wav(_tom(180, 6.0))
    t0 = time.perf_counter()
    tts.acelerar_wav(original, 1.25)
    assert time.perf_counter() - t0 < 1.0


def test_sintetizar_openai_acelera_e_mede_o_gasto_do_audio_original(monkeypatch):
    original = _wav(_tom(220, 2.0))
    medidos = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return original

    monkeypatch.setattr(tts.urllib.request, "urlopen", lambda *a, **k: Resp())
    monkeypatch.setattr(tts.dervs_gasto, "registrar_voz", lambda dados, modelo: medidos.append(len(dados)))
    caminho = tts.sintetizar_openai("oi", "marin", "gpt-4o-mini-tts", "x", "sk-teste", tempo=1.25)
    assert caminho
    x, taxa = _ler(open(caminho, "rb").read())
    assert abs(len(x) / taxa - 2.0 / 1.25) < 0.08
    assert medidos == [len(original)]            # o custo é do áudio que a API gerou


def test_config_padrao_e_validacao():
    c = dervs_config.carregar()
    assert c["voz_openai"] == "cedar"
    assert 1.0 <= c["voz_openai_tempo"] <= 1.6
    ok = dervs_config._validar({**dervs_config.PADRAO, "voz_openai": "cedar", "voz_openai_tempo": 1.3})
    assert ok["voz_openai"] == "cedar" and ok["voz_openai_tempo"] == 1.3
    for ruim in (0.5, 3, "rapido", True, None):
        r = dervs_config._validar({**dervs_config.PADRAO, "voz_openai_tempo": ruim})
        assert r["voz_openai_tempo"] == dervs_config.PADRAO["voz_openai_tempo"]


def test_o_estilo_pede_firme_natural_agil_em_portugues_do_brasil():
    t = tts.INSTRUCOES_VOZ_BR.lower()
    for palavra in ("português do brasil", "sotaque", "firme", "ágil", "natural", "nunca"):
        assert palavra in t
