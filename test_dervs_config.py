#!/usr/bin/env python3
"""Testes da config: garante que valor torto nunca quebra o DERVS e que as
chaves do navegador autônomo têm padrão e limite sãos."""
import importlib
import json
import os

import dervs_config as cfg


def _recarregar_com_plataforma(monkeypatch, plataforma, **env):
    """Recarrega dervs_config com sys.platform trocado — CONFIG_DIR é
    calculado na importação, então o teste precisa reimportar o módulo."""
    monkeypatch.setattr("sys.platform", plataforma)
    for chave, valor in env.items():
        if valor is None:
            monkeypatch.delenv(chave, raising=False)
        else:
            monkeypatch.setenv(chave, valor)
    return importlib.reload(cfg)


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


# ---- voz_velocidade ----
def test_voz_velocidade_padrao_e_1_2():
    assert cfg.PADRAO["voz_velocidade"] == 1.2


def test_voz_velocidade_fora_da_faixa_cai_no_padrao():
    c = cfg._validar({**cfg.PADRAO, "voz_velocidade": 5.0})
    assert c["voz_velocidade"] == cfg.PADRAO["voz_velocidade"]
    c = cfg._validar({**cfg.PADRAO, "voz_velocidade": 0.1})
    assert c["voz_velocidade"] == cfg.PADRAO["voz_velocidade"]


def test_voz_velocidade_lixo_cai_no_padrao():
    c = cfg._validar({**cfg.PADRAO, "voz_velocidade": "rápido"})
    assert c["voz_velocidade"] == cfg.PADRAO["voz_velocidade"]


def test_voz_velocidade_valida_e_aceita():
    c = cfg._validar({**cfg.PADRAO, "voz_velocidade": 0.8})
    assert c["voz_velocidade"] == 0.8


# ---- CONFIG_DIR por plataforma ----
# CONFIG_DIR é calculado na importação, então o teste força um reload do
# módulo com sys.platform trocado; ao fim, recarrega de novo com a
# plataforma real, para não vazar estado para outros testes.
def test_config_dir_windows_usa_appdata(monkeypatch):
    monkeypatch.setenv("APPDATA", r"C:\Users\alguem\AppData\Roaming")
    mod = _recarregar_com_plataforma(monkeypatch, "win32")
    assert mod.CONFIG_DIR == os.path.join(r"C:\Users\alguem\AppData\Roaming", "dervs")
    monkeypatch.undo()
    importlib.reload(cfg)


def test_config_dir_linux_usa_config_ponto(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    mod = _recarregar_com_plataforma(monkeypatch, "linux")
    assert mod.CONFIG_DIR == os.path.expanduser("~/.config/dervs")
    monkeypatch.undo()
    importlib.reload(cfg)


# ---- carregar() nunca quebra ----
def test_carregar_com_json_corrompido_nao_quebra(tmp_path, monkeypatch):
    caminho = tmp_path / "config.json"
    caminho.write_text("{ isto não é json válido ]", encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(caminho))
    conf = cfg.carregar()
    assert conf["voz_velocidade"] == cfg.PADRAO["voz_velocidade"]


def test_carregar_sem_arquivo_cai_no_padrao(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "nao_existe.json"))
    conf = cfg.carregar()
    assert conf == cfg._validar(dict(cfg.PADRAO))


def test_carregar_le_o_que_o_dono_mudou(tmp_path, monkeypatch):
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"voz_velocidade": 0.9}), encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(caminho))
    conf = cfg.carregar()
    assert conf["voz_velocidade"] == 0.9
