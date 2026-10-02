"""Config das permissões, teto diário de gasto e o freio no cérebro OpenAI.

O teto conta só API paga (tts, stt, cerebro) e NUNCA o Claude da assinatura.
Se o medidor quebrar, o teto falha FECHADO: erro de medição não libera gasto."""
import datetime
import json

import pytest

import dervs_config as cfg
import dervs_gasto as gasto
import dervs_permissoes as perm


# --- config ------------------------------------------------------------------

def test_config_traz_permissoes_e_teto_por_padrao():
    c = cfg.carregar()
    assert c["permissoes"] == perm.PADRAO_PERMISSOES
    assert c["teto_gasto_dia_usd"] == 3.0


def test_config_lixo_cai_no_padrao(tmp_path, monkeypatch):
    arq = tmp_path / "config.json"
    arq.write_text(json.dumps({"permissoes": {"apagar": "sozinho", "abrir": "sozinho"},
                               "teto_gasto_dia_usd": "muito"}), encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(arq))
    c = cfg.carregar()
    assert c["permissoes"]["apagar"] == "pergunta"     # teto duro
    assert c["permissoes"]["abrir"] == "sozinho"       # escolha válida do dono
    assert c["teto_gasto_dia_usd"] == 3.0


@pytest.mark.parametrize("ruim", [0, -1, True, 5000, None])
def test_teto_fora_da_faixa_volta_ao_padrao(tmp_path, monkeypatch, ruim):
    arq = tmp_path / "config.json"
    arq.write_text(json.dumps({"teto_gasto_dia_usd": ruim}), encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(arq))
    assert cfg.carregar()["teto_gasto_dia_usd"] == 3.0


def test_padrao_do_config_nao_e_mutado_por_quem_carrega():
    c = cfg.carregar()
    c["permissoes"]["abrir"] = "sozinho"
    assert cfg.carregar()["permissoes"]["abrir"] == "pergunta"


# --- teto --------------------------------------------------------------------

def _gravar(caminho, itens):
    hoje = datetime.datetime.now().isoformat(timespec="seconds")
    with open(caminho, "w", encoding="utf-8") as f:
        for tipo, usd in itens:
            f.write(json.dumps({"quando": hoje, "tipo": tipo, "usd": usd, "detalhe": ""}) + "\n")


def test_estourou_conta_so_api_paga(tmp_path):
    arq = str(tmp_path / "g.jsonl")
    _gravar(arq, [("claude", 50.0), ("cerebro", 1.0), ("tts", 0.5)])
    assert gasto.estourou(2.0, caminho=arq) is False       # 1,5 de API; o Claude não conta
    assert gasto.estourou(1.5, caminho=arq) is True        # chegou no teto


def test_sem_arquivo_nao_estourou(tmp_path):
    assert gasto.estourou(3.0, caminho=str(tmp_path / "nada.jsonl")) is False


def test_medidor_ilegivel_falha_fechado(tmp_path, monkeypatch):
    arq = tmp_path / "g.jsonl"
    arq.write_text("x", encoding="utf-8")

    def quebra(*a, **k):
        raise OSError("sem acesso")
    monkeypatch.setattr(gasto, "_ler_total", quebra)
    assert gasto.estourou(3.0, caminho=str(arq)) is True


def test_pode_gastar_respeita_so_analisa_e_teto(tmp_path, monkeypatch):
    arq = str(tmp_path / "g.jsonl")
    monkeypatch.setenv("DERVS_GASTO_ARQUIVO", arq)
    _gravar(arq, [("cerebro", 0.1)])
    ok, _ = gasto.pode_gastar({"permissoes": {"gastar_api": "sozinho"}, "teto_gasto_dia_usd": 3.0})
    assert ok is True
    ok, motivo = gasto.pode_gastar({"permissoes": {"gastar_api": "analisa"}, "teto_gasto_dia_usd": 3.0})
    assert ok is False and "análise" in motivo
    ok, motivo = gasto.pode_gastar({"permissoes": {"gastar_api": "sozinho"}, "teto_gasto_dia_usd": 0.05})
    assert ok is False and "teto" in motivo


def test_cerebro_openai_e_pulado_quando_o_teto_estoura(monkeypatch):
    import dervs_brain as gb
    chamou = []
    monkeypatch.setattr(gb, "CEREBRO", "openai")
    monkeypatch.setattr(gb, "OPENAI_KEY", "sk-teste")
    monkeypatch.setattr(gb, "_pensar_openai", lambda *a, **k: chamou.append("openai"))
    monkeypatch.setattr(gb.dervs_gasto, "pode_gastar", lambda conf=None: (False, "teto"))
    monkeypatch.setattr(gb, "USAR_STREAM", True)

    class Sessao:
        def pensar(self, conversa, timeout=0):
            return '{"modo":"responder","fala":"oi","pergunta":"","passos":[]}'
    monkeypatch.setattr(gb, "_sessao", Sessao())
    gb.pensar([{"role": "user", "content": "oi"}])
    assert chamou == []                                   # nem tentou a OpenAI


def test_pastas_de_projeto_so_aceita_caminho_absoluto(tmp_path, monkeypatch):
    arq = tmp_path / "config.json"
    perfil = tmp_path / "perfil"                       # o tmp_path real mora dentro de AppData
    perfil.mkdir()
    for var in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(var, str(perfil))
    monkeypatch.setenv("APPDATA", str(perfil / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(perfil / "AppData" / "Local"))
    pasta = str(tmp_path / "loja")
    arq.write_text(json.dumps({"pastas_de_projeto": [pasta, "relativo/x", 5, None]}), encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(arq))
    assert cfg.carregar()["pastas_de_projeto"] == [pasta]
    arq.write_text(json.dumps({"pastas_de_projeto": "C:/x"}), encoding="utf-8")
    assert cfg.carregar()["pastas_de_projeto"] == []
