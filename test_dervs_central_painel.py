#!/usr/bin/env python3
"""Testes da Central do PC no painel (onda D): a frase de voz, o corte da visão
para a tela, os verbos da ponte e o fluxo inteiro relatório → clique → quarentena
→ desfazer, com arquivos de verdade em `tmp_path` e o motor/executor da onda C.

Rodar: python -m pytest test_dervs_central_painel.py -q
"""
import json
import os
import sys
import threading

import pytest

import dervs_aprovacao as ap
import dervs_central_painel as cpn
import dervs_ponte_electron as pe
from dervs_central import central as central_mod

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="motor do Windows")


class PonteFalsa:
    """Guarda o que a Central mandaria à tela."""

    def __init__(self):
        self.visoes, self.relatorios, self.resultados, self.progresso, self.acoes = [], [], [], [], []

    def enviar_central(self, visao):
        self.visoes.append(visao)

    def enviar_central_relatorio(self, relatorio, cartao):
        self.relatorios.append((relatorio, cartao))

    def enviar_central_resultado(self, resultado):
        self.resultados.append(resultado)

    def enviar_central_progresso(self, coletor, feitos, total):
        self.progresso.append((coletor, feitos, total))

    def enviar_acao(self, papel, texto):
        self.acoes.append((papel, texto))


@pytest.fixture
def motor(tmp_path):
    extras = tmp_path / "caminhos_protegidos.json"
    extras.write_text(json.dumps({"caminhos": []}), encoding="utf-8")
    return ap.Motor(pasta=str(tmp_path / "dervs-local"), arquivo_extras=str(extras))


@pytest.fixture
def ponte():
    return PonteFalsa()


def _central_com(tmp_path, caminhos):
    """Uma análise gravada em disco cujos temporários são os arquivos dados."""
    candidatos = [{"caminho": str(c), "tamanho_bytes": os.path.getsize(c), "idade_dias": 30,
                   "grupo": "Temporários do usuário"} for c in caminhos]
    coletores = {"temporarios": lambda: {"ok": True, "precisa_admin": False, "erro": "",
                                         "itens": [{"nome": "Temporários do usuário", "tamanho_bytes": 1,
                                                    "antigos_bytes": 1}], "candidatos": candidatos}}
    c = central_mod.Central(str(tmp_path / "dervs-local"), coletores=coletores)
    c.analisar()
    return c


def _pc(ponte, motor, **kw):
    pc = cpn.CentralDoPc(ponte, lambda: motor, **kw)
    return pc


def _esperar(t):
    if t is not None:
        t.join(10)
        assert not t.is_alive()


# ------------------------------------------------------------------ voz
@pytest.mark.parametrize("frase", [
    "DERVS, como está meu PC?", "como esta meu computador", "Como está o meu PC", "dervs como anda minha máquina?",
    "diagnóstico do PC", "saúde do meu computador", "qual a saúde do PC", "checkup do computador",
    "diagnóstico do dia"])
def test_frases_que_pedem_o_estado_do_pc(frase):
    assert cpn.eh_pergunta_de_saude(frase)


@pytest.mark.parametrize("frase", [
    "como está o tempo", "abre o chrome", "limpa meu pc", "apaga os temporários", "verifica meu PC",
    "analisa o computador e me diz o que está lento", "como está meu PC e apaga tudo", ""])
def test_frases_que_nao_sao_o_diagnostico(frase):
    assert not cpn.eh_pergunta_de_saude(frase)


def test_diagnostico_por_voz_analisa_quando_nao_ha_leitura_e_fala_o_resumo(tmp_path, motor, ponte):
    falas = []
    pc = _pc(ponte, motor, falar=falas.append)
    pc._central = central_mod.Central(str(tmp_path / "c"), coletores={
        "drivers": lambda: {"ok": True, "precisa_admin": False, "erro": "", "itens": [{"nome": "x"}]}})
    _esperar(pc.diagnostico_por_voz())
    assert "Vou analisar" in falas[0]
    assert "dispositivo" in falas[1] and "Nota de saúde: 90" in falas[1]
    assert ponte.visoes and ponte.visoes[-1]["nota"] == 90


