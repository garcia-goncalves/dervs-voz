"""A política de permissões ligada ao gancho e ao pedido de permissão do Claude
Code. O que importa aqui: o nível do dono só REDUZ poder — o teto (bloqueios do
`motivo_de_bloqueio`) continua valendo mesmo com tudo em "sozinho"."""
import asyncio

import pytest

import dervs_claude_code as cc
import dervs_permissoes as perm

pytestmark = pytest.mark.skipif(cc.sdk is None, reason="claude-agent-sdk não instalado")

PADRAO = perm.normalizar(None)


def _n(**mudancas):
    return perm.normalizar(mudancas)


def nada_protegido(_):
    return False


def sem_leitura_proibida(_, busca=False):
    return None


def gancho(nome, entrada, niveis):
    return cc.decisao_do_gancho(nome, entrada, nada_protegido, sem_leitura_proibida, niveis)


# --- sem política: comportamento antigo intacto ----------------------------------

def test_sem_niveis_nada_muda():
    assert gancho("Read", {"file_path": "a.txt"}, None)[0] is None
    assert gancho("Edit", {"file_path": "a.txt"}, None)[0] == "ask"


def test_padrao_de_fabrica_equivale_ao_comportamento_antigo():
    assert gancho("Read", {"file_path": "a.txt"}, PADRAO)[0] is None
    assert gancho("Bash", {"command": "dir"}, PADRAO)[0] is None
    assert gancho("Edit", {"file_path": "a.txt"}, PADRAO)[0] == "ask"
    assert gancho("Bash", {"command": "pip install rich"}, PADRAO)[0] == "ask"


# --- os três níveis ------------------------------------------------------------------

def test_so_analisa_nega_com_motivo_em_portugues():
    acao, motivo = gancho("Edit", {"file_path": "a.txt"}, _n(alterar_projeto="analisa"))
    assert acao == "deny" and "análise" in motivo


def test_sozinho_deixa_passar_e_pergunta_continua_perguntando():
    assert gancho("Edit", {"file_path": "a.txt"}, _n(alterar_projeto="sozinho")) == (None, None)
    assert gancho("Edit", {"file_path": "a.txt"}, _n(alterar_projeto="pergunta"))[0] == "ask"


def test_leitura_pode_ser_posta_em_pergunta():
    assert gancho("Read", {"file_path": "a.txt"}, _n(ler="pergunta"))[0] == "ask"


# --- o teto continua valendo -------------------------------------------------------------

TUDO_SOZINHO = {c: "sozinho" for c in perm.CATEGORIAS}      # política crua, pior caso


def test_caminho_protegido_continua_negado_com_tudo_liberado():
    acao, _ = cc.decisao_do_gancho("Edit", {"file_path": "C:/segredo/x"}, lambda c: True,
                                   sem_leitura_proibida, TUDO_SOZINHO)
    assert acao == "deny"


def test_comando_destrutivo_nunca_passa_sozinho():
    acao, _ = gancho("Bash", {"command": "rm -rf C:/Users/x"}, TUDO_SOZINHO)
    assert acao in ("deny", "ask")


def test_servidor_nunca_passa_sozinho():
    acao, _ = gancho("Bash", {"command": "ssh vps ls"}, TUDO_SOZINHO)
    assert acao == "ask"


# --- _can_use_tool: o "sozinho" é aprovado sem cartão, e fica registrado ----------------

def _sessao(niveis, eventos):
    return cc.SessaoClaudeCode(lambda v, d: eventos.append((v, d)), arquivo_sessao=None,
                               niveis_fn=lambda: niveis, protegido=nada_protegido)


def test_sozinho_aprova_sem_abrir_cartao(monkeypatch, tmp_path):
    monkeypatch.setenv("DERVS_PERMISSOES_LOG", str(tmp_path / "p.jsonl"))
    eventos = []
    s = _sessao(_n(alterar_projeto="sozinho"), eventos)
    r = asyncio.run(s._can_use_tool("Edit", {"file_path": "a.txt"}, None))
    assert isinstance(r, cc.sdk.PermissionResultAllow)
    assert eventos == []                                   # nenhum cartão no painel
    assert "alterar_projeto" in (tmp_path / "p.jsonl").read_text(encoding="utf-8")


def test_sozinho_nao_aprova_destrutivo_mesmo_que_o_gancho_falhe(monkeypatch, tmp_path):
    """Cinto e suspensório: mesmo que chegue aqui, destrutivo vai para o cartão."""
    monkeypatch.setenv("DERVS_PERMISSOES_LOG", str(tmp_path / "p.jsonl"))
    eventos = []
    s = cc.SessaoClaudeCode(lambda v, d: eventos.append((v, d)), arquivo_sessao=None,
                            niveis_fn=lambda: TUDO_SOZINHO, protegido=nada_protegido,
                            timeout_pedido=0.05)
    r = asyncio.run(s._can_use_tool("Bash", {"command": "rm -rf C:/Users/x"}, None))
    assert isinstance(r, cc.sdk.PermissionResultDeny)       # sem clique em 0,05 s: nega
    assert eventos and eventos[0][0] == "claude_pedido"     # o cartão chegou a abrir


def test_caminho_protegido_nao_e_aprovado_sozinho(monkeypatch, tmp_path):
    monkeypatch.setenv("DERVS_PERMISSOES_LOG", str(tmp_path / "p.jsonl"))
    eventos = []
    s = cc.SessaoClaudeCode(lambda v, d: eventos.append((v, d)), arquivo_sessao=None,
                            niveis_fn=lambda: TUDO_SOZINHO, protegido=lambda c: True,
                            timeout_pedido=0.05)
    r = asyncio.run(s._can_use_tool("Edit", {"file_path": "C:/segredo/x"}, None))
    assert isinstance(r, cc.sdk.PermissionResultDeny)


def test_sem_niveis_o_pedido_continua_indo_ao_cartao():
    eventos = []
    s = cc.SessaoClaudeCode(lambda v, d: eventos.append((v, d)), arquivo_sessao=None,
                            timeout_pedido=0.05)
    r = asyncio.run(s._can_use_tool("Edit", {"file_path": "a.txt"}, None))
    assert isinstance(r, cc.sdk.PermissionResultDeny)
    assert eventos[0][0] == "claude_pedido"


def test_politica_que_explode_cai_no_cartao():
    def quebra():
        raise RuntimeError("config ilegível")
    eventos = []
    s = cc.SessaoClaudeCode(lambda v, d: eventos.append((v, d)), arquivo_sessao=None,
                            niveis_fn=quebra, timeout_pedido=0.05)
    r = asyncio.run(s._can_use_tool("Edit", {"file_path": "a.txt"}, None))
    assert isinstance(r, cc.sdk.PermissionResultDeny)
    assert eventos[0][0] == "claude_pedido"
