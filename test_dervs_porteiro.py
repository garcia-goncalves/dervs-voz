#!/usr/bin/env python3
"""Testes do porteiro — a peça que decide, na máquina, se a fala foi com o DERVS.

O teste mais importante deste arquivo é `test_porteiro_nao_manda_audio_para_a_nuvem`:
ele é a trava que impede alguém, um dia, de reinverter a ordem e voltar a mandar
o áudio do dia inteiro do dono para um servidor de terceiro.

Rodar: python -m pytest test_dervs_porteiro.py -q
"""
import json

import pytest

import dervs_porteiro as porteiro_mod
import dervs_stt_daemon as daemon
from dervs_porteiro import COLA_PORTEIRO, PorteiroLocal, criar_porteiro


def _porteiro_que_ouve(texto):
    """Um porteiro com dublê: não carrega modelo nenhum, devolve o texto dado."""
    return PorteiroLocal(transcritor=lambda _caminho: texto)


# ---------------------------------------------------------------- o porteiro

def test_acorda_quando_o_nome_foi_dito():
    acordou, texto = _porteiro_que_ouve("dervs que horas sao").ouviu_o_nome("x.wav")
    assert acordou is True
    assert texto == "dervs que horas sao"


def test_acorda_com_ok_na_frente():
    acordou, _ = _porteiro_que_ouve("ok dervs abre o chrome").ouviu_o_nome("x.wav")
    assert acordou is True


def test_acorda_com_o_nome_no_fim():
    acordou, _ = _porteiro_que_ouve("que horas sao dervs").ouviu_o_nome("x.wav")
    assert acordou is True


def test_nao_acorda_sem_o_nome():
    acordou, _ = _porteiro_que_ouve("que horas sao").ouviu_o_nome("x.wav")
    assert acordou is False


def test_nao_acorda_com_deus():
    """A armadilha que a medição revelou: sem o aviso de vocabulário, o Whisper
    trocava 'Dervs' por 'Deus'. O casador difuso não pode aceitar 'Deus', senão
    o DERVS acorda toda vez que alguém se assusta."""
    for frase in ("meu deus que susto voce me deu",
                  "deus me livre disso ai",
                  "ok deus abriu chrome"):
        acordou, _ = _porteiro_que_ouve(frase).ouviu_o_nome("x.wav")
        assert acordou is False, "acordou à toa com: %r" % frase


def test_audio_ruim_nao_derruba_a_escuta():
    """Erro ao ouvir tem de virar 'não era comigo', nunca exceção — senão um
    arquivo corrompido cala o DERVS para o resto do dia."""
    def explode(_caminho):
        raise OSError("arquivo corrompido")

    acordou, texto = PorteiroLocal(transcritor=explode).ouviu_o_nome("x.wav")
    assert acordou is False
    assert texto == ""


def test_o_aviso_de_vocabulario_menciona_o_nome():
    """É o aviso que faz o porteiro funcionar: sem a palavra dentro dele, o
    modelo troca 'Dervs' por 'Deus' (medido em 01/09/2026, 10/14 contra 14/14)."""
    assert "dervs" in COLA_PORTEIRO.lower()


# ------------------------------------------------------- a escolha do porteiro

def test_porteiro_padrao_e_o_local():
    assert isinstance(criar_porteiro({}), PorteiroLocal)
    assert isinstance(criar_porteiro(None), PorteiroLocal)


def test_porteiro_local_usa_o_modelo_medido():
    assert criar_porteiro({}).tamanho == "tiny"


def test_porcupine_ainda_nao_existe_e_diz_o_que_fazer():
    with pytest.raises(NotImplementedError) as erro:
        criar_porteiro({"porteiro": "porcupine"})
    assert "picovoice" in str(erro.value).lower()


# ------------------------------------- A TRAVA: a ordem nuvem-depois-do-portão

class _EspiaoDaNuvem:
    """Conta quantas vezes a nuvem foi chamada, e com quê."""
    def __init__(self):
        self.chamadas = []

    def __call__(self, caminho):
        self.chamadas.append(caminho)
        return "texto preciso da nuvem"


