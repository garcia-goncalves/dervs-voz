#!/usr/bin/env python3
"""Testes da promessa de privacidade do DERVS.

O porteiro impede que o áudio SAIA da máquina (isso é testado em
`test_dervs_porteiro.py`). Este arquivo testa a outra metade da promessa: o
áudio também não pode FICAR acumulado na máquina.

Cada frase captada vira um .wav em disco antes de o porteiro decidir se era
com o DERVS — inclusive as frases que ele descarta. Ligado o dia inteiro, sem
apagar, isso deixaria centenas de gravações da sala do dono paradas para
sempre na pasta temporária do Windows, que não se limpa sozinha.

Rodar: python -m pytest test_dervs_privacidade.py -q
"""
import importlib.util
import os
import sys
import tempfile

import pytest


def _carregar_dervs():
    """Importa dervs.py sem abrir janela. Pula o teste se o Qt não existir no
    Python que está rodando a suíte (o Qt vive no ambiente isolado)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if importlib.util.find_spec("PyQt6") is None:
        pytest.skip("PyQt6 não está neste Python — o app vive no ambiente isolado")
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dervs.py")
    spec = importlib.util.spec_from_file_location("dervs_app", caminho)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["dervs_app"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _wav_de_mentira():
    fd, caminho = tempfile.mkstemp(suffix=".wav", prefix="dervs_teste_")
    os.write(fd, b"RIFF____WAVEfmt ")
    os.close(fd)
    return caminho


def test_gravacao_de_frase_e_apagada():
    """A frase que o porteiro descartou não pode ficar no disco."""
    dervs = _carregar_dervs()
    wav = _wav_de_mentira()
    assert os.path.exists(wav)
    dervs.descartar_wav(wav)
    assert not os.path.exists(wav), "a gravação da frase ficou no disco"


def test_gravacao_manual_e_poupada():
    """A gravação do botão Gravar/Parar reusa sempre o mesmo caminho e o dono
    pode querer reenviá-la — apagá-la quebraria o botão."""
    dervs = _carregar_dervs()
    with open(dervs.REC_WAV, "wb") as f:
        f.write(b"RIFF____WAVEfmt ")
    try:
        dervs.descartar_wav(dervs.REC_WAV)
        assert os.path.exists(dervs.REC_WAV), "apagou a gravação manual, que devia ficar"
    finally:
        try:
            os.remove(dervs.REC_WAV)
        except OSError:
            pass


def test_apagar_o_que_ja_sumiu_nao_quebra():
    """Apagar duas vezes, ou apagar arquivo que outro processo já levou, não
    pode derrubar a escuta — ficar surdo é pior que deixar um arquivo."""
    dervs = _carregar_dervs()
    wav = _wav_de_mentira()
    dervs.descartar_wav(wav)
    dervs.descartar_wav(wav)          # de novo, já não existe
    dervs.descartar_wav(None)         # nada
    dervs.descartar_wav("")           # vazio
    dervs.descartar_wav(os.path.join(tempfile.gettempdir(), "nao_existe_mesmo.wav"))
