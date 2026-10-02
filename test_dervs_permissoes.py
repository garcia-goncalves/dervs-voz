"""A política de permissões: o dono libera ou trava categorias, mas o painel só
pode REDUZIR poder — nunca passar do teto fixo do dervs_safety (02/10/2026)."""
import pytest

import dervs_permissoes as p


def rev(rede=False):
    return {"nivel": "reversivel", "rede": rede}


def muda(rede=False):
    return {"nivel": "muda_estado", "rede": rede}


DESTR = {"nivel": "destrutivo", "rede": False}


def test_padrao_de_fabrica():
    d = p.PADRAO_PERMISSOES
    assert d["ler"] == "sozinho"
    assert d["gastar_api"] == "sozinho"            # mantém o que já funcionava
    for c in ("abrir", "instalar", "alterar_projeto", "apagar", "internet", "servidor"):
        assert d[c] == "pergunta"
    assert set(d) == set(p.CATEGORIAS)


@pytest.mark.parametrize("lixo", [None, 3, "sozinho", [], {"ler": 5}, {"x": "sozinho"}])
def test_normalizar_lixo_cai_no_padrao(lixo):
    assert p.normalizar(lixo) == p.PADRAO_PERMISSOES


def test_normalizar_aceita_valido_e_ignora_invalido():
    r = p.normalizar({"abrir": "sozinho", "instalar": "voa", "inventada": "sozinho"})
    assert r["abrir"] == "sozinho"
    assert r["instalar"] == p.PADRAO_PERMISSOES["instalar"]
    assert "inventada" not in r


@pytest.mark.parametrize("cat", ["apagar", "servidor"])
def test_teto_duro_apagar_e_servidor_nunca_sozinho(cat):
    assert p.normalizar({cat: "sozinho"})[cat] == "pergunta"


def test_ler_nunca_fica_em_so_analisa_e_api_nunca_em_pergunta():
    assert p.normalizar({"ler": "analisa"})["ler"] == "sozinho"
    assert p.normalizar({"gastar_api": "pergunta"})["gastar_api"] == "sozinho"


def test_normalizar_nao_muta_o_padrao():
    r = p.normalizar({"abrir": "sozinho"})
    r["abrir"] = "analisa"
    assert p.PADRAO_PERMISSOES["abrir"] == "pergunta"


@pytest.mark.parametrize("nome,entrada,risco,cat", [
    ("Read", {}, rev(), "ler"),
    ("Bash", {"command": "ls"}, rev(), "ler"),
    ("Edit", {"file_path": "a.py"}, muda(), "alterar_projeto"),
    ("Bash", {"command": "pip install requests"}, muda(), "instalar"),
    ("Bash", {"command": "winget install foo"}, muda(), "instalar"),
    ("Bash", {"command": "ssh vps ls"}, muda(True), "servidor"),
    ("Bash", {"command": "rm -rf x"}, DESTR, "apagar"),
    ("WebFetch", {"url": "http://x"}, muda(True), "internet"),
    ("Bash", {"command": "start notepad"}, muda(), "abrir"),
    ("Bash", {"command": "Start-Process calc"}, muda(), "abrir"),
])
def test_categoria_da_acao(nome, entrada, risco, cat):
    assert p.categoria_da_acao(nome, entrada, risco) == cat


def test_so_analisa_nega():
    n = p.normalizar({"alterar_projeto": "analisa"})
    d = p.decidir("Edit", {"file_path": "a.py"}, muda(), n)
    assert d["acao"] == "negar"
    assert "análise" in d["motivo"]


def test_pergunta_mantem_o_cartao():
    d = p.decidir("Edit", {"file_path": "a.py"}, muda(), p.PADRAO_PERMISSOES)
    assert d["acao"] == "perguntar"


def test_sozinho_so_para_o_que_nao_e_destrutivo():
    n = p.normalizar({"alterar_projeto": "sozinho", "apagar": "sozinho"})
    assert p.decidir("Edit", {"file_path": "a.py"}, muda(), n)["acao"] == "permitir"
    assert p.decidir("Bash", {"command": "rm -rf x"}, DESTR, n)["acao"] == "perguntar"


def test_politica_crua_toda_sozinho_ainda_nao_libera_destrutivo_nem_servidor():
    n = {c: "sozinho" for c in p.CATEGORIAS}      # nem passou pelo normalizar
    assert p.decidir("Bash", {"command": "pip install x; rm -rf /"}, DESTR, n)["acao"] == "perguntar"
    assert p.decidir("Bash", {"command": "ssh vps ls"}, muda(True), n)["acao"] == "perguntar"


def test_leitura_em_pergunta_vira_cartao():
    n = p.normalizar({"ler": "pergunta"})
    assert p.decidir("Read", {}, rev(), n)["acao"] == "perguntar"
    assert p.decidir("Read", {}, rev(), p.PADRAO_PERMISSOES)["acao"] == "permitir"


def test_politica_ilegivel_cai_no_mais_cauteloso():
    assert p.decidir("Edit", {}, muda(), None)["acao"] == "perguntar"
