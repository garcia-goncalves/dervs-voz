#!/usr/bin/env python3
"""Testes da tela Integração do painel (`dervs_integracao_painel.py`): cérebro, painel
web (fila e avisos), terminal SSH com cartão e segunda confirmação, e a validação dos
verbos novos na ponte do Electron. Nenhum teste abre rede nem servidor: o `ssh` é um
executor falso, a ponte web é um dublê e os arquivos vivem em `tmp_path`.

Rodar: python -m pytest test_dervs_integracao_painel.py -q
"""
import ast
import json
import os
import sys

import pytest

import dervs_aprovacao as ap
import dervs_cerebros as cer
import dervs_integracao_painel as ip
import dervs_ponte_electron as pe
import dervs_ponte_tratador as tr
import dervs_ssh as dss

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="motor do Windows")

AQUI = os.path.dirname(os.path.abspath(__file__))
HOSTS = {"teste": {"host": "host-de-teste.invalid", "usuario": "deploy", "porta": 22}}


class PonteFalsa:
    def __init__(self):
        self.enviadas = []

    def enviar_integracao(self, parte, dados):
        self.enviadas.append((parte, dados))

    def ultimas(self, parte):
        return [d for p, d in self.enviadas if p == parte]


class PonteWebFalsa:
    ligada = True
    motivo = None
    calma = False

    def __init__(self, resposta=None):
        self.chamadas = []
        self.resposta = resposta or {"ok": True, "tarefa_id": "t1", "novo": True, "aviso": ""}

    def pedir_conserto(self, alerta_id, frase):
        self.chamadas.append((alerta_id, frase))
        return self.resposta


class Executor:
    def __init__(self):
        self.chamadas = []
        self.resposta = (0, b"saida do servidor de mentira\n")

    def __call__(self, argv, timeout):
        self.chamadas.append(list(argv))
        return self.resposta


class Cerebro:
    def __init__(self, ok=True, motivo=""):
        self._r = (ok, motivo)

    def disponivel(self):
        return self._r


class Ctx:
    pass


@pytest.fixture
def ctx(tmp_path):
    c = Ctx()
    c.ponte = PonteFalsa()
    c.web = PonteWebFalsa()
    extras = tmp_path / "protegidos.json"
    extras.write_text(json.dumps({"caminhos": []}), encoding="utf-8")
    c.motor = ap.Motor(pasta=str(tmp_path / "motor"), arquivo_extras=str(extras))
    c.hosts = tmp_path / "ssh_hosts.json"
    c.hosts.write_text(json.dumps(HOSTS), encoding="utf-8")
    c.exec = Executor()
    c.seletor = cer.Seletor({"claude_code": Cerebro(), "hermes": Cerebro(False, "sem WSL"),
                             "jev": Cerebro(False, "sem chave")}, arquivo=str(tmp_path / "cerebro.json"))
    c.tratador = tr.TratadorLocal(raizes=[str(tmp_path)], arquivo_propostas=str(tmp_path / "p.jsonl"))
    c.terminais = []

    def fabrica(motor):
        t = dss.TerminalSSH(motor.log, dss.AprovadorMotor(motor), executar_ssh=c.exec,
                            arquivo_hosts=str(c.hosts), ssh_exe="ssh-de-teste")
        c.terminais.append(t)
        return t
    c.integ = ip.IntegracaoLocal(
        c.ponte, motor_fabrica=lambda: c.motor, seletor_fn=lambda: c.seletor,
        ponte_web_fn=lambda: (c.web, ""), tratador=c.tratador, terminal_fabrica=fabrica,
        arquivo_avisos=str(tmp_path / "avisos_web.jsonl"), arquivo_hosts=str(c.hosts))
    return c


def rodar(c, verbo, **dados):
    c.integ.tratar(verbo, dados).join(10)


# ------------------------------------------------------------ funções puras

