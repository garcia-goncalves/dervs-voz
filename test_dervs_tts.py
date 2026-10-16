#!/usr/bin/env python3
"""Testes da localização dos motores de voz.

O que estes testes protegem: no Linux o projeto irmão instala os daemons e os
ambientes isolados em `~/voice`. No Windows essa pasta NÃO existe — os daemons
vêm com o repositório e as bibliotecas moram no `dervs-venv` do projeto. Com os
caminhos do Linux fixos no código, `Voz.disponivel()` respondia False e o DERVS
ficava MUDO nesta máquina, mesmo com o modelo do Kokoro baixado e o
`kokoro-onnx` instalado.

Rodar: python -m pytest test_dervs_tts.py -q
"""
import os
import sys
import pytest
import dervs_tts as tts

so_windows = pytest.mark.skipif(sys.platform != "win32",
                                reason="caminho de voz específico do Windows")


@so_windows
def test_o_daemon_do_kokoro_existe_no_disco():
    """Sem o script do daemon não há como subir a voz."""
    assert os.path.exists(tts.KOKORO_DAEMON), (
        f"daemon do Kokoro não está em {tts.KOKORO_DAEMON} — no Windows ele vem "
        "com o repositório, não em ~/voice")


@so_windows
def test_o_python_que_roda_o_kokoro_existe_e_tem_a_biblioteca():
    """O daemon precisa de um Python com kokoro-onnx. No Windows é o venv do
    próprio projeto, não um `~/voice/kokoro-venv` que nunca foi criado aqui."""
    assert os.path.exists(tts.KOKORO_PY), f"Python do Kokoro não está em {tts.KOKORO_PY}"
    import subprocess
    r = subprocess.run([tts.KOKORO_PY, "-c", "import kokoro_onnx"],
                       capture_output=True, timeout=120)
    assert r.returncode == 0, (
        f"{tts.KOKORO_PY} não tem kokoro-onnx: {r.stderr.decode('utf-8', 'replace')[:300]}")


@so_windows
def test_o_daemon_nao_e_procurado_na_pasta_do_linux():
    """Trava a regressão: nada de voz pode apontar para ~/voice no Windows."""
    for nome in ("KOKORO_PY", "KOKORO_DAEMON", "PIPER_DAEMON", "XTTS_DAEMON"):
        caminho = getattr(tts, nome).replace("\\", "/")
        assert "/voice/" not in caminho, (
            f"{nome} aponta para a pasta do Linux ({caminho}) — ela não existe no Windows")


@so_windows
@pytest.mark.skipif(not os.path.exists(tts.KOKORO_MODELO),
                    reason="modelo do Kokoro não baixado nesta máquina")
def test_o_dervs_consegue_falar_nesta_maquina():
    """O teste que interessa ao dono: existe ALGUM motor de voz de pé?"""
    voz = tts.Voz(ligada=False, motor="kokoro")   # a voz Gemini precisa da chave, que o teste não tem
    assert voz._kokoro_instalado(), (
        "Kokoro não considerado instalado — o DERVS fica mudo. "
        f"py={tts.KOKORO_PY} daemon={tts.KOKORO_DAEMON} modelo={tts.KOKORO_MODELO}")
    assert voz.disponivel(), "nenhum motor de voz disponível: o DERVS fica mudo"


def test_motor_padrao_do_tts_e_o_da_config_uma_fonte_so():
    """Havia três padrões diferentes (docstring, MOTOR_PADRAO e config). A config manda."""
    import dervs_config
    assert tts.MOTOR_PADRAO == dervs_config.PADRAO["motor"]


# ---- voz única (16/10/2026): o dono ouviu "duas vozes" (cedar + Charon, e Kokoro robótico) ----
def _voz_gemini(monkeypatch, sintetizar):
    monkeypatch.setattr(tts, "sintetizar_gemini", sintetizar)
    monkeypatch.setattr(tts.Voz, "_chave_gemini", lambda self: "chave-de-mentira")
    v = tts.Voz(ligada=True, motor="gemini")
    tocados = []
    monkeypatch.setattr(v, "_tocar_e_apagar", lambda wav: tocados.append(wav))
    for nome in ("_falar_openai", "_falar_kokoro", "_falar_piper", "_sintetizar_piper_direto"):
        monkeypatch.setattr(v, nome, lambda *a, **k: (_ for _ in ()).throw(AssertionError(nome)))
    return v, tocados


def test_motor_gemini_fala_a_resposta_inteira_numa_ida(monkeypatch):
    pedidos = []
    v, tocados = _voz_gemini(monkeypatch, lambda texto, voz, chave: pedidos.append((texto, voz)) or "x.wav")
    v._falar_bloqueante("Primeira frase. Segunda frase.")
    assert pedidos == [("Primeira frase. Segunda frase.", "Charon")] and tocados == ["x.wav"]


def test_motor_gemini_falhou_fica_calado_em_vez_de_trocar_de_voz(monkeypatch):
    v, tocados = _voz_gemini(monkeypatch, lambda *a: None)
    v._falar_bloqueante("Olá.")                  # nenhuma outra voz é chamada (AssertionError)
    assert tocados == []


def test_motor_gemini_nao_toca_os_acuses_gravados_em_outra_voz(monkeypatch):
    v, _ = _voz_gemini(monkeypatch, lambda *a: "x.wav")
    monkeypatch.setattr(tts, "criar_reprodutor", lambda a: (_ for _ in ()).throw(AssertionError("acuse")))
    v.acusar_recebimento(bloquear=True)


def test_silenciada_nao_fala(monkeypatch):
    v, tocados = _voz_gemini(monkeypatch, lambda *a: "x.wav")
    v.silenciada = True
    v.falar("Olá.")
    assert tocados == []


def test_motor_padrao_e_o_gemini():
    import dervs_config
    assert dervs_config.PADRAO["motor"] == "gemini"
    assert dervs_config._validar(dict(dervs_config.PADRAO, motor="gemini"))["motor"] == "gemini"


def test_aparar_silencio_tira_o_mudo_das_pontas():
    import numpy as np
    mudo = np.zeros(24000, np.int16)
    fala = (np.ones(2400, np.int16) * 5000)
    x = tts.aparar_silencio(np.concatenate([mudo, fala, mudo]).tobytes())
    assert len(x) // 2 < 2400 + 2 * int(24000 * 0.12) + 2
    assert tts.aparar_silencio(mudo.tobytes()) == b""
