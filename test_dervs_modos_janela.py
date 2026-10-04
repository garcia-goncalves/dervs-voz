"""Modos de escuta dentro do motor de verdade (Onda A, 04/10/2026).

Prova o que o briefing `dervs-jarvis` exige: em `Desligado` nenhum microfone é
aberto; `Atalho` só abre enquanto a tecla está apertada; o microfone esquecido
fecha sozinho; "pare de ouvir" fecha. A `Escuta` é trocada por uma falsa que só
conta aberturas — nenhum stream de microfone real é aberto aqui.
"""
import pytest

pytest.importorskip("PyQt6", reason="o motor é Qt")

from PyQt6 import QtWidgets                            # noqa: E402
import dervs                                          # noqa: E402
import dervs_electron                                 # noqa: E402
import dervs_modos_escuta as modos                    # noqa: E402

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Sinal:
    def connect(self, *a, **k):
        pass


class EscutaFalsa:
    abertas = 0
    paradas = 0

    def __init__(self):
        self.fala = self.mudo = self.nivel = self.finished = _Sinal()
        self.pausado = False

    def start(self):
        EscutaFalsa.abertas += 1

    def parar(self):
        EscutaFalsa.paradas += 1


class PonteFalsa:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        if nome.startswith("__"):
            raise AttributeError(nome)
        return lambda *a, **k: self.chamadas.append((nome, a))


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def motor(monkeypatch):
    EscutaFalsa.abertas = EscutaFalsa.paradas = 0
    monkeypatch.setattr(dervs, "Escuta", EscutaFalsa)
    gravados = {}
    monkeypatch.setattr(dervs.cfg, "gravar",
                        lambda chave, valor: gravados.__setitem__(chave, valor) or True)
    m = dervs_electron.Motor(PonteFalsa())
    m.gravados = gravados
    m.voz.ligada = False                       # nada de voz de verdade
    yield m
    dervs.encerrar_tudo(m)


def _apertar(motor, estados):
    """Troca a leitura do teclado por uma sequência de estados."""
    it = iter(estados)
    motor._tecla = modos.TeclaSegurada(leitor=lambda teclas: next(it))


def test_desligado_nao_abre_microfone_nenhum(motor):
    motor.definir_modo_escuta(modos.DESLIGADO)
    assert motor.escuta is None and EscutaFalsa.abertas == 0
    assert motor.modo_escuta() == "desligado"
    assert motor.gravados["modo_escuta"] == "desligado"


def test_voz_abre_e_arma_o_desligamento_automatico(motor):
    motor.definir_modo_escuta(modos.VOZ)
    assert motor.escuta is not None and EscutaFalsa.abertas == 1
    assert motor._auto.armado
    assert motor.gravados["modo_escuta"] == "voz"


def test_clique_no_botao_vira_modo_voz_e_desligar_vira_desligado(motor):
    motor.b_conversa.setChecked(True)
    assert motor.modo_escuta() == "voz" and motor.escuta is not None
    motor.b_conversa.setChecked(False)
    assert motor.modo_escuta() == "desligado" and motor.escuta is None
    assert not motor._auto.armado


def test_atalho_mantem_microfone_fechado_ate_apertar(motor):
    motor.definir_modo_escuta(modos.ATALHO)
    assert motor.escuta is None and EscutaFalsa.abertas == 0
    assert motor.gravados["modo_escuta"] == "atalho"
    assert motor._timer_tecla.isActive()


def test_atalho_abre_so_enquanto_aperta_e_fecha_depois_da_graca(motor):
    motor.definir_modo_escuta(modos.ATALHO)
    _apertar(motor, [True, True, False, False, False])
    motor._passo_tecla()                         # apertou
    assert motor.escuta is not None and EscutaFalsa.abertas == 1
    assert motor._esta_desperto()                # falou de propósito: sem porteiro
    motor._passo_tecla()                         # segurando
    assert motor.escuta is not None
    motor._passo_tecla()                         # soltou: ainda na graça
    assert motor.escuta is not None
    motor._atalho_soltou_em -= motor.GRACA_ATALHO_S + 0.1
    motor._passo_tecla()
    assert motor.escuta is None and EscutaFalsa.paradas == 1
    assert motor.modo_escuta() == "atalho"       # abrir/fechar pelo atalho não troca o modo
    assert motor.gravados["modo_escuta"] == "atalho"