def test_alerta_so_com_prefixo_exato_e_id_estrito():
    assert ip.extrair_alerta("[alerta:proj.a-1:x] Disco cheio") == ("proj.a-1:x", "Disco cheio")
    for ruim in ("[alerta:] sem id", "[alerta:a b] espaço", "[alerta:a/b] barra", "[alerta:a;b] ponto e vírgula",
                 "[ALERTA:a] maiúsculo", "  [alerta:a] começa com espaço", "[alerta:a]sem espaço",
                 "texto [alerta:a] no meio", "[alerta:" + "a" * 201 + "] longo", "[alerta:é] acento"):
        assert ip.extrair_alerta(ruim)[0] is None, ruim
    assert ip.extrair_alerta("[alerta:" + "a" * 200 + "] no limite")[0] == "a" * 200
    assert ip.extrair_alerta(None) == (None, "")


def test_frase_da_ponte_para_leigo():
    assert ip.frase_da_ponte(None, "falta o token")["codigo"] == "desligada"
    assert "falta o token" in ip.frase_da_ponte(None, "falta o token")["frase"]
    web = PonteWebFalsa()
    assert ip.frase_da_ponte(web)["codigo"] == "ligada"
    web.motivo, web.calma = "o painel ainda não publicou", True
    r = ip.frase_da_ponte(web)
    assert r["codigo"] == "calma" and "modo calmo" in r["frase"] and "não publicou" in r["frase"]
    web.calma = False
    assert ip.frase_da_ponte(web)["codigo"] == "com_problema"
    web.ligada = False
    assert ip.frase_da_ponte(web)["codigo"] == "desligada"


def test_frases_dos_cerebros_jev_nunca_e_escolhivel():
    r = ip.frases_dos_cerebros({"cerebro_ativo": "claude_code", "cerebros": {
        "claude_code": {"disponivel": True, "motivo": ""},
        "hermes": {"disponivel": False, "motivo": "sem WSL"},
        "jev": {"disponivel": True, "motivo": ""}}})
    por_nome = {c["nome"]: c for c in r["cerebros"]}
    assert por_nome["claude_code"]["ativo"] and por_nome["claude_code"]["escolhivel"]
    assert not por_nome["hermes"]["disponivel"] and "sem WSL" in por_nome["hermes"]["frase"]
    assert not por_nome["jev"]["escolhivel"] and not por_nome["jev"]["ativo"]
    assert "Triagem rápida — não conversa" in por_nome["jev"]["frase"]


# ------------------------------------------------------------ 1. cérebro

def test_pedir_manda_todos_os_blocos(ctx):
    rodar(ctx, "integracao_pedir")
    partes = {p for p, _ in ctx.ponte.enviadas}
    assert {"cerebros", "web", "fila", "avisos", "ssh"} <= partes
    assert ctx.ponte.ultimas("ssh")[0]["apelidos"] == ["teste"]
    assert ctx.ponte.ultimas("ssh")[0]["arquivo_hosts"] == str(ctx.hosts)


def test_escolher_cerebro_usa_o_seletor_compartilhado(ctx, tmp_path):
    ctx.seletor._cerebros["hermes"] = Cerebro(True)
    rodar(ctx, "integracao_cerebro", nome="hermes")
    assert ctx.seletor.ativo == "hermes"      # o MESMO objeto que a ponte web usa
    assert ctx.ponte.ultimas("mensagem")[-1]["ok"] is True
    assert ctx.ponte.ultimas("cerebros")[-1]["ativo"] == "hermes"


def test_hermes_indisponivel_nao_e_escolhido_e_diz_o_motivo(ctx):
    rodar(ctx, "integracao_cerebro", nome="hermes")
    assert ctx.seletor.ativo == "claude_code"
    m = ctx.ponte.ultimas("mensagem")[-1]
    assert m["ok"] is False and "sem WSL" in m["texto"]


def test_jev_e_nome_desconhecido_sao_recusados(ctx):
    rodar(ctx, "integracao_cerebro", nome="jev")
    assert "triagem" in ctx.ponte.ultimas("mensagem")[-1]["texto"]
    rodar(ctx, "integracao_cerebro", nome="outro")
    assert ctx.ponte.ultimas("mensagem")[-1]["ok"] is False
    assert ctx.seletor.ativo == "claude_code"


