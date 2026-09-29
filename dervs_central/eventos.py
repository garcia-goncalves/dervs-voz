"""Erros do Visualizador de Eventos dos últimos 7 dias, agrupados por (fonte, id)."""
from dervs_central.base import ErroConsulta, consultar, falha, resultado, texto_curto

_CONSULTA = ("Get-WinEvent -FilterHashtable @{LogName='System','Application';Level=1,2;"
             "StartTime=(Get-Date).AddDays(-7)} -MaxEvents 300 | Select-Object "
             "@{n='Quando';e={$_.TimeCreated.ToString('s')}},Id,ProviderName,LevelDisplayName,"
             "@{n='Msg';e={if($_.Message){$_.Message.Substring(0,[Math]::Min(200,$_.Message.Length))}else{''}}}")

# (trecho da fonte, id ou None para qualquer) — têm texto próprio em explicacoes.py
CONHECIDOS = (("kernel-power", 41), ("eventlog", 6008), ("bugcheck", 1001), ("whea-logger", None),
              ("service control manager", 7031), ("service control manager", 7034),
              ("application error", 1000))


def _conhecido(fonte: str, ident) -> bool:
    fonte = fonte.casefold()
    return any(f in fonte and (i is None or i == ident) for f, i in CONHECIDOS)


def coletar(rodar=None) -> dict:
    try:
        brutos = consultar(rodar, _CONSULTA)
    except ErroConsulta as erro:
        return falha(erro, erro.admin)
    grupos = {}
    for e in brutos:
        chave = (str(e.get("ProviderName") or "?"), e.get("Id"))
        g = grupos.setdefault(chave, {"fonte": chave[0], "id": chave[1],
                                      "nivel": e.get("LevelDisplayName") or "", "quantidade": 0,
                                      "ultima": ""})
        g["quantidade"] += 1
        g["ultima"] = max(g["ultima"], str(e.get("Quando") or ""))
    itens = sorted(grupos.values(), key=lambda g: (-g["quantidade"], g["fonte"]))
    for g in itens:
        g["conhecido"] = _conhecido(g["fonte"], g["id"])
    return resultado(itens, total=len(brutos))
