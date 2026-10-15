"""Roteador: o dono fala e o DERVS decide quem atende, sem ele escolher cérebro.

Conservador de propósito: um falso positivo manda o pedido ao Claude Code (mais
lento, gasta a assinatura); então só pedido CLARO de desenvolvimento ou de
análise vai para lá. O resto continua no planejador rápido de sempre."""
import json

import pytest

import dervs_roteador as r


@pytest.mark.parametrize("fala", [
    "cria um site para a minha clínica",
    "Dervs, conserta o bug do login",
    "desenvolve um aplicativo de agenda",
    "implementa a tela de cadastro",
    "refatora essa função",
    "escreve um script para renomear as fotos",
    "corrige o teste que está falhando",
    "faz uma API de pacientes",
    "Olá dervs, cria um site",
    "faça um site para mim",
    "corrija o bug do login",
    "desenvolva um sistema de agenda",
    "quero que você crie um aplicativo",
    "pode criar um site pra mim",
    "preciso que você conserte o bug",
])
def test_pedido_de_desenvolvimento_vai_para_o_claude_code(fala):
    d = r.rotear(fala)
    assert d["executor"] == "claude_code"
    assert d["intencao"] == "desenvolver"
    assert d["pedido"]
    assert d["motivo"]


@pytest.mark.parametrize("fala", [
    "pede pro Claude olhar a minha agenda",
    "analisa o meu disco",
    "verifica meu pc",
])
def test_pedido_explicito_de_trabalho_continua_indo_ao_claude_code(fala):
    d = r.rotear(fala)
    assert d["executor"] == "claude_code"
    assert d["intencao"] == "trabalho"


@pytest.mark.parametrize("fala", [
    "que horas são",
    "abre o chrome",
    "cria um lembrete para amanhã às nove",
    "faz um café",
    "conserta a impressora",
    "",
    "   ",
    "o site está lento hoje",
    "Dervs, faz um teste do microfone",
    "cria um lembrete na tela",
    "faz um programa de televisão",
    "quero um café",
])
def test_o_resto_fica_no_planejador_rapido(fala):
    d = r.rotear(fala)
    assert d["executor"] == "planejador"
    assert d["pedido"] is None


def test_o_pedido_enviado_e_o_texto_original_sem_o_vocativo():
    assert r.rotear("Dervs, cria um site simples")["pedido"].lower().endswith("cria um site simples")


def test_registra_o_motivo_e_lista_os_recentes(tmp_path, monkeypatch):
    log = tmp_path / "roteamento.jsonl"
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(log))
    r.registrar(r.rotear("cria um site"), "cria um site")
    r.registrar(r.rotear("que horas são"), "que horas são")
    linhas = log.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2 and json.loads(linhas[0])["executor"] == "claude_code"
    rec = r.recentes(5)
    assert [x["executor"] for x in rec] == ["planejador", "claude_code"]   # mais novo primeiro


def test_fala_do_planejador_nao_fica_no_disco(tmp_path, monkeypatch):
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(tmp_path / "r.jsonl"))
    r.registrar(r.rotear("a senha do banco e 1234"), "a senha do banco e 1234")
    texto = (tmp_path / "r.jsonl").read_text(encoding="utf-8")
    assert "1234" not in texto and "planejador" in texto


def test_log_nao_guarda_o_texto_inteiro_nem_derruba(tmp_path, monkeypatch):
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(tmp_path / "x" / "y.jsonl"))
    r.registrar(r.rotear("cria um site " + "a" * 5000), "cria um site " + "a" * 5000)
    assert len(r.recentes(1)[0]["fala"]) <= 80
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(tmp_path))      # é uma pasta: não pode levantar
    r.registrar(r.rotear("cria um site"), "cria um site")


# --- Codex como reserva do Claude ocupado (esteira codex-reserva) ------------------

def _reserva(fala, ocupado=True, pronto=True, ligado=True):
    return r.reserva_codex(r.rotear(fala), claude_ocupado=ocupado,
                           codex_pronto=pronto, ligado=ligado)


def test_analise_com_claude_ocupado_vai_ao_codex_so_para_leitura():
    i = _reserva("analisa o projeto dervs-voz")
    assert i == {"tipo": "codex_leitura", "pedido": "analisa o projeto dervs-voz", "projeto": "dervs-voz"}


def test_projeto_no_fim_da_frase_vai_como_projeto_sem_pergunta_solta():
    i = _reserva("investiga o bug do login no projeto dervs voz")
    assert i == {"tipo": "codex_leitura", "pedido": "investiga o bug do login", "projeto": "dervs voz"}


@pytest.mark.parametrize("fala", [
    "verifica meu PC",
    "analisa meus documentos",
    "analisa a pasta ~/.ssh",
    "audita o AppData",
])
def test_sem_projeto_nunca_desvia_porque_o_codex_enxergaria_o_disco_todo(fala):
    assert r.rotear(fala)["intencao"] == "trabalho"
    assert _reserva(fala) is None


