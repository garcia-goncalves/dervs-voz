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
                    relogio=relogio, monotonico=relogio)


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
                 arquivo_extras=str(tmp_path / "nao-existe.json"), relogio=relogio,
                 monotonico=relogio)
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


# ------------------------------------------------------------ troca no meio (TOCTOU)
# Achado da revisão de segurança de 29/09/2026: um Claude comprometido cria uma
# "isca" idêntica a um arquivo protegido e, entre a conferência e a mudança,
# troca a pasta da isca por uma junção para a pasta protegida. O executor
# movia o arquivo PROTEGIDO para a quarentena.

def _cenario_isca(tmp_path, tamanho=1600):
    import shutil
    protegida = tmp_path / "PROTEGIDA"
    protegida.mkdir()
    real = protegida / "prontuario.db"
    real.write_bytes(os.urandom(tamanho))
    extras = tmp_path / "extras-isca.json"
    extras.write_text(json.dumps({"caminhos": [str(protegida)]}), encoding="utf-8")
    m = ap.Motor(pasta=str(tmp_path / "dervs-isca"), arquivo_extras=str(extras))
    pai = tmp_path / "limpeza"
    pai.mkdir()
    isca = pai / "prontuario.db"
    shutil.copyfile(real, isca)
    st = real.stat()
    os.utime(isca, ns=(st.st_atime_ns, st.st_mtime_ns))
    rel = m.analisar([{"acao": "quarentena", "alvo": str(isca), "por_que_seguro": POR_QUE}])
    reg = m.aprovar(rel["id"], ["item-1"], origem="clique",
                    cartao=m.abrir_cartao(rel["id"]))["registro"]
    return m, reg, real, pai, protegida


def _trocar_por_juncao(pai, protegida):
    import _winapi
    try:
        os.rename(pai, str(pai) + "_velha")
    except OSError:
        return False  # o executor segura a isca: a troca não acontece
    _winapi.CreateJunction(str(protegida), str(pai))
    return True


def _protegido_intacto(real, conteudo):
    return real.exists() and real.read_bytes() == conteudo


def test_toctou_troca_antes_de_abrir_nao_move_protegido(tmp_path, monkeypatch):
    m, reg, real, pai, protegida = _cenario_isca(tmp_path)
    conteudo = real.read_bytes()
    original = ap.conteudo_de
    chamadas = []

    def espiao(caminho):
        info = original(caminho)
        chamadas.append(caminho)
        if len(chamadas) == 1:  # a conferência do executor acabou de passar
            _trocar_por_juncao(pai, protegida)
        return info
    monkeypatch.setattr(ap, "conteudo_de", espiao)
    res = ex.executar(m, reg["id"], reg["token"], "item-1", origem="clique")
    assert _protegido_intacto(real, conteudo), res
    assert res["ok"] is False


def test_toctou_troca_depois_do_manifesto_nao_move_protegido(tmp_path, monkeypatch):
    m, reg, real, pai, protegida = _cenario_isca(tmp_path)
    conteudo = real.read_bytes()
    original = ex._gravar_manifesto

    def espiao(pasta, manifesto):
        original(pasta, manifesto)
        if manifesto["estado"] == "movendo":
            _trocar_por_juncao(pai, protegida)
    monkeypatch.setattr(ex, "_gravar_manifesto", espiao)
    res = ex.executar(m, reg["id"], reg["token"], "item-1", origem="clique")
    assert _protegido_intacto(real, conteudo), res