def test_diagnostico_por_voz_com_leitura_recente_nao_reanalisa(tmp_path, motor, ponte):
    falas = []
    pc = _pc(ponte, motor, falar=falas.append)
    pc._central = central_mod.Central(str(tmp_path / "c"), coletores={"espaco": lambda: {
        "ok": True, "precisa_admin": False, "erro": "", "itens": []}})
    pc._central.analisar()
    _esperar(pc.diagnostico_por_voz())
    assert len(falas) == 1 and "em ordem" in falas[0]


# ------------------------------------------------------------------ o corte para a tela
def test_visao_para_tela_cabe_folgada_e_nao_leva_comando_de_programa(tmp_path):
    grande = [{"nome": f"prog{i}", "comando": "C:\\segredo\\x.exe --token=abc", "ativo": True} for i in range(300)]
    c = central_mod.Central(str(tmp_path), coletores={
        "inicializacao": lambda: {"ok": True, "precisa_admin": False, "erro": "", "itens": grande},
        "eventos": lambda: {"ok": True, "precisa_admin": False, "erro": "", "itens": [
            {"fonte": f"f{i}", "id": i, "quantidade": 2, "nivel": "Erro"} for i in range(200)]}})
    c.analisar()
    v = cpn.visao_para_tela(c.visao())
    texto = json.dumps(v, ensure_ascii=False)
    assert len(texto) < 20000 and "segredo" not in texto and "token" not in texto
    assert v["inicializacao"]["total"] == 300 and len(v["inicializacao"]["ativos"]) == 15
    assert len(v["eventos"]) == 8


def test_visao_sem_analise_previa_tem_nota_nula(tmp_path):
    v = cpn.visao_para_tela(central_mod.Central(str(tmp_path), coletores={}).visao())
    assert v["nota"] is None and v["descontos"] == [] and v["em_andamento"] is False


def test_relatorio_para_tela_tira_impressao_digital(tmp_path, motor):
    f = tmp_path / "a.tmp"
    f.write_text("x" * 10)
    rel = motor.analisar([{"acao": "quarentena", "alvo": str(f), "por_que_seguro": "sobra antiga de teste"}])
    tela = cpn.relatorio_para_tela(rel)
    assert "impressao" not in tela["itens"][0] and "identidade" not in tela["itens"][0]
    assert tela["itens"][0]["acao"] == "quarentena"


# ------------------------------------------------------------------ o fluxo inteiro
def _fluxo(tmp_path, motor, ponte, quantos=2):
    pasta = tmp_path / "sobras"
    pasta.mkdir()
    arquivos = []
    for i in range(quantos):
        f = pasta / f"sobra{i}.tmp"
        f.write_text("conteudo velho\n" * (i + 5))
        arquivos.append(f)
    pc = _pc(ponte, motor)
    pc._central = _central_com(tmp_path, arquivos)
    return pc, arquivos


def test_propor_limpeza_entrega_relatorio_e_cartao_so_para_a_tela(tmp_path, motor, ponte):
    pc, arquivos = _fluxo(tmp_path, motor, ponte)
    _esperar(pc._thread(pc._propor_limpeza))
    relatorio, cartao = ponte.relatorios[0]
    assert len(relatorio["itens"]) == 2 and isinstance(cartao, str) and len(cartao) > 20
    assert all(i["por_que_seguro"] and i["o_que_muda"] for i in relatorio["itens"])
    assert all(f.exists() for f in arquivos)          # propor não mexe em nada


