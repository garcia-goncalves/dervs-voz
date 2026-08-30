#!/usr/bin/env python3
"""Testes dos atalhos locais.

O que mais importa aqui NÃO é acertar a hora — é NÃO disparar em frase que o
cérebro deveria pensar. Um atalho que responde errado no lugar do cérebro é
pior que atalho nenhum. Por isso metade dos testes é de negativa."""
from datetime import datetime
import grimoire_atalhos as at


# ---- hora por extenso ----
def test_hora_meia_noite():
    assert at.hora_falada(datetime(2026, 8, 30, 0, 0)) == "É meia-noite."


def test_hora_meio_dia():
    assert at.hora_falada(datetime(2026, 8, 30, 12, 0)) == "É meio-dia."


def test_hora_uma_e_meia_da_tarde():
    assert at.hora_falada(datetime(2026, 8, 30, 13, 30)) == "É uma e meia da tarde."


def test_hora_tres_e_meia_da_tarde():
    assert at.hora_falada(datetime(2026, 8, 30, 15, 30)) == "São três e meia da tarde."


def test_hora_dez_em_ponto_da_manha():
    assert at.hora_falada(datetime(2026, 8, 30, 10, 0)) == "São dez da manhã."


def test_hora_minuto_doze_nao_desloca():
    # regressão do bug do "doze" que faltava na lista de números
    assert at.hora_falada(datetime(2026, 8, 30, 9, 12)) == "São nove e doze da manhã."


def test_hora_madrugada():
    assert at.hora_falada(datetime(2026, 8, 30, 2, 5)) == "São duas e cinco da madrugada."


def test_hora_noite_com_minutos():
    assert at.hora_falada(datetime(2026, 8, 30, 21, 45)) == "São nove e quarenta e cinco da noite."


# ---- data por extenso ----
def test_data():
    # 30/08/2026 é um domingo
    assert at.data_falada(datetime(2026, 8, 30)) == "Hoje é domingo, 30 de agosto."


# ---- reconhecimento de hora (POSITIVOS) ----
def test_pega_que_horas_sao():
    f = at.tentar("Que horas são?", agora=datetime(2026, 8, 30, 15, 30))
    assert f is not None and f["modo"] == "conversar"
    assert f["fala"] == "São três e meia da tarde."


def test_pega_me_diz_as_horas():
    assert at.tentar("me diz as horas", agora=datetime(2026, 8, 30, 12, 0)) is not None


def test_pega_que_hora_e():
    assert at.tentar("que hora é agora", agora=datetime(2026, 8, 30, 12, 0)) is not None


# ---- reconhecimento de data (POSITIVOS) ----
def test_pega_que_dia_e_hoje():
    f = at.tentar("que dia é hoje", agora=datetime(2026, 8, 30))
    assert f is not None and "domingo" in f["fala"]


def test_pega_qual_a_data():
    assert at.tentar("qual a data de hoje", agora=datetime(2026, 8, 30)) is not None


# ---- abrir apps (POSITIVOS) ----
def test_abre_firefox():
    f = at.tentar("abre o firefox")
    assert f is not None and f["modo"] == "planejar"
    assert f["passos"][0]["comando"] == "firefox"
    assert f["passos"][0]["risco"] == "reversivel"


def test_abre_navegador():
    f = at.tentar("pode abrir o navegador pra mim")
    assert f is not None and f["passos"][0]["comando"] == "firefox"


def test_abre_calculadora():
    f = at.tentar("abrir a calculadora")
    assert f is not None and f["passos"][0]["comando"] == "kcalc"


def test_abre_terminal():
    f = at.tentar("abre o terminal")
    assert f is not None and f["passos"][0]["comando"] == "konsole"


# ---- NEGATIVOS: tem que cair no cérebro (devolver None) ----
def test_nao_pega_pergunta_de_verdade():
    assert at.tentar("me explica o que é kerberoast") is None


def test_nao_pega_abrir_arquivo():
    # "abre o relatório" não é app: o cérebro decide
    assert at.tentar("abre o relatório de ontem") is None


def test_nao_pega_abrir_site():
    assert at.tentar("abre o site do banco") is None


def test_nao_pega_abrir_porta():
    assert at.tentar("abre a porta 8080 no firewall") is None


def test_nao_pega_conversa():
    assert at.tentar("bom dia, tudo bem?") is None


def test_nao_pega_horario_dentro_de_frase_maior():
    # fala sobre agendar algo: NÃO é pedido de hora
    assert at.tentar("marca uma reunião para as três horas amanhã") is None


def test_vazio_devolve_none():
    assert at.tentar("") is None
    assert at.tentar("   ") is None


def test_norm_tira_acento_e_pontuacao():
    assert at._norm("Que HORAS são?!") == "que horas sao"


# ---- confirmação por voz (ok / não / correção) ----
def test_confirma_sim():
    for f in ["ok", "OK!", "pode", "faz", "isso", "confirma", "beleza", "manda ver",
              "pode sim", "isso mesmo", "vai la"]:
        assert at.eh_confirmacao(f) == "sim", f

def test_confirma_nao():
    for f in ["não", "nao", "cancela", "deixa", "esquece", "para", "melhor não",
              "cancela isso"]:
        assert at.eh_confirmacao(f) == "nao", f

def test_confirma_correcao_vira_none():
    # frase longa NÃO é um simples ok: é correção → cérebro re-planeja
    assert at.eh_confirmacao("não, faz no Firefox em vez do Chrome") is None
    assert at.eh_confirmacao("na verdade abre o chromium") is None
    assert at.eh_confirmacao("") is None
