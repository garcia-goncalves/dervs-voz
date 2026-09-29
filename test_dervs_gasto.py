"""Testes do registrador do gasto do dia (dervs_gasto) e dos pontos que o chamam."""
import datetime
import io
import json
import os
import wave

import pytest

import dervs_gasto as g


@pytest.fixture
def arq(tmp_path, monkeypatch):
    p = tmp_path / "gasto.jsonl"
    monkeypatch.setenv("DERVS_GASTO_ARQUIVO", str(p))
    return p


def _wav(segundos, taxa=8000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(b"\x00\x00" * int(taxa * segundos))
    return buf.getvalue()


def test_precos_por_minuto():
    assert g.usd_voz(60) == pytest.approx(0.015)
    assert g.usd_transcricao(120) == pytest.approx(0.012)
    assert g.usd_voz(-5) == 0


def test_cerebro_por_tokens_e_modelo_desconhecido():
    assert g.usd_cerebro("gpt-4.1-nano", 1_000_000, 1_000_000) == pytest.approx(0.50)
    assert g.usd_cerebro("modelo-x", 1_000_000, 0) == pytest.approx(0.40)


def test_registrar_e_somar_so_o_dia_de_hoje(arq):
    ontem = datetime.datetime(2026, 9, 27, 10, 0)
    hoje = datetime.datetime(2026, 9, 28, 10, 0)
    assert g.registrar("tts", 0.01, caminho=str(arq), agora=ontem)
    assert g.registrar("tts", 0.02, caminho=str(arq), agora=hoje)
    assert g.registrar("stt", 0.03, caminho=str(arq), agora=hoje)
    r = g.total_do_dia(str(arq), hoje=datetime.date(2026, 9, 28))
    assert r["total"] == pytest.approx(0.05)
    assert r["tts"] == pytest.approx(0.02)
    assert r["stt"] == pytest.approx(0.03)


def test_arquivo_ausente_ou_torto_nao_quebra(arq):
    assert g.total_do_dia(str(arq))["total"] == 0
    arq.write_text("lixo\n{\"quando\": 1}\n[]\n", encoding="utf-8")
    assert g.total_do_dia(str(arq))["total"] == 0


def test_valor_zero_ou_negativo_nao_grava(arq):
    assert not g.registrar("tts", 0, caminho=str(arq))
    assert not g.registrar("tts", -1, caminho=str(arq))
    assert not arq.exists()


def test_linha_nao_guarda_texto_nem_segredo(arq):
    g.registrar("tts", 0.01, "gpt-4o-mini-tts", caminho=str(arq))
    linha = json.loads(arq.read_text(encoding="utf-8"))
    assert set(linha) == {"quando", "tipo", "usd", "detalhe"}


def test_sob_pytest_sem_variavel_nao_grava(monkeypatch):
    monkeypatch.delenv("DERVS_GASTO_ARQUIVO", raising=False)
    assert g.caminho_padrao() is None
    assert g.registrar("tts", 0.5) is False


def test_formatar_usd():
    assert g.formatar_usd(0) == "US$ 0,00"
    assert g.formatar_usd(1.234) == "US$ 1,23"
    assert g.formatar_usd(0.004) == "US$ 0,004"


def test_registrar_voz_mede_o_wav(arq):
    g.registrar_voz(_wav(30), "gpt-4o-mini-tts")
    assert g.total_do_dia(str(arq))["tts"] == pytest.approx(0.0075)


def test_registrar_cerebro_usa_usage(arq):
    g.registrar_cerebro("gpt-4.1-nano", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert g.total_do_dia(str(arq))["cerebro"] == pytest.approx(0.0003)
    g.registrar_cerebro("gpt-4.1-nano", None)     # sem usage: ignora em silêncio


# --- o gasto SOBE quando o DERVS fala, transcreve ou pensa (critério 4) -----

class _Resp:
    def __init__(self, dados):
        self._d = dados

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sintetizar_openai_registra_gasto(arq, monkeypatch):
    import dervs_tts
    monkeypatch.setattr(dervs_tts.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(_wav(60)))
    caminho = dervs_tts.sintetizar_openai("oi", "coral", "gpt-4o-mini-tts", "x", "chave")
    assert caminho
    os.remove(caminho)
    assert g.total_do_dia(str(arq))["tts"] == pytest.approx(0.015)


def test_transcricao_do_daemon_registra_gasto(arq, monkeypatch, tmp_path):
    import dervs_stt_daemon as d
    wav = tmp_path / "f.wav"
    wav.write_bytes(_wav(60))
    monkeypatch.setattr(d.urllib.request, "urlopen", lambda *a, **k: _Resp(b"ola"))
    monkeypatch.setattr(d, "OPENAI_KEY", "chave")
    assert d._transcrever_openai(str(wav)) == "ola"
    assert g.total_do_dia(str(arq))["stt"] == pytest.approx(0.006)


def test_transcricao_de_arquivo_registra_gasto(arq, monkeypatch, tmp_path):
    import dervs_transcrever as t
    wav = tmp_path / "f.wav"
    wav.write_bytes(_wav(120))
    monkeypatch.setattr(t.urllib.request, "urlopen", lambda *a, **k: _Resp(b"texto"))
    assert t._enviar(str(wav), "chave", "m", "") == "texto"
    assert g.total_do_dia(str(arq))["stt"] == pytest.approx(0.012)


def test_cerebro_openai_registra_gasto(arq, monkeypatch):
    import dervs_brain as b
    ficha = {"modo": "conversar", "fala": "oi", "pergunta": None, "passos": None}
    corpo = json.dumps({"choices": [{"message": {"content": json.dumps(ficha)}}],
                        "usage": {"prompt_tokens": 2000, "completion_tokens": 100}}).encode()
    monkeypatch.setattr(b.urllib.request, "urlopen", lambda *a, **k: _Resp(corpo))
    monkeypatch.setattr(b, "OPENAI_KEY", "chave")
    b._pensar_openai([{"papel": "dono", "texto": "oi"}], 10)
    assert g.total_do_dia(str(arq))["cerebro"] > 0
