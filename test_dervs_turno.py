#!/usr/bin/env python3
"""Testes do árbitro de vez com dublês de VAD e de Smart Turn: nenhum modelo nem rede."""
import hashlib
import io
import os

import numpy as np
import pytest

import dervs_config as cfg
import dervs_turno as T

N = T.FRAME_AMOSTRAS


def fala(n=1):
    return [(0.3 * np.sin(np.arange(N) / 7.0)).astype(np.float32)] * n


def silencio(n=1):
    return [np.zeros(N, np.float32)] * n


class VadFalso:
    """Fala = quadro com energia."""

    def __call__(self, quadro):
        return 1.0 if np.abs(T._para_float(quadro)).max() > 0.05 else 0.0


class TurnoFalso:
    def __init__(self, *probs):
        self.probs, self.chamadas = list(probs), []

    def __call__(self, audio):
        self.chamadas.append(len(audio))
        return self.probs.pop(0) if len(self.probs) > 1 else self.probs[0]


def alimentar(arb, quadros):
    out = []
    for q in quadros:
        out += arb.processar(q)
    return out


def tipos(eventos):
    return [type(e).__name__ for e in eventos]


def test_frase_completa_fecha_a_vez_apos_300ms():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.9))
    ev = alimentar(arb, fala(20) + silencio(10))
    assert tipos(ev) == ["InicioFala", "Pausa", "FimDeVez"]
    fim = ev[-1]
    assert fim.t == pytest.approx(30 * 0.03)
    assert len(fim.audio) >= 20 * N * 2 and isinstance(fim.audio, bytes)


def test_inicio_de_fala_tem_o_instante_do_primeiro_quadro():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.9))
    ev = alimentar(arb, silencio(10) + fala(5))
    assert isinstance(ev[0], T.InicioFala) and ev[0].t == pytest.approx(10 * 0.03, abs=0.001)


def test_pausa_para_pensar_nao_fecha_e_retomada_cancela():
    turno = TurnoFalso(0.1)
    arb = T.Arbitro(VadFalso(), turno)
    ev = alimentar(arb, fala(20) + silencio(40) + fala(20) + silencio(10))
    assert tipos(ev).count("FimDeVez") == 0
    assert tipos(ev).count("Pausa") == 2           # uma por silêncio de 300 ms; a retomada recomeça a conta
    assert len(turno.chamadas) == 5                # 4 no silêncio longo (a cada 300 ms) + 1 no final


def test_reavalia_a_cada_300ms_e_fecha_quando_o_modelo_muda_de_ideia():
    turno = TurnoFalso(0.1, 0.1, 0.8)
    arb = T.Arbitro(VadFalso(), turno)
    ev = alimentar(arb, fala(20) + silencio(30))
    assert len(turno.chamadas) == 3
    assert tipos(ev)[-1] == "FimDeVez"
    assert ev[-1].t == pytest.approx((20 + 30) * 0.03)


def test_teto_de_espera_fecha_mesmo_com_modelo_em_duvida():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.0), espera_max_s=1.5)
    ev = alimentar(arb, fala(20) + silencio(60))
    assert tipos(ev).count("FimDeVez") == 1
    assert ev[-1].t == pytest.approx((20 + 50) * 0.03)


def test_limiar_configuravel():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.6), prob_fim=0.7, espera_max_s=1.0)
    ev = alimentar(arb, fala(20) + silencio(10))
    assert "FimDeVez" not in tipos(ev)


def test_modelo_nao_ve_cauda_longa_de_silencio():
    turno = TurnoFalso(0.0)
    arb = T.Arbitro(VadFalso(), turno, espera_max_s=3.0, cola_max_ms=600)
    alimentar(arb, fala(20) + silencio(60))
    # a última avaliação (silêncio de 1,8 s) recebeu fala + só 600 ms de cauda
    assert turno.chamadas[-1] == (20 + 20) * N


def test_depois_do_fim_pode_comecar_outra_vez():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.9))
    ev = alimentar(arb, fala(20) + silencio(10) + silencio(10) + fala(10) + silencio(10))
    assert tipos(ev).count("FimDeVez") == 2 and tipos(ev).count("InicioFala") == 2


def test_clique_curto_nao_vira_fala():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.9))
    assert alimentar(arb, silencio(5) + fala(2) + silencio(30)) == []


