"""Modos de escuta: normalização, 'pare de ouvir', auto-desligamento e tecla."""
import pytest

import dervs_modos_escuta as m


@pytest.mark.parametrize("v,esperado", [
    ("voz", "voz"), ("ATALHO", "atalho"), (" desligado ", "desligado"),
    (None, "desligado"), (True, "desligado"), ("sempre", "desligado"), (3, "desligado"),
])
def test_normalizar_modo_cai_no_lado_seguro(v, esperado):
    assert m.normalizar_modo(v) == esperado


@pytest.mark.parametrize("v,esperado", [
    (10, 10), ("5", 5), (0, 1), (-3, 1), (9999, 240), ("x", 10), (None, 10), (True, 10),
])
def test_minutos_ficam_entre_1_e_240(v, esperado):
    assert m.normalizar_minutos(v) == esperado


@pytest.mark.parametrize("frase", [
    "pare de ouvir", "Para de ouvir.", "pare de me ouvir", "desliga o microfone",
    "fecha o microfone agora", "chega de ouvir", "por favor, pare de escutar",
    "feche a escuta", "pare de ouvir, DERVS", "pare de ouvir dervs",
])
def test_pare_de_ouvir_casa(frase):
    assert m.eh_pare_de_ouvir(frase)


@pytest.mark.parametrize("frase", [
    "", "não pare de ouvir", "para de ouvir música e toca outra",
    "que horas são", "liga o microfone", "abre o chrome", "x" * 200,
    "para escutar música", "para ouvir isso", "chega ouvir", "fecha ouvir",
])
def test_pare_de_ouvir_nao_casa_com_conversa(frase):
    assert not m.eh_pare_de_ouvir(frase)


class Relogio:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_auto_desligamento_so_vence_depois_de_armado_e_do_prazo():
    r = Relogio()
    a = m.AutoDesligamento(2, relogio=r)
    assert not a.armado and a.restante_s() is None and not a.venceu()
    r.t += 9999
    assert not a.venceu()                  # desarmado nunca vence
    a.armar()
    r.t += 119
    assert not a.venceu()
    r.t += 2
    assert a.venceu() and a.restante_s() == 0.0


def test_tocar_renova_o_prazo_e_desarmar_para():
    r = Relogio()
    a = m.AutoDesligamento(1, relogio=r)
    a.armar()
    r.t += 50
    a.tocar()
    r.t += 50
    assert not a.venceu()                  # renovou aos 50 s
    a.desarmar()
    r.t += 9999
    assert not a.venceu()
    a.tocar()                               # tocar desarmado não arma
    assert not a.armado


def test_configurar_limita_minutos():
    a = m.AutoDesligamento(5)
    a.configurar(0)
    assert a.minutos == 1


def test_tecla_segurada_gera_so_as_bordas():
    estados = iter([False, True, True, False, False, True])
    t = m.TeclaSegurada(leitor=lambda teclas: next(estados))
    assert [t.passo() for _ in range(6)] == [None, "apertou", None, "soltou", None, "apertou"]
    assert t.apertada


def test_tecla_segurada_falha_de_leitura_conta_como_solta():
    def quebra(teclas):
        raise OSError("sem teclado")
    t = m.TeclaSegurada(leitor=quebra)
    assert t.passo() is None and not t.apertada


def test_atalho_usa_so_ctrl_e_alt_da_esquerda_para_nao_casar_com_altgr():
    assert m.COMBINACAO_PADRAO == (0xA2, 0xA4, 0x20)    # LCtrl, LAlt, Espaço