def test_clique_aprova_so_o_marcado_e_manda_para_a_quarentena_com_desfazer(tmp_path, motor, ponte):
    pc, arquivos = _fluxo(tmp_path, motor, ponte)
    _esperar(pc._thread(pc._propor_limpeza))
    relatorio, cartao = ponte.relatorios[0]
    marcado = relatorio["itens"][0]
    alvo = next(f for f in arquivos if f.name == os.path.basename(marcado["alvo"]))
    outro = next(f for f in arquivos if f != alvo)
    pc.tratar("central_aprovar", {"relatorio_id": relatorio["id"], "ids": [marcado["id"]],
                                  "cartao": cartao, "dupla": []})
    _esperar_resultados(ponte, 1)
    r = ponte.resultados[-1]
    assert r["ok"] and r["itens"][0]["ok"] and r["itens"][0]["desfazer_id"] and r["liberados_bytes"] > 0
    assert not alvo.exists() and outro.exists()       # só o marcado saiu do lugar
    # desfazer com um clique devolve exatamente para onde estava
    desfazer_id = r["itens"][0]["desfazer_id"]
    assert pc.quarentena_ativa()[0]["desfazer_id"] == desfazer_id
    pc.tratar("central_desfazer", {"desfazer_id": desfazer_id})
    _esperar_resultados(ponte, 2)
    assert ponte.resultados[-1]["ok"] and alvo.exists()
    assert pc.quarentena_ativa() == []


def _esperar_resultados(ponte, n):
    import time
    fim = time.time() + 10
    while len(ponte.resultados) < n and time.time() < fim:
        time.sleep(0.02)
    assert len(ponte.resultados) >= n


def test_clique_com_cartao_errado_e_recusado_e_nada_se_move(tmp_path, motor, ponte):
    pc, arquivos = _fluxo(tmp_path, motor, ponte)
    _esperar(pc._thread(pc._propor_limpeza))
    relatorio, _ = ponte.relatorios[0]
    pc.tratar("central_aprovar", {"relatorio_id": relatorio["id"], "ids": [relatorio["itens"][0]["id"]],
                                  "cartao": "cartao-forjado", "dupla": []})
    _esperar_resultados(ponte, 1)
    assert ponte.resultados[-1]["ok"] is False and all(f.exists() for f in arquivos)


def test_cartao_so_vale_uma_vez(tmp_path, motor, ponte):
    pc, arquivos = _fluxo(tmp_path, motor, ponte)
    _esperar(pc._thread(pc._propor_limpeza))
    relatorio, cartao = ponte.relatorios[0]
    pedido = {"relatorio_id": relatorio["id"], "ids": [relatorio["itens"][0]["id"]], "cartao": cartao, "dupla": []}
    pc.tratar("central_aprovar", pedido)
    _esperar_resultados(ponte, 1)
    pc.tratar("central_aprovar", pedido)
    _esperar_resultados(ponte, 2)
    assert ponte.resultados[-1]["ok"] is False


def test_sem_sobra_segura_avisa_e_nao_cria_relatorio(tmp_path, motor, ponte):
    pc = _pc(ponte, motor)
    pc._central = central_mod.Central(str(tmp_path / "vazio"), coletores={})
    _esperar(pc._thread(pc._propor_limpeza))
    assert ponte.relatorios == [] and "Não achei sobra" in ponte.resultados[0]["motivo"]


def test_proposta_em_pasta_protegida_e_recusada_pelo_motor(tmp_path, ponte):
    extras = tmp_path / "extras.json"
    protegida = tmp_path / "clinica"
    protegida.mkdir()
    f = protegida / "paciente.tmp"
    f.write_text("dado")
    extras.write_text(json.dumps({"caminhos": [str(protegida)]}), encoding="utf-8")
    motor = ap.Motor(pasta=str(tmp_path / "dervs-local"), arquivo_extras=str(extras))
    pc = _pc(ponte, motor)
    pc._central = _central_com(tmp_path, [f])
    _esperar(pc._thread(pc._propor_limpeza))
    relatorio, cartao = ponte.relatorios[0]
    assert relatorio["itens"] == [] and "protegido" in relatorio["recusados"][0]["motivo"] and cartao is None
    assert f.exists()


def test_windows_temp_nunca_vira_proposta(tmp_path, motor, ponte):
    f = tmp_path / "w.tmp"
    f.write_text("x")
    candidatos = [{"caminho": str(f), "tamanho_bytes": 1, "idade_dias": 90, "grupo": "Temporários do Windows"}]
    pc = _pc(ponte, motor)
    pc._central = central_mod.Central(str(tmp_path / "c"), coletores={"temporarios": lambda: {
        "ok": True, "precisa_admin": False, "erro": "", "itens": [], "candidatos": candidatos}})
    pc._central.analisar()
    _esperar(pc._thread(pc._propor_limpeza))
    assert ponte.relatorios == []


