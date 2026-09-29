"""Defender, antivírus de terceiros e firewall. Só leitura."""
from dervs_central.base import ErroConsulta, consultar, falha, resultado, texto_curto

_STATUS = ("Get-MpComputerStatus | Select-Object AMServiceEnabled,AntivirusEnabled,"
           "RealTimeProtectionEnabled,@{n='AssinaturaEm';e={$_.AntivirusSignatureLastUpdated.ToString('s')}},"
           "@{n='ExameRapidoEm';e={if($_.QuickScanEndTime){$_.QuickScanEndTime.ToString('s')}}}")
_AMEACAS = "Get-MpThreatDetection | Select-Object -First 20 ThreatID,ProcessName,Resources"
_TERCEIROS = ("Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | "
              "Select-Object displayName")
_FIREWALL = ("Get-NetFirewallProfile | Select-Object Name,@{n='Ligado';e={[string]$_.Enabled}},"
             "@{n='EntradaPadrao';e={[string]$_.DefaultInboundAction}}")


def coletar_defender(rodar=None) -> dict:
    try:
        st = consultar(rodar, _STATUS)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    s = st[0] if st else {}
    itens = [{"servico": bool(s.get("AMServiceEnabled")), "antivirus": bool(s.get("AntivirusEnabled")),
              "tempo_real": bool(s.get("RealTimeProtectionEnabled")),
              "assinatura_em": str(s.get("AssinaturaEm") or "")[:10],
              "exame_rapido_em": str(s.get("ExameRapidoEm") or "")[:10]}] if s else []
    precisa_admin, ameacas, terceiros = False, [], []
    try:
        ameacas = [{"processo": texto_curto(a.get("ProcessName"), 80),
                    "alvo": texto_curto(a.get("Resources"), 160)} for a in consultar(rodar, _AMEACAS)]
    except ErroConsulta as erro:
        precisa_admin = erro.admin
    try:
        terceiros = [t.get("displayName") or "" for t in consultar(rodar, _TERCEIROS)
                     if "defender" not in str(t.get("displayName")).casefold()]
    except ErroConsulta:
        pass
    # Com antivírus de terceiro, o Defender desligado é normal: a nota não desconta.
    return resultado(itens, precisa_admin=precisa_admin, ameacas=ameacas, antivirus_de_terceiros=terceiros)


def coletar_firewall(rodar=None) -> dict:
    try:
        perfis = consultar(rodar, _FIREWALL)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    return resultado([{"perfil": p.get("Name") or "", "ligado": str(p.get("Ligado")).casefold() == "true",
                       "entrada_padrao": p.get("EntradaPadrao") or ""} for p in perfis])
