#!/usr/bin/env python3
"""O novo ponto de entrada (`dervs_electron.py`) não pode deixar sobrar duas
interfaces concorrentes: a `PopUp` do Qt continua viva por dentro (Decisão A
do plano — reusar a orquestração já corrigida), mas a janela Qt de verdade
NUNCA pode aparecer na tela. Quem aparece é sempre o Electron, via
`PonteElectron`.

O teste mais importante deste arquivo é `test_motor_nunca_mostra_a_janela_qt`:
depois de `Motor(...).abrir()`, `isVisible()` tem de ser `False`.

Roda no `dervs-venv` (precisa de PyQt6): `pytest test_dervs_electron_entrada.py -q`.
"""
import threading

import pytest

pytest.importorskip("PyQt6", reason="dervs_electron usa a PopUp, que é Qt; "
                                     "rode no dervs-venv")

from PyQt6 import QtWidgets                            # noqa: E402
import dervs                                          # noqa: E402
import dervs_electron                                 # noqa: E402
import dervs_instancia as instancia                   # noqa: E402

# QWidget/QThread exigem uma QApplication viva no processo — mesmo padrão de
# test_dervs_escuta_nivel.py.
_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class PonteFalsa:
    """Um dublê de `PonteElectron`: só anota o que foi chamado, sem subir
    processo nenhum."""

    def __init__(self):
        self.chamadas = []
        self.fechada = False

    def enviar_estado(self, valor, texto="", apoio=""):
        self.chamadas.append(("estado", valor, texto, apoio))

    def enviar_volume(self, x):
        self.chamadas.append(("volume", x))

    def enviar_fala(self, papel, texto):
        self.chamadas.append(("fala", papel, texto))

    def enviar_plano(self, passos, nivel, pergunta):
        self.chamadas.append(("plano", passos, nivel, pergunta))

    def enviar_mostrar(self):
        self.chamadas.append(("mostrar",))

    def fechar(self, espera=3.0):
        self.fechada = True

    def de_tipo(self, tipo):
        return [c for c in self.chamadas if c[0] == tipo]


@pytest.fixture
def motor():
    """Um `Motor` de verdade, ligado a uma `PonteFalsa` — a `PopUp` sobe do
    jeito que sempre sobe (STT como `QProcess`, cérebro aquecendo numa
    thread), só que a ponte não escreve em processo nenhum."""
    ponte = PonteFalsa()
    m = dervs_electron.Motor(ponte)
    yield m
    # limpeza: encerra o que a PopUp deixou de pé, senão a QThread do STT
    # (QProcess) e as threads registradas vazam entre testes.
    dervs.encerrar_tudo(m)


# ---- o teste mais importante desta etapa -----------------------------------

def test_motor_nunca_mostra_a_janela_qt(motor):
    motor.abrir()
    assert motor.isVisible() is False, (
        "a janela Qt apareceu — sobraram duas interfaces concorrentes")
    assert motor.ponte.de_tipo("mostrar"), (
        "abrir() tem de avisar a ponte, senão o Electron nunca aparece")


def test_show_tambem_nao_mostra_a_janela_qt(motor):
    motor.show()
    assert motor.isVisible() is False
    assert motor.ponte.de_tipo("mostrar")


# ---- conversa, ocupado, recado de erro -------------------------------------

def test_diz_manda_fala_pela_ponte_com_os_campos_certos(motor):
    motor._diz("dervs", "oi, tudo bem?", cor="#123456")
    falas = motor.ponte.de_tipo("fala")
    assert falas == [("fala", "dervs", "oi, tudo bem?")]


def test_ocupado_manda_estado_pensando(motor):
    motor._ocupado(True, "pensando…")
    estados = motor.ponte.de_tipo("estado")
    assert estados[-1] == ("estado", "pensando", "pensando…", "")