def test_erro_inesperado_vira_resultado_na_tela(tmp_path, motor, ponte):
    pc = _pc(ponte, motor)
    _esperar(pc._thread(lambda: 1 / 0))
    assert ponte.resultados[0]["ok"] is False and "ZeroDivisionError" in ponte.resultados[0]["motivo"]


def test_a_central_nunca_expoe_aprovar_ao_claude(tmp_path, motor, ponte):
    """A voz e o Claude só recebem o resumo; `perguntar_claude` leva texto, não o motor."""
    recebidos = []
    pc = _pc(ponte, motor, perguntar_claude=lambda t: recebidos.append(t) or True)
    pc._central = central_mod.Central(str(tmp_path / "c"), coletores={"drivers": lambda: {
        "ok": True, "precisa_admin": False, "erro": "", "itens": [{"nome": "x"}]}})
    pc._central.analisar()
    pc.tratar("central_explicar", {"codigo": "driver_com_erro"})
    assert len(recebidos) == 1 and isinstance(recebidos[0], str) and "só leia" in recebidos[0]


def test_explicar_codigo_que_nao_existe_nao_pergunta_nada(tmp_path, motor, ponte):
    recebidos = []
    pc = _pc(ponte, motor, perguntar_claude=lambda t: recebidos.append(t) or True)
    pc._central = central_mod.Central(str(tmp_path / "c"), coletores={})
    pc.tratar("central_explicar", {"codigo": "inventado"})
    assert recebidos == []


def test_explicar_mascara_pasta_protegida_antes_de_mandar_ao_claude(tmp_path, monkeypatch, motor, ponte):
    recebidos = []
    pc = _pc(ponte, motor, perguntar_claude=lambda t: recebidos.append(t) or True)
    pc._central = central_mod.Central(str(tmp_path / "c"), coletores={"repositorios": lambda: {
        "ok": True, "precisa_admin": False, "erro": "", "itens": [{"ahead": 2, "nome": "clinica"}]}})
    pc._central.analisar()
    monkeypatch.setattr(central_mod.nota, "calcular", lambda u: {"nota": 90, "sem_leitura": [], "descontos": [
        {"codigo": "commit_sem_push", "pontos": 5, "motivo": "C:\\Clinica\\prontuarios", "frase": "x"}]})
    monkeypatch.setattr(central_mod.cp, "carregar_extras", lambda *a, **k: ["C:\\Clinica"])
    pc.tratar("central_explicar", {"codigo": "commit_sem_push"})
    assert "Clinica" not in recebidos[0] and "[caminho protegido]" in recebidos[0]


# ------------------------------------------------------------------ rotina diária
def test_rotina_diaria_so_roda_com_pc_ocioso_e_uma_vez(tmp_path, motor, ponte):
    pc = _pc(ponte, motor)
    pc._central = central_mod.Central(str(tmp_path / "c"), coletores={"espaco": lambda: {
        "ok": True, "precisa_admin": False, "erro": "", "itens": []}})
    parar = threading.Event()
    ocupado = {"v": 90.0}
    t = pc.iniciar_rotina_diaria(parar, atraso_inicial=0, intervalo=0.05, medir_cpu=lambda: ocupado["v"])
    parar.wait(0.3)
    assert pc._central.ultima() is None               # CPU alta: não analisou
    ocupado["v"] = 5.0
    parar.wait(0.4)
    parar.set()
    t.join(3)
    assert pc._central.ultima() is not None and len(ponte.acoes) == 1 and "nota" in ponte.acoes[0][1]


# ------------------------------------------------------------------ verbos da ponte
class Alvo:
    def __init__(self):
        self.chamadas = []

    def __call__(self, verbo, dados):
        self.chamadas.append((verbo, dados))


def _ponte_real():
    alvo = Alvo()
    p = pe.PonteElectron(ao_sair=lambda: None, ao_plano=lambda *a: None, ao_pronto=lambda: None,
                         ao_central=alvo)
    return p, alvo


def _mandar(p, dado):
    p._processar_linha((json.dumps(dado) + "\n").encode("utf-8"))


