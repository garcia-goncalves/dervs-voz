#!/usr/bin/env python3
"""Estourar o tempo tem de matar o comando INTEIRO, não só a casca dele.

Por que existe (achado na revisão de 02/09/2026, noite):

`dervs_exec.rodar` e `dervs_browser.rodar_para_app` usavam
`subprocess.run(..., timeout=N)`. Quando o tempo estoura, o Python mata o
processo que ELE abriu — e só ele. Os netos ficam vivos.

Isso não é teoria. Dois cenários concretos:

  1. O dono diz "roda o nmap no alvo" (frase que está no próprio vocabulário do
     DERVS). O `powershell.exe` dispara o `nmap.exe`. Passa dos 60 s: o
     PowerShell morre, o nmap CONTINUA varrendo a rede. A tela diz "foi
     interrompido" — e mente.
  2. O navegador autônomo abre o Chrome do dono com o perfil de verdade. Passa
     do tempo: o Python que o comandava morre sem rodar o `finally` que fecha o
     navegador, e sobra um `chrome.exe` órfão segurando o perfil. Depois disso
     o dono não consegue mais abrir o próprio Chrome, e não tem como saber que
     foi o DERVS que travou.

Estes testes abrem processos DE VERDADE, com netos de verdade, e conferem que
o neto morreu junto. Dublê não provaria nada aqui — o defeito é exatamente na
fronteira com o sistema operacional.

Rodar: python -m pytest test_dervs_arvore_de_processos.py -q
"""
import subprocess
import sys
import time

import pytest

import dervs_processos as proc


# Um pai que abre um neto de vida longa, anota o PID do neto num arquivo, e
# então dorme. Se a árvore for morta direito, o neto morre junto.
_PAI = """
import subprocess, sys, time
neto = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(sys.argv[1], "w").write(str(neto.pid))
time.sleep(120)
"""


def _vivo(pid: int) -> bool:
    if sys.platform == "win32":
        saida = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                               capture_output=True, text=True).stdout
        return str(pid) in saida
    import os
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _esperar_morrer(pid: int, segundos=15) -> bool:
    fim = time.time() + segundos
    while time.time() < fim:
        if not _vivo(pid):
            return True
        time.sleep(0.3)
    return False


def _pid_do_neto(arquivo, segundos=20) -> int:
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            texto = arquivo.read_text().strip()
            if texto:
                return int(texto)
        except OSError:
            pass
        time.sleep(0.2)
    pytest.fail("o processo de teste não chegou a abrir o neto")


# ---- o contrato normal (sem estouro de tempo) --------------------------

def test_comando_que_termina_a_tempo_devolve_saida_e_codigo():
    r = proc.rodar_com_arvore([sys.executable, "-c", "print('oi')"],
                              timeout=60, capture_output=True, text=True)
    assert r.returncode == 0
    assert "oi" in r.stdout


def test_codigo_de_erro_chega_inteiro():
    r = proc.rodar_com_arvore([sys.executable, "-c", "import sys; sys.exit(3)"],
                              timeout=60, capture_output=True, text=True)
    assert r.returncode == 3


def test_a_saida_de_erro_vem_separada():
    r = proc.rodar_com_arvore(
        [sys.executable, "-c", "import sys; sys.stderr.write('deu ruim')"],
        timeout=60, capture_output=True, text=True)
    assert "deu ruim" in r.stderr


def test_sem_timeout_tambem_funciona():
    r = proc.rodar_com_arvore([sys.executable, "-c", "print('sem prazo')"],
                              capture_output=True, text=True)
    assert r.returncode == 0


def test_respeita_a_pasta_de_trabalho(tmp_path):
    r = proc.rodar_com_arvore([sys.executable, "-c", "import os; print(os.getcwd())"],
                              timeout=60, cwd=str(tmp_path),
                              capture_output=True, text=True)
    assert str(tmp_path).lower() in r.stdout.strip().lower()


# ---- o que este arquivo existe para provar -----------------------------

def test_estouro_de_tempo_ainda_levanta_TimeoutExpired(tmp_path):
    """Quem chama já trata essa exceção — o contrato não pode mudar."""
    with pytest.raises(subprocess.TimeoutExpired):
        proc.rodar_com_arvore(
            [sys.executable, "-c", _PAI, str(tmp_path / "neto.txt")],
            timeout=3, capture_output=True, text=True)


def test_o_neto_morre_junto_com_o_pai_no_estouro(tmp_path):
    """O CORAÇÃO: o nmap não pode continuar varrendo depois do "interrompido"."""
    marcador = tmp_path / "neto.txt"
    with pytest.raises(subprocess.TimeoutExpired):
        proc.rodar_com_arvore(
            [sys.executable, "-c", _PAI, str(marcador)],
            timeout=5, capture_output=True, text=True)
    neto = _pid_do_neto(marcador)
    assert _esperar_morrer(neto), (
        f"o processo {neto} sobreviveu ao estouro de tempo — é o nmap "
        f"continuando a varrer, ou o Chrome segurando o perfil do dono")


def test_encerrar_arvore_nao_estoura_com_processo_ja_morto():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait(timeout=30)
    proc.encerrar_arvore(p)          # não pode levantar nada
