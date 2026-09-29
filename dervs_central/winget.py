"""Programas com versão nova no winget. Só consulta; atualizar é ação com aprovação."""
import re
import subprocess

import dervs_processos as processos
from dervs_central.base import ErroConsulta, consultar, falha, resultado

_LINHA_RESUMO = re.compile(r"^\d+\s+(?:upgrades?|atualiza|pacotes?|packages?)", re.IGNORECASE)
_MODULO = ("Get-WinGetPackage | Where-Object IsUpdateAvailable | Select-Object Name,Id,"
           "InstalledVersion,@{n='Nova';e={[string]$_.AvailableVersions[0]}}")


def rodar_winget(timeout: float = 90) -> str:
    try:
        p = subprocess.run(["winget", "upgrade", "--include-unknown", "--disable-interactivity"],
                           capture_output=True, timeout=timeout, **processos.sem_janela())
    except (OSError, subprocess.TimeoutExpired) as erro:
        raise ErroConsulta(f"winget indisponível ({erro.__class__.__name__})") from erro
    return p.stdout.decode("utf-8", "replace")


def interpretar_texto(texto: str) -> list:
    """Lê a tabela de `winget upgrade`: acha o cabeçalho, corta as colunas pelas
    posições dele e para na linha '... atualizações disponíveis'."""
    linhas = [l.rstrip("\r") for l in (texto or "").splitlines()]
    for i, linha in enumerate(linhas):
        if i > 0 and linha.strip() and set(linha.strip()) == {"-"}:
            cab, corpo = linhas[i - 1], linhas[i + 1:]
            break
    else:
        return []
    marcas = {}
    for nome, opcoes in (("nome", ("Name", "Nome")), ("id", ("Id", "ID")),
                         ("versao", ("Version", "Versão")), ("nova", ("Available", "Disponível")),
                         ("fonte", ("Source", "Origem"))):
        for o in opcoes:
            pos = cab.find(o)
            if pos >= 0:
                marcas[nome] = pos
                break
    if not {"nome", "id", "versao", "nova"} <= set(marcas):
        return []
    ordem = sorted(marcas.items(), key=lambda kv: kv[1])
    itens = []
    for linha in corpo:
        if not linha.strip() or _LINHA_RESUMO.match(linha.strip()):
            break
        campos = {}
        for n, (nome, pos) in enumerate(ordem):
            fim = ordem[n + 1][1] if n + 1 < len(ordem) else len(linha)
            campos[nome] = linha[pos:fim].strip()
        if campos.get("id"):
            itens.append({"nome": campos["nome"], "id": campos["id"],
                          "versao_instalada": campos["versao"], "versao_nova": campos["nova"]})
    return itens


def coletar(rodar=None, rodar_texto=None) -> dict:
    try:
        brutos = consultar(rodar, _MODULO)
        itens = [{"nome": p.get("Name") or "", "id": p.get("Id") or "",
                  "versao_instalada": str(p.get("InstalledVersion") or ""),
                  "versao_nova": str(p.get("Nova") or "")} for p in brutos]
        return resultado(itens, via="modulo")
    except ErroConsulta:
        pass
    try:
        return resultado(interpretar_texto((rodar_texto or rodar_winget)()), via="texto")
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