def test_aceita_bytes_int16_e_float():
    for conv in (lambda q: (q * 32767).astype(np.int16).tobytes(),
                 lambda q: (q * 32767).astype(np.int16), lambda q: q):
        arb = T.Arbitro(VadFalso(), TurnoFalso(0.9))
        ev = alimentar(arb, [conv(q) for q in fala(20) + silencio(10)])
        assert tipos(ev)[-1] == "FimDeVez"


def test_caracteristicas_tem_o_formato_do_modelo():
    f = T.caracteristicas(np.random.default_rng(0).standard_normal(16000).astype(np.float32) * 0.1)
    assert f.shape == (80, 800) and f.dtype == np.float32 and np.isfinite(f).all()
    assert f.min() >= f.max() - 2.0 - 1e-4          # teto de 8 em log10 => faixa de 2 após (x+4)/4


def test_caracteristicas_cola_zeros_no_comeco_e_guarda_o_fim():
    curto = np.random.default_rng(1).standard_normal(8000).astype(np.float32)
    longo = np.concatenate([np.random.default_rng(2).standard_normal(50000).astype(np.float32), curto])
    f1, f2 = T.caracteristicas(curto), T.caracteristicas(longo)
    assert f1.shape == f2.shape == (80, 800)
    assert np.abs(f1[:, :300] - f1[:, :1]).max() < 0.2          # começo é o enchimento de zeros


def test_caracteristicas_batem_com_o_whisper_feature_extractor_de_referencia():
    """Valor de referência gerado UMA vez com o WhisperFeatureExtractor(chunk_length=8) do transformers
    4/5 (instalado só fora do venv), no mesmo caminho do Pipecat: 0,5 s de sinal + zeros no começo."""
    rng = np.random.default_rng(20261015)
    t = np.arange(8000) / 16000.0
    sinal = (0.3 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 1330 * t)
             + 0.02 * rng.standard_normal(len(t))).astype(np.float32)
    ref = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "mel_referencia.npz"))
    f = T.caracteristicas(sinal)
    assert np.allclose(f[:, -60:], ref["fim"], atol=1e-3)         # a fala, no fim da janela
    assert np.allclose(f[:, :1], ref["inicio"], atol=1e-3)        # o enchimento de zeros, no começo


def test_banco_mel_slaney_do_whisper():
    f = T._filtros_mel()
    assert f.shape == (201, 80) and (f >= 0).all()
    assert f[:, 0].argmax() < f[:, 79].argmax()
    assert f.sum(axis=0).min() > 0


def test_energia_de_reserva_emite_os_mesmos_eventos():
    arb = T.ArbitroEnergia()
    quadros = [np.zeros(N, np.int16)] * 30 + [(8000 * np.sin(np.arange(N) / 5.0)).astype(np.int16)] * 30 \
        + [np.zeros(N, np.int16)] * 45
    ev = alimentar(arb, quadros)
    assert tipos(ev) == ["InicioFala", "FimDeVez"]
    assert len(ev[-1].audio) > 30 * N * 2 * 0.9


def _resposta(conteudo):
    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    return R(conteudo)


def test_download_confere_sha_e_grava_atomico(tmp_path, monkeypatch):
    conteudo = b"modelo de mentira"
    monkeypatch.setitem(T.MODELOS, "x.onnx", ("http://exemplo/x.onnx", hashlib.sha256(conteudo).hexdigest()))
    monkeypatch.setattr(T.urllib.request, "urlopen", lambda url, timeout=0: _resposta(conteudo))
    caminho = T.garantir_modelo("x.onnx", str(tmp_path))
    assert caminho == str(tmp_path / "x.onnx") and (tmp_path / "x.onnx").read_bytes() == conteudo
    assert [p.name for p in tmp_path.iterdir()] == ["x.onnx"]          # sem sobra .parcial