def test_estado_do_seletor_nao_ganha_chave_para_o_painel_web(ctx):
    """O painel web rejeita chave extra em /estado: a tela Integração não pode mudar o que o Seletor manda."""
    assert set(ctx.seletor.estado()) == {"cerebro_ativo", "cerebros"}
    rodar(ctx, "integracao_pedir")
    assert set(ctx.seletor.estado()) == {"cerebro_ativo", "cerebros"}


# ------------------------------------------------------------ 2a. fila

def _pedido(c, id_, texto="faça algo", tipo="propor"):
    c.tratador.propor({"id": id_, "tipo": tipo, "alvo": "dervs", "texto": texto})


def test_fila_mostra_pendentes_e_dispensar_marca_no_arquivo(ctx):
    _pedido(ctx, "r1", "<img src=x onerror=alert(1)>")
    _pedido(ctx, "r2")
    rodar(ctx, "integracao_pedir")
    itens = ctx.ponte.ultimas("fila")[-1]["itens"]
    assert [i["id"] for i in itens] == ["r1", "r2"]
    assert itens[0]["texto"] == "<img src=x onerror=alert(1)>"       # texto cru: a tela usa textContent
    rodar(ctx, "integracao_dispensar", id="r1")
    assert [i["id"] for i in ctx.ponte.ultimas("fila")[-1]["itens"]] == ["r2"]
    linhas = [json.loads(l) for l in open(ctx.tratador._arquivo, encoding="utf-8")]
    assert [l["estado"] for l in linhas] == ["dispensado", "pendente"]
    assert "dispensado_em" in linhas[0]


def test_dispensar_nao_executa_nada_e_nao_acha_o_que_ja_saiu(ctx):
    _pedido(ctx, "r1")
    rodar(ctx, "integracao_dispensar", id="r1")
    rodar(ctx, "integracao_dispensar", id="r1")
    assert ctx.ponte.ultimas("mensagem")[-1]["ok"] is False
    rodar(ctx, "integracao_dispensar", id="nao-existe")
    assert ctx.ponte.ultimas("mensagem")[-1]["ok"] is False
    assert ctx.exec.chamadas == []


def test_proposta_dispensada_pode_chegar_de_novo_com_o_mesmo_id_e_fica_ignorada(ctx):
    _pedido(ctx, "r1")
    ctx.tratador.dispensar("r1")
    assert "já estava na fila" in ctx.tratador.propor({"id": "r1", "tipo": "propor", "texto": "x"})
    assert ctx.tratador.pendentes() == []


# ------------------------------------------------------------ 2b. avisos

def test_aviso_e_gravado_redigido_e_com_teto(ctx):
    segredo = "api_key" + "=" + "sk-" + "abcdefghijklmnopqrstuvwx"
    ctx.integ.ao_aviso("falha com " + segredo, "dervs")
    a = ctx.integ.avisos()[0]
    assert "sk-" not in a["texto"] and "[SEGREDO REMOVIDO]" in a["texto"]
    for n in range(ip.TETO_AVISOS + 15):
        ctx.integ.ao_aviso("aviso %d" % n, "")
    avisos = ctx.integ.avisos()
    assert len(avisos) == ip.TETO_AVISOS
    assert avisos[0]["texto"] == "aviso %d" % (ip.TETO_AVISOS + 14)        # mais novo primeiro
    assert len(open(ctx.integ._arquivo_avisos, encoding="utf-8").read().splitlines()) == ip.TETO_AVISOS


def test_aviso_corta_texto_enorme(ctx):
    ctx.integ.ao_aviso("x" * 5000, "y" * 500)
    a = ctx.integ.avisos()[0]
    assert len(a["texto"]) == ip.TETO_TEXTO_AVISO and len(a["alvo"]) == 80


def test_botao_de_conserto_so_com_prefixo_valido(ctx):
    ctx.integ.ao_aviso("[alerta:mem_crlf:dervs:1] CRLF fora do lugar", "dervs")
    ctx.integ.ao_aviso("sem prefixo nenhum", "dervs")
    ctx.integ.ao_aviso("[alerta:com espaco] id ruim", "dervs")
    por_texto = {a["texto"]: a["pode_conserto"] for a in ctx.integ.avisos()}
    assert por_texto == {"[alerta:mem_crlf:dervs:1] CRLF fora do lugar": True,
                         "sem prefixo nenhum": False, "[alerta:com espaco] id ruim": False}


