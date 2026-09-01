#!/usr/bin/env python3
"""Testes da config: garante que valor torto nunca quebra o DERVS e que as
chaves do navegador autônomo têm padrão e limite sãos."""
import dervs_config as cfg


def test_padrao_completo_carrega():
    c = cfg._validar(dict(cfg.PADRAO))
    assert c["navegador_ligado"] is True
    assert c["navegador_max_passos"] == 15
    assert c["navegador_perfil_nome"] == "Default"


def test_max_passos_absurdo_cai_no_limite():
    c = cfg._validar({**cfg.PADRAO, "navegador_max_passos": 9999})
    assert c["navegador_max_passos"] == 60  # teto
    c = cfg._validar({**cfg.PADRAO, "navegador_max_passos": 0})
    assert c["navegador_max_passos"] == 1   # piso


def test_max_passos_lixo_cai_no_padrao():
    c = cfg._validar({**cfg.PADRAO, "navegador_max_passos": "muito"})
    assert c["navegador_max_passos"] == cfg.PADRAO["navegador_max_passos"]


def test_navegador_ligado_vira_bool():
    c = cfg._validar({**cfg.PADRAO, "navegador_ligado": "sim"})
    assert isinstance(c["navegador_ligado"], bool)


def test_perfil_vazio_cai_no_padrao():
    c = cfg._validar({**cfg.PADRAO, "navegador_perfil_chrome": ""})
    assert c["navegador_perfil_chrome"] == cfg.PADRAO["navegador_perfil_chrome"]