def test_porteiro_nao_manda_audio_para_a_nuvem():
    """A trava central do projeto.

    Com o verbo PORTEIRO, a função que fala com a nuvem NÃO pode ser chamada —
    nem quando o porteiro acorda, nem quando não acorda. É esta ordem que faz o
    DERVS custar ~US$ 5/mês em vez de ~US$ 43/mês, e que impede a conversa da
    casa do dono de sair da máquina dele.
    """
    nuvem = _EspiaoDaNuvem()

    # caso 1: não era com ele
    resposta = daemon.atender("PORTEIRO fala.wav", _porteiro_que_ouve("que horas sao"), nuvem)
    assert json.loads(resposta.split(" ", 1)[1])["acordou"] is False
    assert nuvem.chamadas == [], "mandou áudio para a nuvem sem o porteiro abrir"

    # caso 2: era com ele — mesmo assim o verbo PORTEIRO não chama a nuvem;
    # quem decide chamar é o app, no passo seguinte
    resposta = daemon.atender("PORTEIRO fala.wav", _porteiro_que_ouve("dervs abre o chrome"), nuvem)
    assert json.loads(resposta.split(" ", 1)[1])["acordou"] is True
    assert nuvem.chamadas == [], "o verbo PORTEIRO não pode falar com a nuvem"


def test_transcrever_chama_a_nuvem():
    """O outro lado da trava: depois que o portão abre, a nuvem TEM de ser usada
    — é dela que vem a precisão que o dono pediu."""
    nuvem = _EspiaoDaNuvem()
    resposta = daemon.atender("TRANSCREVER fala.wav", _porteiro_que_ouve(""), nuvem)
    assert nuvem.chamadas == ["fala.wav"]
    assert json.loads(resposta.split(" ", 1)[1]) == "texto preciso da nuvem"


def test_caminho_cru_continua_funcionando():
    """Forma antiga do protocolo (só o caminho, sem verbo) não pode quebrar —
    a gravação manual do botão Gravar/Parar ainda a usa."""
    nuvem = _EspiaoDaNuvem()
    resposta = daemon.atender("/tmp/dervs_rec.wav", _porteiro_que_ouve(""), nuvem)
    assert nuvem.chamadas == ["/tmp/dervs_rec.wav"]
    assert resposta.startswith("RESULT ")


def test_linha_vazia_nao_gera_resposta():
    nuvem = _EspiaoDaNuvem()
    assert daemon.atender("", _porteiro_que_ouve(""), nuvem) == ""
    assert daemon.atender("   \n", _porteiro_que_ouve(""), nuvem) == ""
    assert nuvem.chamadas == []


def test_erro_na_nuvem_vira_texto_vazio_e_nao_derruba():
    def explode(_caminho):
        raise RuntimeError("sem internet")

    resposta = daemon.atender("TRANSCREVER fala.wav", _porteiro_que_ouve(""), explode)
    assert json.loads(resposta.split(" ", 1)[1]) == ""


def test_resposta_do_porteiro_e_json_de_uma_linha():
    """O app lê a saída linha a linha: uma resposta com quebra de linha no meio
    embaralharia o protocolo."""
    resposta = daemon.atender(
        "PORTEIRO fala.wav", _porteiro_que_ouve("dervs\nabre o chrome"), _EspiaoDaNuvem())
    assert "\n" not in resposta
    assert resposta.startswith("PORTEIRO ")
    json.loads(resposta.split(" ", 1)[1])   # tem de ser JSON válido


# ------------------------------------------------- o modelo preciso configurado

def test_modelo_de_transcricao_e_o_novo():
    """gpt-transcribe (28/07/2026) é mais preciso E mais barato que o
    gpt-4o-transcribe. O dono pediu precisão em letra maiúscula.

    Aqui se testa a reserva do daemon. O valor EFETIVO vem de
    `dervs_config.PADRAO["stt_openai_modelo"]`, que precisa dizer o mesmo — há
    um teste disso em `test_dervs_config.py`.
    """
    import dervs_config
    assert daemon.STT_MODELO_PADRAO == "gpt-transcribe"
    assert dervs_config.PADRAO["stt_openai_modelo"] == "gpt-transcribe"


def test_porteiro_local_e_o_padrao_da_configuracao():
    """O porteiro local é o padrão de fábrica: quem instala o DERVS não precisa
    criar conta em lugar nenhum para ele já parar de mandar tudo para a nuvem."""
    import dervs_config
    assert dervs_config.PADRAO["porteiro"] == "local"
    # valor inventado no arquivo do dono cai no padrão em vez de derrubar o app
    conf = dict(dervs_config.PADRAO, porteiro="coisa inventada")
    assert dervs_config._validar(conf)["porteiro"] == "local"