def test_aviso_nunca_pede_conserto_sozinho(ctx):
    ctx.integ.ao_aviso("[alerta:a1] algo grave", "dervs")
    rodar(ctx, "integracao_pedir")
    assert ctx.web.chamadas == []


def test_pedir_conserto_por_clique_leva_o_id_e_a_frase_e_mostra_a_resposta(ctx):
    ctx.integ.ao_aviso("[alerta:a1] arquivo com fim de linha errado", "dervs")
    aviso_id = ctx.integ.avisos()[0]["id"]
    rodar(ctx, "integracao_conserto", aviso_id=aviso_id)
    assert ctx.web.chamadas == [("a1", "arquivo com fim de linha errado")]
    m = ctx.ponte.ultimas("mensagem")[-1]
    assert m["ok"] and "Pode fazer" in m["texto"]
    assert "Pode fazer" in ctx.integ.avisos()[0]["conserto"]


def test_conserto_ja_existente_e_recusa_do_painel_viram_frase_leiga(ctx):
    ctx.integ.ao_aviso("[alerta:a1] x", "")
    aviso_id = ctx.integ.avisos()[0]["id"]
    ctx.web.resposta = {"ok": True, "tarefa_id": "t1", "novo": False, "aviso": ""}
    rodar(ctx, "integracao_conserto", aviso_id=aviso_id)
    assert "já tinha esse pedido" in ctx.ponte.ultimas("mensagem")[-1]["texto"]
    ctx.web.resposta = {"ok": False, "motivo": "O painel não conhece esse alerta (ou ele é de outra conta)."}
    rodar(ctx, "integracao_conserto", aviso_id=aviso_id)
    m = ctx.ponte.ultimas("mensagem")[-1]
    assert m["ok"] is False and "não conhece esse alerta" in m["texto"]


def test_a_tela_nao_escolhe_o_alerta_so_o_aviso_gravado(ctx):
    ctx.integ.ao_aviso("sem prefixo", "")
    rodar(ctx, "integracao_conserto", aviso_id=ctx.integ.avisos()[0]["id"])
    rodar(ctx, "integracao_conserto", aviso_id="inventado")
    assert ctx.web.chamadas == []
    assert all(m["ok"] is False for m in ctx.ponte.ultimas("mensagem"))


def test_conserto_com_a_ponte_desligada_diz_o_porque(ctx):
    ctx.integ.ao_aviso("[alerta:a1] x", "")
    ctx.integ._ponte_web_fn = lambda: (None, "falta o token")
    rodar(ctx, "integracao_conserto", aviso_id=ctx.integ.avisos()[0]["id"])
    m = ctx.ponte.ultimas("mensagem")[-1]
    assert m["ok"] is False and "desligada" in m["texto"] and "falta o token" in m["texto"]


def test_ao_aviso_nunca_levanta(ctx, tmp_path):
    ctx.integ._arquivo_avisos = str(tmp_path)        # um diretório: gravar falha
    ctx.integ.ao_aviso("qualquer", "x")              # não pode levantar


# ------------------------------------------------------------ 3. terminal SSH

def test_leitura_roda_direto_e_mostra_a_saida(ctx):
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="uptime")
    r = ctx.ponte.ultimas("ssh_resultado")[-1]
    assert r["ok"] and r["tipo"] == "leitura" and "servidor de mentira" in r["saida"] and r["rc"] == 0
    assert len(ctx.exec.chamadas) == 1 and ctx.ponte.ultimas("ssh_cartao") == []


def test_muda_estado_mostra_cartao_e_nao_executa_antes_do_clique(ctx):
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="systemctl restart nginx")
    c = ctx.ponte.ultimas("ssh_cartao")[-1]
    assert c["servidor"] == "teste" and c["comando"] == "systemctl restart nginx"
    assert c["risco"] == "alto" and c["valida_min"] == 15
    assert "systemctl restart nginx" in c["o_que_muda"] and c["como_desfazer"]
    assert ctx.exec.chamadas == []
    senha = next(iter(ctx.motor._cartoes.values()))
    assert senha not in json.dumps(c)       # a senha do clique fica no Python, nunca vai à tela
    assert set(c) == {"servidor", "comando", "risco", "o_que_muda", "como_desfazer", "proposta_id", "valida_min"}


