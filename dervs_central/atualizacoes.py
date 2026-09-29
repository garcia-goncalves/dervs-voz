"""Windows Update: pendentes, último instalado e reinício pendente."""
import datetime

from dervs_central.base import ErroConsulta, consultar, falha, resultado

TIMEOUT_BUSCA = 150  # a busca do Windows Update leva de 30 a 120 s
_BUSCA = ("$u=(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()"
          ".Search('IsInstalled=0 and IsHidden=0').Updates; $u | Select-Object Title,"
          "@{n='Sev';e={[string]$_.MsrcSeverity}},IsDownloaded,"
          "@{n='Desde';e={$_.LastDeploymentChangeTime.ToString('s')}}")
_ULTIMO = ("Get-CimInstance Win32_QuickFixEngineering | Sort-Object InstalledOn -Descending | "
           "Select-Object -First 1 HotFixID,@{n='Em';e={if($_.InstalledOn){$_.InstalledOn.ToString('s')}}}")
_REINICIO = ("[pscustomobject]@{Pendente=(Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\"
             "CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired')}")
SEGURANCA = ("critical", "important")


def _dias(desde, agora: datetime.datetime):
    try:
        return max(0, (agora - datetime.datetime.fromisoformat(desde)).days)
    except (TypeError, ValueError):
        return None


def coletar(rodar=None, agora=None) -> dict:
    agora = agora or datetime.datetime.now()
    try:
        brutos = consultar(rodar, _BUSCA, TIMEOUT_BUSCA)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    itens = []
    for u in brutos:
        sev = str(u.get("Sev") or "")
        itens.append({"titulo": u.get("Title") or "atualização", "severidade": sev,
                      "seguranca": sev.casefold() in SEGURANCA,
                      "baixada": bool(u.get("IsDownloaded")),
                      "dias_pendente": _dias(u.get("Desde"), agora)})
    extras = {"ultimo_instalado": "", "reinicio_pendente": False}
    try:
        for r in consultar(rodar, _ULTIMO):
            extras["ultimo_instalado"] = f"{r.get('HotFixID', '')} em {str(r.get('Em') or '')[:10]}".strip()
    except ErroConsulta:
        pass
    try:
        for r in consultar(rodar, _REINICIO):
            extras["reinicio_pendente"] = bool(r.get("Pendente"))
    except ErroConsulta:
        pass
    return resultado(itens, **extras)
