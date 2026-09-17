#!/usr/bin/env python3
"""A `Escuta` calcula o nível do microfone quadro a quadro e joga fora — o HUD
não tem como desenhar a onda de voz sem esse número. Este teste trava que:
  1. o sinal `nivel` sai maior para quadro alto do que para quadro baixo;
  2. durante a pausa (enquanto o DERVS fala) nada é emitido — quem cuida do
     nível da fala do DERVS é outra etapa (dervs_tts.py);
  3. `fala` e `mudo` continuam se comportando como antes.

Rodar: python -m pytest test_dervs_escuta_nivel.py -q
"""
import array
import math

import pytest

# A `Escuta` mexe em Qt de verdade (QThread, pyqtSignal). Sem o
# `importorskip`, um Python sem PyQt6 falha na COLETA e derruba a suíte
# inteira — mesmo padrão de test_dervs_aviso_de_silencio.py:24-27.
pytest.importorskip("PyQt6", reason="a Escuta é QThread; rode no dervs-venv")

from PyQt6 import QtWidgets                            # noqa: E402
import dervs                                          # noqa: E402
from dervs_listen import TAXA                         # noqa: E402

# QThread e pyqtSignal exigem uma QApplication viva no processo — sem ela,
# emitir um sinal de dentro de Escuta.run() pode derrubar o interpretador
# (falha nativa, não exceção Python). Os testes deste arquivo são os
# primeiros do repositório a emitir sinal de verdade fora do app real.
_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _coletor():
    """Uma lista comum não aceita weakref, e o PyQt tenta enfraquecer a
    referência do slot ao conectar direto num `list.append` — nesta máquina
    isso derruba o interpretador (falha nativa) assim que o sinal dispara
    depois de muitas emissões. Uma função-fecho comum não tem esse problema:
    devolve a lista e uma função que a alimenta, para conectar a função."""
    itens = []
    return itens, lambda *a: itens.append(a[0] if a else None)


def _pcm(amostras) -> bytes:
    return array.array("h", amostras).tobytes()


def _quadro_de_silencio() -> bytes:
    return _pcm([0] * dervs.FRAME_AMOSTRAS)


def _quadro(amplitude) -> bytes:
    return _pcm(int(amplitude * math.sin(2 * math.pi * 440 * i / TAXA))
                for i in range(dervs.FRAME_AMOSTRAS))


class MicrofoneDeMentira:
    """Entrega uma lista de quadros, um por `ler()`, e deixa `run()` disparar
    a religada de verdade uma vez — na segunda vez que ligarem o microfone,
    `abrir()` explode, o que faz `run()` desistir e voltar (mesmo caminho que
    o microfone caindo de vez usa hoje)."""

    _chamadas_abrir = 0

    def __init__(self, escuta, frames, pausar_no):
        self._escuta = escuta
        self._frames = list(frames)
        self._pausar_no = pausar_no  # índice (1-based) em que liga a pausa
        self._n = 0

    def abrir(self):
        MicrofoneDeMentira._chamadas_abrir += 1
        if MicrofoneDeMentira._chamadas_abrir > 1:
            raise RuntimeError("fim do teste: não religa de novo")

    def ler(self):
        self._n += 1
        if self._n == self._pausar_no:
            self._escuta.pausado = True
        if not self._frames:
            return b""
        return self._frames.pop(0)

    def motivo_da_queda(self):
        return "fim do teste"

    def fechar(self):
        pass


def _rodar(frames, pausar_no=None):
    """Roda `Escuta.run()` direto na thread do teste (sem `.start()`), do
    mesmo jeito que test_dervs_aviso_de_silencio.py roda `GravacaoManual`.

    Troca `dervs.Microfone`/`dervs.time.sleep` na mão (sem a fixture
    `monkeypatch`) e devolve tudo no `finally`, para deixar o módulo como
    achou mesmo se `run()` explodir.
    """
    MicrofoneDeMentira._chamadas_abrir = 0
    e = dervs.Escuta()
    niveis, _add_nivel = _coletor()
    falas, _add_fala = _coletor()
    mudos, _add_mudo = _coletor()
    e.nivel.connect(_add_nivel)
    e.fala.connect(_add_fala)
    e.mudo.connect(_add_mudo)

    microfone_original = dervs.Microfone
    sleep_original = dervs.time.sleep
    dervs.Microfone = lambda: MicrofoneDeMentira(e, frames, pausar_no)
    dervs.time.sleep = lambda s: None
    try:
        e._rodando = True
        e.run()
    finally:
        dervs.Microfone = microfone_original
        dervs.time.sleep = sleep_original
    return e, niveis, falas, mudos


def test_escuta_emite_nivel_maior_para_quadro_alto_que_para_baixo():
    frames = [_quadro(9000), _quadro(500)]
    _e, niveis, _falas, _mudos = _rodar(frames)

    assert len(niveis) == 2
    alto, baixo = niveis
    assert alto > baixo


def test_escuta_nao_emite_nivel_durante_a_pausa():
    # pausar_no=1: já na primeira leitura a escuta está pausada, então o
    # quadro alto entra só para aquecer o endpointer — nunca deve virar nível.
    frames = [_quadro(9000), _quadro(9000)]
    _e, niveis, _falas, _mudos = _rodar(frames, pausar_no=1)

    assert niveis == [], "emitiu nível com o DERVS falando (pausado)"


def test_escuta_continua_emitindo_fala_e_mudo_como_antes():
    # VigiaDeSilencio só avisa depois de SEGUNDOS_ATE_AVISAR_MUDO (8s) de
    # silêncio seguido — a 30ms por quadro, são ~267 quadros mudos.
    frames = [_quadro_de_silencio()] * 280 + [_quadro(9000)] * 10
    _e, _niveis, _falas, mudos = _rodar(frames)

    assert mudos, "vigia de silêncio parou de avisar"
