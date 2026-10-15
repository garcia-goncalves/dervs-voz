#!/usr/bin/env python3
"""Testes dos pedidos de infraestrutura por voz (`dervs_voz_infra.py`, Ondas B, C e D).

Nada toca servidor, GitHub de verdade nem a config do dono: terminal, config e processos são
injetados; o único git real roda em pastas temporárias com um remoto local.
Rodar: python -m pytest test_dervs_voz_infra.py -q
"""
import os
import re
import subprocess

import pytest

import dervs_voz_infra as vi

APELIDOS = ["Dervs-Root", "Dervs-Tiba", "VPS-OVH"]


def i(fala, apelidos=APELIDOS):
    return vi.interpretar(fala, apelidos)


# ------------------------------------------------ servidor (Onda B)

@pytest.mark.parametrize("fala,comando", [
    ("Dervs, como está o disco da VPS?", "df -h"),
    ("qual a memória no servidor vps", "free -m"),
    ("há quanto tempo a VPS está no ar", "uptime"),
    ("quais containers estão rodando na vps", "docker ps"),
    ("status do nginx na vps", "systemctl status nginx"),
    ("logs do dervs-app na vps", "journalctl -u dervs-app -n 50 --no-pager"),
    ("roda uptime na vps", "uptime"),
])
def test_leituras_por_voz_viram_comando_conhecido(fala, comando):
    r = i(fala)
    assert r == {"tipo": "ssh", "apelido": "VPS-OVH", "comando": comando, "claude": False}


def test_o_modulo_de_voz_nao_importa_o_ssh():
    fonte = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dervs_voz_infra.py"),
                 encoding="utf-8").read()
    assert "import dervs_ssh" not in fonte and "from dervs_ssh" not in fonte


def test_servidor_ambiguo_pergunta_qual():
    r = i("como está o disco no servidor")
    assert r["tipo"] == "falar" and "Dervs-Root" in r["fala"] and "VPS-OVH" in r["fala"]


def test_apelido_pelo_nome_escolhe_um_so():
    assert i("roda uptime no dervs tiba")["apelido"] == "Dervs-Tiba"


def test_sem_servidor_cadastrado_diz_que_nao_tem():
    r = vi.interpretar("como está o disco da vps", [])
    assert r["tipo"] == "falar" and "cadastrado" in r["fala"]


def test_pergunta_ao_claude_da_vps_leva_a_pergunta_e_nao_um_comando():
    r = i("pergunta pro Claude da VPS por que o nginx caiu")
    assert r == {"tipo": "ssh", "apelido": "VPS-OVH", "comando": None,
                 "pergunta": "por que o nginx caiu", "claude": True}


def test_pergunta_longa_demais_nao_vai():
    assert i("pergunta pro claude da vps " + "x " * 200)["tipo"] == "falar"


def test_frase_sem_servidor_vai_ao_cerebro():
    assert i("que horas são") is None
    assert i("como está o disco") is None          # sem dizer onde: não adivinha servidor
    assert i("pede pro claude analisar meu pc") is None


# ------------------------------------------------ projetos e GitHub (Onda C)

def test_abrir_projeto_entende_a_frase():
    assert i("abre o projeto dervs voz no VS Code") == {"tipo": "projeto_abrir", "nome": "dervs voz"}


def test_pedir_conserto_nos_dois_jeitos():
    a = i("pede pro claude consertar o login no projeto dervs voz")
    b = i("no projeto dervs voz, pede pro claude consertar o login")
    assert a == {"tipo": "projeto_claude", "pedido": "consertar o login", "nome": "dervs voz"}
    assert b == a


def test_pedir_ao_claude_sem_projeto_nao_e_do_modulo():
    assert i("pede pro claude consertar o login") is None


@pytest.mark.parametrize("fala", [
    "faz push forçado do projeto dervs voz no github",
    "força o push do projeto dervs voz no github",
    "deixa o repositório público no github",
    "apaga o branch remoto do projeto dervs voz",
    "deleta a tag v1 do repositório",
])
def test_force_publico_e_apagar_remoto_ganham_recusa(fala):
    r = i(fala)
    assert r["tipo"] == "falar" and "não faço por voz" in r["fala"]


def test_commit_e_push_vira_envio():
    assert i("faz commit e push do projeto dervs voz") == {"tipo": "git_enviar", "nome": "dervs voz"}


def test_nenhum_caminho_do_modulo_usa_force_ou_publico():
    fonte = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dervs_voz_infra.py"),
                 encoding="utf-8").read()
    chamadas = re.findall(r"self\._git\([^)]*\)", fonte)
    assert chamadas and not any("force" in c or '"-f"' in c or "--delete" in c or "public" in c
                                for c in chamadas)
    assert "shell=True" not in fonte


