"""Chamada ESTRITA: o DERVS só acorda se o nome vier no começo da fala.

Origem: o dono pediu que ele "não ative do nada". O casador antigo aceitava o
nome em qualquer posição, então falar SOBRE o DERVS ("vou mostrar o dervs pra
ele") ligava o agente. No modo estrito só vale o nome no início, com no máximo
uma saudação ("ei", "ok", "oi"...) antes dele.
"""
import pytest

from dervs_listen import separar_chamada


@pytest.mark.parametrize("fala, resto", [
    ("DERVS, que horas são", "que horas são"),
    ("Dervs que horas são", "que horas são"),
    ("Ei DERVS toca uma música", "toca uma música"),
    ("OK DERVS abre o chrome", "abre o chrome"),
    ("ok, dervs, abre o chrome", "abre o chrome"),
    ("Hey DERVS faz isso", "faz isso"),
    ("oi dervs", ""),
    ("dervs", ""),
    ("Ei, DERVS!", ""),
])
def test_estrito_acorda_quando_chamam_no_comeco(fala, resto):
    tem, pedido = separar_chamada(fala, estrito=True)
    assert tem is True
    assert pedido == resto


@pytest.mark.parametrize("fala", [
    "ontem eu estava falando do dervs com o André",
    "o dervs não acordou hoje",
    "vou mostrar o dervs pra ele",
    "depois me lembra, dervs, de ligar",
    "eu acho que o ok dervs é legal",
    "meu Deus do céu",
    "ok google",
    "nervos à flor da pele",
    "",
])
def test_estrito_nao_acorda_quando_so_falam_sobre_ele(fala):
    tem, _ = separar_chamada(fala, estrito=True)
    assert tem is False


def test_estrito_devolve_a_fala_inteira_quando_nao_acorda():
    fala = "vou mostrar o dervs pra ele"
    assert separar_chamada(fala, estrito=True) == (False, fala)


def test_modo_antigo_continua_aceitando_o_nome_em_qualquer_lugar():
    # compatibilidade: quem desligar a chamada estrita volta ao comportamento de antes
    tem, resto = separar_chamada("depois me lembra, dervs, de ligar")
    assert tem is True
    assert resto == "depois me lembra de ligar"


def test_ok_colado_no_nome_nao_sobra_no_pedido_no_modo_antigo():
    assert separar_chamada("OK DERVS abre o chrome") == (True, "abre o chrome")


# ---- ligação com o porteiro e a configuração -------------------------------
def test_porteiro_novo_nasce_estrito(tmp_path):
    from dervs_porteiro import PorteiroLocal
    p = PorteiroLocal(transcritor=lambda wav: "vou mostrar o dervs pra ele")
    assert p.ouviu_o_nome("x.wav")[0] is False


def test_porteiro_estrito_acorda_com_chamada_no_comeco():
    from dervs_porteiro import PorteiroLocal
    p = PorteiroLocal(transcritor=lambda wav: "Ei DERVS, que horas são")
    assert p.ouviu_o_nome("x.wav")[0] is True


def test_porteiro_pode_voltar_ao_modo_antigo():
    from dervs_porteiro import PorteiroLocal
    p = PorteiroLocal(transcritor=lambda wav: "vou mostrar o dervs pra ele", estrito=False)
    assert p.ouviu_o_nome("x.wav")[0] is True


def test_criar_porteiro_le_a_chave_da_config():
    from dervs_porteiro import criar_porteiro
    assert criar_porteiro({}).estrito is True
    assert criar_porteiro({"chamada_estrita": False}).estrito is False


def test_config_chamada_estrita_padrao_e_validacao(monkeypatch, tmp_path):
    import dervs_config
    assert dervs_config.PADRAO["chamada_estrita"] is True
    conf = dict(dervs_config.PADRAO, chamada_estrita="false")   # texto não é booleano
    assert dervs_config._validar(conf)["chamada_estrita"] is True
    conf = dict(dervs_config.PADRAO, chamada_estrita=False)
    assert dervs_config._validar(conf)["chamada_estrita"] is False


@pytest.mark.parametrize("fala", [
    "♪ Dervs ♪ toca",           # o que o Whisper escreve quando ouve música
    "10 dervs abre o chrome",
    "2025: Dervs lança",
    "- dervs abre",             # legenda de TV/vídeo
])
def test_estrito_nao_acorda_com_simbolo_ou_numero_antes_do_nome(fala):
    assert separar_chamada(fala, estrito=True)[0] is False


def test_e_ai_sai_do_pedido():
    assert separar_chamada("E aí, DERVS, tudo bem?", estrito=True) == (True, "tudo bem?")


@pytest.mark.parametrize("fala, resto", [
    # "Ô DERVS" o Whisper escreve "O Dervs." (teste de voz de 15/10): vocativo, com pontuação logo após
    ("O Dervs. Como que você pode me ajudar?", "Como que você pode me ajudar?"),
    ("O Dervs, abre a calculadora", "abre a calculadora"),
])
def test_o_vocativo_com_pontuacao_acorda(fala, resto):
    assert separar_chamada(fala, estrito=True) == (True, resto)


def test_o_sem_pontuacao_continua_sendo_falar_sobre_ele():
    assert separar_chamada("o dervs não acordou hoje", estrito=True)[0] is False
    assert separar_chamada("o dervs é legal", estrito=True)[0] is False