def test_o_texto_do_cartao_bate_com_o_item_do_motor(ctx):
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="touch /tmp/a")
    c = ctx.ponte.ultimas("ssh_cartao")[-1]
    rel = next(iter(ctx.motor._relatorios.values()))["dados"]["itens"][0]
    assert c["o_que_muda"] == rel["o_que_muda"] and c["como_desfazer"] == rel["como_desfazer"]
    assert c["risco"] == rel["risco"]


def test_segunda_confirmacao_executa_uma_vez_e_grava_no_log_do_motor(ctx):
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="touch /tmp/a")
    pid = ctx.ponte.ultimas("ssh_cartao")[-1]["proposta_id"]
    rodar(ctx, "integracao_ssh_confirmar", proposta_id=pid, segunda=True)
    r = ctx.ponte.ultimas("ssh_resultado")[-1]
    assert r["ok"] and r["tipo"] == "muda_estado" and len(ctx.exec.chamadas) == 1
    eventos = [l["evento"] for l in ctx.motor.log.ler()]
    assert "aprovou" in eventos and eventos[-1] == "executou"
    assert ctx.terminais[0]._log is ctx.motor.log
    # duplo clique: o cartão já foi gasto
    rodar(ctx, "integracao_ssh_confirmar", proposta_id=pid, segunda=True)
    assert ctx.ponte.ultimas("ssh_resultado")[-1]["ok"] is False and len(ctx.exec.chamadas) == 1


def test_sem_a_segunda_confirmacao_estrita_nada_roda(ctx):
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="touch /tmp/a")
    pid = ctx.ponte.ultimas("ssh_cartao")[-1]["proposta_id"]
    for valor in (None, False, "true", 1, "sim"):
        rodar(ctx, "integracao_ssh_confirmar", proposta_id=pid, segunda=valor)
        assert ctx.ponte.ultimas("ssh_resultado")[-1]["ok"] is False
    assert ctx.exec.chamadas == []
    rodar(ctx, "integracao_ssh_confirmar", proposta_id=pid, segunda=True)    # o cartão ainda vale
    assert ctx.ponte.ultimas("ssh_resultado")[-1]["ok"] is True


def test_confirmar_proposta_que_nao_existe_ou_venceu_e_recusado(ctx):
    rodar(ctx, "integracao_ssh_confirmar", proposta_id="abc123", segunda=True)
    assert ctx.ponte.ultimas("ssh_resultado")[-1]["ok"] is False
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="touch /tmp/a")
    pid = ctx.ponte.ultimas("ssh_cartao")[-1]["proposta_id"]
    ctx.integ._cartoes[pid]["criado"] -= ip.VALIDADE_CARTAO_S + 1
    rodar(ctx, "integracao_ssh_confirmar", proposta_id=pid, segunda=True)
    assert "não está mais esperando" in ctx.ponte.ultimas("ssh_resultado")[-1]["motivo"]
    assert ctx.exec.chamadas == []


def test_cancelar_descarta_o_cartao(ctx):
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="touch /tmp/a")
    pid = ctx.ponte.ultimas("ssh_cartao")[-1]["proposta_id"]
    rodar(ctx, "integracao_ssh_cancelar", proposta_id=pid)
    assert ctx.ponte.ultimas("ssh_cancelado")[-1]["tinha"] is True
    rodar(ctx, "integracao_ssh_confirmar", proposta_id=pid, segunda=True)
    assert ctx.exec.chamadas == [] and ctx.ponte.ultimas("ssh_resultado")[-1]["ok"] is False


def test_recusas_do_terminal_chegam_como_motivo(ctx):
    rodar(ctx, "integracao_ssh_rodar", apelido="nao-cadastrado", comando="uptime")
    assert "fora da lista" in ctx.ponte.ultimas("ssh_resultado")[-1]["motivo"]
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="rm -rf /")
    assert ctx.ponte.ultimas("ssh_resultado")[-1]["ok"] is False
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="touch  /tmp/a")    # espaço repetido: o Motor recusa
    assert ctx.ponte.ultimas("ssh_resultado")[-1]["ok"] is False
    assert ctx.exec.chamadas == [] and ctx.ponte.ultimas("ssh_cartao") == []