# ------------------------------------------------ configuração (Onda D)

def test_fala_mais_rapido_e_devagar():
    assert i("fala mais rápido") == {"tipo": "config_ritmo", "sentido": 1}
    assert i("dervs, fale mais devagar") == {"tipo": "config_ritmo", "sentido": -1}


def test_troca_a_voz():
    assert i("troca a voz para onyx") == {"tipo": "config", "chave": "voz_openai", "valor": "onyx"}
    assert i("troca a voz para ônix")["valor"] == "onyx"
    assert i("troca a voz para o zumbi")["tipo"] == "falar"


def test_modo_sempre_confirmar():
    assert i("ativa o modo sempre confirmar") == {"tipo": "config", "chave": "confirmar_plano",
                                                  "valor": "sempre"}
    assert i("desativa o modo sempre confirmar")["valor"] == "grave"


@pytest.mark.parametrize("fala", [
    "aumenta o teto de gasto", "muda as permissões", "libera as pastas de projeto",
    "troca a senha", "altera o limite de gasto para 100",
])
def test_chave_de_seguranca_nao_muda_por_voz(fala):
    assert i(fala) == {"tipo": "config_protegida"}


# ------------------------------------------------ execução

class Cfg:
    def __init__(self, **ini):
        self.dados = dict(ini)
        self.vivo = []

    def gravar(self, k, v):
        self.dados[k] = v
        return True

    def ler(self):
        return dict(self.dados)


@pytest.fixture
def acoes(tmp_path):
    cfg = Cfg(voz_openai_tempo=1.25, voz_velocidade=1.2)
    repos = tmp_path / "repos"
    (repos / "dervs-voz").mkdir(parents=True)
    (repos / "grimoire").mkdir()
    chamadas = []
    a = vi.AcoesVoz(terminal_por_voz=lambda ap, c, p=None: chamadas.append((ap, c)) or "feito",
                    raizes_fn=lambda: [str(repos)], gravar_config=cfg.gravar, ler_config=cfg.ler,
                    aplicar_ao_vivo=lambda k, v: cfg.vivo.append((k, v)),
                    abrir_vscode=lambda p: f"abri {os.path.basename(p)}",
                    abrir_claude=lambda p, t: chamadas.append(("claude", p, t)),
                    pasta_worktrees=str(tmp_path / "wt"))
    a.cfg, a.chamadas, a.repos = cfg, chamadas, repos
    return a


def test_ssh_vai_ao_terminal_injetado(acoes):
    assert acoes.executar({"tipo": "ssh", "apelido": "VPS-OVH", "comando": "uptime"}) == "feito"
    assert acoes.chamadas == [("VPS-OVH", "uptime")]


def test_ritmo_sobe_e_para_no_teto(acoes):
    for _ in range(10):
        acoes.executar({"tipo": "config_ritmo", "sentido": 1})
    assert acoes.cfg.dados["voz_openai_tempo"] == 1.6 and acoes.cfg.dados["voz_velocidade"] == 2.0
    assert "mais rápido que a voz aguenta" in acoes.executar({"tipo": "config_ritmo", "sentido": 1})


def test_ritmo_desce_e_para_no_piso(acoes):
    for _ in range(10):
        acoes.executar({"tipo": "config_ritmo", "sentido": -1})
    assert acoes.cfg.dados["voz_openai_tempo"] == 1.0 and acoes.cfg.dados["voz_velocidade"] == 0.5


def test_so_chave_da_lista_fixa_grava(acoes):
    assert "não muda por voz" in acoes.executar(
        {"tipo": "config", "chave": "teto_gasto_dia_usd", "valor": 99})
    assert "teto_gasto_dia_usd" not in acoes.cfg.dados
    acoes.executar({"tipo": "config", "chave": "voz_openai", "valor": "onyx"})
    assert acoes.cfg.dados["voz_openai"] == "onyx" and ("voz_openai", "onyx") in acoes.cfg.vivo


def test_config_protegida_nao_grava_nada(acoes):
    assert "clique no painel" in acoes.executar({"tipo": "config_protegida"})
    assert acoes.cfg.dados == {"voz_openai_tempo": 1.25, "voz_velocidade": 1.2}


def test_achar_projeto_por_nome_aproximado(acoes):
    assert acoes.executar({"tipo": "projeto_abrir", "nome": "dervs voz"}) == "abri dervs-voz"
    assert acoes.executar({"tipo": "projeto_abrir", "nome": "grimoar"}) == "abri grimoire"
    assert "Não achei" in acoes.executar({"tipo": "projeto_abrir", "nome": "banco do brasil"})


