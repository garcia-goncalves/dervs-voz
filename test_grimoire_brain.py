#!/usr/bin/env python3
"""Testes das partes puras do cérebro e da lógica da sessão persistente.

Nenhum teste aqui chama o `claude` de verdade — a parte que conversa com o
modelo é isolada com dublês. Rodar: python -m pytest test_grimoire_brain.py -q
"""
import pytest
import grimoire_brain as gb
from grimoire_brain import _extrair_json, _normalizar, montar_prompt, _Sessao


def test_extrai_json_limpo():
    assert _extrair_json('{"modo":"conversar","fala":"oi"}')["modo"] == "conversar"


def test_extrai_json_com_cerca_de_codigo():
    bruto = '```json\n{"modo":"perguntar","fala":"qual rede?"}\n```'
    assert _extrair_json(bruto)["modo"] == "perguntar"


def test_extrai_json_com_texto_em_volta():
    bruto = 'Claro! Aqui vai:\n{"modo":"conversar","fala":"feito"}\nEspero ter ajudado.'
    assert _extrair_json(bruto)["fala"] == "feito"


def test_extrai_json_vazio_quebra():
    with pytest.raises(ValueError):
        _extrair_json("")


def test_normalizar_preenche_campos_do_passo():
    ficha = _normalizar({"modo": "planejar", "passos": [{"comando": "ls"}]})
    p = ficha["passos"][0]
    assert p["risco"] == "reversivel"
    assert p["reversivel"] is True
    assert p["toca_alvo"] is False
    assert "descricao" in p


def test_normalizar_passo_navegador_ganha_defaults_certos():
    ficha = _normalizar({"modo": "planejar", "passos": [
        {"tipo": "navegador", "objetivo": "entrar no Gmail e contar não lidos"}]})
    p = ficha["passos"][0]
    # navegador age no Chrome logado: no mínimo muda_estado e toca alvo
    assert p["risco"] == "muda_estado"
    assert p["reversivel"] is False
    assert p["toca_alvo"] is True
    assert p["objetivo"] == "entrar no Gmail e contar não lidos"
    assert p["comando"] == ""


def test_normalizar_navegador_sem_objetivo_usa_descricao():
    ficha = _normalizar({"modo": "planejar", "passos": [
        {"tipo": "navegador", "descricao": "abrir o YouTube"}]})
    assert ficha["passos"][0]["objetivo"] == "abrir o YouTube"


def test_normalizar_passo_enriquecer_e_passivo():
    ficha = _normalizar({"modo": "planejar", "passos": [
        {"tipo": "enriquecer", "dominio": "empresa.com.br"}]})
    p = ficha["passos"][0]
    # passivo/defensivo: NÃO toca o alvo, não vira destrutivo
    assert p["toca_alvo"] is False
    assert p["risco"] == "muda_estado"
    assert p["dominio"] == "empresa.com.br"
    assert p["comando"] == ""


def test_normalizar_sem_modo_vira_conversar():
    assert _normalizar({}).get("fala") == ""


def test_montar_prompt_inclui_papeis():
    conversa = [
        {"papel": "dono", "texto": "abre o firefox"},
        {"papel": "grimoire", "texto": "qual site?"},
        {"papel": "resultado", "texto": "exit 0"},
    ]
    p = montar_prompt(conversa)
    assert "[dono] abre o firefox" in p
    assert "[grimoire] qual site?" in p
    assert "[resultado de um comando] exit 0" in p


# --- Sessão persistente: a lógica de mandar só o turno NOVO -----------------

def test_delta_sessao_fria_manda_a_conversa_inteira():
    """Sessão fria (nada entregue ainda): manda toda a fala do dono, sem pedir
    reinício redundante — quem sobe o processo é o pensar()."""
    s = _Sessao()
    conversa = [{"papel": "dono", "texto": "que horas são?"}]
    texto, reiniciar = s._delta(conversa)
    assert reiniciar is False
    assert "que horas são?" in texto


def test_delta_continuacao_manda_so_o_novo_e_pula_grimoire():
    """Depois de um turno, só o dado NOVO do dono/resultado vai — a resposta
    do próprio grimoire NÃO é reenviada (o daemon já a tem)."""
    s = _Sessao()
    conversa1 = [{"papel": "dono", "texto": "que horas são?"}]
    # simula que o turno 1 já foi entregue ao daemon
    s._enviada = [(m["papel"], m["texto"]) for m in conversa1]
    conversa2 = conversa1 + [
        {"papel": "grimoire", "texto": "São três e meia."},
        {"papel": "dono", "texto": "e a data?"},
    ]
    texto, reiniciar = s._delta(conversa2)
    assert reiniciar is False
    assert "e a data?" in texto
    assert "São três e meia" not in texto   # resposta do grimoire não reenviada
    assert "que horas são?" not in texto     # turno velho não reenviado


def test_delta_conversa_editada_pede_reinicio():
    """Se a conversa não é continuação do que já foi mandado, reinicia."""
    s = _Sessao()
    s._enviada = [("dono", "abre o firefox")]
    conversa = [{"papel": "dono", "texto": "outra conversa totalmente diferente"}]
    texto, reiniciar = s._delta(conversa)
    assert reiniciar is True