def test_ponte_entrega_verbos_sem_campos():
    p, alvo = _ponte_real()
    for v in ("central_pedir", "central_analisar", "central_propor_limpeza"):
        _mandar(p, {"verbo": v})
    assert [c[0] for c in alvo.chamadas] == ["central_pedir", "central_analisar", "central_propor_limpeza"]


def test_ponte_aprovar_valido_passa_e_invalido_e_ignorado():
    p, alvo = _ponte_real()
    _mandar(p, {"verbo": "central_aprovar", "relatorio_id": "abc", "ids": ["item-1"], "cartao": "s" * 40, "dupla": []})
    assert alvo.chamadas[-1][1]["ids"] == ["item-1"]
    n = len(alvo.chamadas)
    for ruim in ({"relatorio_id": "abc", "ids": [], "cartao": "x", "dupla": []},
                 {"relatorio_id": "abc", "ids": "item-1", "cartao": "x"},
                 {"relatorio_id": "abc", "ids": ["item-1"]},
                 {"relatorio_id": 5, "ids": ["item-1"], "cartao": "x"},
                 {"relatorio_id": "abc", "ids": ["item-1"], "cartao": "x" * 500},
                 {"relatorio_id": "abc", "ids": [1], "cartao": "x"},
                 {"relatorio_id": "abc", "ids": ["i"] * 51, "cartao": "x"},
                 {"relatorio_id": "abc", "ids": ["item-1"], "cartao": "x", "dupla": [None]}):
        _mandar(p, dict(ruim, verbo="central_aprovar"))
    assert len(alvo.chamadas) == n


def test_ponte_desfazer_e_explicar_validam_formato():
    p, alvo = _ponte_real()
    _mandar(p, {"verbo": "central_desfazer", "desfazer_id": "20260929-abc123"})
    _mandar(p, {"verbo": "central_desfazer", "desfazer_id": ""})
    _mandar(p, {"verbo": "central_desfazer"})
    _mandar(p, {"verbo": "central_explicar", "codigo": "disco_cheio"})
    _mandar(p, {"verbo": "central_explicar", "codigo": "x; rm -rf /"})
    assert [c[0] for c in alvo.chamadas] == ["central_desfazer", "central_explicar"]


class Saida:
    def __init__(self):
        self.linhas = []

    def write(self, b):
        self.linhas.append(b)

    def flush(self):
        pass


def _ponte_com_saida():
    p = pe.PonteElectron(ao_sair=lambda: None, ao_plano=lambda *a: None, ao_pronto=lambda: None)
    saida = Saida()
    p._canal_saida = saida
    return p, saida


def _enviadas(saida):
    return [json.loads(b.decode("utf-8")) for b in saida.linhas]


def test_ponte_corta_texto_hostil_e_limita_lista_ao_enviar_central():
    p, saida = _ponte_com_saida()
    p.enviar_central({"resumo": ["a" * 5000] * 3, "eventos": [{"fonte": "f", "id": i} for i in range(200)]})
    m = _enviadas(saida)[0]
    assert m["verbo"] == "central" and len(m["resumo"][0]) == 600 and len(m["eventos"]) == 50


def test_ponte_linha_grande_demais_esvazia_as_listas_em_vez_de_estourar():
    p, saida = _ponte_com_saida()
    p.enviar_central({"nota": 90, "resumo": ["x" * 600] * 50, "discos": [{"volume": "y" * 600, "outro": "z" * 600}] * 50})
    m = _enviadas(saida)[0]
    assert m["nota"] == 90 and m["resumo"] == [] and m["discos"] == []


def test_ponte_relatorio_leva_o_cartao_e_progresso_e_resultado_vao_como_verbos_proprios():
    p, saida = _ponte_com_saida()
    p.enviar_central_relatorio({"id": "r1", "itens": []}, "senha-do-cartao")
    p.enviar_central_progresso("eventos", 3, 13)
    p.enviar_central_resultado({"ok": True, "motivo": "feito", "itens": []})
    a, b, c = _enviadas(saida)
    assert a["cartao"] == "senha-do-cartao" and b == {"verbo": "central_progresso", "coletor": "eventos", "feitos": 3, "total": 13}
    assert c["verbo"] == "central_resultado" and c["ok"] is True