def test_apertar_de_novo_na_graca_nao_reabre_nem_fecha(motor):
    motor.definir_modo_escuta(modos.ATALHO)
    _apertar(motor, [True, False, True, True])
    motor._passo_tecla()
    motor._passo_tecla()                         # soltou
    motor._passo_tecla()                         # apertou de novo na graça
    motor._passo_tecla()
    assert motor.escuta is not None and EscutaFalsa.abertas == 1
    assert motor._atalho_soltou_em is None


def test_tecla_apertada_fora_do_modo_atalho_nao_faz_nada(motor):
    motor.definir_modo_escuta(modos.DESLIGADO)
    _apertar(motor, [True, True])
    motor._passo_tecla()
    assert motor.escuta is None and EscutaFalsa.abertas == 0


def test_atalho_na_reuniao_nao_abre(motor):
    motor.definir_modo_escuta(modos.ATALHO)
    motor._reuniao_fim = 99999.0
    _apertar(motor, [True, True])
    motor._passo_tecla()
    assert motor.escuta is None and EscutaFalsa.abertas == 0


def test_botao_tira_do_modo_atalho_e_para_o_relogio_da_tecla(motor):
    motor.definir_modo_escuta(modos.ATALHO)
    motor.b_conversa.setChecked(True)
    assert motor.modo_escuta() == "voz"
    assert not motor._timer_tecla.isActive()


def test_microfone_esquecido_fecha_sozinho(motor):
    relogio = Relogio()
    motor._auto = modos.AutoDesligamento(2, relogio=relogio)
    motor.definir_modo_escuta(modos.VOZ)
    relogio.t += 60
    motor._checar_auto_desligamento()
    assert motor.escuta is not None              # 1 min: ainda não
    relogio.t += 61
    motor._checar_auto_desligamento()
    assert motor.escuta is None and motor.modo_escuta() == "desligado"
    assert motor.gravados["modo_escuta"] == "desligado"


def test_conversa_renova_o_desligamento_automatico(motor):
    relogio = Relogio()
    motor._auto = modos.AutoDesligamento(2, relogio=relogio)
    motor.definir_modo_escuta(modos.VOZ)
    relogio.t += 100
    motor._acordar(novo=True)                    # ele foi chamado: houve uso
    relogio.t += 100
    motor._checar_auto_desligamento()
    assert motor.escuta is not None


def test_pare_de_ouvir_fecha_o_microfone_quando_chamado_pelo_nome(motor):
    motor.definir_modo_escuta(modos.VOZ)
    motor._entrada_continua("DERVS, pare de ouvir")
    assert motor.escuta is None and motor.modo_escuta() == "desligado"


def test_pare_de_ouvir_sem_o_nome_e_sem_estar_desperto_e_ignorado(motor):
    motor.definir_modo_escuta(modos.VOZ)
    motor._entrada_continua("pare de ouvir")     # papo de sala, não é com ele
    assert motor.escuta is not None


def test_reuniao_nao_vira_a_escolha_do_dono(motor):
    motor.definir_modo_escuta(modos.VOZ)
    motor.pedir_reuniao(True)
    _app.processEvents()
    assert motor.escuta is None
    assert motor.gravados["modo_escuta"] == "voz"    # ainda "voz" no disco


def test_modo_invalido_cai_em_desligado(motor):
    motor.definir_modo_escuta("sempre-ouvindo")
    assert motor.modo_escuta() == "desligado" and motor.escuta is None
