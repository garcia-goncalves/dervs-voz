#!/usr/bin/env python3
"""Testes dos lembretes por voz.

Regra que manda aqui: NUNCA chutar a hora. Metade dos testes é de frase que
tem de ser recusada. Nenhum teste toca o %APPDATA% real: a Agenda recebe o
caminho (tmp_path) e o relógio.
"""
import json
from datetime import datetime, timedelta

import pytest

import dervs_atalhos as at
import dervs_lembretes as lb

# Quarta-feira, 23/09/2026, 14:00:00
AGORA = datetime(2026, 9, 23, 14, 0, 0)


def quando(fala, agora=AGORA):
    r = lb.interpretar(fala, agora)
    return r[0] if r else None


def texto(fala, agora=AGORA):
    r = lb.interpretar(fala, agora)
    return r[1] if r else None


# ---- duração ----
@pytest.mark.parametrize("fala,delta", [
    ("me lembra em 10 minutos de ligar para o cliente", timedelta(minutes=10)),
    ("me lembra daqui a 5 minutos de tomar água", timedelta(minutes=5)),
    ("daqui a 2 horas me avisa da reunião", timedelta(hours=2)),
    ("me lembra em uma hora de ligar", timedelta(hours=1)),
    ("me lembra em duas horas de ligar", timedelta(hours=2)),
    ("me lembra em meia hora de ligar", timedelta(minutes=30)),
    ("me lembra em uma hora e meia de sair", timedelta(minutes=90)),
    ("me lembra em 30 segundos de desligar o forno", timedelta(seconds=30)),
    ("me lembra em vinte minutos de ligar", timedelta(minutes=20)),
    ("me lembra em vinte e cinco minutos de ligar", timedelta(minutes=25)),
    ("me lembra em quinze minutos de ligar", timedelta(minutes=15)),
    ("me lembra em um minuto de ligar", timedelta(minutes=1)),
    ("me lembra dentro de 3 horas de ligar", timedelta(hours=3)),
    ("me lembra em 2 dias de pagar a conta", timedelta(days=2)),
    ("Me lembra, em 10 minutos, de ligar!", timedelta(minutes=10)),
])
def test_duracao(fala, delta):
    assert quando(fala) == AGORA + delta


# ---- relógio ----
@pytest.mark.parametrize("fala,esperado", [
    ("me lembra às 15h30 de tomar o remédio", datetime(2026, 9, 23, 15, 30)),
    ("me lembra às 15:30 de tomar o remédio", datetime(2026, 9, 23, 15, 30)),
    ("me lembra às 15h de ligar", datetime(2026, 9, 23, 15, 0)),
    ("me lembra às 15 horas de ligar", datetime(2026, 9, 23, 15, 0)),
    ("me lembra às 9 de ligar", datetime(2026, 9, 24, 9, 0)),          # já passou: amanhã
    ("me lembra às 9 da noite de ligar", datetime(2026, 9, 23, 21, 0)),
    ("me lembra às nove da noite de ligar", datetime(2026, 9, 23, 21, 0)),
    ("me lembra às 3 da tarde de ligar", datetime(2026, 9, 23, 15, 0)),
    ("me lembra às 9 da manhã de ligar", datetime(2026, 9, 24, 9, 0)),
    ("me lembra às 9 e meia da noite de ligar", datetime(2026, 9, 23, 21, 30)),
    ("me lembra às 9h15 da noite de ligar", datetime(2026, 9, 23, 21, 15)),
    ("amanhã às 9 me lembra de ligar", datetime(2026, 9, 24, 9, 0)),
    ("me lembra amanhã às 9h de ligar", datetime(2026, 9, 24, 9, 0)),
    ("me lembra amanhã de manhã às 8 de ligar", datetime(2026, 9, 24, 8, 0)),
    ("me lembra ao meio-dia de almoçar", datetime(2026, 9, 24, 12, 0)),  # 14h: já passou
    ("me lembra amanhã ao meio-dia de almoçar", datetime(2026, 9, 24, 12, 0)),
    ("me lembra à meia-noite de dormir", datetime(2026, 9, 24, 0, 0)),
    ("me lembra hoje às 18h de sair", datetime(2026, 9, 23, 18, 0)),
    ("me lembra às 14h30 de sair", datetime(2026, 9, 23, 14, 30)),
])
def test_relogio(fala, esperado):
    assert quando(fala) == esperado


def test_meio_dia_antes_do_meio_dia_e_hoje():
    assert quando("me lembra ao meio-dia de almoçar",
                  datetime(2026, 9, 23, 9, 0)) == datetime(2026, 9, 23, 12, 0)


