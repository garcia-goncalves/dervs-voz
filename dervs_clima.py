"""DERVS — previsão do tempo por voz (17/10/2026).

No teste por voz o dono pediu "a previsão do tempo aqui para Mooca" e o DERVS respondeu que não
tinha acesso à internet. Aqui a consulta vai ao Open-Meteo (gratuito, sem cadastro e sem chave):
primeiro acha o lugar pelo nome (bairro ou cidade, no Brasil), depois a previsão dele.
A resposta é UMA frase falada. Nunca levanta: sem rede, diz com franqueza.
"""
import http.client
import json
import urllib.parse
import urllib.request

URL_LUGAR = "https://geocoding-api.open-meteo.com/v1/search"
URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"
TEMPO_LIMITE_S = 8

# Códigos WMO do Open-Meteo, em português falado.
_DESCRICAO = (
    ((0,), "céu limpo"), ((1,), "céu quase limpo"), ((2,), "parcialmente nublado"),
    ((3,), "nublado"), ((45, 48), "neblina"), ((51, 53, 55, 56, 57), "garoa"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "chuva"), ((71, 73, 75, 77, 85, 86), "neve"),
    ((95, 96, 99), "trovoada"),
)


def descrever(codigo) -> str:
    for codigos, nome in _DESCRICAO:
        if codigo in codigos:
            return nome
    return ""


def _buscar_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "DERVS"})
    with urllib.request.urlopen(req, timeout=TEMPO_LIMITE_S) as r:
        return json.loads(r.read(1_000_000))         # teto: a resposta normal tem ~1 kB


def _graus(valor) -> int:
    return int(round(float(valor)))


def previsao(lugar: str, quando: str = "hoje", *, buscar=_buscar_json) -> str:
    """Frase com a previsão de `quando` ("hoje" ou "amanha") em `lugar`."""
    lugar = (lugar or "").strip()[:80]
    if not lugar:
        return "De qual cidade, senhor?"
    try:
        achados = buscar(URL_LUGAR + "?" + urllib.parse.urlencode(
            {"name": lugar, "count": 1, "language": "pt", "countryCode": "BR"})).get("results") or []
        if not achados:
            return "Não achei o lugar %s, senhor." % lugar
        p = achados[0]
        dados = buscar(URL_PREVISAO + "?" + urllib.parse.urlencode({
            "latitude": p["latitude"], "longitude": p["longitude"],
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max",
            "timezone": "auto", "forecast_days": 2}))
        dia = 1 if (quando or "").strip().lower() in ("amanha", "amanhã") else 0
        d = dados["daily"]
        ceu = descrever(d["weather_code"][dia])
        chuva = d["precipitation_probability_max"][dia]
        nome = str(p.get("name") or lugar)[:60]      # texto de terceiro vai à fala: curto
        if dia == 0:
            atual = dados["current"]
            frase = "Agora em %s faz %d graus%s. Hoje, máxima de %d e mínima de %d" % (
                nome, _graus(atual["temperature_2m"]),
                ", " + descrever(atual["weather_code"]) if descrever(atual["weather_code"]) else "",
                _graus(d["temperature_2m_max"][0]), _graus(d["temperature_2m_min"][0]))
        else:
            frase = "Amanhã em %s, %smáxima de %d e mínima de %d" % (
                nome, ceu + ", " if ceu else "",
                _graus(d["temperature_2m_max"][1]), _graus(d["temperature_2m_min"][1]))
        if chuva is not None:
            frase += ", com %d%% de chance de chuva" % int(chuva)
        return frase + "."
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError,
            http.client.HTTPException):
        return "Não consegui consultar a previsão agora, senhor."