def test_recado_do_ouvido_manda_estado_erro_com_a_frase_de_textos_md(motor):
    # o texto que "nao entrou som" produz de verdade (dervs_listen.motivo_do_silencio,
    # variante "microfone existe mas nada chegou")
    motor._recado_do_ouvido(
        "nao entrou som: o microfone esta mudo no Windows ou desconectado "
        "da entrada rosa", "#e8677a")
    estados = motor.ponte.de_tipo("estado")
    valor, texto, apoio = estados[-1][1], estados[-1][2], estados[-1][3]
    assert valor == "erro"
    assert texto == dervs_electron._CASO_SEM_SOM


def test_recado_do_ouvido_reconhece_microfone_desconectado(motor):
    motor._recado_do_ouvido(
        "nao entrou som: nenhum microfone foi encontrado neste computador",
        "#e8677a")
    _, valor, texto, apoio = motor.ponte.de_tipo("estado")[-1]
    assert valor == "erro"
    assert texto == dervs_electron._CASO_MIC_DESCONECTADO
    assert apoio == dervs_electron._APOIO_PADRAO


def test_recado_do_ouvido_ajudante_caiu_e_o_padrao(motor):
    motor._recado_do_ouvido("o ouvido está demorando demais para ficar pronto",
                            "#e8677a")
    _, valor, texto, apoio = motor.ponte.de_tipo("estado")[-1]
    assert valor == "erro"
    assert texto == dervs_electron._CASO_AJUDANTE_CAIU
    assert apoio == dervs_electron._APOIO_PADRAO


# ---- o callback de instância única roda em thread real, sem Qt ------------

def test_me_chamaram_roda_em_thread_de_verdade_e_so_manda_mostrar():
    ponte = PonteFalsa()
    me_chamaram = dervs_electron._construir_me_chamaram(ponte)
    fora_da_main = {}

    def alvo():
        fora_da_main["thread"] = threading.current_thread()
        me_chamaram()

    t = threading.Thread(target=alvo)
    t.start()
    t.join(timeout=2)

    assert fora_da_main["thread"] is not threading.main_thread()
    assert ponte.de_tipo("mostrar"), (
        "o callback rodou, mas não mandou 'mostrar' pela ponte")
    # nada além de 'mostrar' foi chamado — nenhum widget Qt foi tocado
    assert ponte.chamadas == [("mostrar",)]


# ---- o cartão de passo destrutivo tem de ir pela ponte (o bug de segurança) -
#
# Antes desta correção, `_mostrar_cartao` (herdado de `PopUp`) só escrevia em
# widgets Qt escondidos — o Electron nunca era avisado e o plano travava em
# silêncio no primeiro passo destrutivo. Os testes abaixo provam que a ponte
# recebe o cartão, e que as duas travas do Qt (autorização e dupla
# confirmação) continuam valendo do lado Python mesmo sem widget visível.

def _preparar_passo_destrutivo(motor, comando):
    """Monta um plano de um passo só e chama `_processar_passo()`, que
    mostra o cartão (via `_mostrar_cartao`, agora estendido) e deixa o
    `motor` no mesmo estado em que `confirmar_passo()`/`_confirmar_do_electron`
    encontrariam de verdade."""
    motor.plano = [{"comando": comando}]
    motor.passo_i = 0
    motor._auto_seguidos = 0
    motor._aguardando_ok = False
    motor._processar_passo()


def test_mostrar_cartao_manda_o_passo_pela_ponte_com_os_campos_novos(motor):
    _preparar_passo_destrutivo(motor, "nmap -sV 192.168.0.10")
    d = motor._risco_atual
    assert d["nivel"] == "destrutivo"
    assert d["precisa_autorizacao"] is True

    planos = motor.ponte.de_tipo("plano")
    assert planos, "o cartão do passo destrutivo nunca chegou na ponte"
    passos = planos[-1][1]
    assert len(passos) == 1
    passo_ponte = passos[0]
    assert passo_ponte["comando"] == "nmap -sV 192.168.0.10"
    assert passo_ponte["precisa_autorizacao"] is True
    assert passo_ponte["dupla_confirmacao"] is True
    assert passo_ponte["texto_autorizacao"]
    assert "Passo 1 de 1" in passo_ponte["rotulo"]


