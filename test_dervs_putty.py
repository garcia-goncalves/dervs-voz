#!/usr/bin/env python3
"""Testes das sessões do PuTTY e do Claude da VPS (Onda B da esteira dervs-jarvis).

Nenhum teste lê o registro real nem abre rede: o leitor do PuTTY e o executor são injetados.
Rodar: python -m pytest test_dervs_putty.py -q
"""
import ast
import json
import os

import pytest

import dervs_aprovacao as ap
import dervs_putty as dp
import dervs_ssh as dss

AQUI = os.path.dirname(os.path.abspath(__file__))
SESSAO = {"host": "vps.exemplo.test", "usuario": "root", "porta": 22, "origem": "putty",
          "sessao": "vps ovh"}


def dados(**kw):
    base = {"protocolo": "ssh", "host": "vps.exemplo.test", "usuario": "root", "porta": 22,
            "proxy": 0, "redirecionamentos": ""}
    return {**base, **kw}


# ------------------------------------------------ leitura das sessões

def test_sessao_ssh_vira_apelido_com_so_quatro_dados():
    (apelido, entrada), motivo = dp.interpretar("vps ovh", dados())
    assert motivo is None and apelido == "vps-ovh"
    assert entrada == SESSAO


def test_nome_codificado_do_registro_volta_ao_nome_do_dono():
    assert dp.nome_da_sessao("vps%20ovh") == "vps ovh"


def test_usuario_no_campo_de_endereco_e_separado():
    (_, entrada), _ = dp.interpretar("x", dados(host="deploy@10.0.0.5", usuario=""))
    assert entrada["host"] == "10.0.0.5" and entrada["usuario"] == "deploy"


@pytest.mark.parametrize("campos,trecho", [
    ({"protocolo": "telnet"}, "SSH"),
    ({"host": ""}, "falta"),
    ({"usuario": ""}, "falta"),
    ({"porta": 0}, "porta"),
    ({"porta": 70000}, "porta"),
    ({"proxy": 5}, "proxy"),
    ({"redirecionamentos": "L8080=localhost:80"}, "redirecionamento"),
])
def test_sessao_que_faria_mais_que_rodar_comando_e_pulada(campos, trecho):
    entrada, motivo = dp.interpretar("x", dados(**campos))
    assert entrada is None and trecho.lower() in motivo.lower()


def test_proxy_por_telnet_nao_roda_programa_local_e_passa():
    entrada, _ = dp.interpretar("x", dados(proxy=4))
    assert entrada is not None


def test_nome_sem_aproveitamento_e_pulado():
    entrada, _ = dp.interpretar("ççç", dados())
    assert entrada is None


