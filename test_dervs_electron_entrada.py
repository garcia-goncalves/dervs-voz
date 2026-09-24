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

    def enviar_plano(self, passos, nivel, pergunta, cartao_id=None):
        self.chamadas.append(("plano", passos, nivel, pergunta, cartao_id))

    def enviar_mostrar(self):
        self.chamadas.append(("mostrar",))

    def enviar_microfone(self, ligado):
        self.chamadas.append(("microfone", ligado))

    def enviar_reuniao(self, restante_s):
        self.chamadas.append(("reuniao", restante_s))

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


# ---- identidade do cartão: a correção de concorrência (achado de segurança) -
#
# No Qt, esconder a barra do cartão era síncrono — widget escondido não
# recebe clique, então duplo-clique rápido nunca disparava duas respostas
# para o mesmo cartão. No Electron, "sumir o cartão anterior" é uma mensagem
# assíncrona que pode ainda não ter chegado quando o próximo clique sai. Os
# testes abaixo provam os dois cenários reproduzidos pelo revisor que o
# `cartao_id` fecha: resposta atrasada/duplicada do MESMO cartão, e resposta
# de um cartão JÁ SUPERADO por um cartão novo.

def test_ao_plano_ignora_segunda_resposta_atrasada_ao_mesmo_cartao(motor, monkeypatch):
    chamadas = []
    monkeypatch.setattr(motor, "confirmar_passo", lambda: chamadas.append("confirmar_passo"))
    cartao_id = motor._novo_cartao_id()
    ao_plano = dervs_electron._construir_ao_plano(motor)

    # 1ª mensagem: aplicada.
    ao_plano("confirmar", False, cartao_id)
    assert chamadas == ["confirmar_passo"]

    # 2ª mensagem: a mesma resposta original, que só chega depois (o duplo
    # clique cujas duas mensagens saem antes do cartão sumir da tela) — o
    # `_cartao_pendente` já foi zerado ao consumir a 1ª, então esta é
    # ignorada em silêncio, sem rodar nada de novo.
    ao_plano("confirmar", False, cartao_id)
    assert chamadas == ["confirmar_passo"], (
        "a 2ª resposta ao mesmo cartão rodou de novo — o bug de segurança voltou")


def test_ao_plano_ignora_resposta_de_cartao_ja_superado_por_um_novo(motor, monkeypatch):
    chamadas = []
    monkeypatch.setattr(motor, "confirmar_passo", lambda: chamadas.append("confirmar_passo"))
    id_antigo = motor._novo_cartao_id()
    id_novo = motor._novo_cartao_id()   # um cartão novo já foi mandado por cima
    ao_plano = dervs_electron._construir_ao_plano(motor)

    ao_plano("confirmar", False, id_antigo)
    assert chamadas == [], "resposta de um cartão anterior, já superado, não podia rodar nada"

    ao_plano("confirmar", False, id_novo)
    assert chamadas == ["confirmar_passo"], "a resposta do cartão atual tinha de rodar"


def test_ao_plano_ignora_resposta_sem_cartao_pendente(motor, monkeypatch):
    # nenhum cartão foi enviado ainda (`_cartao_pendente` é None) — qualquer
    # resposta que chegue é desatualizada por definição.
    chamadas = []
    monkeypatch.setattr(motor, "confirmar_passo", lambda: chamadas.append("confirmar_passo"))
    ao_plano = dervs_electron._construir_ao_plano(motor)
    ao_plano("confirmar", False, None)
    assert chamadas == []


def test_confirmar_plano_gera_cartao_id_novo_a_cada_chamada(motor):
    motor.plano = [{"comando": "echo oi"}]
    motor._confirmar_plano()
    primeiro = motor._cartao_pendente
    assert primeiro is not None

    motor.plano = [{"comando": "echo de novo"}]
    motor._confirmar_plano()
    segundo = motor._cartao_pendente
    assert segundo is not None
    assert segundo != primeiro, "o segundo cartão tinha de ter um id diferente do primeiro"

    planos = motor.ponte.de_tipo("plano")
    assert planos[-2][4] == primeiro
    assert planos[-1][4] == segundo


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
    parar_sistema = threading.Event()

    dervs_electron._encerrar(motor, ponte, posse, parar_sistema)

    assert chamadas == [motor]
    assert ponte.fechada is True
    assert posse.solta is True
    assert parar_sistema.is_set(), "encerrar tem de parar a thread do painel de sistema"


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