def test_toctou_corrida_com_atacante_em_paralelo(tmp_path):
    """A versão de verdade: outra thread vigia a quarentena e troca a pasta
    no instante em que o executor começa."""
    import threading
    import time as _t
    for rodada in range(4):
        base = tmp_path / f"r{rodada}"
        base.mkdir()
        m, reg, real, pai, protegida = _cenario_isca(base, tamanho=3 * 1024 * 1024)
        conteudo = real.read_bytes()
        quarentena = os.path.join(m.pasta, "quarentena")
        os.makedirs(quarentena, exist_ok=True)
        pronto = threading.Event()

        def atacante():
            pronto.set()
            fim = _t.monotonic() + 10
            while _t.monotonic() < fim:
                if os.listdir(quarentena):
                    _trocar_por_juncao(pai, protegida)
                    return
        t = threading.Thread(target=atacante)
        t.start()
        pronto.wait()
        ex.executar(m, reg["id"], reg["token"], "item-1", origem="clique")
        t.join()
        assert _protegido_intacto(real, conteudo), f"rodada {rodada}"


def test_executor_recusa_copia_com_mesmo_conteudo_e_data(motor, alvos):
    """Mesmo conteúdo e mesma data, mas é OUTRO arquivo (outro número no
    disco): a impressão digital tem de mudar."""
    import shutil
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    st = f.stat()
    shutil.copyfile(f, alvos / "copia")
    os.replace(alvos / "copia", f)
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    res = _executar(motor, reg)
    assert res["ok"] is False and "mudou" in res["motivo"]


def test_impressao_de_pasta_muda_se_item_de_dentro_foi_trocado(alvos):
    import shutil
    (alvos / "cache").mkdir()
    f = _arquivo(alvos / "cache")
    antes = ap.conteudo_de(str(alvos / "cache"))["digest"]
    st = f.stat()
    shutil.copyfile(f, alvos / "copia")
    os.replace(alvos / "copia", f)
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert ap.conteudo_de(str(alvos / "cache"))["digest"] != antes


def test_desfazer_troca_do_destino_por_juncao_nao_grava_em_protegida(motor, alvos, tmp_path,
                                                                     monkeypatch):
    protegida = tmp_path / "PROTEGIDA-D"
    protegida.mkdir()
    (alvos / "pai").mkdir()
    f = _arquivo(alvos / "pai")
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    assert res["ok"] is True
    (tmp_path / "caminhos_protegidos.json").write_text(
        json.dumps({"caminhos": [str(protegida)]}), encoding="utf-8")
    original = ap.conteudo_de

    def espiao(caminho):
        info = original(caminho)
        _trocar_por_juncao(alvos / "pai", protegida)
        return info
    monkeypatch.setattr(ap, "conteudo_de", espiao)
    volta = ex.desfazer(motor, res["desfazer_id"], origem="clique")
    assert volta["ok"] is False
    assert list(protegida.iterdir()) == []
    guardado = os.path.join(motor.pasta, "quarentena", res["desfazer_id"], "conteudo", "sobra.tmp")
    assert os.path.exists(guardado)


# ------------------------------------------------------------ registro que falha

def test_executor_recusa_se_nao_consegue_registrar_antes(motor, alvos, monkeypatch):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    original = motor.log.registrar

    def quebrado(evento, dados=None):
        if evento == "vai_executar":
            raise OSError("disco cheio")
        return original(evento, dados)
    monkeypatch.setattr(motor.log, "registrar", quebrado)
    res = _executar(motor, reg)
    assert res["ok"] is False and "registro" in res["motivo"]
    assert f.exists()