def test_saida_do_servidor_e_cortada_para_a_tela(ctx):
    ctx.exec.resposta = (0, (b"x" * 49 + b"\n") * 800)
    rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="uptime")
    r = ctx.ponte.ultimas("ssh_resultado")[-1]
    assert len(r["saida"]) <= ip.TETO_SAIDA_NA_TELA and r["truncada"] is True


def test_sem_apelido_cadastrado_a_tela_recebe_a_lista_vazia(ctx, tmp_path):
    ctx.hosts.write_text("{}", encoding="utf-8")
    rodar(ctx, "integracao_pedir")
    assert ctx.ponte.ultimas("ssh")[-1]["apelidos"] == []


def test_cartoes_guardados_tem_teto(ctx):
    for n in range(ip.MAX_CARTOES + 3):
        rodar(ctx, "integracao_ssh_rodar", apelido="teste", comando="touch /tmp/a%d" % n)
    assert len(ctx.integ._cartoes) <= ip.MAX_CARTOES


def test_erro_inesperado_vira_mensagem_e_nao_derruba(ctx):
    ctx.integ._seletor_fn = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    rodar(ctx, "integracao_cerebro", nome="claude_code")
    assert "falhou por dentro" in ctx.ponte.ultimas("mensagem")[-1]["texto"]


# ------------------------------------------------------------ a ponte do Electron

class Alvo:
    def __init__(self):
        self.chamadas = []

    def __call__(self, verbo, dados):
        self.chamadas.append((verbo, dados))


def _ponte_real():
    alvo = Alvo()
    p = pe.PonteElectron(ao_sair=lambda: None, ao_plano=lambda *a: None, ao_pronto=lambda: None,
                         ao_integracao=alvo)
    return p, alvo


def _mandar(p, dado):
    p._processar_linha((json.dumps(dado) + "\n").encode("utf-8"))


def test_ponte_entrega_os_verbos_validos():
    p, alvo = _ponte_real()
    _mandar(p, {"verbo": "integracao_pedir"})
    _mandar(p, {"verbo": "integracao_cerebro", "nome": "hermes"})
    _mandar(p, {"verbo": "integracao_dispensar", "id": "rec-1.a"})
    _mandar(p, {"verbo": "integracao_conserto", "aviso_id": "a1b2c3"})
    _mandar(p, {"verbo": "integracao_ssh_rodar", "apelido": "teste", "comando": "uptime"})
    _mandar(p, {"verbo": "integracao_ssh_confirmar", "proposta_id": "ab12", "segunda": True})
    _mandar(p, {"verbo": "integracao_ssh_cancelar", "proposta_id": "ab12"})
    assert [c[0] for c in alvo.chamadas] == [
        "integracao_pedir", "integracao_cerebro", "integracao_dispensar", "integracao_conserto",
        "integracao_ssh_rodar", "integracao_ssh_confirmar", "integracao_ssh_cancelar"]


@pytest.mark.parametrize("ruim", [
    {"verbo": "integracao_cerebro"}, {"verbo": "integracao_cerebro", "nome": "Hermes; x"},
    {"verbo": "integracao_cerebro", "nome": 5},
    {"verbo": "integracao_dispensar", "id": ""}, {"verbo": "integracao_dispensar", "id": "a" * 65},
    {"verbo": "integracao_dispensar", "id": "a/../b"},
    {"verbo": "integracao_conserto", "aviso_id": "tem espaco"}, {"verbo": "integracao_conserto", "aviso_id": None},
    {"verbo": "integracao_ssh_rodar", "apelido": "teste"},
    {"verbo": "integracao_ssh_rodar", "apelido": "teste", "comando": "   "},
    {"verbo": "integracao_ssh_rodar", "apelido": "teste", "comando": "x" * 401},
    {"verbo": "integracao_ssh_rodar", "apelido": "a b", "comando": "uptime"},
    {"verbo": "integracao_ssh_rodar", "apelido": "teste", "comando": ["uptime"]},
    {"verbo": "integracao_ssh_confirmar", "proposta_id": "ab12"},
    {"verbo": "integracao_ssh_confirmar", "proposta_id": "ab12", "segunda": "true"},
    {"verbo": "integracao_ssh_confirmar", "proposta_id": "ab12", "segunda": 1},
    {"verbo": "integracao_ssh_confirmar", "proposta_id": "ab12", "segunda": False},
    {"verbo": "integracao_ssh_cancelar"},
])
def test_ponte_ignora_verbo_fora_do_formato(ruim):
    p, alvo = _ponte_real()
    _mandar(p, ruim)
    assert alvo.chamadas == []


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


