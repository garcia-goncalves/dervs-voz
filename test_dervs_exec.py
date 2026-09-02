#!/usr/bin/env python3
"""Testes do executor do DERVS.

Rodar: python -m pytest test_dervs_exec.py -q
(Nesta máquina 'pytest' só responde por 'python -m pytest'.)

O que estes testes protegem: o atalho de "app de tela" abria a linha inteira num
shell e só olhava o primeiro token. "notepad && net user invasor 123 /add"
passava como app inofensivo e o cmd.exe rodava as duas partes.
"""
import pytest

from dervs_exec import eh_app_de_tela, _argumentos


@pytest.mark.parametrize("comando", [
    "firefox",
    "chrome https://google.com",
    "notepad",
    r"notepad C:\Users\dono\nota.txt",
    "explorer.exe",
    "code",
])
def test_app_de_tela_continua_sendo_app(comando):
    assert eh_app_de_tela(comando) is True


@pytest.mark.parametrize("comando", [
    "notepad && net user invasor 123 /add",
    "chrome https://google.com & schtasks /create /tn B /tr p.exe /sc onlogon",
    "notepad; Remove-Item C:\\x -Recurse",
    "explorer | Out-File x.txt",
    "notepad ^ calc",
    "chrome `whoami`",
])
def test_linha_que_emenda_outro_comando_nao_e_app_de_tela(comando):
    assert eh_app_de_tela(comando) is False


def test_argumentos_quebra_sem_shell_preservando_caminho_do_windows():
    partes = _argumentos(r'notepad "C:\Users\dono\meu arquivo.txt"')
    assert partes[0] == "notepad"
    assert partes[1].endswith("meu arquivo.txt")
    assert '"' not in partes[1]
