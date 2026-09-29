"""Tendência a partir do historico.jsonl: quando o disco enche, erros subindo
ou caindo, nota de hoje contra a de 7 dias atrás. Só aritmética simples."""
import datetime

JANELA_DIAS = 14


def _quando(linha: dict):
    try:
        return datetime.datetime.fromisoformat(linha["em"])
    except (KeyError, TypeError, ValueError):
        return None


def _recentes(historico: list, agora: datetime.datetime, dias: int) -> list:
    saida = []
    for l in historico or []:
        q = _quando(l)
        if q is not None and 0 <= (agora - q).total_seconds() <= dias * 86400:
            saida.append((q, l))
    return sorted(saida, key=lambda t: t[0])


def dias_para_encher(historico: list, volume: str, agora: datetime.datetime | None = None):
    """Dias até o volume encher no ritmo dos últimos 14 dias, ou None se não
    está enchendo (ou se faltam pelo menos dois dias de histórico)."""
    agora = agora or datetime.datetime.now()
    pontos = [(q, l["disco_livre_bytes"][volume]) for q, l in _recentes(historico, agora, JANELA_DIAS)
              if volume in (l.get("disco_livre_bytes") or {})]
    if len(pontos) < 2:
        return None
    (q0, v0), (q1, v1) = pontos[0], pontos[-1]
    dias = (q1 - q0).total_seconds() / 86400
    if dias < 1 or v1 >= v0:
        return None
    ritmo = (v0 - v1) / dias  # bytes por dia
    return round(v1 / ritmo, 1)


def variacao_erros(historico: list, agora: datetime.datetime | None = None):
    """'sobe', 'cai', 'estavel' ou None, comparando a 1ª e a última leitura da semana."""
    agora = agora or datetime.datetime.now()
    pontos = _recentes(historico, agora, 7)
    if len(pontos) < 2:
        return None
    a, b = pontos[0][1].get("erros", 0), pontos[-1][1].get("erros", 0)
    return "sobe" if b > a else "cai" if b < a else "estavel"


def nota_ha_7_dias(historico: list, agora: datetime.datetime | None = None):
    agora = agora or datetime.datetime.now()
    candidatas = [(abs((agora - q).total_seconds() - 7 * 86400), l["nota"])
                  for q, l in _recentes(historico, agora, 9) if "nota" in l and (agora - q).days >= 6]
    return min(candidatas)[1] if candidatas else None


def resumo(historico: list, volumes, nota_hoje: int, agora: datetime.datetime | None = None) -> dict:
    agora = agora or datetime.datetime.now()
    return {"enche_em_dias": {v: dias_para_encher(historico, v, agora) for v in volumes},
            "erros": variacao_erros(historico, agora),
            "nota_ha_7_dias": nota_ha_7_dias(historico, agora), "nota_hoje": nota_hoje}
