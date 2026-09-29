#!/usr/bin/env python3
"""Testes da voz de nuvem (OpenAI): a que soa como gente, em português do Brasil.

Sem rede e sem som: a chamada HTTP e o alto-falante são trocados por dublês.
O que se protege: o pedido pede sotaque brasileiro; a chave nunca vai parar em
mensagem de erro; e, se a nuvem falhar, o DERVS NUNCA fica mudo — cai no Kokoro.

Rodar: python -m pytest test_dervs_tts_openai.py -q
"""
import json
import threading

import pytest

import dervs_config
import dervs_tts as tts


# ---- o pedido -------------------------------------------------------------

def test_pedido_pede_portugues_do_brasil_e_wav():
    p = tts.pedido_openai("Olá, tudo bem?", "ash", "gpt-4o-mini-tts", tts.INSTRUCOES_VOZ_BR)
    assert p["input"] == "Olá, tudo bem?"
    assert p["voice"] == "ash"
    assert p["model"] == "gpt-4o-mini-tts"
    assert p["response_format"] == "wav"
    assert "português do Brasil" in p["instructions"]
    assert "sotaque" in p["instructions"].lower()


def test_instrucao_nao_manda_soar_como_robo():
    assert "robótic" in tts.INSTRUCOES_VOZ_BR.lower()   # "nunca robótico"


# ---- a chamada de rede ----------------------------------------------------

class _Resposta:
    def __init__(self, dados):
        self._d = dados

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


WAV_MINIMO = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVEfmt " + b"\x10\x00\x00\x00" + b"\x01\x00\x01\x00" \
    + b"\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00" + b"data\x00\x00\x00\x00"


def test_sintetizar_grava_wav_e_manda_a_chave_no_cabecalho(monkeypatch, tmp_path):
    visto = {}

    def falso(req, timeout=None):
        visto["auth"] = req.get_header("Authorization")
        visto["corpo"] = json.loads(req.data.decode("utf-8"))
        visto["url"] = req.full_url
        return _Resposta(WAV_MINIMO)

    monkeypatch.setattr(tts.urllib.request, "urlopen", falso)
    caminho = tts.sintetizar_openai("Oi", "ash", "gpt-4o-mini-tts", "x", "sk-teste")
    try:
        assert caminho and open(caminho, "rb").read(4) == b"RIFF"
    finally:
        import os
        os.remove(caminho)
    assert visto["auth"] == "Bearer sk-teste"
    assert visto["url"] == tts.OPENAI_TTS_URL
    assert visto["corpo"]["input"] == "Oi"


def test_sintetizar_falha_devolve_none_sem_vazar_a_chave(monkeypatch, capsys):
    def falso(req, timeout=None):
        raise OSError("sem rede sk-SEGREDO123")

    monkeypatch.setattr(tts.urllib.request, "urlopen", falso)
    assert tts.sintetizar_openai("Oi", "ash", "m", "x", "sk-SEGREDO123") is None
    saida = capsys.readouterr()
    assert "SEGREDO123" not in saida.out + saida.err


def test_resposta_que_nao_e_wav_e_recusada(monkeypatch):
    monkeypatch.setattr(tts.urllib.request, "urlopen",
                        lambda req, timeout=None: _Resposta(b'{"error":"x"}'))
    assert tts.sintetizar_openai("Oi", "ash", "m", "x", "sk-t") is None


# ---- o motor dentro da Voz --------------------------------------------------

def _voz(monkeypatch, chave="sk-t"):
    monkeypatch.setattr(dervs_config, "segredo", lambda nome: chave)
    v = tts.Voz(ligada=True, motor="openai")
    return v


def test_motor_openai_e_aceito_pela_config():
    conf = dervs_config._validar({**dervs_config.PADRAO, "motor": "openai", "voz_openai": "onyx"})
    assert conf["motor"] == "openai"
    assert conf["voz_openai"] == "onyx"


def test_voz_openai_invalida_volta_ao_padrao():
    conf = dervs_config._validar({**dervs_config.PADRAO, "motor": "openai", "voz_openai": "inexistente"})
    assert conf["voz_openai"] == dervs_config.PADRAO["voz_openai"]


def test_openai_indisponivel_sem_chave(monkeypatch):
    assert not _voz(monkeypatch, chave=None)._openai_disponivel()


def test_openai_disponivel_com_chave(monkeypatch):
    assert _voz(monkeypatch)._openai_disponivel()


