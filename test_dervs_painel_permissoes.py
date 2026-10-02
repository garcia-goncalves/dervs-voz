#!/usr/bin/env python3
"""Testes da tela "O que o DERVS pode fazer" (`dervs_painel_permissoes.py`), da validação
dos verbos novos na ponte do Electron e das travas estáticas do JS/HTML.
Nenhum teste toca o config real: o conftest isola o APPDATA em tmp_path.

Rodar: python -m pytest test_dervs_painel_permissoes.py -q
"""
import json
import os
import re
import sys

import pytest

import dervs_config as config
import dervs_painel_permissoes as pp
import dervs_permissoes as perm
import dervs_ponte_electron as pe

AQUI = os.path.dirname(os.path.abspath(__file__))


class PonteFalsa:
    def __init__(self):
        self.enviadas = []

    def enviar_permissoes(self, dados):
        self.enviadas.append(dados)

    def estados(self):
        return [d for d in self.enviadas if d["parte"] == "estado"]

    def mensagens(self):
        return [d for d in self.enviadas if d["parte"] == "mensagem"]


class GastoFalso:
    @staticmethod
    def total_do_dia():
        return {"total": 1.5}


@pytest.fixture
def tela():
    ponte = PonteFalsa()
    return pp.PermissoesLocal(ponte, config=config, gasto=GastoFalso, ler_log=lambda: []), ponte


def test_pedir_devolve_as_oito_categorias_com_rotulos_e_permitidos(tela):
    local, ponte = tela
    local.tratar("permissoes_pedir", {})
    (e,) = ponte.estados()
    assert tuple(e["categorias"]) == perm.CATEGORIAS and len(e["categorias"]) == 8
    assert e["rotulos"] == perm.ROTULOS
    assert e["permitidos"]["apagar"] == ["analisa", "pergunta"]
    assert e["niveis"] == perm.PADRAO_PERMISSOES
    assert e["teto"] == config.carregar()["teto_gasto_dia_usd"]
    assert e["gasto_hoje"] == 1.5 and e["recentes"] == []


def test_definir_valido_persiste_e_reenvia_o_estado(tela):
    local, ponte = tela
    local.tratar("permissoes_definir", {"categoria": "abrir", "nivel": "sozinho"})
    assert config.carregar()["permissoes"]["abrir"] == "sozinho"
    assert ponte.estados()[-1]["niveis"]["abrir"] == "sozinho"
    assert ponte.mensagens()[-1]["ok"] is True
    # as outras categorias ficam como estavam
    assert config.carregar()["permissoes"]["ler"] == perm.PADRAO_PERMISSOES["ler"]


@pytest.mark.parametrize("categoria", ["apagar", "servidor"])
def test_definir_sozinho_em_apagar_e_servidor_e_recusado(tela, categoria):
    local, ponte = tela
    antes = config.carregar()["permissoes"]
    local.tratar("permissoes_definir", {"categoria": categoria, "nivel": "sozinho"})
    assert config.carregar()["permissoes"] == antes
    (m,) = ponte.mensagens()
    assert m["ok"] is False and "Nada foi mudado" in m["texto"]
    assert ponte.estados() == []


def test_definir_nivel_fora_do_permitido_de_ler_e_recusado(tela):
    local, ponte = tela
    local.tratar("permissoes_definir", {"categoria": "ler", "nivel": "analisa"})
    assert ponte.mensagens()[-1]["ok"] is False


@pytest.mark.parametrize("dados", [
    {"categoria": "inventada", "nivel": "sozinho"},
    {"categoria": None, "nivel": "sozinho"},
    {"categoria": "abrir", "nivel": "tudo"},
    {"categoria": "abrir", "nivel": 3},
    {},
])
def test_categoria_ou_nivel_inventado_e_recusado(tela, dados):
    local, ponte = tela
    antes = config.carregar()["permissoes"]
    local.tratar("permissoes_definir", dados)
    assert config.carregar()["permissoes"] == antes
    assert ponte.mensagens()[-1]["ok"] is False


def test_teto_valido_persiste(tela):
    local, ponte = tela
    local.tratar("permissoes_teto", {"valor": 7.5})
    assert config.carregar()["teto_gasto_dia_usd"] == 7.5
    assert ponte.estados()[-1]["teto"] == 7.5


@pytest.mark.parametrize("valor", [0, 0.001, 1000.01, -1, "3", None, True, float("nan"), float("inf")])
def test_teto_fora_da_faixa_e_recusado(tela, valor):
    local, ponte = tela
    antes = config.carregar()["teto_gasto_dia_usd"]
    local.tratar("permissoes_teto", {"valor": valor})
    assert config.carregar()["teto_gasto_dia_usd"] == antes
    assert ponte.mensagens()[-1]["ok"] is False


def test_falha_ao_gravar_avisa_e_nao_finge_que_salvou():
    class ConfigQueFalha:
        carregar = staticmethod(config.carregar)

        @staticmethod
        def gravar(chave, valor):
            return False
    ponte = PonteFalsa()
    pp.PermissoesLocal(ponte, config=ConfigQueFalha, gasto=GastoFalso,
                       ler_log=lambda: []).tratar("permissoes_definir", {"categoria": "abrir", "nivel": "sozinho"})
    assert ponte.mensagens()[-1]["ok"] is False and ponte.estados() == []


