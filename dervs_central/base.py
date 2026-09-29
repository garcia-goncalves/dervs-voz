"""Base dos coletores: roda uma consulta do PowerShell (só leitura) e devolve
sempre o mesmo formato `{ok, itens, precisa_admin, erro}`.

`rodar(consulta) -> str` é injetável: os testes passam saída gravada, o uso
real passa `rodar_powershell`. Coletor nunca levanta exceção para quem chama —
falha vira `ok=False` com o motivo, e "precisa de administrador" vira aviso.
"""
import json
import os
import subprocess

import dervs_processos as processos

TIMEOUT_PADRAO = 30
_NEGADO = ("access is denied", "unauthorizedaccess", "acesso negado", "não é permitido",
           "requires elevation", "run as administrator", "administrador")
_SEM_RESULTADO = ("no events were found", "nenhum evento", "no matching events")


class ErroConsulta(Exception):
    def __init__(self, mensagem: str, admin: bool = False):
        super().__init__(mensagem)
        self.admin = admin


def _negado(texto: str) -> bool:
    baixo = (texto or "").casefold()
    return any(marca in baixo for marca in _NEGADO)


def ambiente_limpo() -> dict:
    """O ambiente do PowerShell 5.1 sem o `PSModulePath` herdado: quando o DERVS
    é aberto por um PowerShell 7 (ou por uma ferramenta que o usa), essa variável
    aponta os módulos do 7 primeiro e o 5.1 deixa de carregar os módulos de
    segurança e de rede — `Get-AuthenticodeSignature` devolvia vazio. Sem ela, o
    Windows recalcula o caminho certo."""
    return {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}


def rodar_powershell(consulta: str, timeout: float = TIMEOUT_PADRAO) -> str:
    """Executa a consulta sem janela e devolve o JSON compacto que ela imprime."""
    comando = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='Stop'; "
               f"{consulta} | ConvertTo-Json -Depth 4 -Compress")
    try:
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", comando],
            capture_output=True, timeout=timeout, env=ambiente_limpo(), **processos.sem_janela())
    except subprocess.TimeoutExpired as erro:
        raise ErroConsulta(f"demorou mais de {int(timeout)} s") from erro
    except OSError as erro:
        raise ErroConsulta(f"não consegui abrir o PowerShell ({erro.__class__.__name__})") from erro
    saida = p.stdout.decode("utf-8", "replace").strip()
    erro_txt = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0:
        if any(m in erro_txt.casefold() for m in _SEM_RESULTADO):
            return ""
        raise ErroConsulta(erro_txt[:200] or f"saída {p.returncode}", admin=_negado(erro_txt))
    return saida


def resultado(itens=None, *, ok: bool = True, precisa_admin: bool = False, erro: str = "",
              **extras) -> dict:
    r = {"ok": ok, "itens": list(itens or []), "precisa_admin": precisa_admin, "erro": erro}
    r.update(extras)
    return r


def falha(erro, admin: bool = False) -> dict:
    return resultado(ok=False, precisa_admin=admin, erro=str(erro)[:200])


def como_lista(texto: str) -> list:
    """`ConvertTo-Json` devolve objeto solto quando há um item só e nada quando
    não há nenhum; aqui vira sempre lista de dicionários."""
    texto = (texto or "").strip()
    if not texto:
        return []
    dados = json.loads(texto)
    if isinstance(dados, dict):
        return [dados]
    return [d for d in dados if isinstance(d, dict)] if isinstance(dados, list) else []


def consultar(rodar, consulta: str, timeout: float = TIMEOUT_PADRAO) -> list:
    """Roda e converte. Levanta `ErroConsulta` — os coletores traduzem em resultado."""
    rodar = rodar or rodar_powershell
    try:
        try:
            saida = rodar(consulta, timeout)
        except TypeError:
            saida = rodar(consulta)
        return como_lista(saida)
    except ErroConsulta:
        raise
    except json.JSONDecodeError as erro:
        raise ErroConsulta("resposta do PowerShell ilegível") from erro


def aspas(texto: str) -> str:
    """Texto seguro dentro de aspas simples do PowerShell."""
    return "'" + str(texto).replace("'", "''") + "'"


def texto_curto(valor, limite: int = 200) -> str:
    return " ".join(str(valor or "").split())[:limite]
