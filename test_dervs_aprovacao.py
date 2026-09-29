#!/usr/bin/env python3
"""Testes do motor de aprovação e do executor seguro (onda C da central do PC).

A exigência do dono, palavra por palavra: "Não pode apagar nada sem antes
analisar tudo profundamente e me dizer o que é cada coisa que quer apagar.
Sempre com minha aprovação." Estes testes são a prova automatizada do critério
4 do briefing: a ação RECUSA sem aprovação registrada — e também com aprovação
vencida, reaproveitada, de voz, de item fora do relatório, com o arquivo mudado
depois da análise, em caminho protegido ou através de junção.

Todo arquivo que estes testes tocam mora em `tmp_path`. A quarentena também.

Rodar: python -m pytest test_dervs_aprovacao.py -q
"""
import json
import os
import sys

import pytest

import dervs_aprovacao as ap
import dervs_executor_seguro as ex
import dervs_log_acoes as log_acoes

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="motor do Windows")

POR_QUE = "É sobra de instalação antiga; nenhum programa aberto usa este arquivo."


class Relogio:
    def __init__(self):
        self.agora = 1_900_000_000.0

    def __call__(self):
        return self.agora


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def motor(tmp_path, relogio):
    extras = tmp_path / "caminhos_protegidos.json"
    extras.write_text(json.dumps({"caminhos": []}), encoding="utf-8")
    return ap.Motor(pasta=str(tmp_path / "dervs-local"), arquivo_extras=str(extras),
                    relogio=relogio)


@pytest.fixture
def alvos(tmp_path):
    pasta = tmp_path / "alvos"
    pasta.mkdir()
    return pasta


def _arquivo(pasta, nome="sobra.tmp", conteudo="conteúdo velho\n" * 20):
    caminho = pasta / nome
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def _propor(motor, *caminhos, acao="quarentena", **extra):
    itens = [dict({"acao": acao, "alvo": str(c), "por_que_seguro": POR_QUE}, **extra)
             for c in caminhos]
    return motor.analisar(itens, origem="claude")


def _aprovar(motor, rel, ids=None, **kw):
    ids = ids if ids is not None else [i["id"] for i in rel["itens"]]
    kw.setdefault("origem", "clique")
    kw.setdefault("cartao", motor.abrir_cartao(rel["id"]))
    return motor.aprovar(rel["id"], ids, **kw)


def _fluxo_ate_aprovar(motor, *caminhos, **kw):
    rel = _propor(motor, *caminhos, **kw)
    assert rel["itens"], rel["recusados"]
    res = _aprovar(motor, rel)
    assert res["ok"], res
    return rel, res["registro"]


def _executar(motor, registro, item_id="item-1", origem="clique"):
    return ex.executar(motor, registro["id"], registro["token"], item_id, origem=origem)


# ------------------------------------------------------------ o relatório

def test_relatorio_tem_cada_campo_por_item(motor, alvos):
    f = _arquivo(alvos)
    rel = _propor(motor, f, explicacao="Arquivo que o instalador do Chrome deixou.")
    item = rel["itens"][0]
    for campo in ("id", "acao", "caminho_real", "tipo", "tamanho_bytes", "data", "o_que_e",
                  "por_que_seguro", "o_que_muda", "como_desfazer", "reversivel", "risco",
                  "impressao"):
        assert item[campo] not in (None, ""), campo
    assert item["caminho_real"] == os.path.realpath(str(f))
    assert item["tipo"] == "arquivo"
    assert item["tamanho_bytes"] == f.stat().st_size
    assert "temporário" in item["o_que_e"]            # regra determinística
    assert "instalador do Chrome" in item["o_que_e"]  # explicação do Claude
    assert item["reversivel"] is True
    assert rel["total_bytes"] == f.stat().st_size
    gravado = json.loads(open(os.path.join(motor.pasta, "relatorios", rel["id"] + ".json"),
                              encoding="utf-8").read())
    assert gravado["itens"][0]["impressao"] == item["impressao"]


