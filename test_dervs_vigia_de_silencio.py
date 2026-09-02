#!/usr/bin/env python3
"""Escutar o dia inteiro e não ouvir nada tem de virar aviso, não silêncio.

Por que existe: o `esta_mudo` que entrou junto com este arquivo cobre o botão
Gravar — o dono aperta, fala, e é avisado se não entrou som. Mas o DERVS também
escuta SOZINHO, o tempo todo (o "Ei DERVS"). Nesse modo ninguém aperta nada:
com o microfone desconectado, o porteiro simplesmente nunca acorda, a tela
segue escrito "pronto", e o dono passa horas achando que o DERVS o está
ignorando. Foi exatamente o que aconteceu em 02/09/2026.

O vigia abaixo é pura lógica (entra quadro, sai decisão) de propósito — dá para
testar sem microfone nenhum.

Rodar: python -m pytest test_dervs_vigia_de_silencio.py -q
"""
import array
import math

from dervs_listen import (FRAME_AMOSTRAS, FRAME_MS, PICO_SILENCIO, TAXA,
                          VigiaDeSilencio)


def _mudo() -> bytes:
    return array.array("h", [0] * FRAME_AMOSTRAS).tobytes()


def _com_som() -> bytes:
    return array.array("h", [int(6000 * math.sin(2 * math.pi * 440 * i / TAXA))
                             for i in range(FRAME_AMOSTRAS)]).tobytes()


def _quadros(segundos: float) -> int:
    return int(segundos * 1000 / FRAME_MS)


def _rodar(vigia, quadro, quantos) -> int:
    """Quantas vezes o vigia gritou ao longo de N quadros."""
    return sum(1 for _ in range(quantos) if vigia.ver(quadro))


# ---- não gritar cedo demais --------------------------------------------

def test_silencio_curto_nao_e_motivo_de_alarme():
    """Ninguém fala o tempo todo: pausa de 2 s é conversa normal."""
    assert _rodar(VigiaDeSilencio(segundos=8), _mudo(), _quadros(2.0)) == 0


def test_um_quadro_mudo_sozinho_nao_alarma():
    assert VigiaDeSilencio(segundos=8).ver(_mudo()) is False


def test_microfone_com_som_nunca_alarma():
    assert _rodar(VigiaDeSilencio(segundos=8), _com_som(), _quadros(60.0)) == 0


def test_chiado_baixo_de_microfone_ligado_nao_alarma():
    """Um microfone LIGADO num quarto quieto ainda entrega ruído de fundo."""
    quadro = array.array(
        "h", [(PICO_SILENCIO * 3) * (1 if i % 2 else -1)
              for i in range(FRAME_AMOSTRAS)]).tobytes()
    assert _rodar(VigiaDeSilencio(segundos=8), quadro, _quadros(60.0)) == 0


# ---- gritar quando é para gritar ---------------------------------------

def test_silencio_digital_continuo_alarma():
    assert _rodar(VigiaDeSilencio(segundos=8), _mudo(), _quadros(9.0)) == 1


def test_alarma_exatamente_uma_vez_por_mais_que_dure():
    """Aviso repetido vira ruído e o dono para de ler."""
    assert _rodar(VigiaDeSilencio(segundos=8), _mudo(), _quadros(300.0)) == 1


def test_o_tempo_e_configuravel():
    assert _rodar(VigiaDeSilencio(segundos=1), _mudo(), _quadros(1.5)) == 1
    assert _rodar(VigiaDeSilencio(segundos=30), _mudo(), _quadros(1.5)) == 0


# ---- voltar a vigiar quando o som volta --------------------------------

def test_um_som_no_meio_zera_a_contagem():
    vigia = VigiaDeSilencio(segundos=8)
    _rodar(vigia, _mudo(), _quadros(7.0))
    assert vigia.ver(_com_som()) is False
    assert _rodar(vigia, _mudo(), _quadros(7.0)) == 0, "não zerou a contagem"


def test_depois_de_avisar_o_som_volta_e_pode_avisar_de_novo():
    """O dono desconecta, é avisado, reconecta, e desconecta outra vez: tem de
    ser avisado outra vez. Um alerta que só serve uma vez por sessão é pior."""
    vigia = VigiaDeSilencio(segundos=1)
    assert _rodar(vigia, _mudo(), _quadros(1.5)) == 1
    _rodar(vigia, _com_som(), _quadros(1.0))
    assert _rodar(vigia, _mudo(), _quadros(1.5)) == 1


# ---- não quebrar com o que a fonte devolve quando cai -------------------

def test_quadro_vazio_da_fonte_caida_nao_conta_nem_estoura():
    """b'' significa "a fonte caiu" — quem trata disso é o religamento da
    escuta, não o vigia. Ele não pode nem estourar nem contar como silêncio."""
    vigia = VigiaDeSilencio(segundos=1)
    assert _rodar(vigia, b"", _quadros(60.0)) == 0


def test_o_padrao_de_tempo_e_razoavel():
    """Nem tão curto que atrapalhe, nem tão longo que o dono desista antes."""
    vigia = VigiaDeSilencio()
    assert _rodar(vigia, _mudo(), _quadros(3.0)) == 0
    assert _rodar(vigia, _mudo(), _quadros(60.0)) == 1