def test_hora_igual_a_agora_vai_para_amanha():
    assert quando("me lembra às 14h de ligar") == datetime(2026, 9, 24, 14, 0)


# ---- texto do lembrete ----
@pytest.mark.parametrize("fala,esperado", [
    ("me lembra em 10 minutos de ligar para o cliente", "ligar para o cliente"),
    ("me lembra às 15h30 de tomar o remédio", "tomar o remédio"),
    ("daqui a 2 horas me avisa da reunião", "reunião"),
    ("me lembra de ligar para o cliente em 10 minutos", "ligar para o cliente"),
    ("me lembra que eu tenho reunião às 15h", "eu tenho reunião"),
    ("me lembra em 5 minutos para buscar as crianças, por favor", "buscar as crianças"),
    ("me lembra amanhã às 9 de pagar o boleto", "pagar o boleto"),
])
def test_texto(fala, esperado):
    assert texto(fala) == esperado


def test_texto_cortado_em_200():
    longo = "x" * 500
    assert len(texto(f"me lembra em 5 minutos de {longo}")) == lb.MAX_TEXTO


def test_texto_e_so_dado_nao_e_interpretado():
    # "às 3" dentro do texto do lembrete confunde: duas horas => recusa
    assert lb.interpretar("me lembra em 5 minutos de abrir o chrome às 3 horas", AGORA) is None


def test_sem_texto_devolve_vazio():
    assert texto("me lembra em 10 minutos") == ""


# ---- NUNCA chutar ----
@pytest.mark.parametrize("fala", [
    "me lembra de ligar para o cliente",              # sem hora
    "me lembra daqui a pouco de ligar",               # vago
    "me lembra depois de ligar",
    "me lembra amanhã de ligar",                      # dia sem hora
    "me lembra às 25h de ligar",                      # hora impossível
    "me lembra às 9h75 de ligar",                     # minuto impossível
    "me lembra em zero minutos de ligar",
    "me lembra em 8 dias de ligar",                   # além de 7 dias
    "me lembra em 200 horas de ligar",
    "me lembra hoje às 8 de ligar",                   # hoje, e já passou (14h)
    "me lembra em 10 minutos e às 15h de ligar",      # duas horas
    "me lembra de pegar as 2 caixas",                 # "as 2" não é hora
    "me lembra às 9 caixas de ligar",
    "que horas são",                                  # nem é lembrete
    "abre o chrome",
    "me lembra do meu nome",
])
def test_recusa_sem_chutar(fala):
    assert lb.interpretar(fala, AGORA) is None


def test_me_avisa_sem_hora_nao_e_comigo():
    assert lb.eh_pedido("me avisa quando chegar") is False
    assert lb.interpretar("me avisa quando chegar", AGORA) is None


# ---- descrição falada ----
@pytest.mark.parametrize("delta,esperado", [
    (timedelta(seconds=30), "em 30 segundos"),
    (timedelta(seconds=1), "em 1 segundo"),
    (timedelta(minutes=1), "em 1 minuto"),
    (timedelta(minutes=10), "em 10 minutos"),
    (timedelta(hours=1, minutes=30), "às 15h30"),
    (timedelta(days=1, hours=-5), "amanhã às 9h"),
    (timedelta(days=3, hours=-5), "dia 26 às 9h"),
])
def test_descrever(delta, esperado):
    assert lb.descrever(AGORA + delta, AGORA) == esperado


def test_descrever_meio_dia_e_meia_noite():
    assert lb.descrever(datetime(2026, 9, 24, 12, 0), AGORA) == "amanhã ao meio-dia"
    assert lb.descrever(datetime(2026, 9, 24, 0, 0), AGORA) == "amanhã à meia-noite"


# ---- persistência ----
@pytest.fixture
def agenda(tmp_path):
    relogio = {"t": AGORA}
    a = lb.Agenda(str(tmp_path / "lembretes.json"), lambda: relogio["t"])
    a.relogio = relogio
    return a


def test_agenda_arquivo_ausente(agenda):
    assert agenda.listar() == []
    assert agenda.retirar_vencido() is None
    assert agenda.cancelar_todos() == 0


def test_agenda_grava_e_le(agenda):
    assert agenda.adicionar(AGORA + timedelta(minutes=5), "ligar")
    assert agenda.adicionar(AGORA + timedelta(minutes=1), "água")
    itens = agenda.listar()
    assert [i["texto"] for i in itens] == ["água", "ligar"]   # ordenado por hora
    dados = json.load(open(agenda.caminho, encoding="utf-8"))
    assert len(dados["lembretes"]) == 2


