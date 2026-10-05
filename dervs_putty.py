#!/usr/bin/env python3
"""DERVS — sessões salvas do PuTTY (só leitura do registro do Windows).

Lê `HKCU\\Software\\SimonTatham\\PuTTY\\Sessions` e devolve, para cada sessão SSH, só
quatro coisas: o nome, o endereço, o usuário e a porta. Senha e chave NUNCA são lidas
(nem o caminho do arquivo de chave): quem autentica é o próprio plink/ssh do dono, com
o agente ou a chave que ele já configurou.

Sessão que mandaria o DERVS fazer mais do que "rodar um comando" é pulada, com o motivo
(proxy local, redirecionamento de porta): o dono não cadastrou isso para
virar uma execução por voz.
"""
import os
import re
import urllib.parse

try:  # só existe no Windows
    import winreg
except ImportError:  # pragma: no cover
    winreg = None

RAIZ = r"Software\SimonTatham\PuTTY\Sessions"
_APELIDO_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
_INVALIDO = re.compile(r"[^A-Za-z0-9._-]+")
MAX_SESSOES = 50


def nome_da_sessao(chave: str) -> str:
    """O PuTTY grava o nome da sessão com %20 etc.; devolve o nome como o dono o vê."""
    return urllib.parse.unquote(chave)


def apelido_da_sessao(nome: str) -> str | None:
    """Apelido no formato do terminal SSH, ou None se não sobrar nada aproveitável."""
    apelido = _INVALIDO.sub("-", nome).strip("-.")[:40]
    return apelido if _APELIDO_OK.fullmatch(apelido) else None


def _valor(chave, nome, padrao=None):
    try:
        return winreg.QueryValueEx(chave, nome)[0]
    except OSError:
        return padrao


def ler_sessoes_do_registro() -> tuple[dict, list]:
    """({apelido: {"host","usuario","porta","origem":"putty","sessao"}}, [(nome, motivo_pulada)])."""
    if winreg is None:
        return {}, []
    sessoes, puladas = {}, []
    try:
        raiz = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RAIZ)
    except OSError:
        return {}, []
    with raiz:
        i = 0
        while i < MAX_SESSOES:
            try:
                chave_nome = winreg.EnumKey(raiz, i)
            except OSError:
                break
            i += 1
            nome = nome_da_sessao(chave_nome)
            if nome == "Default Settings":
                continue
            try:
                with winreg.OpenKey(raiz, chave_nome) as k:
                    dados = {
                        "protocolo": _valor(k, "Protocol", "ssh"),
                        "host": _valor(k, "HostName", ""),
                        "usuario": _valor(k, "UserName", ""),
                        "porta": _valor(k, "PortNumber", 22),
                        "proxy": _valor(k, "ProxyMethod", 0),
                        "redirecionamentos": _valor(k, "PortForwardings", ""),
                    }
            except OSError:
                continue
            entrada, motivo = interpretar(nome, dados)
            if entrada is None:
                puladas.append((nome, motivo))
            else:
                sessoes[entrada[0]] = entrada[1]
    return sessoes, puladas


def interpretar(nome: str, d: dict):
    """((apelido, entrada), None) ou (None, motivo). Pura: não toca o registro."""
    if str(d.get("protocolo", "ssh")).lower() != "ssh":
        return None, "não é SSH"
    host = d.get("host") or ""
    usuario = d.get("usuario") or ""
    if not isinstance(host, str) or not isinstance(usuario, str):
        return None, "endereço ou usuário ilegível"
    if "@" in host:                       # o PuTTY aceita "usuario@servidor" no campo de endereço
        usuario_do_host, _, host = host.rpartition("@")
        usuario = usuario or usuario_do_host
    if not host or not usuario:
        return None, "falta o endereço ou o usuário na sessão"
    porta = d.get("porta", 22)
    if not isinstance(porta, int) or isinstance(porta, bool) or not 1 <= porta <= 65535:
        return None, "porta inválida"
    if d.get("proxy") == 5:               # método 5 = "Local": o PuTTY rodaria um programa deste PC
        return None, "usa um comando local como proxy"
    if d.get("redirecionamentos"):
        return None, "tem redirecionamento de porta"
    apelido = apelido_da_sessao(nome)
    if apelido is None:
        return None, "nome da sessão não vira apelido"
    return (apelido, {"host": host, "usuario": usuario, "porta": porta,
                      "origem": "putty", "sessao": nome}), None


def localizar_plink() -> str | None:
    """SÓ o plink.exe da instalação do PuTTY em Program Files. Nada de PATH ou pasta atual:
    um `plink` plantado ali receberia o comando e a chave do dono."""
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if not base:
            continue
        candidato = os.path.join(base, "PuTTY", "plink.exe")
        if os.path.isfile(candidato):
            return candidato
    return None


def montar_argv_plink(plink_exe: str, sessao: str, comando: str) -> list:
    """`plink -load <sessão> -batch` — sem pergunta, sem agente repassado, sem X11. O comando
    remoto é o ÚLTIMO argumento, inteiro, sem shell local."""
    return [plink_exe, "-load", sessao, "-batch", "-T", "-a", "-x", comando]
