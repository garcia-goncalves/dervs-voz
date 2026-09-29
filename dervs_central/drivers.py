"""Dispositivos com defeito no Gerenciador de Dispositivos."""
from dervs_central.base import ErroConsulta, consultar, falha, resultado

_CONSULTA = ("Get-CimInstance Win32_PnPEntity | Where-Object {$_.ConfigManagerErrorCode -ne 0} | "
             "Select-Object Name,DeviceID,ConfigManagerErrorCode")


def coletar(rodar=None) -> dict:
    try:
        brutos = consultar(rodar, _CONSULTA)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    return resultado([{"nome": d.get("Name") or "dispositivo sem nome",
                       "id": (d.get("DeviceID") or "")[:120],
                       "codigo": d.get("ConfigManagerErrorCode")} for d in brutos])