def test_item_sem_por_que_seguro_e_recusado_na_criacao(motor, alvos):
    f = _arquivo(alvos)
    rel = motor.analisar([{"acao": "quarentena", "alvo": str(f), "por_que_seguro": "  "}],
                         origem="claude")
    assert rel["itens"] == []
    assert "por que" in rel["recusados"][0]["motivo"]


def test_acao_desconhecida_e_recusada_na_criacao(motor, alvos):
    rel = _propor(motor, _arquivo(alvos), acao="apagar_direto")
    assert rel["itens"] == [] and rel["recusados"]


def test_caminho_protegido_nem_entra_no_relatorio(motor):
    rel = _propor(motor, os.environ.get("SystemRoot", r"C:\Windows") + r"\win.ini")
    assert rel["itens"] == []
    assert "protegid" in rel["recusados"][0]["motivo"] or "sistema" in rel["recusados"][0]["motivo"]


def test_pasta_com_juncao_dentro_nem_entra_no_relatorio(motor, alvos):
    import _winapi
    (alvos / "cache").mkdir()
    _winapi.CreateJunction(os.environ.get("SystemRoot", r"C:\Windows"),
                           str(alvos / "cache" / "j"))
    rel = _propor(motor, alvos / "cache")
    assert rel["itens"] == []
    assert "junção" in rel["recusados"][0]["motivo"] or "atalho" in rel["recusados"][0]["motivo"]


def test_risco_nunca_desce_do_que_o_motor_calcula(motor, alvos):
    (alvos / "pasta").mkdir()
    _arquivo(alvos / "pasta")
    rel = _propor(motor, alvos / "pasta", risco="baixo")
    assert rel["itens"][0]["risco"] in ("medio", "alto")


# ------------------------------------------------------------ a aprovação

def test_aprovacao_de_voz_e_recusada(motor, alvos):
    rel = _propor(motor, _arquivo(alvos))
    res = _aprovar(motor, rel, origem="voz")
    assert res["ok"] is False and "clique" in res["motivo"]


@pytest.mark.parametrize("origem", ["claude", "api", "CLIQUE", " clique", "", None])
def test_aprovacao_de_qualquer_origem_que_nao_clique_e_recusada(motor, alvos, origem):
    rel = _propor(motor, _arquivo(alvos))
    assert _aprovar(motor, rel, origem=origem)["ok"] is False


def test_aprovacao_sem_cartao_valido_e_recusada(motor, alvos):
    rel = _propor(motor, _arquivo(alvos))
    assert _aprovar(motor, rel, cartao="inventado")["ok"] is False
    assert _aprovar(motor, rel, cartao=None)["ok"] is False


def test_nao_existe_aprovar_tudo_as_cegas(motor, alvos):
    rel = _propor(motor, _arquivo(alvos))
    for ids in ([], "*", "todos", None, ["item-1", "item-1"]):
        assert motor.aprovar(rel["id"], ids, origem="clique",
                             cartao=motor.abrir_cartao(rel["id"]))["ok"] is False


def test_aprovacao_de_item_fora_do_relatorio_e_recusada(motor, alvos):
    rel = _propor(motor, _arquivo(alvos))
    res = _aprovar(motor, rel, ids=["item-1", "item-99"])
    assert res["ok"] is False and "item-99" in res["motivo"]


def test_aprovacao_de_relatorio_inexistente_e_recusada(motor):
    res = motor.aprovar("nao-existe", ["item-1"], origem="clique", cartao="x")
    assert res["ok"] is False


def test_risco_alto_exige_dupla_confirmacao(motor, alvos):
    rel = _propor(motor, _arquivo(alvos), risco="alto")
    assert rel["itens"][0]["risco"] == "alto"
    assert _aprovar(motor, rel)["ok"] is False
    assert _aprovar(motor, rel, dupla_confirmacao=["item-1"])["ok"] is True