@pytest.mark.parametrize("ocupado,pronto,ligado", [
    (False, True, True),     # Claude livre: ele atende
    (True, False, True),     # Codex fora ou ocupado
    (True, True, False),     # dono desligou a reserva
])
def test_sem_todas_as_condicoes_nao_desvia(ocupado, pronto, ligado):
    assert _reserva("analisa o projeto dervs-voz", ocupado, pronto, ligado) is None


@pytest.mark.parametrize("fala", [
    "pede pro Claude analisar o projeto dervs-voz",
    "Claude, verifica meu PC",
    "Dervs, pergunta pro Claude o que tem de errado no login",
    "analisa o projeto dervs-voz com o Claude",
])
def test_quem_cita_o_claude_nunca_e_desviado(fala):
    assert r.rotear(fala)["executor"] == "claude_code"
    assert _reserva(fala) is None


@pytest.mark.parametrize("fala", ["conserta o bug do login", "cria um site para a minha clínica"])
def test_pedido_de_desenvolver_nunca_vai_ao_codex_por_desvio(fala):
    assert r.rotear(fala)["intencao"] == "desenvolver"
    assert _reserva(fala) is None


def test_planejador_e_entrada_torta_nao_desviam():
    assert _reserva("que horas são") is None
    assert r.reserva_codex(None, claude_ocupado=True, codex_pronto=True, ligado=True) is None
    assert r.reserva_codex({}, claude_ocupado=True, codex_pronto=True, ligado=True) is None


def test_dica_do_codex_so_para_desenvolver():
    assert "pede pro Codex" in r.dica_codex(r.rotear("conserta o bug do login"), ligado=True)
    assert r.dica_codex(r.rotear("conserta o bug do login"), ligado=False) == ""
    assert r.dica_codex(r.rotear("analisa o projeto dervs-voz"), ligado=True) == ""


def test_desvio_fica_no_registro_com_o_motivo(tmp_path, monkeypatch):
    log = tmp_path / "roteamento.jsonl"
    monkeypatch.setenv("DERVS_ROTEAMENTO_LOG", str(log))
    r.registrar(r.DECISAO_RESERVA, "analisa o projeto dervs-voz")
    linha = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert linha["executor"] == "codex"
    assert linha["motivo"] == "claude ocupado: reserva automática"
    assert linha["fala"] == "analisa o projeto dervs-voz"


# --- destino: cérebro do DERVS ou harness emprestado de um projeto (15/10) --------------

@pytest.fixture
def raizes(tmp_path):
    for nome in ("dervs-voz", "grimoire", "medconsultoria"):
        (tmp_path / nome).mkdir()
    return [str(tmp_path)]


@pytest.mark.parametrize("fala", [
    "no projeto grimoire, corrige o bug do login",
    "corrige o bug do login no projeto grimoire",
    "Dervs, conserta a tela de cadastro do projeto grimoire",
    "pede pro Claude analisar o código no projeto grimoire",
    "analisa o projeto grimoire",
])
def test_trabalho_com_projeto_empresta_o_harness_na_pasta_do_projeto(fala, raizes):
    d = r.destino(fala, raizes)
    assert d["executor"] == "claude_code" and d["perfil"] == "projeto"
    assert d["projeto"] == str(__import__("pathlib").Path(raizes[0]) / "grimoire")


def test_desenvolver_sem_projeto_pergunta_qual_e_nao_empresta(raizes):
    d = r.destino("cria um site para a minha clínica", raizes)
    assert d["executor"] == "falar" and "projeto" in d["fala"].lower()
    assert d.get("projeto") is None


def test_projeto_que_nao_existe_e_dito_em_voz(raizes):
    d = r.destino("corrige o bug no projeto xyzw", raizes)
    assert d["executor"] == "falar" and "xyzw" in d["fala"]


@pytest.mark.parametrize("fala,executor", [
    ("abre a calculadora", "planejador"),
    ("verifica meu PC", "claude_code"),
    ("que horas são", "planejador"),
])
def test_o_resto_fica_no_cerebro_do_dervs(fala, executor, raizes):
    d = r.destino(fala, raizes)
    assert d["executor"] == executor and d["perfil"] == "dervs" and d.get("projeto") is None


def test_projeto_citado_sem_pedido_de_trabalho_nao_empresta(raizes):
    d = r.destino("no projeto grimoire, que horas são", raizes)
    assert d["perfil"] == "dervs" and d.get("projeto") is None


def test_destino_sem_raizes_e_com_entrada_torta_nao_quebra():
    assert r.destino("", [])["perfil"] == "dervs"
    assert r.destino("corrige o bug no projeto grimoire", [])["executor"] == "falar"