def test_enviar_integracao_corta_texto_hostil_mas_deixa_a_saida_do_ssh_caber():
    p, saida = _ponte_com_saida()
    p.enviar_integracao("avisos", {"itens": [{"texto": "a" * 5000}] * 3 + [{"texto": "b"}] * 297})
    m = _enviadas(saida)[0]
    assert m["verbo"] == "integracao" and m["parte"] == "avisos"
    assert len(m["itens"]) == 100 and len(m["itens"][0]["texto"]) == 600
    p.enviar_integracao("ssh_resultado", {"ok": True, "saida": "é" * 30000, "comando": "c" * 900})
    m = _enviadas(saida)[1]
    assert len(m["saida"]) == 16000 and len(m["comando"]) == 600
    assert len(saida.linhas[1]) < 64 * 1024


def test_enviar_integracao_linha_grande_demais_esvazia_em_vez_de_estourar():
    p, saida = _ponte_com_saida()
    p.enviar_integracao("ssh_resultado", {"ok": True, "saida": "😀" * 16000})     # 4 bytes cada: 64 000 bytes
    m = _enviadas(saida)[0]
    assert m["saida"] == "" and m["truncada"] is True


# ------------------------------------------------------------ isolamento

def test_so_o_modulo_da_tela_local_importa_o_ssh():
    alvo = "dervs_ssh"
    donos = []
    for nome in sorted(os.listdir(AQUI)):
        if not (nome.startswith("dervs") and nome.endswith(".py")) or nome == "dervs_ssh.py":
            continue
        arvore = ast.parse(open(os.path.join(AQUI, nome), encoding="utf-8").read())
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import) and any(alvo in a.name for a in no.names):
                donos.append(nome)
            elif isinstance(no, ast.ImportFrom) and alvo in (no.module or ""):
                donos.append(nome)
    assert set(donos) == {"dervs_integracao_painel.py"}


def test_o_claude_e_a_ponte_web_nao_conhecem_a_tela_de_integracao():
    for nome in ("dervs_claude_code.py", "dervs_brain.py", "dervs_cerebros.py", "dervs_ponte_web.py",
                 "dervs_ponte_tratador.py", "dervs_aprovacao.py"):
        fonte = open(os.path.join(AQUI, nome), encoding="utf-8").read()
        assert "dervs_integracao_painel" not in fonte, nome


# ------------------------------------------------------------ o modo calmo da ponte web

def test_ponte_web_guarda_se_o_ultimo_ciclo_foi_modo_calmo(tmp_path):
    import dervs_ponte_web as pw

    class Calma(pw.PonteWeb):
        def enviar_estado(self):
            raise pw.PonteIndisponivel("o painel ainda não publicou a ponte", calma=True)

    class Bem(pw.PonteWeb):
        def enviar_estado(self):
            pass

        def buscar_recados(self):
            return []

    ponte = Calma("https://painel.exemplo.test", tr.TratadorLocal(arquivo_propostas=str(tmp_path / "p.jsonl")),
                  arquivo_token=str(tmp_path / "sem-token.json"), log=type("L", (), {"registrar": lambda *a, **k: None})())
    assert ponte.calma is False
    ponte.ciclo()
    assert ponte.calma is True and "não publicou" in ponte.motivo
    assert ip.frase_da_ponte(ponte)["codigo"] in ("calma", "desligada")      # sem laço ligado: desligada
    ponte.__class__ = Bem
    ponte.ciclo()
    assert ponte.calma is False and ponte.motivo is None