def test_exclusao_em_massa_em_pasta_pessoal_e_recusada(tmp_path, relogio):
    perfil = tmp_path / "Usuarios" / "dono"
    docs = perfil / "Documents"
    docs.mkdir(parents=True)
    ambiente = {"USERPROFILE": str(perfil), "APPDATA": str(perfil / "AppData" / "Roaming"),
                "LOCALAPPDATA": str(perfil / "AppData" / "Local")}
    m = ap.Motor(pasta=str(perfil / "AppData" / "Local" / "dervs"), ambiente=ambiente,
                 arquivo_extras=str(tmp_path / "nao-existe.json"), relogio=relogio)
    arquivos = [_arquivo(docs, f"f{n}.txt") for n in range(5)]
    rel = _propor(m, *arquivos)
    assert len(rel["itens"]) == 5
    todos = [i["id"] for i in rel["itens"]]
    assert all(i["risco"] == "alto" for i in rel["itens"])     # pasta pessoal = risco alto
    res = _aprovar(m, rel, dupla_confirmacao=todos)             # 5 de uma vez: não
    assert res["ok"] is False and "massa" in res["motivo"]
    assert _aprovar(m, rel, ids=["item-1"], dupla_confirmacao=["item-1"])["ok"] is True
    rel_pasta = _propor(m, docs)                                 # a pasta inteira: nunca
    assert rel_pasta["itens"] == []


# ------------------------------------------------------------ o executor: as recusas

def test_executor_recusa_sem_registro(motor, alvos):
    f = _arquivo(alvos)
    _propor(motor, f)
    for reg_id, token in ((None, None), ("", ""), ("inventado", "inventado")):
        res = ex.executar(motor, reg_id, token, "item-1", origem="clique")
        assert res["ok"] is False and "aprova" in res["motivo"]
    assert f.exists()


