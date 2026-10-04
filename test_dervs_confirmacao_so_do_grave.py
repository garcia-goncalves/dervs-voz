"""O dono pediu (03/10/2026): "só pedirá confirmações quando for coisa grave e
perigosa; sempre dirá se entendeu e repete o que vai fazer".

Regra: plano sem passo destrutivo, sem alvo de rede, sem segredo e sem navegador
logado roda sozinho depois de o DERVS anunciar o que entendeu. O resto continua
pedindo o clique. `confirmar_plano: "sempre"` volta ao comportamento antigo."""
import pytest

import dervs

pede = dervs.plano_pede_confirmacao


def passo(comando, risco="reversivel", **extra):
    return {"descricao": "x", "comando": comando, "risco": risco, "toca_alvo": False, **extra}


@pytest.mark.parametrize("plano", [
    [passo("dir")],
    [passo("notepad", "muda_estado")],
    [passo("calc", "reversivel"), passo("explorer", "reversivel")],
    [{"tipo": "enriquecer", "dominio": "empresa.com.br", "risco": "muda_estado", "toca_alvo": False}],
])
def test_plano_inofensivo_roda_sem_pedir(plano):
    assert pede(plano, "grave") is False


@pytest.mark.parametrize("plano", [
    [passo("rm -rf C:/Users/x/Documents", "destrutivo")],
    [passo("del /s /q C:\\dados", "destrutivo")],
    [passo("dir"), passo("rm -rf x", "destrutivo")],
    [passo("nmap 10.0.0.5", "muda_estado", toca_alvo=True)],
    [passo("curl http://alvo.interno/x", "muda_estado", toca_alvo=True)],
    [{"tipo": "navegador", "objetivo": "apagar a caixa de entrada", "risco": "muda_estado", "toca_alvo": True}],
    [{"descricao": "sem comando nem tipo"}],
    [],
])
def test_plano_grave_continua_pedindo_o_clique(plano):
    assert pede(plano, "grave") is True


def test_o_dono_pode_voltar_a_confirmar_sempre():
    assert pede([passo("dir")], "sempre") is True
    assert pede([passo("dir")], "valor-estranho") is True        # na dúvida, pergunta


def test_a_classificacao_local_manda_mais_que_o_risco_declarado_pelo_cerebro():
    # o cérebro diz "reversivel", mas a lista local sabe que isso apaga
    assert pede([passo("rm -rf C:/Users/x", "reversivel")], "grave") is True


def test_config_nova_e_validada():
    import dervs_config as c
    assert c.carregar()["confirmar_plano"] == "grave"
    assert c._validar({**c.PADRAO, "confirmar_plano": "sempre"})["confirmar_plano"] == "sempre"
    assert c._validar({**c.PADRAO, "confirmar_plano": "talvez"})["confirmar_plano"] == "grave"