# ---- microfone: o liga/desliga que voltou ao HUD ----------------------------

class _EscutaFalsa:
    pausado = False


def test_atualizar_avisa_o_hud_quando_o_microfone_abre_e_fecha(motor):
    motor.atualizar()
    assert motor.ponte.de_tipo("microfone")[-1] == ("microfone", False)
    motor.escuta = _EscutaFalsa()
    motor.atualizar()
    assert motor.ponte.de_tipo("microfone")[-1] == ("microfone", True)
    motor.escuta = None
    motor.atualizar()
    assert motor.ponte.de_tipo("microfone")[-1] == ("microfone", False)


def test_atualizar_nao_repete_microfone_que_nao_mudou(motor):
    motor.atualizar()
    motor.atualizar()
    motor.atualizar()
    assert len(motor.ponte.de_tipo("microfone")) == 1


def test_pedido_de_outra_thread_chega_ao_botao_na_thread_da_tela(motor):
    registro = []

    class BotaoFalso:
        def setChecked(self, valor):
            registro.append((valor, threading.current_thread()))

    motor.b_conversa = BotaoFalso()
    # `False` de propósito: o timer de abertura do motor (config
    # `escuta_ao_abrir` ligada) também chama `setChecked(True)` no botão.
    t = threading.Thread(target=motor.pedir_microfone, args=(False,))
    t.start()
    t.join()
    _app.processEvents()      # entrega o sinal enfileirado à thread da tela
    pedidos = [thread for valor, thread in registro if valor is False]
    assert pedidos == [threading.main_thread()], (
        "o botão foi tocado fora da thread da tela — derruba o app")


# ---- "sair" vindo do Electron roda em outra thread e precisa fechar o Qt ----

def test_ao_sair_de_outra_thread_fecha_o_qt_na_thread_da_tela():
    from PyQt6 import QtCore
    registro = []

    class AppFalso(QtCore.QObject):
        @QtCore.pyqtSlot()
        def quit(self):
            registro.append(threading.current_thread())

    alvo = AppFalso()
    ao_sair = dervs_electron._construir_ao_sair(alvo)
    t = threading.Thread(target=ao_sair)
    t.start()
    t.join()
    _app.processEvents()
    assert registro == [threading.main_thread()], (
        "quit() tem de rodar na thread da tela; chamado de outra thread o "
        "Qt ignora e o Python fica vivo, sem cara, com o microfone aberto")


# ---- modo reunião: microfone fechado por 1 hora, reabre sozinho -------------

class _BotaoFalso:
    """Faz o papel do `b_conversa` de verdade: `setChecked` dispara o mesmo
    `alternar_conversa` do Motor (que grava `escuta_ao_abrir`), sem abrir
    microfone nenhum."""

    def __init__(self, motor, ligado):
        self.motor = motor
        self.ligado = ligado

    def isChecked(self):
        return self.ligado

    def setChecked(self, valor):
        if valor != self.ligado:
            self.ligado = valor
            self.motor.alternar_conversa(valor)


@pytest.fixture
def reuniao(motor, monkeypatch):
    """Motor com botão falso, config falsa (guarda o que foi gravado) e
    relógio injetável — nada dorme de verdade."""
    gravados = []
    conf = {"escuta_ao_abrir": True}
    monkeypatch.setattr(dervs.cfg, "carregar", lambda: dict(conf))
    monkeypatch.setattr(dervs.cfg, "gravar",
                        lambda chave, valor: gravados.append((chave, valor)) or True)
    # `PopUp.alternar_conversa(True)` de verdade abriria o microfone: troca só
    # o miolo herdado por um que grava a escolha, como a versão real faz
    # primeiro. O `Motor.alternar_conversa` (que detecta o clique manual) fica
    # o de verdade.
    monkeypatch.setattr(
        dervs.PopUp, "alternar_conversa",
        lambda self, ligar: dervs.cfg.gravar("escuta_ao_abrir", bool(ligar)))
    motor.b_conversa = _BotaoFalso(motor, True)
    agora = [1000.0]
    motor._relogio = lambda: agora[0]
    motor.ponte.chamadas.clear()

    class Ctx:
        pass
    c = Ctx()
    c.motor, c.gravados, c.agora = motor, gravados, agora
    c.pedir = lambda ligar: (motor.pedir_reuniao(ligar), _app.processEvents())
    c.restantes = lambda: [x[1] for x in motor.ponte.de_tipo("reuniao")]
    return c


