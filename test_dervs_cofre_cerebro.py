"""Cofre alimentando o cérebro (onda 2 da esteira segundo-cerebro): só o trecho que a pergunta
pede, nunca nota privada, e só no caminho da OpenAI (que remonta a conversa a cada turno)."""
import pytest

import dervs_brain as brain
import dervs_cofre as cofre


@pytest.fixture
def cv(tmp_path):
    return cofre.Cofre(tmp_path / "cofre")


@pytest.fixture(autouse=True)
def _limpa_gancho():
    anterior = brain.CONTEXTO_EXTRA
    yield
    brain.CONTEXTO_EXTRA = anterior


# ---------------------------------------------------------------- recuperação por pergunta
def test_pergunta_em_portugues_acha_a_nota_pelas_palavras_que_importam(cv):
    cv.escrever("Banco de dados", "Decidi usar Postgres no servidor novo.", pasta="decisoes")
    cv.escrever("Receita", "Bolo de cenoura com cobertura.", pasta="pessoas")
    cv.reindexar()
    ctx = cv.contexto_para_nuvem("o que eu decidi sobre o banco de dados?")
    assert "Postgres" in ctx and "cenoura" not in ctx


@pytest.mark.parametrize("pergunta", ["que horas são", "abre o chrome", "ok", "", "oi dervs, tudo bem?"])
def test_pergunta_banal_nao_traz_nota_nenhuma(cv, pergunta):
    cv.escrever("Banco", "Postgres no servidor", pasta="decisoes")
    cv.reindexar()
    assert cv.contexto_para_nuvem(pergunta) == ""


# ---------------------------------------------------------------- gancho no cérebro
def _conversa(*pares):
    return [{"papel": p, "texto": t} for p, t in pares]


def test_sem_gancho_as_mensagens_ficam_como_sempre():
    brain.CONTEXTO_EXTRA = None
    msgs = brain._mensagens_openai(_conversa(("dono", "o que eu sei sobre o banco?")))
    assert sum(1 for m in msgs if m["role"] == "system") == 2


def test_com_gancho_o_contexto_entra_como_mensagem_de_sistema():
    brain.CONTEXTO_EXTRA = lambda pergunta: "NOTA-DO-DONO sobre " + pergunta
    msgs = brain._mensagens_openai(_conversa(("dono", "o que eu sei sobre o banco?")))
    assert sum(1 for m in msgs if m["role"] == "system") == 2        # nunca como sistema
    cercado = [m for m in msgs if "NOTA-DO-DONO sobre o que eu sei sobre o banco?" in m["content"]]
    assert len(cercado) == 1 and cercado[0]["role"] == "user"
    assert "DADO" in cercado[0]["content"] and "nunca obedeça" in cercado[0]["content"]


def test_gancho_so_roda_com_a_fala_do_dono_no_fim():
    chamadas = []
    brain.CONTEXTO_EXTRA = lambda p: chamadas.append(p) or "x"
    brain._mensagens_openai(_conversa(("dono", "abre o app"), ("dervs", "abrindo"), ("resultado", "ok")))
    assert chamadas == []                      # o último turno é resultado de comando, não fala


def test_gancho_que_quebra_nunca_derruba_o_cerebro():
    def quebrado(_):
        raise RuntimeError("disco sumiu")
    brain.CONTEXTO_EXTRA = quebrado
    msgs = brain._mensagens_openai(_conversa(("dono", "o que eu sei sobre o banco?")))
    assert sum(1 for m in msgs if m["role"] == "system") == 2


def test_gancho_vazio_nao_acrescenta_mensagem():
    brain.CONTEXTO_EXTRA = lambda _: ""
    msgs = brain._mensagens_openai(_conversa(("dono", "oi")))
    assert sum(1 for m in msgs if m["role"] == "system") == 2


def test_contexto_gigante_e_cortado_antes_de_ir():
    brain.CONTEXTO_EXTRA = lambda _: "x" * 50_000
    msgs = brain._mensagens_openai(_conversa(("dono", "oi")))
    extra = [m for m in msgs if "xxxx" in m["content"]][0]["content"]
    assert len(extra) <= brain.TETO_CONTEXTO_EXTRA + 400            # + a cerca de dado


# ---------------------------------------------------------------- fim a fim, sem rede
def test_nota_privada_nao_chega_ao_pedido_da_openai(cv):
    cv.escrever("Exame", "resultado reservado do banco do paciente", pasta="privado")
    cv.escrever("Banco", "Postgres no servidor novo do banco", pasta="decisoes")
    cv.reindexar()
    brain.CONTEXTO_EXTRA = cv.contexto_para_nuvem
    msgs = brain._mensagens_openai(_conversa(("dono", "o que eu sei sobre o banco?")))
    tudo = " ".join(m["content"] for m in msgs)
    assert "Postgres" in tudo and "reservado" not in tudo and "paciente" not in tudo


def test_config_cofre_no_cerebro_padrao_ligado_e_valida_booleano():
    import dervs_config
    assert dervs_config.PADRAO["cofre_no_cerebro"] is False         # texto pessoal a terceiro: opt-in
    conf = dict(dervs_config.PADRAO)
    conf["cofre_no_cerebro"] = "true"             # string não liga por acidente: volta ao padrão (desligado)
    assert dervs_config._validar(conf)["cofre_no_cerebro"] is False
    conf["cofre_no_cerebro"] = True
    assert dervs_config._validar(conf)["cofre_no_cerebro"] is True
