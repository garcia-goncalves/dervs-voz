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
    voz = tts.Voz(ligada=False)
    assert voz._kokoro_instalado(), (
        "Kokoro não considerado instalado — o DERVS fica mudo. "
        f"py={tts.KOKORO_PY} daemon={tts.KOKORO_DAEMON} modelo={tts.KOKORO_MODELO}")
    assert voz.disponivel(), "nenhum motor de voz disponível: o DERVS fica mudo"
