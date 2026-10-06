"""Segundo cérebro por voz (`dervs_cofre_voz`): critério 5 do briefing."""
import pytest

import dervs_cofre as cofre
import dervs_cofre_voz as voz


@pytest.fixture
def cv(tmp_path):
    return cofre.Cofre(tmp_path / "cofre")


# ------------------------------------------------------------ interpretar
@pytest.mark.parametrize("fala,texto", [
    ("Anota que preciso ligar para a Maria amanhã", "preciso ligar para a Maria amanhã"),
    ("DERVS, anota que o disco do servidor encheu.", "o disco do servidor encheu."),
    ("anote isso: reunião às 15h com o contador", "reunião às 15h com o contador"),
    ("Lembra que a senha do wifi está no post-it", "a senha do wifi está no post-it"),
    ("não esquece que o dentista é na terça", "o dentista é na terça"),
    ("Ei DERVS, por favor anota que comprei o domínio", "comprei o domínio"),
])
def test_anotar(fala, texto):
    r = voz.interpretar(fala)
    assert r == {"tipo": "cofre_anotar", "texto": texto, "privado": False}


@pytest.mark.parametrize("fala", [
    "anota em privado que o exame deu alteração",
    "anota privado que o exame deu alteração",
    "Anota em segredo que o exame deu alteração",
])
def test_anotar_privado(fala):
    r = voz.interpretar(fala)
    assert r["tipo"] == "cofre_anotar" and r["privado"] is True
    assert r["texto"] == "o exame deu alteração"


@pytest.mark.parametrize("fala,consulta", [
    ("o que eu sei sobre o servidor?", "o servidor"),
    ("DERVS, o que eu anotei sobre dentista", "dentista"),
    ("O que eu decidi sobre o banco de dados?", "o banco de dados"),
    ("procura nas minhas notas disco cheio", "disco cheio"),
    ("busca no meu cofre por contador", "contador"),
    ("pesquisa nas minhas anotações sobre férias", "férias"),
])
def test_buscar(fala, consulta):
    assert voz.interpretar(fala) == {"tipo": "cofre_buscar", "consulta": consulta}


@pytest.mark.parametrize("fala", ["abre o cofre", "abre meu cofre", "DERVS abre minhas notas"])
def test_abrir(fala):
    assert voz.interpretar(fala) == {"tipo": "cofre_abrir"}


@pytest.mark.parametrize("fala", [
    "me lembra em 10 minutos de tomar água",       # é do módulo de lembretes
    "me lembra de ligar para o cliente",
    "que horas são",
    "abre o projeto dervs-voz",
    "anota",                                       # sem conteúdo
    "anota que",
    "o que eu sei",                                # sem assunto
    "procura arquivo no computador",               # não é nas notas
    "",
    None,
])
def test_nao_e_do_cofre(fala):
    assert voz.interpretar(fala) is None


# ------------------------------------------------------------ executar
def test_anotar_grava_em_entrada_e_acha_logo(cv):
    fala = voz.executar({"tipo": "cofre_anotar", "texto": "preciso renovar o domínio dervs", "privado": False}, cv)
    assert fala.startswith("Anotei")
    achados = cv.buscar("domínio")
    assert achados and achados[0]["caminho"].startswith("entrada/")
    assert "preciso renovar" in cv.ler(achados[0]["caminho"])["corpo"]


def test_anotar_privado_vai_para_pasta_privado(cv):
    fala = voz.executar({"tipo": "cofre_anotar", "texto": "exame alterado do cliente", "privado": True}, cv)
    assert "privado" in fala.lower()
    assert cv.buscar("exame")[0]["caminho"].startswith("privado/")


def test_anotar_recusa_segredo_e_nao_grava(cv):
    fala = voz.executar({"tipo": "cofre_anotar", "texto": "a chave é " + "s" + "k-" + "abcdefghijklmnopqrstuvwxyz0123456789",
                         "privado": False}, cv)
    assert "segredo" in fala.lower()
    cv.reindexar()
    assert cv.contagem() == 0


def test_buscar_fala_titulo_e_trecho_curto(cv):
    cv.escrever("Dentista", "consulta do dentista marcada para terça às 9h", pasta="pessoas")
    cv.reindexar()
    fala = voz.executar({"tipo": "cofre_buscar", "consulta": "dentista"}, cv)
    assert "Dentista" in fala and "terça" in fala
    assert len(fala) < 300


def test_buscar_nota_privada_nao_fala_nem_titulo_nem_trecho(cv):
    # a voz de resposta pode ser de nuvem: título de nota costuma nascer do conteúdo, então também não sai
    cv.escrever("Diagnóstico", "resultado reservado do paciente joao", pasta="privado")
    cv.reindexar()
    fala = voz.executar({"tipo": "cofre_buscar", "consulta": "paciente"}, cv)
    assert "Diagnóstico" not in fala and "joao" not in fala and "reservado" not in fala
    assert "privada" in fala.lower()


def test_buscar_mistura_publica_e_privada(cv):
    cv.escrever("Contador", "o contador pediu o balanço", pasta="pessoas")
    cv.escrever("Segredo", "o contador recebeu o valor combinado", pasta="privado")
    cv.reindexar()
    fala = voz.executar({"tipo": "cofre_buscar", "consulta": "contador"}, cv)
    assert "Contador" in fala and "valor combinado" not in fala and "Segredo" not in fala
    assert "1 nota privada" in fala


def test_buscar_nao_fala_trecho_com_segredo(cv):
    cv.escrever("Acesso", "senha: abcdefghij123 do servidor", pasta="entrada")
    cv.reindexar()
    fala = voz.executar({"tipo": "cofre_buscar", "consulta": "servidor"}, cv)
    assert "abcdefghij123" not in fala


def test_buscar_sem_resultado(cv):
    fala = voz.executar({"tipo": "cofre_buscar", "consulta": "unicornio"}, cv)
    assert "não achei" in fala.lower() and "unicornio" in fala


def test_abrir_chama_o_explorer_com_a_pasta(cv):
    chamadas = []
    fala = voz.executar({"tipo": "cofre_abrir"}, cv, abrir_pasta=chamadas.append)
    assert chamadas == [str(cv.raiz)] and "cofre" in fala.lower()


def test_abrir_sem_abridor_nao_quebra(cv):
    assert "cofre" in voz.executar({"tipo": "cofre_abrir"}, cv).lower()


def test_intencao_desconhecida_devolve_none(cv):
    assert voz.executar({"tipo": "outra"}, cv) is None


@pytest.mark.parametrize("fala", [
    "anotei o recado com a Maria",             # "anotei" não é "anota"
    "anotações do mês passado",
    "lembra que horas são?",                   # pergunta
    "anota isso",                              # sem conteúdo
    "abre o projeto cofre-de-banco",
])
def test_falsos_positivos_ficam_de_fora(fala):
    assert voz.interpretar(fala) is None


@pytest.mark.parametrize("fala", ["abrir o cofre", "abre as notas"])
def test_abrir_variantes(fala):
    assert voz.interpretar(fala) == {"tipo": "cofre_abrir"}


def test_senha_falada_nao_e_anotada(cv):
    fala = voz.executar({"tipo": "cofre_anotar", "texto": "a senha do wifi é bananas123", "privado": False}, cv)
    assert "segredo" in fala.lower()


def test_abriu_do_reconhecedor_vale_como_abre():
    assert voz.interpretar("Dervs abriu o cofre.") == {"tipo": "cofre_abrir"}
