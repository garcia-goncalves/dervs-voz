#!/usr/bin/env python3
"""Testes das partes puras do cérebro e da lógica da sessão persistente.

Nenhum teste aqui chama o `claude` de verdade — a parte que conversa com o
modelo é isolada com dublês. Rodar: python -m pytest test_dervs_brain.py -q
"""
import json
import sys
import pytest
import dervs_brain as gb
from dervs_brain import _extrair_json, _normalizar, montar_prompt, _Sessao


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
        {"papel": "dervs", "texto": "qual site?"},
        {"papel": "resultado", "texto": "exit 0"},
    ]
    p = montar_prompt(conversa)
    assert "[dono] abre o firefox" in p
    assert "[dervs] qual site?" in p
    # a saída de comando é rotulada E cercada: ela é dado observado, não ordem,
    # e pode conter texto plantado imitando um pedido do dono. Ver
    # test_dervs_voz_nao_e_senha.py::test_saida_de_comando_vai_cercada_e_com_aviso
    assert "[resultado de um comando]" in p
    assert "exit 0" in p
    assert "SAIDA-DE-COMANDO-INICIO" in p


# --- Sessão persistente: a lógica de mandar só o turno NOVO -----------------

def test_delta_sessao_fria_manda_a_conversa_inteira():
    """Sessão fria (nada entregue ainda): manda toda a fala do dono, sem pedir
    reinício redundante — quem sobe o processo é o pensar()."""
    s = _Sessao()
    conversa = [{"papel": "dono", "texto": "que horas são?"}]
    texto, reiniciar = s._delta(conversa)
    assert reiniciar is False
    assert "que horas são?" in texto


def test_delta_continuacao_manda_so_o_novo_e_pula_dervs():
    """Depois de um turno, só o dado NOVO do dono/resultado vai — a resposta
    do próprio dervs NÃO é reenviada (o daemon já a tem)."""
    s = _Sessao()
    conversa1 = [{"papel": "dono", "texto": "que horas são?"}]
    # simula que o turno 1 já foi entregue ao daemon
    s._enviada = [(m["papel"], m["texto"]) for m in conversa1]
    conversa2 = conversa1 + [
        {"papel": "dervs", "texto": "São três e meia."},
        {"papel": "dono", "texto": "e a data?"},
    ]
    texto, reiniciar = s._delta(conversa2)
    assert reiniciar is False
    assert "e a data?" in texto
    assert "São três e meia" not in texto   # resposta do dervs não reenviada
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
        {"papel": "dervs", "texto": "Já listo."},
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
    """Com DERVS_BRAIN_STREAM=0 o streaming nem é tentado."""
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


# ---- o prompt não pode mandar o LLM usar comando de outro sistema ----
def test_bloco_de_comandos_windows_nao_menciona_linux(monkeypatch):
    monkeypatch.setattr(gb.sys, "platform", "win32")
    bloco = gb._bloco_comandos_do_sistema()
    assert "konsole" not in bloco
    assert "kcalc" not in bloco
    assert "wt" in bloco
    assert "chrome" in bloco


def test_bloco_de_comandos_linux_nao_menciona_windows(monkeypatch):
    monkeypatch.setattr(gb.sys, "platform", "linux")
    bloco = gb._bloco_comandos_do_sistema()
    assert "konsole" in bloco
    assert "kcalc" in bloco
    assert "explorer" not in bloco
    assert "notepad" not in bloco


def test_sistema_atual_reflete_o_sistema_operacional_da_maquina():
    # SISTEMA é montado uma vez, no import, para o sistema DESTA máquina — não
    # pode conter os dois vocabulários misturados nem o do sistema errado.
    if sys.platform == "win32":
        assert "konsole" not in gb.SISTEMA
        assert "kcalc" not in gb.SISTEMA
        assert "wt" in gb.SISTEMA
    else:
        assert "konsole" in gb.SISTEMA
        assert "kcalc" in gb.SISTEMA


# ---- a resposta da OpenAI precisa vir travada por schema ----
def _espiar_corpo(monkeypatch, resposta='{"modo":"conversar","fala":"oi","pergunta":null,"passos":null}'):
    """Intercepta o urlopen e devolve o corpo JSON que o DERVS mandou."""
    import io
    import json as _json
    visto = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _falso_urlopen(req, timeout=None):
        visto["corpo"] = _json.loads(req.data.decode("utf-8"))
        corpo = _json.dumps({"choices": [{"message": {"content": resposta}}]})
        return _Resp(corpo.encode("utf-8"))

    monkeypatch.setattr(gb.urllib.request, "urlopen", _falso_urlopen)
    monkeypatch.setattr(gb, "OPENAI_KEY", "sk-teste")
    return visto