def test_o_leitor_nunca_pede_senha_nem_chave():
    fonte = open(os.path.join(AQUI, "dervs_putty.py"), encoding="utf-8").read()
    for proibido in ("PublicKeyFile", "Password", "ProxyPassword", "ProxyUsername"):
        assert proibido not in fonte
    arvore = ast.parse(fonte)
    chamadas = {n.func.attr for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not chamadas & {"CreateKey", "SetValueEx", "DeleteKey", "DeleteValue"}


def test_argv_do_plink_trava_agente_x11_e_pergunta():
    argv = dp.montar_argv_plink("C:/PuTTY/plink.exe", "vps ovh", "uptime")
    assert argv[:3] == ["C:/PuTTY/plink.exe", "-load", "vps ovh"]
    assert {"-batch", "-T", "-a", "-x"} <= set(argv) and argv[-1] == "uptime"
    assert "-pw" not in argv and "-i" not in argv


# ------------------------------------------------ ligação com o terminal SSH

class Executor:
    def __init__(self):
        self.chamadas = []

    def __call__(self, argv, timeout):
        self.chamadas.append(list(argv))
        return 0, b"ok\n"


@pytest.fixture
def term(tmp_path):
    arq = tmp_path / "ssh_hosts.json"
    arq.write_text("{}", encoding="utf-8")
    extras = tmp_path / "p.json"
    extras.write_text(json.dumps({"caminhos": []}), encoding="utf-8")
    motor = ap.Motor(pasta=str(tmp_path / "m"), arquivo_extras=str(extras))
    ex = Executor()
    t = dss.TerminalSSH(motor.log, dss.AprovadorMotor(motor), executar_ssh=ex,
                        arquivo_hosts=str(arq), ssh_exe="ssh-de-teste",
                        plink_exe="C:/PuTTY/plink.exe",
                        leitor_putty=lambda: ({"vps-ovh": dict(SESSAO)}, []))
    t.ex, t.arq, t.motor = ex, arq, motor
    return t


def test_sessao_do_putty_aparece_na_lista(term):
    assert term.apelidos() == ["vps-ovh"]


def test_sem_leitor_do_putty_a_lista_nao_muda(tmp_path):
    motor = ap.Motor(pasta=str(tmp_path / "m"))
    t = dss.TerminalSSH(motor.log, arquivo_hosts=str(tmp_path / "h.json"))
    assert t.apelidos() == []


def test_leitor_que_quebra_nao_derruba_a_lista(tmp_path):
    motor = ap.Motor(pasta=str(tmp_path / "m"))

    def quebra():
        raise OSError("registro")
    t = dss.TerminalSSH(motor.log, arquivo_hosts=str(tmp_path / "h.json"), leitor_putty=quebra)
    assert t.apelidos() == []


def test_arquivo_do_dono_vence_apelido_repetido(term):
    term.arq.write_text(json.dumps({"vps-ovh": {"host": "10.1.1.1", "usuario": "eu"}}),
                        encoding="utf-8")
    assert term._hosts()["vps-ovh"]["host"] == "10.1.1.1"
    assert "origem" not in term._hosts()["vps-ovh"]


def test_leitura_em_sessao_do_putty_roda_pelo_plink_sem_cartao(term):
    r = term.rodar("vps-ovh", "uptime")
    assert r["ok"] and r["saida"].strip() == "ok"
    assert term.ex.chamadas == [["C:/PuTTY/plink.exe", "-load", "vps ovh", "-batch", "-T", "-a",
                                 "-x", "uptime"]]


def test_comando_que_muda_servidor_pede_cartao_tambem_no_putty(term):
    r = term.rodar("vps-ovh", "systemctl restart nginx")
    assert not r["ok"] and r["precisa_clique"] and term.ex.chamadas == []


def test_sem_plink_cai_no_ssh_do_windows(tmp_path, monkeypatch):
    motor = ap.Motor(pasta=str(tmp_path / "m"))
    ex = Executor()
    t = dss.TerminalSSH(motor.log, executar_ssh=ex, arquivo_hosts=str(tmp_path / "h.json"),
                        ssh_exe="ssh-de-teste", plink_exe="",
                        leitor_putty=lambda: ({"vps-ovh": dict(SESSAO)}, []))
    monkeypatch.setattr(dp, "localizar_plink", lambda: None)
    assert t.rodar("vps-ovh", "uptime")["ok"]
    assert ex.chamadas[0][0] == "ssh-de-teste" and "-l" in ex.chamadas[0]


def test_o_hash_inclui_o_nome_da_sessao_do_putty():
    a = dss.hash_do_par("vps-ovh", "uptime", SESSAO)
    b = dss.hash_do_par("vps-ovh", "uptime", dict(SESSAO, sessao="outra"))
    assert a != b


# ------------------------------------------------ Claude da VPS

def test_pergunta_vira_claude_p_com_aspas_e_nunca_e_leitura():
    c = dss.comando_claude_da_vps("como está o disco?")
    assert c == "claude -p 'como está o disco?'"
    assert dss.classificar_comando(c)["nivel"] == "muda_estado"


def test_pergunta_com_aspas_e_cifrao_nao_escapa_do_argumento():
    c = dss.comando_claude_da_vps("e se eu disser 'oi'; $(whoami)")
    import shlex
    assert shlex.split(c) == ["claude", "-p", "e se eu disser 'oi'; $(whoami)"]
    assert dss.classificar_comando(c)["nivel"] != "leitura"


@pytest.mark.parametrize("p", [None, 5, "", "   ", "linha\x00invisivel", "x" * 500])
def test_pergunta_invalida_ou_longa_nao_vira_comando(p):
    assert dss.comando_claude_da_vps(p) is None


def test_pergunta_com_pedido_destrutivo_e_recusada_pelo_classificador():
    c = dss.comando_claude_da_vps("apague tudo com rm -rf /")
    assert dss.classificar_comando(c)["nivel"] == "recusado"


def test_pergunta_espacada_e_normalizada_para_o_que_o_dono_ve():
    assert dss.comando_claude_da_vps("  oi   tudo  bem ") == "claude -p 'oi tudo bem'"


# ---------------------------------------------------------------- projetos que o DERVS não toca (06/10)
def test_sessoes_de_projetos_que_nao_se_tocam_ficam_fora():
    base = {"protocolo": "ssh", "host": "1.2.3.4", "usuario": "root", "porta": 22}
    for nome in ("TineHost-medconsultoria", "ccvp prod", "Zacareli", "sophia-site", "Camargo e Soares", "Nexa-api"):
        entrada, motivo = dp.interpretar(nome, dict(base))
        assert entrada is None and "não toca" in motivo, nome
    entrada, _ = dp.interpretar("VPS-OVH", dict(base))
    assert entrada is not None


def test_bloqueio_extra_da_config():
    base = {"protocolo": "ssh", "host": "1.2.3.4", "usuario": "root", "porta": 22}
    assert dp.interpretar("cliente-x", dict(base), dp.BLOQUEADAS_PADRAO + ("cliente-x",))[0] is None
    assert dp.interpretar("cliente-x", dict(base))[0] is not None
