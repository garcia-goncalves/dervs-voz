"""Os 10 processos que mais pesam agora, com a assinatura digital de cada um."""
import time

from dervs_central.base import ErroConsulta, aspas, consultar, falha, resultado

try:
    import psutil
except ImportError:
    psutil = None


def _assinaturas(rodar, caminhos):
    if not caminhos:
        return {}
    lista = ",".join(aspas(c) for c in caminhos)
    consulta = (f"{lista} | ForEach-Object {{ $s=Get-AuthenticodeSignature -LiteralPath $_; "
                "[pscustomobject]@{Caminho=$_;Status=[string]$s.Status;"
                "Assinante=[string]$s.SignerCertificate.Subject} }")
    return {a.get("Caminho"): a for a in consultar(rodar, consulta)}


def coletar(rodar=None, modulo_psutil=None, dormir=time.sleep, topo: int = 10) -> dict:
    mod = modulo_psutil or psutil
    if mod is None:
        return falha("psutil não está instalado")
    erros = (mod.Error, OSError)
    try:
        procs = list(mod.process_iter(["pid", "name"]))
        for p in procs:
            try:
                p.cpu_percent(None)
            except erros:
                pass
        dormir(1.0)
        amostras = []
        for p in procs:
            try:
                cpu = p.cpu_percent(None)
                rss = p.memory_info().rss
                try:
                    exe = p.exe() or ""
                except erros:
                    exe = ""
                amostras.append({"pid": p.pid, "nome": p.info.get("name") or "", "cpu_pct": round(cpu, 1),
                                 "memoria_bytes": int(rss), "caminho": exe})
            except erros:
                continue
    except erros as erro:
        return falha(erro)
    amostras.sort(key=lambda a: (-a["cpu_pct"], -a["memoria_bytes"]))
    itens = amostras[:topo]
    try:
        assin = _assinaturas(rodar, sorted({i["caminho"] for i in itens if i["caminho"]}))
    except ErroConsulta:
        assin = {}
    for i in itens:
        a = assin.get(i["caminho"], {})
        i["assinatura"] = a.get("Status") or "Desconhecida"
        i["assinante"] = (a.get("Assinante") or "")[:120]
    return resultado(itens)
