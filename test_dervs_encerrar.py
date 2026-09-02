#!/usr/bin/env python3
"""Fechar o DERVS tem de desligar TUDO — inclusive depois de um tropeço.

Por que existe: o fechamento do app era um bloco só, dentro de um único
`try/except Exception: pass`. A primeira linha dele chamava `pop.rec.kill()`,
um método que `GravacaoManual` NÃO tem — ela é uma `QtCore.QThread`, e `kill()`
é de `QProcess`. Sobrou de quando a gravação era um `subprocess.Popen` do
`pw-record`.

Consequência: se o dono fechasse o DERVS com uma gravação em andamento, o
`AttributeError` daquela primeira linha abortava o bloco INTEIRO. Nunca
rodavam: parar a escuta, desligar a voz, esperar as threads vivas terminarem e
encerrar o motor de transcrição. O app fechava deixando os daemons de voz e de
transcrição vivos e órfãos, segurando microfone e memória — e uma `QThread`
ainda gravando era destruída pelo Qt, que derruba o processo sem traceback.

Duas correções, e a segunda é a que importa: usar o método que existe
(`parar()`), e tornar cada passo do fechamento independente dos outros, para
que o próximo defeito nesta lista custe UM passo, e não todos.
"""
import pytest

# Este arquivo testa o fechamento do app, que é Qt de verdade: importar
# `dervs` puxa PyQt6. Sem o `importorskip` abaixo, um Python sem PyQt6
# falha na COLETA -- e erro de coleta interrompe a suíte INTEIRA,
# escondendo os outros 370+ testes que nada têm com Qt. Pular um arquivo
# é ruim; esconder todos é muito pior. No ambiente do projeto
# (dervs-venv), onde o app de fato roda, este arquivo roda normalmente.
pytest.importorskip("PyQt6", reason="o fechamento do app é Qt; rode no dervs-venv")

import dervs


class Peca:
    """Uma peça do app que anota se foi desligada — e pode falhar de propósito."""

    def __init__(self, explode=False):
        self.desligada = False
        self.explode = explode

    def _agir(self):
        if self.explode:
            raise AttributeError("'Peca' object has no attribute 'kill'")
        self.desligada = True

    parar = _agir
    desligar = _agir
    kill = _agir


class ThreadFalsa:
    def __init__(self):
        self.esperada = 0

    def wait(self, ms):
        self.esperada = ms
        return True


class PopFalso:
    """O pop-up do DERVS reduzido ao que o fechamento toca."""

    def __init__(self, rec=None, escuta=None, voz=None, stt=None, threads=None):
        self._stt_encerrando = False
        self.rec = rec
        self.escuta = escuta
        self.voz = voz if voz is not None else Peca()
        self.stt = stt if stt is not None else Peca()
        self._threads = threads if threads is not None else []


def test_avisa_que_esta_encerrando_antes_de_qualquer_coisa():
    """Sem esta marca, o motor de voz morrendo dispara o aviso de queda e uma
    tentativa de religar no meio do fechamento."""
    pop = PopFalso()
    dervs.encerrar_tudo(pop)
    assert pop._stt_encerrando is True


def test_desliga_todas_as_pecas():
    rec, escuta, voz, stt = Peca(), Peca(), Peca(), Peca()
    t = ThreadFalsa()
    pop = PopFalso(rec=rec, escuta=escuta, voz=voz, stt=stt, threads=[t])

    falhas = dervs.encerrar_tudo(pop)

    assert not falhas
    assert rec.desligada and escuta.desligada and voz.desligada and stt.desligada
    assert t.esperada == 3000


def test_uma_peca_que_falha_nao_impede_as_outras_de_desligar():
    """O defeito real: `rec.kill()` levantava AttributeError na PRIMEIRA linha
    e tudo o que vinha depois era pulado, deixando daemons órfãos vivos."""
    rec = Peca(explode=True)
    escuta, voz, stt = Peca(), Peca(), Peca()
    pop = PopFalso(rec=rec, escuta=escuta, voz=voz, stt=stt)

    falhas = dervs.encerrar_tudo(pop)

    assert escuta.desligada, "a escuta ficou ligada porque a gravação falhou antes"
    assert voz.desligada, "a voz ficou ligada porque a gravação falhou antes"
    assert stt.desligada, "o motor de transcrição ficou ÓRFÃO VIVO"
    assert len(falhas) == 1 and "gravação" in falhas[0].lower()


def test_o_motor_de_transcricao_e_encerrado_mesmo_se_tudo_mais_falhar():
    """É ele que segura mais memória; ficar órfão é o pior caso."""
    stt = Peca()
    pop = PopFalso(rec=Peca(explode=True), escuta=Peca(explode=True),
                   voz=Peca(explode=True), stt=stt)

    falhas = dervs.encerrar_tudo(pop)

    assert stt.desligada
    assert len(falhas) == 3


def test_pecas_ausentes_nao_sao_erro():
    """Fechar o app sem nunca ter gravado nem escutado é o caso comum."""
    pop = PopFalso(rec=None, escuta=None)
    assert dervs.encerrar_tudo(pop) == []


def test_a_gravacao_e_parada_pelo_metodo_que_ela_tem_de_verdade():
    """`GravacaoManual` é uma QThread: tem `parar()`, não tem `kill()`.

    Este teste trava a regressão exata que causou o defeito.
    """
    from PyQt6 import QtCore

    assert issubclass(dervs.GravacaoManual, QtCore.QThread)
    assert hasattr(dervs.GravacaoManual, "parar")
    assert not hasattr(dervs.GravacaoManual, "kill"), (
        "se a QThread ganhou um kill(), reveja o fechamento do app")

    chamados = []

    class SoParar:
        def parar(self):
            chamados.append("parar")

        def __getattr__(self, nome):
            raise AttributeError(
                "o fechamento chamou %r, que GravacaoManual não tem" % nome)

    dervs.encerrar_tudo(PopFalso(rec=SoParar()))
    assert chamados == ["parar"]


if __name__ == "__main__":            # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
