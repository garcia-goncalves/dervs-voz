"""O teto diário e o "só analisa" da categoria "gastar com API" valem em TODA
chamada paga da OpenAI (cérebro, voz, transcrição, navegador), não só no cérebro.
Achado da revisão de 02/10/2026: a tela prometia o teto, mas só o cérebro o
respeitava."""
import pytest

import dervs_config
import dervs_gasto
import dervs_tts as tts


@pytest.fixture
def sem_orcamento(monkeypatch):
    monkeypatch.setattr(dervs_gasto, "pode_gastar", lambda conf=None: (False, "teto atingido"))


@pytest.fixture
def com_orcamento(monkeypatch):
    monkeypatch.setattr(dervs_gasto, "pode_gastar", lambda conf=None: (True, ""))


def _voz(monkeypatch):
    monkeypatch.setattr(dervs_config, "segredo", lambda nome: "sk-t")
    return tts.Voz(ligada=True, motor="openai")


def test_voz_na_nuvem_para_quando_o_teto_estoura(monkeypatch, sem_orcamento):
    assert not _voz(monkeypatch)._openai_disponivel()      # cai na voz local


def test_voz_na_nuvem_continua_com_orcamento(monkeypatch, com_orcamento):
    assert _voz(monkeypatch)._openai_disponivel()


def test_transcricao_do_daemon_cai_no_local_quando_o_teto_estoura(monkeypatch, sem_orcamento):
    import dervs_stt_daemon as stt
    chamadas = []
    monkeypatch.setattr(stt, "STT", "openai")
    monkeypatch.setattr(stt, "OPENAI_KEY", "sk-t")
    monkeypatch.setattr(stt, "_transcrever_openai", lambda c: chamadas.append("nuvem") or "x")
    monkeypatch.setattr(stt, "_transcrever_local", lambda c: "local")
    assert stt._transcrever("a.wav") == "local"
    assert chamadas == []


def test_transcricao_de_arquivo_recusa_com_motivo_quando_o_teto_estoura(monkeypatch, sem_orcamento):
    import dervs_transcrever as tr
    monkeypatch.setattr(tr.dervs_config, "segredo", lambda nome: "sk-t")
    with pytest.raises(RuntimeError, match="teto"):
        tr.transcrever("qualquer.wav")


def test_navegador_autonomo_recusa_quando_o_teto_estoura(monkeypatch, sem_orcamento):
    import dervs_browser as br
    monkeypatch.setattr(br, "_carregar_chave_openai", lambda: "sk-t")
    r = br.rodar_tarefa("abre o banco")
    assert r["codigo"] == 1 and "teto" in r["saida"]