def test_reuniao_fecha_o_microfone_e_conta_1h(reuniao):
    reuniao.pedir(True)
    assert reuniao.motor.b_conversa.ligado is False
    assert reuniao.restantes() == [3600]


def test_reuniao_reabre_sozinha_ao_fim_da_hora(reuniao):
    reuniao.pedir(True)
    reuniao.agora[0] += 3599
    reuniao.motor.atualizar()
    assert reuniao.motor.b_conversa.ligado is False
    assert reuniao.restantes()[-1] == 1
    reuniao.agora[0] += 1
    reuniao.motor.atualizar()
    assert reuniao.motor.b_conversa.ligado is True
    assert reuniao.restantes()[-1] is None


def test_reuniao_manda_o_tempo_que_falta(reuniao):
    reuniao.pedir(True)
    reuniao.agora[0] += 48        # 59:12 no relógio do HUD
    reuniao.motor.atualizar()
    assert reuniao.restantes()[-1] == 3552


def test_reuniao_nao_repete_o_mesmo_segundo(reuniao):
    reuniao.pedir(True)
    reuniao.motor.atualizar()
    reuniao.motor.atualizar()
    assert reuniao.restantes() == [3600]


def test_clicar_de_novo_cancela_e_reabre_na_hora(reuniao):
    reuniao.pedir(True)
    reuniao.agora[0] += 10
    reuniao.pedir(False)
    assert reuniao.motor.b_conversa.ligado is True
    assert reuniao.restantes()[-1] is None
    reuniao.agora[0] += 5000      # o fim antigo não pode reabrir de novo
    reuniao.motor.atualizar()
    assert reuniao.restantes()[-1] is None


def test_reuniao_nao_grava_escuta_ao_abrir_false(reuniao):
    # o dono abre ouvindo (True): depois de a reunião fechar e reabrir o
    # microfone, a última escolha gravada tem de continuar sendo True
    reuniao.pedir(True)
    assert reuniao.gravados[-1] == ("escuta_ao_abrir", True)
    reuniao.agora[0] += 3600
    reuniao.motor.atualizar()
    assert reuniao.gravados[-1] == ("escuta_ao_abrir", True)


def test_dono_religa_o_microfone_no_meio_cancela_a_reuniao(reuniao):
    reuniao.pedir(True)
    reuniao.motor.b_conversa.setChecked(True)    # clique manual no botão Qt
    assert reuniao.restantes()[-1] is None
    reuniao.agora[0] += 4000
    reuniao.motor.atualizar()
    assert reuniao.restantes()[-1] is None       # não reabre/fecha nada depois


def test_dono_desliga_e_religa_manual_durante_a_reuniao_cancela(reuniao):
    reuniao.pedir(True)
    reuniao.motor.b_conversa.setChecked(True)
    reuniao.motor.b_conversa.setChecked(False)   # desliga manualmente de novo
    reuniao.agora[0] += 4000
    reuniao.motor.atualizar()
    assert reuniao.motor.b_conversa.ligado is False   # a reunião não o reabre


def test_reuniao_com_microfone_ja_desligado_nao_reabre_no_fim(reuniao):
    reuniao.motor.b_conversa.ligado = False
    reuniao.pedir(True)
    reuniao.agora[0] += 3600
    reuniao.motor.atualizar()
    assert reuniao.motor.b_conversa.ligado is False


def test_cancelar_sem_reuniao_ativa_nao_faz_nada(reuniao):
    reuniao.pedir(False)
    assert reuniao.restantes() == []
    assert reuniao.motor.b_conversa.ligado is True


def test_pedido_de_reuniao_de_outra_thread_chega_na_thread_da_tela(reuniao):
    registro = []
    reuniao.motor._reuniao_na_tela = lambda ligar: registro.append(
        (ligar, threading.current_thread()))
    # o sinal já estava ligado ao método original: religa ao substituto
    reuniao.motor._pedido_reuniao.disconnect()
    reuniao.motor._pedido_reuniao.connect(reuniao.motor._reuniao_na_tela)
    t = threading.Thread(target=reuniao.motor.pedir_reuniao, args=(True,))
    t.start()
    t.join()
    _app.processEvents()
    assert registro == [(True, threading.main_thread())]
