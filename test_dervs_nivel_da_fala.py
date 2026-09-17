#!/usr/bin/env python3
"""Testes de `Voz._tocar` acompanhando o nível da fala do DERVS (C9 — Etapa 4).

O que estes testes protegem: enquanto o DERVS fala, quem ligou `voz.ao_nivel`
tem que ver a onda se mexer — e parar de se mexer assim que a fala acaba ou é
cortada por `calar()` (barge-in). Sem `ao_nivel` ligado, `_tocar` não pode
mudar de comportamento nem um pingo.

Usa um reprodutor dublê (poll()/terminate()/wait() controláveis pelo teste) no
lugar do sounddevice/winsound real — não precisa de áudio de verdade para
provar a lógica de acompanhamento.

Rodar: python -m pytest test_dervs_nivel_da_fala.py -q
"""
import math
import struct
import threading
import time
import wave

import pytest

import dervs_tts as tts


def _escrever_wav_16bits(caminho: str, segundos: float, taxa: int = 16000) -> None:
    """Gera um .wav PCM 16 bits mono com um tom audível (não silêncio), para
    o envelope ter valores acima de zero."""
    n = int(taxa * segundos)
    amostras = []
    for i in range(n):
        valor = int(12000 * math.sin(2 * math.pi * 440 * i / taxa))
        amostras.append(valor)
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(struct.pack(f"<{n}h", *amostras))


def _escrever_wav_8bits(caminho: str, segundos: float, taxa: int = 16000) -> None:
    """Gera um .wav de 8 bits — formato que `envelope_do_wav` recusa, devolvendo
    lista vazia. Serve para provar que envelope vazio não sobe thread nenhuma."""
    n = int(taxa * segundos)
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(taxa)
        w.writeframes(bytes([128] * n))


class _ReprodutorDublePorTempo:
    """Imita `_ReprodutorWinsound`: poll() volta None enquanto o "tempo de
    tocar" não passou, e vira 0 quando termina naturalmente ou é `terminate()`."""

    def __init__(self, duracao: float):
        self._duracao = duracao
        self._inicio = time.monotonic()
        self._parado = False

    def poll(self):
        if self._parado:
            return 0
        return None if (time.monotonic() - self._inicio) < self._duracao else 0

    def terminate(self):
        self._parado = True

    def wait(self):
        while self.poll() is None:
            time.sleep(0.01)


class _ReprodutorDubleManual:
    """Só termina quando o teste chama `.parar()` — para testar o corte no
    meio (barge-in) de forma determinística, sem depender de tempo real."""

    def __init__(self):
        self._parado = False

    def poll(self):
        return 0 if self._parado else None

    def terminate(self):
        self._parado = True

    def wait(self):
        while self.poll() is None:
            time.sleep(0.01)

    def parar(self):
        self._parado = True


@pytest.fixture
def wav_com_som(tmp_path):
    caminho = str(tmp_path / "fala.wav")
    _escrever_wav_16bits(caminho, segundos=0.15)  # ~5 blocos de 30ms
    return caminho


@pytest.fixture
def wav_vazio(tmp_path):
    """8 bits: `envelope_do_wav` devolve lista vazia para este arquivo."""
    caminho = str(tmp_path / "fala_estranha.wav")
    _escrever_wav_8bits(caminho, segundos=0.1)
    return caminho


def test_ao_nivel_recebe_valores_maiores_que_zero_e_termina_em_zero(wav_com_som, monkeypatch):
    reprodutor = _ReprodutorDublePorTempo(duracao=0.2)
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: reprodutor)

    voz = tts.Voz.__new__(tts.Voz)
    voz._lock = threading.Lock()
    voz._play = None
    voz.ao_nivel = None
    recebidos = []
    voz.ao_nivel = lambda v: recebidos.append(v)

    voz._tocar(wav_com_som)

    assert recebidos, "ao_nivel não recebeu nenhum valor"
    assert any(v > 0.0 for v in recebidos), "nenhum valor maior que zero — onda não reagiu"
    assert recebidos[-1] == 0.0, "última chamada tem que zerar a onda"


def test_barge_in_para_as_chamadas_de_nivel(wav_com_som, monkeypatch):
    reprodutor = _ReprodutorDubleManual()
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: reprodutor)

    voz = tts.Voz.__new__(tts.Voz)
    voz._lock = threading.Lock()
    voz._play = None
    recebidos = []

    def registrar(v):
        recebidos.append(v)
        if len(recebidos) == 1:
            # simula calar() cortando a reprodução assim que a onda começa a se mexer
            reprodutor.parar()

    voz.ao_nivel = registrar

    voz._tocar(wav_com_som)
    # dá tempo da thread de acompanhamento perceber o poll() != None e sair
    time.sleep(0.2)

    assert recebidos[-1] == 0.0, "corte no meio tem que zerar a onda mesmo assim"
    # não pode ter continuado recebendo nível depois do corte: só o valor que
    # disparou o corte e o zero final
    assert len(recebidos) <= 2, f"chamadas continuaram depois do barge-in: {recebidos}"


def test_sem_ao_nivel_ligado_tocar_se_comporta_como_antes(wav_com_som, monkeypatch):
    reprodutor = _ReprodutorDublePorTempo(duracao=0.05)
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: reprodutor)

    voz = tts.Voz.__new__(tts.Voz)
    voz._lock = threading.Lock()
    voz._play = None
    voz.ao_nivel = None

    # não pode lançar exceção, e tem que voltar assim que play.wait() destravar
    voz._tocar(wav_com_som)

    assert voz._play is reprodutor


def test_envelope_vazio_nao_sobe_thread_e_nao_quebra_a_fala(wav_vazio, monkeypatch):
    reprodutor = _ReprodutorDublePorTempo(duracao=0.05)
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: reprodutor)

    voz = tts.Voz.__new__(tts.Voz)
    voz._lock = threading.Lock()
    voz._play = None
    chamadas = []
    voz.ao_nivel = lambda v: chamadas.append(v)

    voz._tocar(wav_vazio)

    assert chamadas == [], "envelope vazio não pode disparar ao_nivel nenhuma vez"


def test_reprodutor_none_nao_quebra_com_ao_nivel_ligado(monkeypatch):
    monkeypatch.setattr(tts, "criar_reprodutor", lambda wav: None)

    voz = tts.Voz.__new__(tts.Voz)
    voz._lock = threading.Lock()
    voz._play = None
    voz.ao_nivel = lambda v: None

    voz._tocar("caminho/que/nao/importa.wav")  # não pode lançar exceção