def test_download_corrompido_e_descartado(tmp_path, monkeypatch):
    monkeypatch.setitem(T.MODELOS, "x.onnx", ("http://exemplo/x.onnx", hashlib.sha256(b"certo").hexdigest()))
    monkeypatch.setattr(T.urllib.request, "urlopen", lambda url, timeout=0: _resposta(b"adulterado"))
    assert T.garantir_modelo("x.onnx", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_sem_rede_devolve_none(tmp_path, monkeypatch):
    def falha(*a, **k):
        raise OSError("sem rede")
    monkeypatch.setattr(T.urllib.request, "urlopen", falha)
    assert T.garantir_modelo("silero_vad.onnx", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_criar_sem_modelos_cai_na_energia(tmp_path):
    assert isinstance(T.criar({}, pasta=str(tmp_path), baixar=False), T.ArbitroEnergia)


def test_download_acima_do_teto_de_tamanho_e_descartado(tmp_path, monkeypatch):
    conteudo = b"x" * 5000
    monkeypatch.setitem(T.MODELOS, "x.onnx", ("https://exemplo/x.onnx", hashlib.sha256(conteudo).hexdigest()))
    monkeypatch.setattr(T.urllib.request, "urlopen", lambda url, timeout=0: _resposta(conteudo))
    monkeypatch.setattr(T, "MAX_DOWNLOAD_BYTES", 1000)
    assert T.garantir_modelo("x.onnx", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []                            # nem o .parcial fica


def test_urls_dos_modelos_estao_fixadas_em_versao_imutavel():
    for nome, (url, _sha) in T.MODELOS.items():
        assert url.startswith("https://") and "/master/" not in url and "/main/" not in url, nome
    assert "bfdc0193023f121ea5b3cc7b176dbed570a68a59" in T.MODELOS["silero_vad.onnx"][0]


def test_buffer_da_fala_tem_teto_de_30s_e_descarta_o_mais_antigo():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.0))
    ev = alimentar(arb, fala(1100))                    # 33 s de fala sem pausa
    assert len(arb._buf) == 1000 and tipos(ev) == ["InicioFala"]


def test_fim_de_vez_depois_do_teto_entrega_no_maximo_30s():
    arb = T.Arbitro(VadFalso(), TurnoFalso(0.9))
    ev = alimentar(arb, fala(1100) + silencio(10))
    assert tipos(ev)[-1] == "FimDeVez" and len(ev[-1].audio) <= 1000 * N * 2


def test_criar_avisa_uma_vez_que_caiu_na_energia(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(T, "_avisou_reserva", False)
    with caplog.at_level("WARNING", logger="dervs.turno"):
        T.criar({}, pasta=str(tmp_path), baixar=False)
        T.criar({}, pasta=str(tmp_path), baixar=False)
    avisos = [r for r in caplog.records if r.name == "dervs.turno"]
    assert len(avisos) == 1 and "energia" in avisos[0].getMessage() and "modelos" in avisos[0].getMessage()


def test_criar_avisa_o_motivo_quando_o_modelo_nao_carrega(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(T, "_avisou_reserva", False)
    monkeypatch.setattr(T, "garantir_modelo", lambda nome, pasta=None, baixar=True: "caminho")

    def quebra(caminho):
        raise RuntimeError("onnx quebrado")
    monkeypatch.setattr(T, "VadSilero", quebra)
    with caplog.at_level("WARNING", logger="dervs.turno"):
        assert isinstance(T.criar({}, pasta=str(tmp_path)), T.ArbitroEnergia)
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize("espera,silencio", [(0.5, 300), (2.0, 2000), (1.0, 800)])
def test_config_espera_max_tem_de_passar_do_silencio_minimo_mais_300ms(espera, silencio):
    """Teto de espera <= silêncio mínimo faria o árbitro fechar a vez sem nunca consultar o modelo."""
    c = cfg._validar(dict(cfg.PADRAO, turno_espera_max_s=espera, turno_silencio_min_ms=silencio))
    assert (c["turno_espera_max_s"], c["turno_silencio_min_ms"]) == (
        cfg.PADRAO["turno_espera_max_s"], cfg.PADRAO["turno_silencio_min_ms"])


def test_config_espera_max_coerente_e_mantida():
    c = cfg._validar(dict(cfg.PADRAO, turno_espera_max_s=2.5, turno_silencio_min_ms=2000))
    assert (c["turno_espera_max_s"], c["turno_silencio_min_ms"]) == (2.5, 2000)


def test_config_padrao_do_turno():
    assert (cfg.PADRAO["turno_prob_fim"], cfg.PADRAO["turno_espera_max_s"],
            cfg.PADRAO["turno_silencio_min_ms"]) == (0.5, 3.0, 300)
