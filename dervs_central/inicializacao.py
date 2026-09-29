"""O que abre sozinho quando o Windows liga (programas e tarefas de logon)."""
from dervs_central.base import ErroConsulta, consultar, falha, resultado

_COMANDOS = "Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location,User"
_APROVADO = ("foreach($h in 'HKCU','HKLM'){$k=$h+':\\Software\\Microsoft\\Windows\\CurrentVersion\\"
             "Explorer\\StartupApproved\\Run'; if(Test-Path $k){$p=Get-ItemProperty $k; "
             "foreach($n in (Get-Item $k).GetValueNames()){[pscustomobject]@{Nome=$n;"
             "Estado=[int]($p.$n)[0]}}}}")
_TAREFAS = ("Get-ScheduledTask | Where-Object {$_.Triggers.CimClass.CimClassName -contains "
            "'MSFT_TaskLogonTrigger'} | Select-Object TaskName,TaskPath,@{n='Estado';e={[string]$_.State}}")


def coletar(rodar=None) -> dict:
    try:
        comandos = consultar(rodar, _COMANDOS)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    estados = {}
    try:
        for a in consultar(rodar, _APROVADO):
            estados[str(a.get("Nome"))] = a.get("Estado")
    except ErroConsulta:
        pass
    itens = []
    for c in comandos:
        nome = c.get("Name") or ""
        estado = estados.get(nome)
        itens.append({"nome": nome, "local": c.get("Location") or "", "usuario": c.get("User") or "",
                      "ativo": estado is None or estado % 2 == 0})
    tarefas = []
    try:
        tarefas = [{"nome": t.get("TaskName") or "", "pasta": t.get("TaskPath") or "",
                    "estado": t.get("Estado") or ""} for t in consultar(rodar, _TAREFAS)]
    except ErroConsulta:
        pass
    return resultado(itens, tarefas_no_logon=tarefas)