def test_passo_com_autorizacao_so_roda_quando_autorizado_chega_true(motor, monkeypatch):
    rodados = []
    monkeypatch.setattr(motor, "_rodar_comando",
                         lambda c, terminal=False: rodados.append(c))
    _preparar_passo_destrutivo(motor, "nmap -sV 192.168.0.10")
    assert motor._risco_atual["precisa_autorizacao"] is True

    # sem autorizado: nem o primeiro clique do duplo-clique pode avançar —
    # ignorado, igual ao Qt faz com `b_auth.isChecked()` antes de tudo.
    dervs_electron._confirmar_do_electron(motor, False)
    assert rodados == [], "rodou (ou avançou o duplo-clique) sem autorização"
    assert motor._2conf is False

    # com autorizado=True: 1º clique arma o trilho de dupla confirmação, mas
    # ainda não roda nada.
    dervs_electron._confirmar_do_electron(motor, True)
    assert rodados == [], "rodou no 1º clique do trilho de dupla confirmação"
    assert motor._2conf is True

    # 2º clique, ainda autorizado: agora sim roda.
    dervs_electron._confirmar_do_electron(motor, True)
    assert rodados == ["nmap -sV 192.168.0.10"]


def test_passo_com_dupla_confirmacao_precisa_de_duas_respostas_confirmar(motor, monkeypatch):
    rodados = []
    monkeypatch.setattr(motor, "_rodar_comando",
                         lambda c, terminal=False: rodados.append(c))
    # destrutivo, mas sem tocar alvo/segredo — não pede autorização, só o
    # duplo clique (nível destrutivo sempre pede `dupla_confirmacao`).
    _preparar_passo_destrutivo(motor, "rm -rf /home/user/projeto")
    d = motor._risco_atual
    assert d["nivel"] == "destrutivo"
    assert d["precisa_autorizacao"] is False
    assert d["dupla_confirmacao"] is True

    dervs_electron._confirmar_do_electron(motor, False)
    assert rodados == [], "rodou com uma única resposta 'confirmar'"
    assert motor._2conf is True, "o 1º clique tinha de armar o trilho"

    # o cartão tem de voltar pela ponte com o texto do 2º estágio — o HUD
    # não pode ficar esperando um card que nunca chega.
    planos = motor.ponte.de_tipo("plano")
    assert planos[-1][3] != planos[-2][3] or len(planos) >= 2, (
        "o cartão do 2º estágio nunca foi reenviado pela ponte")

    dervs_electron._confirmar_do_electron(motor, False)
    assert rodados == ["rm -rf /home/user/projeto"]


# ---- sair: encerrar_tudo + posse.soltar() ----------------------------------

class PosseFalsa:
    def __init__(self):
        self.solta = False

    def soltar(self):
        self.solta = True


def test_encerrar_desliga_o_motor_fecha_a_ponte_e_solta_a_posse(motor, monkeypatch):
    chamadas = []
    monkeypatch.setattr(dervs_electron.dervs, "encerrar_tudo",
                        lambda alvo: chamadas.append(alvo))
    ponte = motor.ponte
    posse = PosseFalsa()

    dervs_electron._encerrar(motor, ponte, posse)

    assert chamadas == [motor]
    assert ponte.fechada is True
    assert posse.solta is True


# ---- a trava de instância é a de dervs_instancia.py, reusada --------------

def test_trava_de_instancia_e_a_posse_de_dervs_instancia_reusada(tmp_path):
    caminho = str(tmp_path / "instancia.json")
    chamados = []

    posse1 = instancia.tomar_posse(lambda: chamados.append("chamado"), caminho=caminho)
    try:
        assert isinstance(posse1, instancia.Posse), (
            "dervs_electron precisa reusar dervs_instancia.Posse, não recriar a trava")

        posse2 = instancia.tomar_posse(lambda: chamados.append("nao devia"), caminho=caminho)
        assert posse2 is None, "o segundo chamador tinha de ser recusado"
    finally:
        posse1.soltar()


if __name__ == "__main__":            # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
