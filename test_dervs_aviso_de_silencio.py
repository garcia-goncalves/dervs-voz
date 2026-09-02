#!/usr/bin/env python3
"""Gravou silêncio? O DERVS tem de DIZER — e não pagar a nuvem por nada.

Por que existe: em 02/09/2026, 19h59, o dono apertou Gravar e falou. O
`dervs_rec.wav` que sobrou tinha 4,71 s e pico 1 numa escala de 32.767 —
silêncio digital puro, porque as duas entradas de microfone do gabinete
estavam DESCONECTADO no Windows. O DERVS mandou aquele silêncio para a OpenAI,
pagou a chamada, recebeu `""` de volta e mostrou um campo vazio, sem nenhuma
explicação. O dono concluiu, com razão, que "a transcrição não funciona".

A transcrição funcionava. A entrada é que não existia. Estes testes travam as
duas metades da correção:
  1. a gravação sabe dizer se entrou som;
  2. quem recebe uma gravação muda avisa o dono e NÃO manda nada para a nuvem.

Rodar: python -m pytest test_dervs_aviso_de_silencio.py -q
"""
import array
import math
import types

import pytest

# Este arquivo toca a janela do app, que é Qt de verdade. Sem o `importorskip`,
# um Python sem PyQt6 falha na COLETA — e erro de coleta interrompe a suíte
# inteira, escondendo os 390+ testes que nada têm com Qt.
pytest.importorskip("PyQt6", reason="a tela do DERVS é Qt; rode no dervs-venv")

import dervs                                          # noqa: E402
from dervs_listen import TAXA                         # noqa: E402


def _pcm(amostras) -> bytes:
    return array.array("h", amostras).tobytes()


def _quadro_de_silencio() -> bytes:
    return _pcm([0] * dervs.FRAME_AMOSTRAS)


def _quadro_de_fala() -> bytes:
    return _pcm(int(8000 * math.sin(2 * math.pi * 440 * i / TAXA))
                for i in range(dervs.FRAME_AMOSTRAS))


class MicrofoneDeMentira:
    """Entrega N quadros e depois "cai" (b""), como o de verdade faz."""

    def __init__(self, quadro, vezes=10):
        self._restam = [quadro] * vezes
        self.fechado = False

    def abrir(self):
        pass

    def ler(self):
        return self._restam.pop() if self._restam else b""

    def fechar(self):
        self.fechado = True


def _gravar(monkeypatch, tmp_path, quadro):
    destino = str(tmp_path / "gravado.wav")
    monkeypatch.setattr(dervs, "Microfone",
                        lambda: MicrofoneDeMentira(quadro))
    rec = dervs.GravacaoManual(destino)
    rec.run()                       # a thread por dentro, sem agendar no Qt
    return rec


# ---- 1. a gravação sabe se entrou som ----------------------------------

def test_gravacao_de_silencio_se_declara_muda(monkeypatch, tmp_path):
    assert _gravar(monkeypatch, tmp_path, _quadro_de_silencio()).mudo is True


def test_gravacao_com_fala_nao_se_declara_muda(monkeypatch, tmp_path):
    assert _gravar(monkeypatch, tmp_path, _quadro_de_fala()).mudo is False


def test_gravacao_cancelada_antes_de_comecar_nao_mente(monkeypatch, tmp_path):
    """Cancelada é cancelada — não é "o microfone está mudo"."""
    destino = str(tmp_path / "cancelada.wav")
    monkeypatch.setattr(dervs, "Microfone",
                        lambda: MicrofoneDeMentira(_quadro_de_fala()))
    rec = dervs.GravacaoManual(destino)
    rec.parar()
    rec.run()
    assert rec.mudo is False


def test_gravacao_nasce_nao_muda(tmp_path):
    """Antes de rodar, ninguém pode afirmar que o microfone está mudo."""
    assert dervs.GravacaoManual(str(tmp_path / "x.wav")).mudo is False


# ---- 2. quem recebe uma gravação muda avisa e não gasta -----------------

class SttDeMentira:
    def __init__(self):
        self.escrito = []

    def write(self, dados):
        self.escrito.append(dados)


def _pop(rec_mudo):
    """A janela reduzida ao que `_gravacao_fechada` de fato usa."""
    return types.SimpleNamespace(
        _rec_enviado=False,
        _stt_pronto=True,
        _pendente=None,
        rec=types.SimpleNamespace(mudo=rec_mudo, parar=lambda: None),
        stt=SttDeMentira(),
        status=types.SimpleNamespace(setText=lambda t: None),
        recados=[],
        _recado_do_ouvido=lambda texto, cor: None,
    )


def _fechar(pop):
    dervs.PopUp._gravacao_fechada(pop)


def test_gravacao_muda_nao_vai_para_a_nuvem():
    pop = _pop(rec_mudo=True)
    _fechar(pop)
    assert pop.stt.escrito == [], "mandou silêncio para a nuvem — isso é dinheiro"


def test_gravacao_muda_avisa_o_dono():
    pop = _pop(rec_mudo=True)
    ditos = []
    pop._recado_do_ouvido = lambda texto, cor: ditos.append(texto)
    _fechar(pop)
    assert ditos, "o DERVS ficou calado sobre não ter entrado som"
    assert "som" in ditos[0].lower()


def test_gravacao_com_som_segue_para_a_nuvem_como_sempre():
    pop = _pop(rec_mudo=False)
    _fechar(pop)
    assert len(pop.stt.escrito) == 1
    assert dervs.REC_WAV.encode() in pop.stt.escrito[0]


def test_gravacao_muda_nao_fica_pendente_para_transcrever_depois():
    """Sem isto, o silêncio voltaria assim que o motor ficasse pronto."""
    pop = _pop(rec_mudo=True)
    pop._stt_pronto = False
    _fechar(pop)
    assert pop._pendente is None


def test_a_trava_de_envio_unico_continua_valendo():
    pop = _pop(rec_mudo=False)
    _fechar(pop)
    pop.rec = types.SimpleNamespace(mudo=False, parar=lambda: None)
    _fechar(pop)
    assert len(pop.stt.escrito) == 1