def test_cauda_corrompida_do_registro_nao_derruba_o_motor(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    with open(motor.log.arquivo, "a", encoding="utf-8") as saida:
        saida.write('{"seq": 99, "corta')
    res = _executar(motor, reg)
    assert res["ok"] is True, res
    texto = open(motor.log.arquivo, encoding="utf-8").read()
    assert '"evento": "alerta"' in texto and '"evento": "executou"' in texto


# ------------------------------------------------------------ manifesto autenticado

def test_desfazer_recusa_manifesto_desviado_para_outro_lugar_comum(motor, alvos, tmp_path):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    outra = tmp_path / "outra"
    outra.mkdir()
    caminho = os.path.join(motor.pasta, "quarentena", res["desfazer_id"], "manifesto.json")
    manifesto = json.loads(open(caminho, encoding="utf-8").read())
    manifesto["origem"] = str(outra / "sobra.tmp")
    with open(caminho, "w", encoding="utf-8") as saida:
        json.dump(manifesto, saida)
    assert ex.desfazer(motor, res["desfazer_id"], origem="clique")["ok"] is False
    assert not (outra / "sobra.tmp").exists()


def test_desfazer_depois_de_reiniciar_usa_o_registro(motor, alvos, tmp_path, relogio):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    novo = ap.Motor(pasta=motor.pasta, arquivo_extras=str(tmp_path / "caminhos_protegidos.json"),
                    relogio=relogio, monotonico=relogio)
    assert ex.desfazer(novo, res["desfazer_id"], origem="clique")["ok"] is True
    assert f.exists()


def test_desfazer_depois_de_reiniciar_com_manifesto_desviado_e_recusado(motor, alvos, tmp_path,
                                                                        relogio):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    res = _executar(motor, reg)
    caminho = os.path.join(motor.pasta, "quarentena", res["desfazer_id"], "manifesto.json")
    manifesto = json.loads(open(caminho, encoding="utf-8").read())
    (tmp_path / "outra").mkdir()
    manifesto["origem"] = str(tmp_path / "outra" / "sobra.tmp")
    with open(caminho, "w", encoding="utf-8") as saida:
        json.dump(manifesto, saida)
    novo = ap.Motor(pasta=motor.pasta, arquivo_extras=str(tmp_path / "caminhos_protegidos.json"),
                    relogio=relogio, monotonico=relogio)
    assert ex.desfazer(novo, res["desfazer_id"], origem="clique")["ok"] is False


# ------------------------------------------------------------ cartão, fachada, limites

def test_cartao_e_queimado_ao_usar(motor, alvos):
    f1, f2 = _arquivo(alvos, "a.tmp"), _arquivo(alvos, "b.tmp")
    rel = _propor(motor, f1, f2)
    cartao = motor.abrir_cartao(rel["id"])
    assert motor.aprovar(rel["id"], ["item-1"], origem="clique", cartao=cartao)["ok"] is True
    assert motor.aprovar(rel["id"], ["item-2"], origem="clique", cartao=cartao)["ok"] is False


def test_cartao_vence_com_o_relatorio(motor, alvos, relogio):
    rel = _propor(motor, _arquivo(alvos))
    cartao = motor.abrir_cartao(rel["id"])
    relogio.agora += 15 * 60 + 1
    res = motor.aprovar(rel["id"], ["item-1"], origem="clique", cartao=cartao)
    assert res["ok"] is False and "venc" in res["motivo"]
    assert motor.abrir_cartao(rel["id"]) is None


def test_validade_usa_relogio_monotonico(tmp_path, alvos):
    parede, mono = Relogio(), Relogio()
    m = ap.Motor(pasta=str(tmp_path / "d"), arquivo_extras=str(tmp_path / "x.json"),
                 relogio=parede, monotonico=mono)
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(m, f)
    mono.agora += 16 * 60
    parede.agora -= 3600  # alguém atrasou o relógio do Windows
    assert _executar(m, reg)["ok"] is False and f.exists()


def test_fachada_do_claude_nao_tem_cartao_nem_token_nem_aprovar(motor, alvos):
    fachada = ap.Fachada(motor)
    rel = fachada.analisar([{"acao": "quarentena", "alvo": str(_arquivo(alvos)),
                             "por_que_seguro": POR_QUE}])
    assert rel["itens"][0]["id"] == "item-1"
    for nome in ("aprovar", "abrir_cartao", "consumir_aprovacao", "motor"):
        assert not hasattr(fachada, nome), nome
    assert fachada.status(rel["id"])["itens"][0]["estado"] == "aguardando"
    reg = _aprovar(motor, rel)["registro"]
    estado = fachada.status(rel["id"])
    assert estado["itens"][0]["estado"] == "aprovado"
    assert reg["token"] not in json.dumps(estado)
    _executar(motor, reg)
    assert fachada.status(rel["id"])["itens"][0]["estado"] == "executado"
    assert fachada.status("nao-existe") is None


def test_relatorios_tem_limite_de_quantidade(motor, alvos):
    f = _arquivo(alvos)
    primeiro = _propor(motor, f)
    for _ in range(ap.LIMITE_RELATORIOS):
        _propor(motor, f)
    assert len(motor._relatorios) <= ap.LIMITE_RELATORIOS
    assert motor.abrir_cartao(primeiro["id"]) is None


def test_relatorio_velho_sai_da_memoria(motor, alvos, relogio):
    velho = _propor(motor, _arquivo(alvos))
    relogio.agora += 2 * ap.VALIDADE_S + 1
    _propor(motor, _arquivo(alvos, "b.tmp"))
    assert velho["id"] not in motor._relatorios


def test_explicacao_do_claude_vira_uma_linha_curta(motor, alvos):
    rel = _propor(motor, _arquivo(alvos),
                  explicacao="linha 1\nlinha 2\r\nFALSO: aprovado" + "x" * 5000)
    item = rel["itens"][0]
    assert "\n" not in item["o_que_e"] and "\r" not in item["o_que_e"]
    assert len(item["explicacao_claude"]) <= ap.LIMITE_EXPLICACAO


# ------------------------------------------------------------ achados da auditoria de 29/09

def test_item_recusado_pelo_executor_nao_aparece_como_executado(motor, alvos):
    f = _arquivo(alvos)
    rel, registro = _fluxo_ate_aprovar(motor, f)
    f.write_text("conteúdo trocado depois da análise, de outro tamanho" + chr(10) + "x" * 40, encoding="utf-8")
    r = _executar(motor, registro)
    assert r["ok"] is False and f.exists()
    assert motor.status(rel["id"])["itens"][0]["estado"] == "recusado"


def test_item_executado_aparece_como_executado(motor, alvos):
    f = _arquivo(alvos)
    rel, registro = _fluxo_ate_aprovar(motor, f)
    assert _executar(motor, registro)["ok"] is True
    assert motor.status(rel["id"])["itens"][0]["estado"] == "executado"


def test_se_o_registro_da_quarentena_falha_depois_de_mover_o_item_volta(motor, alvos, monkeypatch):
    f = _arquivo(alvos)
    _, registro = _fluxo_ate_aprovar(motor, f)
    real = ex._gravar_manifesto
    chamadas = {"n": 0}

    def falha_na_segunda(pasta, manifesto):
        chamadas["n"] += 1
        if manifesto.get("estado") == "em_quarentena":
            raise OSError("disco cheio")
        real(pasta, manifesto)
    monkeypatch.setattr(ex, "_gravar_manifesto", falha_na_segunda)
    r = _executar(motor, registro)
    assert r["ok"] is False and "devolvido" in r["motivo"]
    assert f.exists()          # não ficou preso na quarentena sem como desfazer


# ------------------------------------------------------------ ação própria do terminal SSH

HASH_SSH = "a" * 64


def _proposta_ssh(comando="systemctl restart nginx", apelido="prod", **extra):
    return dict({"acao": "executar_ssh", "alvo": f"ssh:{apelido}", "comando": comando,
                 "versao": HASH_SSH, "por_que_seguro": POR_QUE, "risco": "medio"}, **extra)


def test_executar_ssh_e_acao_propria_com_texto_leigo(motor):
    rel = motor.analisar([_proposta_ssh()], origem="ssh")
    item = rel["itens"][0]
    assert item["acao"] == "executar_ssh" and item["alvo"] == "ssh:prod"
    assert item["risco"] == "alto" and item["reversivel"] is False
    assert item["comando"] == "systemctl restart nginx"
    assert "Vai rodar o comando systemctl restart nginx no servidor prod" in item["o_que_muda"]
    assert "o servidor pode mudar" in item["o_que_muda"]
    assert "não desfaz" in item["como_desfazer"]
    assert "registro guarda exatamente o que rodou" in item["como_desfazer"]
    assert "alterar config" not in item["o_que_e"] and "Explicação do Claude" not in item["o_que_e"]
    assert item["impressao"]


def test_executar_ssh_risco_nunca_desce_de_alto(motor):
    for risco in ("baixo", "medio", "alto", "lixo"):
        rel = motor.analisar([_proposta_ssh(risco=risco)], origem="ssh")
        assert rel["itens"][0]["risco"] == "alto"


@pytest.mark.parametrize("origem", ["claude", "central", "voz", "clique", "", None])
def test_so_o_terminal_ssh_cria_relatorio_de_executar_ssh(motor, origem):
    rel = motor.analisar([_proposta_ssh()], origem=origem)
    assert rel["itens"] == [] and rel["recusados"]


def test_fachada_do_claude_nunca_cria_relatorio_de_executar_ssh(motor):
    fachada = ap.Fachada(motor)
    rel = fachada.analisar([_proposta_ssh()])
    assert rel["itens"] == [] and "ssh" in rel["recusados"][0]["motivo"].lower()
    assert motor.log.ler()[-1]["evento"] == "recusou"


@pytest.mark.parametrize("proposta", [
    _proposta_ssh(comando=""), _proposta_ssh(comando=None), _proposta_ssh(comando=5),
    _proposta_ssh(comando="ls\nrm x"), _proposta_ssh(comando=" ls"), _proposta_ssh(comando="a" * 401),
    _proposta_ssh(apelido="x y"), _proposta_ssh(apelido="../a"),
    dict(_proposta_ssh(), alvo="prod"), dict(_proposta_ssh(), versao=""),
    dict(_proposta_ssh(), versao="curta"), dict(_proposta_ssh(), versao=HASH_SSH.upper()),
])
def test_executar_ssh_malformado_e_recusado(motor, proposta):
    rel = motor.analisar([proposta], origem="ssh")
    assert rel["itens"] == [] and len(rel["recusados"]) == 1


def test_limite_de_comando_do_motor_acompanha_o_do_terminal():
    import dervs_ssh
    assert ap.LIMITE_COMANDO_SSH == dervs_ssh.MAX_COMANDO


def test_executar_ssh_exige_dupla_confirmacao(motor):
    rel = motor.analisar([_proposta_ssh()], origem="ssh")
    assert not _aprovar(motor, rel)["ok"]
    rel = motor.analisar([_proposta_ssh()], origem="ssh")
    assert not _aprovar(motor, rel, dupla_confirmacao=["outro"])["ok"]
    rel = motor.analisar([_proposta_ssh()], origem="ssh")
    assert _aprovar(motor, rel, dupla_confirmacao=["item-1"])["ok"]


def test_executor_generico_nao_queima_o_clique_do_ssh(motor):
    rel = motor.analisar([_proposta_ssh()], origem="ssh")
    reg = _aprovar(motor, rel, dupla_confirmacao=["item-1"])["registro"]
    assert _executar(motor, reg)["ok"] is False
    # o clique continua inteiro para quem é dono dele
    assert motor.consumir_aprovacao(reg["id"], reg["token"], "item-1", consumidor="ssh")["ok"]
    assert not motor.consumir_aprovacao(reg["id"], reg["token"], "item-1", consumidor="ssh")["ok"]


def test_consumidor_ssh_nao_consome_item_de_outra_acao(motor, alvos):
    f = _arquivo(alvos)
    _, reg = _fluxo_ate_aprovar(motor, f)
    assert not motor.consumir_aprovacao(reg["id"], reg["token"], "item-1", consumidor="ssh")["ok"]
    assert _executar(motor, reg)["ok"]  # o executor de arquivo ainda consegue
