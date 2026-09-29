"""Espaço em disco e saúde física (SMART) dos discos. Só leitura."""
from dervs_central.base import ErroConsulta, consultar, falha, resultado

try:
    import psutil
except ImportError:
    psutil = None

_VOLUMES = ("Get-Volume | Where-Object DriveLetter | Select-Object "
            "@{n='Letra';e={[string]$_.DriveLetter}},FileSystemLabel,"
            "@{n='Saude';e={[string]$_.HealthStatus}}")
_FISICOS = ("Get-PhysicalDisk | Select-Object FriendlyName,"
            "@{n='Tipo';e={[string]$_.MediaType}},@{n='Saude';e={[string]$_.HealthStatus}},"
            "@{n='Status';e={[string]$_.OperationalStatus}},Size")
_CONTADORES = ("Get-PhysicalDisk | Get-StorageReliabilityCounter | Select-Object "
               "DeviceId,Temperature,Wear,ReadErrorsTotal,PowerOnHours")


def coletar_espaco(rodar=None, modulo_psutil=None) -> dict:
    mod = modulo_psutil or psutil
    if mod is None:
        return falha("psutil não está instalado")
    saude, aviso = {}, ""
    try:
        for v in consultar(rodar, _VOLUMES):
            saude[str(v.get("Letra", "")).upper()] = (v.get("FileSystemLabel") or "", v.get("Saude") or "")
    except ErroConsulta as erro:
        aviso = str(erro)
    itens = []
    try:
        particoes = mod.disk_partitions(all=False)
    except OSError as erro:
        return falha(erro)
    for p in particoes:
        if "cdrom" in (getattr(p, "opts", "") or "").casefold():
            continue
        try:
            uso = mod.disk_usage(p.mountpoint)
        except OSError:
            continue  # unidade sem mídia ou sem permissão: não é problema do usuário
        letra = (p.mountpoint or "")[:1].upper()
        rotulo, estado = saude.get(letra, ("", ""))
        itens.append({
            "volume": (p.mountpoint or "").rstrip("\\") or p.mountpoint, "rotulo": rotulo,
            "total_bytes": int(uso.total), "livre_bytes": int(uso.free),
            "pct_livre": round(uso.free / uso.total * 100, 1) if uso.total else 0.0,
            "saude": estado or "Desconhecida"})
    return resultado(itens, erro=aviso)


def coletar_saude(rodar=None) -> dict:
    try:
        fisicos = consultar(rodar, _FISICOS)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    itens = [{"nome": d.get("FriendlyName") or "disco", "tipo": d.get("Tipo") or "",
              "saude": d.get("Saude") or "Desconhecida", "status": d.get("Status") or "",
              "tamanho_bytes": int(d.get("Size") or 0)} for d in fisicos]
    precisa_admin, detalhes = False, []
    try:
        for c in consultar(rodar, _CONTADORES):
            detalhes.append({"temperatura_c": c.get("Temperature"), "desgaste_pct": c.get("Wear"),
                             "erros_leitura": c.get("ReadErrorsTotal"),
                             "horas_ligado": c.get("PowerOnHours")})
    except ErroConsulta:
        precisa_admin = True  # o detalhe SMART pede administrador
    return resultado(itens, precisa_admin=precisa_admin, detalhes=detalhes)