def test_delta_resultado_de_comando_eh_reenviado():
    """A saída de um comando que rodou é dado novo e precisa chegar ao modelo."""
    s = _Sessao()
    conversa1 = [{"papel": "dono", "texto": "lista os arquivos"}]
    s._enviada = [(m["papel"], m["texto"]) for m in conversa1]
    conversa2 = conversa1 + [
        {"papel": "grimoire", "texto": "Já listo."},
        {"papel": "resultado", "texto": "a.txt b.txt c.txt"},
    ]
    texto, reiniciar = s._delta(conversa2)
    assert reiniciar is False
    assert "a.txt b.txt c.txt" in texto
    assert "[resultado de um comando]" in texto


# --- pensar(): streaming quando dá certo, fallback quando falha -------------

def test_pensar_usa_streaming_quando_ok(monkeypatch):
    """Se a sessão responde, pensar devolve a ficha do streaming e NÃO cai no
    modo antigo."""
    monkeypatch.setattr(gb, "CEREBRO", "claude")  # testa o caminho do Claude, não a OpenAI
    monkeypatch.setattr(gb, "USAR_STREAM", True)
    monkeypatch.setattr(gb._sessao, "pensar",
                        lambda conversa, timeout: '{"modo":"conversar","fala":"oi"}')
    def _nao_deveria(*a, **k):
        raise AssertionError("não deveria cair no fallback")
    monkeypatch.setattr(gb, "_pensar_oneshot", _nao_deveria)
    ficha = gb.pensar([{"papel": "dono", "texto": "oi"}])
    assert ficha["modo"] == "conversar"
    assert ficha["fala"] == "oi"


def test_pensar_cai_no_fallback_quando_streaming_falha(monkeypatch):
    """Se o streaming explode (daemon morreu, timeout...), pensar NÃO fica mudo:
    usa o modo antigo."""
    monkeypatch.setattr(gb, "CEREBRO", "claude")  # testa o caminho do Claude, não a OpenAI
    monkeypatch.setattr(gb, "USAR_STREAM", True)
    def _explode(conversa, timeout):
        raise RuntimeError("daemon morreu")
    monkeypatch.setattr(gb._sessao, "pensar", _explode)
    monkeypatch.setattr(gb, "_pensar_oneshot",
                        lambda conversa, timeout: {"modo": "conversar", "fala": "fallback"})
    ficha = gb.pensar([{"papel": "dono", "texto": "oi"}])
    assert ficha["fala"] == "fallback"


def test_pensar_stream_desligado_vai_direto_no_oneshot(monkeypatch):
    """Com GRIMOIRE_BRAIN_STREAM=0 o streaming nem é tentado."""
    monkeypatch.setattr(gb, "CEREBRO", "claude")  # testa o caminho do Claude, não a OpenAI
    monkeypatch.setattr(gb, "USAR_STREAM", False)
    monkeypatch.setattr(gb, "_pensar_oneshot",
                        lambda conversa, timeout: {"modo": "conversar", "fala": "antigo"})
    def _nao(*a, **k):
        raise AssertionError("não deveria tocar a sessão persistente")
    monkeypatch.setattr(gb._sessao, "pensar", _nao)
    assert gb.pensar([{"papel": "dono", "texto": "oi"}])["fala"] == "antigo"


def test_pensar_usa_openai_quando_configurado(monkeypatch):
    """cerebro=openai com chave: usa a OpenAI e NÃO toca o Claude."""
    monkeypatch.setattr(gb, "CEREBRO", "openai")
    monkeypatch.setattr(gb, "OPENAI_KEY", "sk-teste")
    monkeypatch.setattr(gb, "_pensar_openai",
                        lambda conversa, timeout: {"modo": "conversar", "fala": "via openai"})
    def _nao(*a, **k):
        raise AssertionError("não deveria tocar o Claude")
    monkeypatch.setattr(gb._sessao, "pensar", _nao)
    monkeypatch.setattr(gb, "_pensar_oneshot", _nao)
    assert gb.pensar([{"papel": "dono", "texto": "oi"}])["fala"] == "via openai"


def test_pensar_openai_falha_cai_no_claude(monkeypatch):
    """Se a OpenAI falhar (sem internet, chave ruim), cai no Claude — não fica mudo."""
    monkeypatch.setattr(gb, "CEREBRO", "openai")
    monkeypatch.setattr(gb, "OPENAI_KEY", "sk-teste")
    def _explode(conversa, timeout):
        raise RuntimeError("sem internet")
    monkeypatch.setattr(gb, "_pensar_openai", _explode)
    monkeypatch.setattr(gb, "USAR_STREAM", True)
    monkeypatch.setattr(gb._sessao, "pensar",
                        lambda conversa, timeout: '{"modo":"conversar","fala":"claude reserva"}')
    assert gb.pensar([{"papel": "dono", "texto": "oi"}])["fala"] == "claude reserva"