def test_projeto_fora_das_pastas_de_projeto_nao_e_achado(acoes, tmp_path):
    (tmp_path / "fora" / "segredo").mkdir(parents=True)
    assert "Não achei" in acoes.executar({"tipo": "projeto_abrir", "nome": "segredo"})


def test_empate_pergunta_qual(tmp_path):
    for n in ("loja-a", "loja-b"):
        (tmp_path / n).mkdir()
    pasta, empate = vi.achar_projeto("loja", [str(tmp_path)])
    assert pasta is None and sorted(empate) == ["loja-a", "loja-b"]


# ------------------------------------------------ git de verdade, em pasta temporária

def ramos_do_remoto(remoto):
    return g(remoto, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()


def g(pasta, *args):
    return subprocess.run(["git", "-C", str(pasta), *args], capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def repo(acoes, tmp_path):
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remoto)], check=True,
                   capture_output=True)
    pasta = acoes.repos / "dervs-voz"
    g(pasta, "init", "-b", "main")
    g(pasta, "config", "user.email", "t@t.t")
    g(pasta, "config", "user.name", "t")
    (pasta / "a.txt").write_text("1")
    g(pasta, "add", "-A")
    g(pasta, "commit", "-m", "base")
    g(pasta, "remote", "add", "origin", str(remoto))
    g(pasta, "push", "-u", "origin", "main")
    acoes.remoto = remoto
    return pasta


def test_conserto_abre_worktree_em_branch_proprio_sem_tocar_a_main(acoes, repo):
    fala = acoes.executar({"tipo": "projeto_claude", "nome": "dervs voz",
                           "pedido": "consertar o login"})
    assert "confirma" in fala and not [c for c in acoes.chamadas if c[0] == "claude"]   # nada abriu ainda
    assert "cópia isolada" in acoes.responder_pendencia(True)
    _, destino, pedido = [c for c in acoes.chamadas if c[0] == "claude"][0]
    assert pedido == "consertar o login" and os.path.isdir(destino)
    assert g(destino, "rev-parse", "--abbrev-ref", "HEAD").strip().startswith("dervs/")
    assert g(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


def test_conserto_nunca_abre_claude_interativo_fora_das_travas_do_dervs():
    """Revisão 15/10: abria `claude` no PowerShell com o config inteiro do dono, sem o
    gancho do DERVS; só `git push` era barrado e `git -C x push`/`gh` passavam."""
    import inspect
    fonte = inspect.getsource(vi)
    assert "disallowedTools" not in fonte and "-NoExit" not in fonte


def test_sem_sessao_do_claude_ligada_o_conserto_nao_cria_copia(acoes, repo, tmp_path):
    acoes._abrir_claude = None
    acoes.executar({"tipo": "projeto_claude", "nome": "dervs voz", "pedido": "consertar o login"})
    fala = acoes.responder_pendencia(True)
    assert "não" in fala.lower() and not (tmp_path / "wt").exists()


def test_claude_ocupado_desfaz_a_copia_isolada(acoes, repo, tmp_path):
    acoes._abrir_claude = lambda pasta, pedido: False
    acoes.executar({"tipo": "projeto_claude", "nome": "dervs voz", "pedido": "consertar o login"})
    fala = acoes.responder_pendencia(True)
    assert "ocupado" in fala
    assert not [p for p in (tmp_path / "wt").iterdir()] if (tmp_path / "wt").exists() else True
    assert "dervs/" not in g(repo, "branch", "--list")


def test_envio_na_main_vai_para_branch_novo_depois_do_confirma(acoes, repo):
    (repo / "novo.txt").write_text("x")
    fala = acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    assert "confirma" in fala and acoes.tem_pendencia()
    assert ramos_do_remoto(acoes.remoto) == ["main"]        # ainda nada saiu
    assert "mandei ao GitHub" in acoes.responder_pendencia(True)
    assert any(r.startswith("dervs/voz-") for r in ramos_do_remoto(acoes.remoto))
    assert g(acoes.remoto, "rev-parse", "main").strip() == g(repo, "rev-parse", "origin/main").strip()
    assert "novo.txt" not in g(repo, "show", "--name-only", "--format=", "main")


def test_dizer_nao_cancela_e_nada_e_enviado(acoes, repo):
    (repo / "novo.txt").write_text("x")
    acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    assert "cancelei" in acoes.responder_pendencia(False)
    assert not acoes.tem_pendencia()
    assert ramos_do_remoto(acoes.remoto) == ["main"]


def test_confirmacao_vence(acoes, repo):
    t = [100.0]
    acoes._relogio = lambda: t[0]
    (repo / "novo.txt").write_text("x")
    acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    t[0] += vi.VALIDADE_CONFIRMACAO_S + 1
    assert not acoes.tem_pendencia()
    assert "venceu" in acoes.responder_pendencia(True)


def test_arquivo_de_segredo_barra_o_envio(acoes, repo):
    (repo / ".env").write_text("CHAVE=1")
    fala = acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    assert "segredo" in fala and not acoes.tem_pendencia()


def test_segredo_que_aparece_depois_do_pedido_tambem_barra(acoes, repo):
    (repo / "novo.txt").write_text("x")
    acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    (repo / "id_rsa").write_text("-----")
    assert "segredo" in acoes.responder_pendencia(True)
    assert ramos_do_remoto(acoes.remoto) == ["main"]


def test_sem_mudanca_nao_ha_o_que_enviar(acoes, repo):
    assert "nada novo" in acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})


