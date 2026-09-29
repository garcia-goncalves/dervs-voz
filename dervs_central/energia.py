"""Bateria (se houver), plano de energia e há quanto tempo o PC está ligado."""
import datetime

from dervs_central.base import ErroConsulta, consultar, falha, resultado

_BATERIA = "Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining,BatteryStatus"
_PLANO = "[pscustomobject]@{Plano=(powercfg /getactivescheme)}"
_BOOT = "[pscustomobject]@{Desde=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('s')}"


def coletar(rodar=None, agora=None) -> dict:
    agora = agora or datetime.datetime.now()
    try:
        boot = consultar(rodar, _BOOT)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    horas = None
    if boot:
        try:
            desde = datetime.datetime.fromisoformat(boot[0]["Desde"])
            horas = round((agora - desde).total_seconds() / 3600, 1)
        except (KeyError, ValueError):
            pass
    try:
        bateria = consultar(rodar, _BATERIA)
    except ErroConsulta:
        bateria = []
    plano = ""
    try:
        for p in consultar(rodar, _PLANO):
            plano = str(p.get("Plano") or "")[:120]
    except ErroConsulta:
        pass
    itens = [{"carga_pct": b.get("EstimatedChargeRemaining"), "status": b.get("BatteryStatus")}
             for b in bateria]
    return resultado(itens, tem_bateria=bool(bateria), horas_ligado=horas, plano=plano)
