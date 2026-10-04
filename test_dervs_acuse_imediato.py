"""Resposta imediata: depois que o dono fala, o DERVS diz "Certo." na hora (áudio já
guardado em disco), enquanto o cérebro pensa e a frase de verdade é gerada na nuvem.
Esconde o silêncio de ~2 s sem inventar nada: nunca atrasa, nunca levanta, e fica
quieto se o áudio ainda não existe."""
import os

import pytest

import dervs_tts as tts


@pytest.fixture
def voz(monkeypatch, tmp_path):
    monkeypatch.setenv("DERVS_ACUSES_DIR", str(tmp_path / "acuses"))
    monkeypatch.setattr(tts.dervs_config, "segredo", lambda nome: "sk-teste")
    monkeypatch.setattr(tts.dervs_gasto, "pode_gastar", lambda conf=None: (True, ""))
    return tts.Voz(ligada=True, motor="openai")


def _wav_falso(tmp_path, nome="x.wav"):
    p = tmp_path / nome
    p.write_bytes(b"RIFF" + b"\0" * 64)
    return str(p)


def test_prepara_os_acuses_uma_vez_e_depois_usa_o_disco(voz, monkeypatch, tmp_path):
    chamadas = []

    def falsa(frase, voz_, modelo, instrucoes, chave, tempo=1.0):
        chamadas.append(frase)
        return _wav_falso(tmp_path, f"g{len(chamadas)}.wav")
    monkeypatch.setattr(tts, "sintetizar_openai", falsa)
    voz.preparar_acuses(bloquear=True)
    assert sorted(chamadas) == sorted(tts.ACUSES)
    assert len(os.listdir(tmp_path / "acuses")) == len(tts.ACUSES)
    chamadas.clear()
    voz.preparar_acuses(bloquear=True)                    # já está em disco: não gasta de novo
    assert chamadas == []


def test_acusar_toca_o_audio_guardado(voz, monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "sintetizar_openai",
                        lambda *a, **k: _wav_falso(tmp_path, f"{abs(hash(a[0]))}.wav"))
    voz.preparar_acuses(bloquear=True)
    tocados = []
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: tocados.append(wav))
    voz.acusar_recebimento(bloquear=True)
    assert len(tocados) == 1 and tocados[0].startswith(str(tmp_path / "acuses"))


def test_sem_audio_guardado_fica_quieto_em_vez_de_atrasar(voz, monkeypatch):
    tocados = []
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: tocados.append(wav))
    voz.acusar_recebimento(bloquear=True)
    assert tocados == []


def test_nao_acusa_com_voz_desligada_ou_motor_local(monkeypatch, tmp_path):
    monkeypatch.setenv("DERVS_ACUSES_DIR", str(tmp_path / "acuses"))
    tocados = []
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: tocados.append(wav))
    tts.Voz(ligada=False, motor="openai").acusar_recebimento(bloquear=True)
    tts.Voz(ligada=True, motor="kokoro").acusar_recebimento(bloquear=True)
    assert tocados == []


def test_nunca_levanta_mesmo_se_tudo_falhar(voz, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(tts, "criar_reprodutor", quebra)
    monkeypatch.setattr(tts, "sintetizar_openai", quebra)
    voz.preparar_acuses(bloquear=True)
    voz.acusar_recebimento(bloquear=True)


def test_sem_orcamento_nao_prepara(voz, monkeypatch):
    monkeypatch.setattr(tts.dervs_gasto, "pode_gastar", lambda conf=None: (False, "teto"))
    chamou = []
    monkeypatch.setattr(tts, "sintetizar_openai", lambda *a, **k: chamou.append(1))
    voz.preparar_acuses(bloquear=True)
    assert chamou == []


def test_a_chave_do_cache_muda_com_a_voz_e_a_velocidade(voz):
    a = voz._arquivo_acuse("Certo.")
    voz.tempo_openai = 1.4
    assert voz._arquivo_acuse("Certo.") != a
    voz.voz_openai = "onyx"
    assert voz._arquivo_acuse("Certo.") != a