@pytest.mark.parametrize("fala,esperado", [
    ("confirma", "sim"), ("Dervs, confirma", "sim"),
    ("não", "nao"), ("cancela", "nao"),
    ("beleza", None), ("ok", None), ("sim", None), ("pode", None), ("manda ver", None),
    ("pode enviar", None), ("pode mandar", None),
])
def test_so_a_palavra_do_pedido_confirma_o_envio(fala, esperado):
    assert vi.resposta_de_envio(fala) == esperado


def test_pergunta_com_apelido_de_hifen_nao_perde_palavras():
    r = i("pergunta pro claude da vps-ovh quantos containers tem")
    assert r["apelido"] == "VPS-OVH" and r["pergunta"] == "quantos containers tem"
    r = i("pergunta pro claude no dervs tiba por que caiu")
    assert r["apelido"] == "Dervs-Tiba" and r["pergunta"] == "por que caiu"


def test_roda_com_em_no_meio_do_comando_fica_inteiro():
    assert i("roda ls em /srv na vps")["comando"] == "ls em /srv"


def test_status_e_logs_nao_tomam_palavra_comum_por_unidade():
    assert i("status do servidor na vps") is None
    assert i("logs do docker na vps") is None or i("logs do docker na vps")["comando"] == "docker ps"


def test_recusa_de_seguranca_vem_antes_do_servidor():
    assert i("muda o limite de memória no servidor") == {"tipo": "config_protegida"}


def test_segredo_dentro_de_pasta_nova_barra_o_envio(acoes, repo):
    (repo / "n").mkdir()
    (repo / "n" / ".env").write_text("X=1")
    assert "segredo" in acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})


def test_confirma_repetido_envia_uma_vez_so(acoes, repo):
    (repo / "novo.txt").write_text("x")
    acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    assert "mandei ao GitHub" in acoes.responder_pendencia(True)
    assert "venceu" in acoes.responder_pendencia(True)


def test_conserto_cancelado_nao_abre_nada(acoes, repo):
    acoes.executar({"tipo": "projeto_claude", "nome": "dervs voz", "pedido": "consertar o login"})
    assert "cancelei" in acoes.responder_pendencia(False)
    assert not [c for c in acoes.chamadas if c[0] == "claude"]


def test_envio_sempre_vai_para_branch_proprio_mesmo_fora_da_main(acoes, repo):
    g(repo, "switch", "-c", "staging")
    (repo / "novo.txt").write_text("x")
    assert "dervs/voz-" in acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    acoes.responder_pendencia(True)
    assert "staging" not in ramos_do_remoto(acoes.remoto)


@pytest.mark.parametrize("nome", ["chave.ppk", "prontuarios.sqlite", "appsettings.Production.json",
                                  "wp-config.php", "gcp-credentials.json", "terraform.tfstate"])
def test_segredos_que_a_lista_antiga_deixava_passar(nome):
    assert vi._SEGREDO.search("deploy/" + nome)


def test_so_vai_o_que_foi_conferido(acoes, repo):
    (repo / "novo.txt").write_text("x")
    acoes.executar({"tipo": "git_enviar", "nome": "dervs voz"})
    (repo / "depois.txt").write_text("y")                       # apareceu depois do "confirma"? não entra
    acoes.responder_pendencia(True)
    ramo = [r for r in ramos_do_remoto(acoes.remoto) if r.startswith("dervs/voz-")][0]
    arquivos = g(acoes.remoto, "show", "--name-only", "--format=", ramo).split()
    assert arquivos == ["novo.txt"]


def test_stt_que_ouve_cloud_no_lugar_de_claude_ainda_entende():
    r = vi.interpretar("pergunta pro cloud da VPS OVH se o docker esta de pe", ("VPS-OVH", "Dervs-Root"))
    assert r["tipo"] == "ssh" and r["apelido"] == "VPS-OVH" and r["claude"] is True