def test_fala_pela_nuvem_toca_cada_frase_e_nao_chama_o_kokoro(monkeypatch):
    v = _voz(monkeypatch)
    pedidas, tocadas = [], []
    monkeypatch.setattr(tts, "sintetizar_openai",
                        lambda texto, *a, **k: pedidas.append(texto) or f"/tmp/{len(pedidas)}.wav")
    monkeypatch.setattr(v, "_tocar_e_apagar", lambda wav: tocadas.append(wav))
    monkeypatch.setattr(v, "_falar_kokoro", lambda *a: pytest.fail("caiu no Kokoro à toa"))
    assert v._falar_openai("Bom dia. Como posso ajudar?", threading.Event()) is True
    assert pedidas == ["Bom dia.", "Como posso ajudar?"]
    assert len(tocadas) == 2


def test_nuvem_falhou_na_primeira_frase_devolve_false_para_cair_no_kokoro(monkeypatch):
    v = _voz(monkeypatch)
    monkeypatch.setattr(tts, "sintetizar_openai", lambda *a, **k: None)
    assert v._falar_openai("Bom dia.", threading.Event()) is False


def test_depois_de_falhar_a_nuvem_descansa_um_tempo(monkeypatch):
    v = _voz(monkeypatch)
    monkeypatch.setattr(tts, "sintetizar_openai", lambda *a, **k: None)
    v._falar_openai("Bom dia.", threading.Event())
    assert not v._openai_disponivel(), "insistiu na nuvem logo depois de ela falhar"


def test_fala_bloqueante_cai_no_kokoro_quando_a_nuvem_falha(monkeypatch):
    v = _voz(monkeypatch)
    ordem = []
    monkeypatch.setattr(v, "_falar_openai", lambda t, e: ordem.append("nuvem") or False)
    monkeypatch.setattr(v, "_kokoro_disponivel", lambda: True)
    monkeypatch.setattr(v, "_falar_kokoro", lambda t, e: ordem.append("kokoro") or True)
    v._falar_bloqueante("Oi")
    assert ordem == ["nuvem", "kokoro"]


def test_barge_in_nao_toca_frase_pronta(monkeypatch):
    v = _voz(monkeypatch)
    evento = threading.Event()
    apagadas = []
    # o dono interrompe enquanto a nuvem ainda gera a frase
    monkeypatch.setattr(tts, "sintetizar_openai",
                        lambda *a, **k: evento.set() or "/tmp/x.wav")
    monkeypatch.setattr(v, "_tocar_e_apagar", lambda wav: pytest.fail("tocou depois de calar"))
    monkeypatch.setattr(tts.os, "remove", lambda p: apagadas.append(p))
    v._falar_openai("Bom dia. Tudo bem?", evento)
    assert apagadas, "deixou wav temporário para trás"


def test_cabecalho_com_tamanho_desconhecido_e_consertado(tmp_path):
    import struct
    import wave
    pcm = struct.pack("<h", 1) * 2400                          # 0,1 s a 24 kHz
    cab = (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16)
           + b"data" + struct.pack("<I", 0xFFFFFFFF))
    arq = tmp_path / "a.wav"
    arq.write_bytes(tts.consertar_cabecalho_wav(cab + pcm))
    with wave.open(str(arq)) as w:
        assert w.getnframes() == 2400
        assert abs(w.getnframes() / w.getframerate() - 0.1) < 1e-6


def test_gasto_da_voz_usa_a_duracao_real_e_nao_a_do_cabecalho_da_nuvem(monkeypatch):
    """A nuvem manda o wav com tamanho 0xFFFFFFFF; sem consertar antes de medir,
    cada fala virava ~US$ 22 (89 mil segundos) no gasto do dia."""
    cabecalho = (b"RIFF" + b"\xff\xff\xff\xff" + b"WAVEfmt " + b"\x10\x00\x00\x00"
                 + b"\x01\x00\x01\x00" + b"\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00"
                 + b"data" + b"\xff\xff\xff\xff")
    wav_da_nuvem = cabecalho + b"\x00" * 16000          # 1 s de audio a 8 kHz/16 bits
    medidos = []
    monkeypatch.setattr(tts.dervs_gasto, "registrar_voz",
                        lambda dados, modelo="": medidos.append(tts.dervs_gasto.segundos_do_wav_bytes(dados)))
    monkeypatch.setattr(tts.urllib.request, "urlopen", lambda req, timeout=None: _Resposta(wav_da_nuvem))
    caminho = tts.sintetizar_openai("Oi", "echo", "gpt-4o-mini-tts", "x", "sk-teste")
    import os
    os.remove(caminho)
    assert medidos and abs(medidos[0] - 1.0) < 0.01
