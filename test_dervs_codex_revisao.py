#!/usr/bin/env python3
"""Achados das revisões de segurança e de Python sobre o Codex (`fix(codex)`).

Rodar: python -m pytest test_dervs_codex_revisao.py -q
"""
import os
import subprocess
import sys
import threading
import time

import pytest

import dervs_codex as cx
import dervs_codex_voz as cv


def _chave():
    return "s" + "k-" + "proj" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4"


# ------------------------------------------------ bloqueante: nada de ferramenta externa

@pytest.mark.parametrize("modo", ["leitura", "escrita"])
def test_argv_isola_config_do_dono_conectores_e_navegador(modo):
    a = cx.montar_argv("codex.exe", "C:\\p", "s.txt", modo)
    assert "--ignore-user-config" in a
    assert 'windows.sandbox="elevated"' in a and 'web_search="disabled"' in a
    desligados = [a[i + 1] for i, x in enumerate(a) if x == "--disable"]
    for f in ("apps", "plugins", "plugin_sharing", "browser_use", "browser_use_external",
              "browser_use_full_cdp_access", "computer_use", "in_app_browser", "hooks", "image_generation"):
        assert f in desligados
    assert a[-1] == "-" and a.index("--ignore-user-config") < a.index("-C")


def test_codex_recusou_opcao_de_seguranca_nao_roda_sem_ela(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_text("x")

    def executor(argv, entrada, timeout, env=None, **_):
        return 2, "", "error: unknown feature 'browser_use'"
    c = cx.Codex(config_fn=lambda: {"codex_ligado": True, "codex_caminho": str(exe)}, executor=executor,
                 pasta_temp=str(tmp_path))
    r = c.perguntar("x", str(tmp_path))
    assert not r["ok"] and "opção de segurança" in r["motivo"]


# ------------------------------------------------ 1. ambiente em lista branca

def test_ambiente_so_leva_a_lista_branca():
    base = {"PATH": "p", "SystemRoot": "C:\\Windows", "TEMP": "t", "CODEX_HOME": "h", "LANG": "pt", "LC_ALL": "x",
            "ProgramFiles(x86)": "pf", "PROCESSOR_ARCHITECTURE": "AMD64", "ANTHROPIC_API_KEY": "a",
            "TYPESAFE_API_KEY": "b", "AWS_SECRET_ACCESS_KEY": "c", "AZURE_CLIENT_SECRET": "d",
            "GIT_SSH_COMMAND": "ssh -i x", "OPENAI_API_KEY": "e", "MINHA_VAR": "z"}
    env = cx._ambiente(False, base)
    assert set(env) == {"PATH", "SystemRoot", "TEMP", "CODEX_HOME", "LANG", "LC_ALL", "ProgramFiles(x86)",
                        "PROCESSOR_ARCHITECTURE"}


def test_ambiente_de_escrita_neutraliza_credencial_hooks_e_fsmonitor():
    env = cx._ambiente(True, {"PATH": "p", "GH_TOKEN": "t"})
    pares = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
    assert pares == {"credential.helper": "", "core.hooksPath": "NUL", "core.fsmonitor": "false"}
    assert "GH_TOKEN" not in env and env["GIT_TERMINAL_PROMPT"] == "0"


# ------------------------------------------------ 2. só .exe, sem UNC

def test_codex_cmd_nao_e_aceito_e_unc_e_recusado(tmp_path):
    cmd = tmp_path / "codex.cmd"
    cmd.write_text("x")
    achado, motivo = cx.localizar(str(cmd), padrao_pacotes=str(tmp_path / "n*"), appx=lambda: None,
                                  onde=lambda n: str(cmd))
    assert achado is None and motivo
    achado, motivo = cx.localizar("\\\\servidor\\pasta\\codex.exe", padrao_pacotes=str(tmp_path / "n*"),
                                  appx=lambda: None, onde=lambda n: None)
    assert achado is None and "rede" in motivo
    achado, _ = cx.localizar("", padrao_pacotes=str(tmp_path / "n*"), appx=lambda: None, onde=lambda n: str(cmd))
    assert achado is None                                    # nem pelo PATH


# ------------------------------------------------ 3. cache de localizar

def test_cache_reusa_enquanto_o_arquivo_existe_e_refaz_se_sumir(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_text("x")
    chamadas = []

    def loc(caminho):
        chamadas.append(caminho)
        return (str(exe) if exe.exists() else None), "motivo"
    c = cx.Codex(config_fn=lambda: {}, localizar_fn=loc, executor=lambda *a, **k: (0, "Logged in using ChatGPT", ""))
    assert c._achar() == (str(exe), "motivo") and c._achar()[0] == str(exe)
    assert len(chamadas) == 1
    exe.unlink()
    assert c._achar()[0] is None and len(chamadas) == 2


def test_cache_negativo_vale_60s_e_depois_procura_de_novo():
    agora, chamadas = [0.0], []

    def loc(caminho):
        chamadas.append(1)
        return None, "não achei"
    c = cx.Codex(config_fn=lambda: {}, localizar_fn=loc, relogio=lambda: agora[0])
    c._achar(), c._achar()
    assert len(chamadas) == 1
    agora[0] = 61.0
    c._achar()
    assert len(chamadas) == 2


def test_cache_nao_grava_em_disco_e_troca_de_config_invalida(tmp_path):
    chamadas = []
    conf = {"codex_caminho": "a"}

    def loc(caminho):
        chamadas.append(caminho)
        return None, "x"
    c = cx.Codex(config_fn=lambda: conf, localizar_fn=loc)
    c._achar()
    conf["codex_caminho"] = "b"
    c._achar()
    assert chamadas == ["a", "b"]


# ------------------------------------------------ 4. limites e blocos de segredo

def test_bloco_de_chave_privada_e_removido_inteiro():
    ini, fim = "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----", "-----END " + "OPENSSH PRIVATE" + " KEY-----"
    pem = ini + "\nAAAAB3Nza\nC1yc2EAAAAD\n" + fim
    r = cx.filtrar_saida(f"antes\n{pem}\ndepois")
    assert "AAAAB3Nza" not in r and "C1yc2EAAAAD" not in r and "antes" in r and "depois" in r


def test_bloco_pem_sem_fim_vai_ate_o_fim_do_texto():
    r = cx.filtrar_saida("a\n" + "-----BEGIN " + "RSA PRIVATE" + " KEY-----" + "\nMIIEow\nresto")
    assert "MIIEow" not in r and "resto" not in r and r.startswith("a")


def test_resposta_gigante_e_cortada_antes_do_filtro(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_text("x")

    def executor(argv, entrada, timeout, env=None, **_):
        with open(argv[argv.index("--output-last-message") + 1], "w", encoding="utf-8") as f:
            f.write("a" * (cx.LIMITE_BYTES * 3))
        return 0, "", ""
    c = cx.Codex(config_fn=lambda: {"codex_ligado": True, "codex_caminho": str(exe)}, executor=executor,
                 pasta_temp=str(tmp_path))
    r = c.perguntar("x", str(tmp_path))
    assert r["ok"] and len(r["texto"]) <= cx.LIMITE_BYTES + 100 and "cortad" in r["texto"]


def test_stdout_gigante_e_truncado_com_aviso():
    _, saida, _ = cx.executar_processo(
        [sys.executable, "-c", f"print('x' * {cx.LIMITE_BYTES * 3})"], "", 30)
    assert len(saida) <= cx.LIMITE_BYTES + 100 and "cortad" in saida


# ------------------------------------------------ 10. parar de verdade

def _vivo(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def test_matar_arvore_derruba_o_neto_que_segura_o_pipe(tmp_path):
    arq = tmp_path / "neto.pid"
    codigo = ("import subprocess,sys,time;"
              "n=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
              f"open(r'{arq}','w').write(str(n.pid));time.sleep(60)")
    guardado, fim = [], []

    def roda():
        try:
            cx.executar_processo([sys.executable, "-c", codigo], "", 120, ao_iniciar=guardado.append)
        except Exception as e:
            fim.append(e)
        else:
            fim.append("ok")
    t = threading.Thread(target=roda)
    t.start()
    for _ in range(100):
        if arq.exists() and arq.read_text():
            break
        time.sleep(0.1)
    neto = int(arq.read_text())
    assert _vivo(neto)
    cx._matar_arvore(guardado[0])
    t.join(30)
    assert not t.is_alive()                                  # o pipe fechou: nada ficou pendurado
    time.sleep(0.5)
    assert not _vivo(neto)


def test_parar_antes_do_popen_mata_o_processo_assim_que_ele_nasce(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_text("x")
    mortos, andamento = [], threading.Event()

    class Proc:
        pid = 1

        def kill(self):
            mortos.append(1)

    def executor(argv, entrada, timeout, env=None, ao_iniciar=None, cwd=None):
        andamento.set()
        time.sleep(0.3)                                      # o dono diz "para" antes de o Popen existir
        ao_iniciar(Proc())
        return 0, "", ""
    c = cx.Codex(config_fn=lambda: {"codex_ligado": True, "codex_caminho": str(exe)}, executor=executor,
                 pasta_temp=str(tmp_path))
    res = []
    t = threading.Thread(target=lambda: res.append(c.perguntar("x", str(tmp_path))))
    t.start()
    assert andamento.wait(5)
    assert c.parar() is True
    t.join(10)
    assert mortos and res[0]["motivo"] == "Parei o Codex."


# ------------------------------------------------ 8. pasta neutra não isola; 9. STT

@pytest.mark.parametrize("pedido", [
    "ler C:\\Users\\Desktop\\.env", "abre /etc/passwd e resume", "mostra o .env", "qual a senha do banco",
    "lista a chave da api", "o token do github", "o segredo do cofre", "leia o auth.json", "cat id_rsa",
])
def test_pedido_sem_projeto_que_cita_caminho_ou_segredo_e_recusado(tmp_path, pedido):
    from test_dervs_codex_voz import CodexFalso
    falso = CodexFalso()
    a = cv.AcoesCodex(codex=falso, raizes_fn=lambda: [], pasta_worktrees=str(tmp_path / "wt"),
                      pasta_neutra=str(tmp_path / "v"))
    fala = a.executar({"tipo": "codex_leitura", "pedido": pedido, "projeto": None})
    assert "escolha um projeto" in fala.lower() and not falso.chamadas


@pytest.mark.parametrize("fala,tipo", [
    ("pede pro códice analisar o login", "codex_leitura"),
    ("pergunta pro Kodex o que é isso", "codex_leitura"),
    ("manda o codecs revisar a função", "codex_leitura"),
    ("pede pro code x explicar o erro", "codex_leitura"),
    ("pede pro kodak analisar o erro", "codex_leitura"),
])
def test_stt_confunde_o_nome_mas_com_verbo_forte_ainda_casa(fala, tipo):
    assert cv.interpretar(fala)["tipo"] == tipo


@pytest.mark.parametrize("fala", [
    "usa o codec h264 para converter", "usa o codecs para explicar", "use o code x para isso",
    "o codec é bom", "usa o kodak para fotografar", "usa o codes para analisar",
])
def test_variante_fraca_com_usa_nao_e_roubada(fala):
    assert cv.interpretar(fala) is None


def test_usa_o_codex_forte_continua_valendo():
    assert cv.interpretar("usa o Codex para explicar o erro")["tipo"] == "codex_leitura"


def test_projeto_inexistente_cai_para_leitura_sem_projeto_com_a_frase_inteira(tmp_path):
    from test_dervs_codex_voz import CodexFalso
    i = cv.interpretar("pede pro Codex explicar o que é um mutex no projeto fantasma")
    assert i["projeto"] == "fantasma" and i["pedido_inteiro"].endswith("no projeto fantasma")
    falso = CodexFalso()
    a = cv.AcoesCodex(codex=falso, raizes_fn=lambda: [str(tmp_path)], pasta_worktrees=str(tmp_path / "wt"),
                      pasta_neutra=str(tmp_path / "v"))
    a.executar(i)
    assert falso.chamadas[0][0] == i["pedido_inteiro"] and falso.chamadas[0][1] == str(tmp_path / "v")