def test_openai_pede_json_travado_por_schema(monkeypatch):
    """`json_object` só PEDE JSON; `json_schema` com strict FORÇA a gramática.

    Sem isso o gpt-4.1-nano quebrava em 3 de 20 chamadas: fechava a 'fala',
    abria uma aspa a mais e degringolava em texto repetido até estourar o
    limite de tokens — e o DERVS caía no cérebro reserva, lento, por nada.
    """
    visto = _espiar_corpo(monkeypatch)
    gb._pensar_openai([{"papel": "dono", "texto": "quanto é 12 vezes 8?"}], timeout=30)
    fmt = visto["corpo"]["response_format"]
    assert fmt["type"] == "json_schema", "precisa da trava forte, não do json_object"
    assert fmt["json_schema"]["strict"] is True, "sem strict a trava não é gramática"


def test_schema_da_openai_cobre_os_tres_modos(monkeypatch):
    """O schema não pode proibir nenhum dos modos que a tela sabe tratar."""
    visto = _espiar_corpo(monkeypatch)
    gb._pensar_openai([{"papel": "dono", "texto": "oi"}], timeout=30)
    esquema = visto["corpo"]["response_format"]["json_schema"]["schema"]
    assert set(esquema["properties"]["modo"]["enum"]) == {"planejar", "conversar", "perguntar"}
    assert esquema["additionalProperties"] is False
    # strict exige TODA propriedade em required; os opcionais viram anuláveis
    assert set(esquema["required"]) == set(esquema["properties"])


def test_openai_aceita_passos_de_navegador_e_enriquecer(monkeypatch):
    """Um plano com passo de navegador tem 'objetivo' e não 'comando' — o
    schema precisa deixar passar, senão a API recusa a resposta inteira."""
    passo = {"descricao": "abrir o Gmail", "comando": None, "tipo": "navegador",
             "objetivo": "entrar no Gmail e contar os não lidos", "dominio": None,
             "risco": "muda_estado", "reversivel": None, "toca_alvo": True}
    resposta = json.dumps({"modo": "planejar", "fala": "vou lá", "pergunta": None,
                           "passos": [passo]})
    visto = _espiar_corpo(monkeypatch, resposta=resposta)
    ficha = gb._pensar_openai([{"papel": "dono", "texto": "vê meu gmail"}], timeout=30)
    assert ficha["passos"][0]["objetivo"] == "entrar no Gmail e contar os não lidos"
    props = visto["corpo"]["response_format"]["json_schema"]["schema"]["properties"]
    campos = props["passos"]["items"]["properties"]
    for c in ("descricao", "comando", "tipo", "objetivo", "dominio", "risco",
              "reversivel", "toca_alvo"):
        assert c in campos, f"o schema esqueceu o campo '{c}' do passo"


def test_normalizar_trata_campo_nulo_como_ausente():
    """Com json_schema strict o modelo manda TODO campo, usando null no que não
    se aplica. `setdefault` não substitui null — só chave ausente — então um
    passo de navegador chegava com comando=None e vazava para a tela."""
    ficha = _normalizar({
        "modo": "planejar", "fala": "vou lá", "pergunta": None,
        "passos": [{"descricao": "abrir o Gmail", "comando": None,
                    "tipo": "navegador", "objetivo": "contar os não lidos",
                    "dominio": None, "risco": "muda_estado",
                    "reversivel": None, "toca_alvo": None}],
    })
    p = ficha["passos"][0]
    assert p["comando"] == "", "comando nulo tem de virar string vazia"
    assert p["objetivo"] == "contar os não lidos"
    assert p["reversivel"] is False
    assert p["toca_alvo"] is True, "navegador age no Chrome logado: toca o alvo"


def test_normalizar_passo_de_comando_com_nulos():
    """Passo comum: os campos de navegador/enriquecer vêm nulos e não atrapalham."""
    ficha = _normalizar({
        "modo": "planejar", "fala": "beleza", "pergunta": None,
        "passos": [{"descricao": "listar a pasta", "comando": "dir",
                    "tipo": None, "objetivo": None, "dominio": None,
                    "risco": "reversivel", "reversivel": None, "toca_alvo": None}],
    })
    p = ficha["passos"][0]
    assert p["comando"] == "dir"
    assert p["reversivel"] is True
    assert p["toca_alvo"] is False