@pytest.mark.parametrize("conteudo", [
    "isto não é json", "", "[1, 2, 3]", '{"lembretes": "torto"}', "null",
    '{"lembretes": [{"quando": "ontem"}, {"texto": "sem hora"}, 7]}',
])
def test_agenda_tolera_arquivo_torto(agenda, conteudo):
    with open(agenda.caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    assert agenda.listar() == []
    assert agenda.adicionar(AGORA + timedelta(minutes=5), "ok")   # e se recupera
    assert len(agenda.listar()) == 1


def test_agenda_entrada_torta_nao_derruba_as_boas(agenda):
    dados = {"lembretes": [{"quando": "lixo"},
                           {"quando": "2026-09-23T15:00:00", "texto": "boa"}]}
    with open(agenda.caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    assert [i["texto"] for i in agenda.listar()] == ["boa"]


def test_agenda_gravacao_atomica_nao_deixa_temporario(agenda, tmp_path):
    agenda.adicionar(AGORA + timedelta(minutes=5), "x")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["lembretes.json"]


def test_agenda_vencimento_com_relogio(agenda):
    agenda.adicionar(AGORA + timedelta(minutes=5), "ligar")
    assert agenda.retirar_vencido() is None
    agenda.relogio["t"] = AGORA + timedelta(minutes=5)
    item = agenda.retirar_vencido()
    assert item["texto"] == "ligar"
    assert agenda.retirar_vencido() is None        # não repete
    assert agenda.listar() == []                   # e saiu do arquivo


def test_agenda_vencidos_saem_um_por_vez_do_mais_antigo(agenda):
    agenda.adicionar(AGORA + timedelta(minutes=2), "segundo")
    agenda.adicionar(AGORA + timedelta(minutes=1), "primeiro")
    agenda.relogio["t"] = AGORA + timedelta(hours=1)
    assert agenda.retirar_vencido()["texto"] == "primeiro"
    assert agenda.retirar_vencido()["texto"] == "segundo"
    assert agenda.retirar_vencido() is None


def test_agenda_limite(agenda):
    for i in range(lb.MAX_LEMBRETES):
        assert agenda.adicionar(AGORA + timedelta(minutes=i + 1), str(i))
    assert agenda.adicionar(AGORA + timedelta(hours=5), "a mais") is False
    assert len(agenda.listar()) == lb.MAX_LEMBRETES


def test_aviso_de_vencido_com_app_fechado():
    item = {"quando": datetime(2026, 9, 23, 13, 0), "texto": "tomar o remédio"}
    f = lb.frase_de_aviso(item, AGORA)
    assert f == "Você tinha um lembrete às 13h: tomar o remédio."


def test_aviso_de_vencido_de_ontem():
    item = {"quando": datetime(2026, 9, 22, 15, 30), "texto": "ligar"}
    assert lb.frase_de_aviso(item, AGORA) == "Você tinha um lembrete ontem às 15h30: ligar."


def test_aviso_no_horario():
    item = {"quando": AGORA - timedelta(seconds=1), "texto": "ligar"}
    assert lb.frase_de_aviso(item, AGORA) == "Lembrete: ligar."


# ---- atalho ponta a ponta ----
class VozFalsa:
    def __init__(self):
        self.ditas = []

    def falar(self, t):
        self.ditas.append(t)


def dizer(fala, agenda):
    """Faz o que o app faz: pede a ficha e fala a resposta."""
    ficha = at.tentar(fala, AGORA, agenda)
    assert ficha is not None, fala
    assert ficha["modo"] == "conversar"        # nunca 'planejar': nada é executado
    assert "passos" not in ficha
    voz = VozFalsa()
    voz.falar(ficha["fala"])
    return voz.ditas[0]


def test_atalho_cria_e_confirma(agenda):
    r = dizer("me lembra às 15h30 de tomar o remédio", agenda)
    assert r == "Certo, te aviso às 15h30: tomar o remédio."
    assert agenda.listar()[0]["quando"] == datetime(2026, 9, 23, 15, 30)


def test_atalho_cria_em_minutos(agenda):
    r = dizer("me lembra em 10 minutos de ligar para o cliente", agenda)
    assert r == "Certo, te aviso em 10 minutos: ligar para o cliente."


def test_atalho_recusa_hora_nao_entendida_e_nao_grava(agenda):
    r = dizer("me lembra daqui a pouco de ligar", agenda)
    assert r.startswith("Não entendi a hora. Diga por exemplo: me lembra em 10 minutos de")
    assert agenda.listar() == []


def test_atalho_lista(agenda):
    assert dizer("quais são meus lembretes", agenda) == "Você não tem lembretes."
    agenda.adicionar(datetime(2026, 9, 23, 15, 30), "tomar o remédio")
    agenda.adicionar(datetime(2026, 9, 24, 9, 0), "ligar para o cliente")
    r = dizer("quais são os meus lembretes?", agenda)
    assert r == ("Você tem 2 lembretes: às 15h30, tomar o remédio; "
                 "e amanhã às 9h, ligar para o cliente.")


def test_atalho_cancela_todos_e_diz_quantos(agenda):
    agenda.adicionar(AGORA + timedelta(minutes=5), "a")
    agenda.adicionar(AGORA + timedelta(minutes=6), "b")
    assert dizer("cancela os lembretes", agenda) == "Apaguei os 2 lembretes."
    assert agenda.listar() == []
    assert dizer("apaga todos os meus lembretes", agenda) == "Você não tinha lembretes para apagar."


def test_atalho_texto_com_comando_nao_executa(agenda):
    # "abrir o chrome" está no TEXTO do lembrete: só é falado, nunca abre nada
    ficha = at.tentar("me lembra em 5 minutos de abrir o chrome", AGORA, agenda)
    assert ficha["modo"] == "conversar" and "passos" not in ficha
    assert agenda.listar()[0]["texto"] == "abrir o chrome"


def test_atalho_sem_hora_com_comando_no_texto_nao_abre_app(agenda):
    ficha = at.tentar("me lembra de abrir o chrome", AGORA, agenda)
    assert ficha["modo"] == "conversar" and "passos" not in ficha


def test_atalho_sem_agenda_deixa_para_o_cerebro():
    # sem agenda injetada, lembrete NÃO grava em lugar nenhum (nem no APPDATA)
    assert at.tentar("me lembra em 5 minutos de abrir o chrome", AGORA) is None
    assert at.tentar("quais são meus lembretes", AGORA) is None


def test_atalho_me_avisa_solto_segue_para_o_cerebro(agenda):
    assert at.tentar("me avisa quando o site cair", AGORA, agenda) is None


def test_atalhos_antigos_continuam(agenda):
    assert at.tentar("que horas são", AGORA, agenda)["fala"] == "São duas da tarde."
    assert at.tentar("que dia é hoje", AGORA, agenda)["fala"].startswith("Hoje é quarta-feira")


# ---- o toque do relógio da PopUp (sem abrir janela: `self` de mentira) ----
class _PopUpFalsa:
    def __init__(self, agenda, falando=False):
        self.agenda = agenda
        self.voz = VozFalsa()
        self.voz.falando = lambda: falando
        self.hud = []

    def _diz(self, papel, texto, cor=None):
        self.hud.append((papel, texto))


def _toque(falsa):
    import dervs
    dervs.PopUp._checar_lembretes(falsa)


def test_toque_avisa_em_voz_e_no_hud_e_nao_repete(agenda):
    agenda.adicionar(AGORA + timedelta(minutes=1), "ligar para o cliente")
    falsa = _PopUpFalsa(agenda)
    _toque(falsa)
    assert falsa.voz.ditas == [] and falsa.hud == []          # ainda não venceu
    agenda.relogio["t"] = AGORA + timedelta(minutes=1)
    _toque(falsa)
    assert falsa.voz.ditas == ["Lembrete: ligar para o cliente."]
    assert falsa.hud == [("dervs", "Lembrete: ligar para o cliente.")]
    _toque(falsa)
    assert len(falsa.voz.ditas) == 1                           # sem repetir


def test_toque_nao_interrompe_fala_em_curso(agenda):
    agenda.adicionar(AGORA, "ligar")
    falando = _PopUpFalsa(agenda, falando=True)
    _toque(falando)
    assert falando.voz.ditas == [] and len(agenda.listar()) == 1   # fica na fila
    livre = _PopUpFalsa(agenda, falando=False)
    _toque(livre)
    assert livre.voz.ditas == ["Lembrete: ligar."]


def test_toque_avisa_vencido_com_app_fechado(agenda):
    agenda.adicionar(datetime(2026, 9, 23, 13, 0), "tomar o remédio")
    falsa = _PopUpFalsa(agenda)
    _toque(falsa)
    assert falsa.voz.ditas == ["Você tinha um lembrete às 13h: tomar o remédio."]