def test_recentes_so_traz_o_que_foi_feito_sozinho_e_no_maximo_dez(tmp_path):
    log = tmp_path / "permissoes.jsonl"
    linhas = [json.dumps({"quando": f"2026-10-02 10:00:{i:02d}", "acao": "permitir",
                          "categoria": "ler", "ferramenta": "Read", "resumo": f"a{i}"}) for i in range(15)]
    linhas.insert(3, json.dumps({"acao": "perguntar", "categoria": "apagar"}))
    linhas.insert(4, "lixo que não é json")
    log.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    r = pp.ler_recentes(str(log))
    assert len(r) == 10 and r[0]["resumo"] == "a14"
    assert all(i["categoria"] == "ler" for i in r)
    assert pp.ler_recentes(str(tmp_path / "nao-existe.jsonl")) == []


# --- verbos IPC na ponte ---------------------------------------------------------

def _ponte_com_captura():
    recebidos = []
    ponte = pe.PonteElectron(ao_sair=lambda: None, ao_plano=lambda *a: None, ao_pronto=lambda: None,
                             ao_permissoes=lambda verbo, dados: recebidos.append((verbo, dados)))
    return ponte, recebidos


def _linha(verbo, **campos):
    return json.dumps({"verbo": verbo, **campos}).encode("utf-8")


def test_a_linha_do_electron_chega_ao_callback_pelo_caminho_real():
    ponte, recebidos = _ponte_com_captura()
    ponte._processar_linha(_linha("permissoes_teto", valor=4))
    ponte._processar_linha(_linha("permissoes_teto", valor=0))      # malformado: some
    ponte._processar_linha(_linha("permissoes_definir", categoria="apagar", nivel="pergunta"))
    assert recebidos == [("permissoes_teto", {"valor": 4}),
                         ("permissoes_definir", {"categoria": "apagar", "nivel": "pergunta"})]


def test_ponte_entrega_verbos_validos():
    ponte, recebidos = _ponte_com_captura()
    ponte._tratar_permissoes("permissoes_pedir", {})
    ponte._tratar_permissoes("permissoes_definir", {"categoria": "abrir", "nivel": "pergunta"})
    ponte._tratar_permissoes("permissoes_teto", {"valor": 2})
    assert recebidos == [("permissoes_pedir", {}),
                         ("permissoes_definir", {"categoria": "abrir", "nivel": "pergunta"}),
                         ("permissoes_teto", {"valor": 2})]


@pytest.mark.parametrize("verbo,dado", [
    ("permissoes_definir", {"categoria": "inventada", "nivel": "sozinho"}),
    ("permissoes_definir", {"categoria": "abrir", "nivel": "tudo"}),
    ("permissoes_definir", {"categoria": ["abrir"], "nivel": "sozinho"}),
    ("permissoes_definir", {}),
    ("permissoes_teto", {"valor": 0}),
    ("permissoes_teto", {"valor": 1001}),
    ("permissoes_teto", {"valor": "3"}),
    ("permissoes_teto", {"valor": True}),
    ("permissoes_teto", {}),
])
def test_ponte_ignora_verbo_malformado(verbo, dado):
    ponte, recebidos = _ponte_com_captura()
    ponte._tratar_permissoes(verbo, dado)
    assert recebidos == []


def test_ponte_despacha_pelo_caminho_normal_dos_verbos():
    assert set(pe._VERBOS_PERMISSOES) == {"permissoes_pedir", "permissoes_definir", "permissoes_teto"}
    assert pe._CATEGORIAS_PERMISSAO == perm.CATEGORIAS and pe._NIVEIS_PERMISSAO == perm.NIVEIS


# --- travas estáticas do JS/HTML -------------------------------------------------

def _fonte(*partes):
    with open(os.path.join(AQUI, "electron", *partes), encoding="utf-8") as f:
        return f.read()


def _sem_comentarios(js):
    return "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))


@pytest.mark.parametrize("arquivo", [("renderer", "painel-permissoes.js"), ("preload.js",), ("main.js",)])
def test_permissoes_sem_innerhtml_nem_console_log(arquivo):
    js = _sem_comentarios(_fonte(*arquivo))
    for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert proibido not in js
    assert "console.log" not in js


def test_preload_das_permissoes_expoe_so_a_lista_estreita():
    js = _fonte("preload.js")
    expostos = set(re.findall(r"^\s{2}((?:aoPermissoes|permissoes)\w*)\s*:", js, re.MULTILINE))
    assert expostos == {"aoPermissoes", "permissoesPedir", "permissoesDefinir", "permissoesTeto"}


def test_main_valida_os_pedidos_das_permissoes():
    js = _fonte("main.js")
    for canal in ("pedir", "definir", "teto"):
        assert f'ipcMain.on("dervs:permissoes-{canal}"' in js
    for cat in perm.CATEGORIAS:
        assert f'"{cat}"' in js
    assert "valor < 0.01 || valor > 1000" in js


def test_html_das_permissoes_tem_os_ids_e_nao_afrouxa_a_csp():
    html = _fonte("renderer", "painel.html")
    assert 'src="painel-permissoes.js"' in html and 'href="painel-permissoes.css"' in html
    for ident in ("p-abrir-permissoes", "p-dialogo-permissoes", "perm-lista", "perm-teto",
                  "perm-gasto", "perm-recentes", "perm-fechar"):
        assert f'id="{ident}"' in html
    assert "style=" not in html and "unsafe-inline" not in html
    assert "O que o DERVS pode fazer".lower() in html.lower()
    assert "Estas travas valem sempre e não aparecem aqui" in html
    assert "lixeira segura" in html and "nunca mexe em servidor sem o seu sim" in html
    assert "default-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'" in html


def test_a_tela_nao_duplica_rotulos_de_categoria():
    js = _fonte("renderer", "painel-permissoes.js")
    for rotulo in perm.ROTULOS.values():
        assert rotulo not in js
