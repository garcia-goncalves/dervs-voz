#!/usr/bin/env python3
"""O microfone precisa aguentar duas mãos ao mesmo tempo.

Por que existe: em 02/09/2026 o dono disse "o DERVS sumiu definitivamente".
O registro de queda (`dervs_registro.py`) gravou o motivo exato:

    Windows fatal exception: code 0xc0000374   <- corrupção de memória
      sounddevice.py:1168 in close
      dervs.py:313 in fechar
      dervs.py:429 in run

Duas threads fechavam o MESMO stream do PortAudio no mesmo instante: a thread
da tela, quando o dono aperta VOZ (`Escuta.parar()`), e a própria thread de
escuta, no `finally` do laço. O `if self._stream is not None` não protege nada
— as duas passam por ele antes de qualquer uma zerar. O PortAudio libera duas
vezes a mesma memória e o Windows mata o processo NA HORA, sem traceback: o app
some da tela e o dono não vê motivo nenhum.

Estes testes usam um stream de mentira que ACUSA o fechamento em dobro, em vez
de corromper a memória de verdade. Assim a corrida vira uma falha de teste
legível em vez de um app que desaparece.
"""
import threading

import pytest

import dervs_listen


class StreamDeMentira:
    """Um stream de áudio que denuncia o mau uso em vez de corromper memória.

    É o PortAudio com um alarme: `close()` duas vezes, ou `read()` depois do
    `close()`, é exatamente o que derruba o app de verdade.
    """

    def __init__(self, atraso_no_close=0.0, atraso_no_read=0.0):
        self.fechado = False
        self.abortado = False
        self.fechamentos = 0
        self.leituras_depois_de_fechar = 0
        self._atraso_no_close = atraso_no_close
        self._atraso_no_read = atraso_no_read
        self._trava = threading.Lock()

    def start(self):
        pass

    def read(self, quadros):
        if self.fechado:
            # No PortAudio de verdade isto é acesso a memória já liberada.
            self.leituras_depois_de_fechar += 1
            raise AssertionError("read() depois do close(): uso de memória liberada")
        if self._atraso_no_read:
            import time
            time.sleep(self._atraso_no_read)
        return (b"\x00\x00" * quadros, False)

    def abort(self):
        self.abortado = True

    def close(self):
        with self._trava:
            self.fechamentos += 1
        if self._atraso_no_close:
            # A janela de tempo onde o PortAudio está no meio da liberação.
            # É aqui que a segunda thread entrava e corrompia o heap.
            import time
            time.sleep(self._atraso_no_close)
        self.fechado = True


def _microfone_com(stream):
    mic = dervs_listen.Microfone()
    mic._stream = stream
    return mic


def test_fechar_duas_vezes_seguidas_fecha_o_stream_uma_vez_so():
    """O caso simples: mesmo em sequência, o segundo fechar é inofensivo."""
    stream = StreamDeMentira()
    mic = _microfone_com(stream)

    mic.fechar()
    mic.fechar()

    assert stream.fechamentos == 1


def test_duas_threads_fechando_ao_mesmo_tempo_fecham_uma_vez_so():
    """A corrida real: a tela e a thread de escuta fechando no mesmo instante.

    O atraso dentro do `close()` abre de propósito a mesma janela de tempo que
    o PortAudio abre ao liberar memória. Sem trava, as duas entram.
    """
    stream = StreamDeMentira(atraso_no_close=0.05)
    mic = _microfone_com(stream)

    largada = threading.Event()

    def fechar():
        largada.wait(2.0)
        mic.fechar()

    maos = [threading.Thread(target=fechar) for _ in range(8)]
    for t in maos:
        t.start()
    largada.set()
    for t in maos:
        t.join(5.0)
        assert not t.is_alive(), "fechar() travou: o app congelaria ao apertar VOZ"

    assert stream.fechamentos == 1, (
        "o stream foi fechado %d vezes — é isto que corrompe a memória e mata "
        "o app na hora" % stream.fechamentos)


def test_ler_durante_o_fechar_nunca_toca_num_stream_fechado():
    """`ler()` em voo enquanto a outra thread fecha: não pode ler o já liberado.

    É o outro lado da mesma corrida — a thread de escuta está bloqueada
    esperando som quando o dono aperta VOZ.
    """
    stream = StreamDeMentira(atraso_no_read=0.02, atraso_no_close=0.02)
    mic = _microfone_com(stream)

    erros = []

    def lendo():
        try:
            for _ in range(200):
                if mic.ler() == b"":
                    return          # fonte fechada: é a saída correta
        except Exception as e:      # pragma: no cover - é a falha que caçamos
            erros.append(e)

    leitor = threading.Thread(target=lendo)
    leitor.start()
    mic.fechar()
    leitor.join(5.0)

    assert not leitor.is_alive(), "ler() ficou preso depois do fechar()"
    assert not erros, "ler() tocou no stream já fechado: %r" % (erros,)
    assert stream.leituras_depois_de_fechar == 0
    assert stream.fechamentos == 1


def test_ler_depois_de_fechar_devolve_vazio_e_nao_explode():
    """Quem chama `ler()` já com a fonte fechada recebe b'', não uma exceção.

    A thread de escuta trata b'' como 'a fonte caiu' e sai do laço; uma exceção
    aqui subiria até o `threading.excepthook` e mataria a escuta.
    """
    stream = StreamDeMentira()
    mic = _microfone_com(stream)
    mic.fechar()

    assert mic.ler() == b""
    assert stream.leituras_depois_de_fechar == 0


def test_fechar_sem_nunca_ter_aberto_e_inofensivo():
    """`parar()` pode chegar antes de `abrir()`; não pode explodir por isso."""
    dervs_listen.Microfone().fechar()


class ProcDeMentira:
    """O caminho `arecord` (Linux, reserva) tem a MESMA corrida."""

    def __init__(self):
        self.terminados = 0
        self.stdout = None
        self.stderr = None

    def terminate(self):
        self.terminados += 1


def test_o_caminho_arecord_tambem_so_e_encerrado_uma_vez():
    mic = dervs_listen.Microfone()
    proc = ProcDeMentira()
    mic._proc = proc

    maos = [threading.Thread(target=mic.fechar) for _ in range(6)]
    for t in maos:
        t.start()
    for t in maos:
        t.join(5.0)

    assert proc.terminados == 1


if __name__ == "__main__":            # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