def test_executor_recusa_token_errado(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = ex.executar(motor, reg["id"], "chute", "item-1", origem="clique")
    assert res["ok"] is False and f.exists()


def test_executor_recusa_com_impressao_mudada(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    f.write_text("outro conteúdo, trocado depois da análise", encoding="utf-8")
    res = _executar(motor, reg)
    assert res["ok"] is False and "mudou" in res["motivo"]
    assert f.exists()


def test_executor_recusa_mesmo_tamanho_e_data_com_conteudo_trocado(motor, alvos):
    f = _arquivo(alvos, conteudo="A" * 1000)
    st = f.stat()
    _, reg = _fluxo_ate_aprovar(motor, f)
    f.write_text("B" * 1000, encoding="utf-8")
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    res = _executar(motor, reg)
    assert res["ok"] is False and "mudou" in res["motivo"]


def test_executor_recusa_aprovacao_vencida(motor, alvos, relogio):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    relogio.agora += 15 * 60 + 1
    res = _executar(motor, reg)
    assert res["ok"] is False and "venc" in res["motivo"]
    assert f.exists()


def test_executor_aceita_antes_de_vencer(motor, alvos, relogio):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    relogio.agora += 14 * 60
    assert _executar(motor, reg)["ok"] is True


def test_executor_recusa_em_caminho_que_ficou_protegido(motor, alvos, tmp_path):
    """O dono acrescentou a pasta à lista DEPOIS de aprovar: vale a lista de agora."""
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    (tmp_path / "caminhos_protegidos.json").write_text(
        json.dumps({"caminhos": [str(alvos)]}), encoding="utf-8")
    res = _executar(motor, reg)
    assert res["ok"] is False and "proteg" in res["motivo"]
    assert f.exists()


def test_executor_recusa_em_juncao(motor, alvos):
    """Depois da análise, a pasta foi trocada por uma junção que aponta para
    outra com um arquivo idêntico. O caminho é o mesmo; o lugar, não."""
    import _winapi
    (alvos / "a").mkdir()
    f = _arquivo(alvos / "a")
    _, reg = _fluxo_ate_aprovar(motor, f)
    os.rename(alvos / "a", alvos / "b")
    _winapi.CreateJunction(str(alvos / "b"), str(alvos / "a"))
    res = _executar(motor, reg)
    assert res["ok"] is False
    assert "junção" in res["motivo"] or "atalho" in res["motivo"]
    assert (alvos / "b" / "sobra.tmp").exists()


def test_executor_recusa_pasta_que_ganhou_juncao_dentro(motor, alvos):
    import _winapi
    (alvos / "cache").mkdir()
    _arquivo(alvos / "cache")
    _, reg = _fluxo_ate_aprovar(motor, alvos / "cache")
    (alvos / "alvo-real").mkdir()
    _winapi.CreateJunction(str(alvos / "alvo-real"), str(alvos / "cache" / "j"))
    res = _executar(motor, reg)
    assert res["ok"] is False
    assert (alvos / "cache" / "sobra.tmp").exists()


def test_executor_recusa_origem_voz(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg, origem="voz")
    assert res["ok"] is False and "clique" in res["motivo"]
    assert f.exists()


def test_executor_recusa_item_fora_do_relatorio(motor, alvos):
    f1, f2 = _arquivo(alvos, "a.tmp"), _arquivo(alvos, "b.tmp")
    rel = _propor(motor, f1, f2)
    reg = _aprovar(motor, rel, ids=["item-1"])["registro"]
    for item_id in ("item-2", "item-99", "../item-1", None):
        res = _executar(motor, reg, item_id=item_id)
        assert res["ok"] is False
    assert f2.exists()


def test_executor_recusa_aprovacao_reutilizada(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    assert _executar(motor, reg)["ok"] is True
    _arquivo(alvos)  # o mesmo arquivo reaparece, idêntico
    res = _executar(motor, reg)
    assert res["ok"] is False and "usad" in res["motivo"]
    assert f.exists()


def test_executor_recusa_motor_falso(alvos):
    class Falso:
        pasta = str(alvos)

        def consumir_aprovacao(self, *a, **k):
            return {"ok": True}
    res = ex.executar(Falso(), "x", "y", "item-1", origem="clique")
    assert res["ok"] is False


def test_executor_recusa_subclasse_do_motor_que_aprova_tudo(tmp_path, alvos):
    class Cumplice(ap.Motor):
        def consumir_aprovacao(self, *a, **k):
            return {"ok": True, "item": {}, "registro": {}}
    f = _arquivo(alvos)
    res = ex.executar(Cumplice(pasta=str(tmp_path / "cumplice")), "x", "y", "item-1",
                      origem="clique")
    assert res["ok"] is False and f.exists()


def test_registro_devolvido_nao_altera_o_motor(motor, alvos):
    """Mexer no dicionário devolvido (trocar alvo, esticar prazo) não muda o
    que o motor guardou."""
    f, outro = _arquivo(alvos, "a.tmp"), _arquivo(alvos, "outro.tmp")
    rel, reg = _fluxo_ate_aprovar(motor, f)
    rel["itens"][0]["alvo"] = str(outro)
    rel["itens"][0]["caminho_real"] = str(outro)
    reg["expira_em"] = 10 ** 12
    assert _executar(motor, reg)["ok"] is True
    assert outro.exists() and not f.exists()


# ------------------------------------------------------------ quarentena e desfazer

def test_quarentena_e_desfazer_de_arquivo(motor, alvos):
    f = _arquivo(alvos)
    original = f.read_bytes()
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    assert res["ok"] is True, res
    assert not f.exists()
    guardado = os.path.join(motor.pasta, "quarentena", res["desfazer_id"])
    manifesto = json.loads(open(os.path.join(guardado, "manifesto.json"), encoding="utf-8").read())
    assert manifesto["origem"] == os.path.realpath(str(f))
    assert manifesto["estado"] == "em_quarentena"
    assert os.path.commonpath([guardado, str(alvos)]) != str(alvos)  # não ficou na origem
    volta = ex.desfazer(motor, res["desfazer_id"], origem="clique")
    assert volta["ok"] is True, volta
    assert f.read_bytes() == original


def test_quarentena_e_desfazer_de_pasta(motor, alvos):
    (alvos / "cache" / "sub").mkdir(parents=True)
    _arquivo(alvos / "cache", "a.tmp")
    _arquivo(alvos / "cache" / "sub", "b.tmp")
    _, reg = _fluxo_ate_aprovar(motor, alvos / "cache")
    res = _executar(motor, reg)
    assert res["ok"] is True and not (alvos / "cache").exists()
    assert ex.desfazer(motor, res["desfazer_id"], origem="clique")["ok"] is True
    assert (alvos / "cache" / "sub" / "b.tmp").exists()


def test_desfazer_nunca_sobrescreve(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    f.write_text("arquivo novo que o dono criou depois", encoding="utf-8")
    volta = ex.desfazer(motor, res["desfazer_id"], origem="clique")
    assert volta["ok"] is False
    assert f.read_text(encoding="utf-8") == "arquivo novo que o dono criou depois"


def test_desfazer_so_uma_vez_e_so_por_clique(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    assert ex.desfazer(motor, res["desfazer_id"], origem="voz")["ok"] is False
    assert ex.desfazer(motor, res["desfazer_id"], origem="clique")["ok"] is True
    assert ex.desfazer(motor, res["desfazer_id"], origem="clique")["ok"] is False


@pytest.mark.parametrize("desfazer_id", ["..", r"..\..\x", "C:\\Windows", "", None, "a/b"])
def test_desfazer_com_id_hostil_e_recusado(motor, desfazer_id):
    assert ex.desfazer(motor, desfazer_id, origem="clique")["ok"] is False


def test_desfazer_com_manifesto_adulterado_para_pasta_protegida_e_recusado(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    caminho = os.path.join(motor.pasta, "quarentena", res["desfazer_id"], "manifesto.json")
    manifesto = json.loads(open(caminho, encoding="utf-8").read())
    manifesto["origem"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "sobra.tmp")
    with open(caminho, "w", encoding="utf-8") as saida:
        json.dump(manifesto, saida)
    assert ex.desfazer(motor, res["desfazer_id"], origem="clique")["ok"] is False


def test_desfazer_recusa_conteudo_trocado_na_quarentena(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    guardado = os.path.join(motor.pasta, "quarentena", res["desfazer_id"], "conteudo", "sobra.tmp")
    with open(guardado, "w", encoding="utf-8") as saida:
        saida.write("conteúdo plantado")
    assert ex.desfazer(motor, res["desfazer_id"], origem="clique")["ok"] is False
    assert not f.exists()


# ------------------------------------------------------------ ações que não são arquivo

@pytest.mark.parametrize("acao", ["desinstalar", "desativar_inicializacao", "atualizar",
                                  "instalar", "alterar_servico", "alterar_registro",
                                  "alterar_firewall", "alterar_config"])
def test_acao_de_sistema_exige_a_mesma_aprovacao_e_nao_esta_implementada(motor, acao):
    rel = motor.analisar([{"acao": acao, "alvo": "Programa.Exemplo", "versao": "1.2.3",
                           "por_que_seguro": POR_QUE}], origem="claude")
    item = rel["itens"][0]
    assert item["reversivel"] is False and item["impressao"]
    sem = ex.executar(motor, None, None, "item-1", origem="clique")
    assert sem["ok"] is False and "aprova" in sem["motivo"]
    reg = _aprovar(motor, rel, dupla_confirmacao=["item-1"])["registro"]
    assert _executar(motor, reg, origem="voz")["ok"] is False
    res = _executar(motor, reg)
    assert res["ok"] is False and "não implementad" in res["motivo"]
    assert _executar(motor, reg)["ok"] is False  # a aprovação foi gasta


def test_lixeira_passa_pelas_travas_e_nao_esta_implementada(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f, acao="lixeira")
    res = _executar(motor, reg)
    assert res["ok"] is False and "não implementad" in res["motivo"]
    assert f.exists()


# ------------------------------------------------------------ o registro de tudo

def test_cada_passo_fica_no_log_encadeado(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    _executar(motor, reg, origem="voz")
    res = _executar(motor, reg)
    ex.desfazer(motor, res["desfazer_id"], origem="clique")
    arquivo = os.path.join(motor.pasta, "acoes.jsonl")
    eventos = [json.loads(linha)["evento"] for linha in open(arquivo, encoding="utf-8")]
    for evento in ("analisou", "propos", "aprovou", "recusou", "executou", "desfez"):
        assert evento in eventos, evento
    assert log_acoes.LogAcoes(arquivo).verificar_cadeia()[0] is True
    texto = open(arquivo, encoding="utf-8").read()
    assert reg["token"] not in texto  # a senha de uso único nunca vai para o log
