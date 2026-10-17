"""Previsão do tempo por voz (17/10/2026): "qual a previsão do tempo aqui para Mooca" era
respondido com "não tenho acesso à internet"."""
import json

import pytest

import dervs_clima as clima

LUGAR = {"results": [{"name": "Mooca", "latitude": -23.56, "longitude": -46.59,
                      "admin1": "São Paulo", "admin2": "São Paulo", "country_code": "BR"}]}
PREVISAO = {"current": {"temperature_2m": 19.2, "weather_code": 1},
            "daily": {"time": ["2026-10-17", "2026-10-18"], "weather_code": [80, 61],
                      "temperature_2m_max": [22.0, 24.4], "temperature_2m_min": [15.7, 14.6],
                      "precipitation_probability_max": [70, 40]}}


def _buscar(respostas, pedidos=None):
    def buscar(url):
        if pedidos is not None:
            pedidos.append(url)
        return respostas["geo" if "geocoding" in url else "previsao"]
    return buscar


def test_previsao_de_hoje_no_bairro():
    frase = clima.previsao("Mooca", buscar=_buscar({"geo": LUGAR, "previsao": PREVISAO}))
    assert "Mooca" in frase and "19 graus" in frase
    assert "máxima de 22" in frase and "mínima de 16" in frase and "70%" in frase


def test_previsao_de_amanha():
    frase = clima.previsao("Mooca", "amanha", buscar=_buscar({"geo": LUGAR, "previsao": PREVISAO}))
    assert "Amanhã" in frase and "máxima de 24" in frase and "chuva" in frase.lower()
    assert "agora" not in frase


def test_nome_do_lugar_vai_codificado_na_url():
    pedidos = []
    clima.previsao("São Paulo & cia", buscar=_buscar({"geo": LUGAR, "previsao": PREVISAO}, pedidos))
    assert "S%C3%A3o+Paulo+%26+cia" in pedidos[0] or "S%C3%A3o%20Paulo%20%26%20cia" in pedidos[0]
    assert pedidos[0].startswith("https://geocoding-api.open-meteo.com/")
    assert pedidos[1].startswith("https://api.open-meteo.com/")


def test_lugar_nao_achado():
    frase = clima.previsao("Xyzwq", buscar=_buscar({"geo": {}, "previsao": PREVISAO}))
    assert "Não achei" in frase and "Xyzwq" in frase


def test_sem_internet_diz_com_franqueza():
    def buscar(url):
        raise OSError("sem rede")
    assert "não consegui consultar" in clima.previsao("Mooca", buscar=buscar).lower()


def test_resposta_torta_nao_quebra():
    frase = clima.previsao("Mooca", buscar=_buscar({"geo": LUGAR, "previsao": {"daily": "x"}}))
    assert "não consegui" in frase.lower()


def test_lugar_vazio_pede_a_cidade():
    assert "cidade" in clima.previsao("", buscar=_buscar({"geo": LUGAR, "previsao": PREVISAO}))


@pytest.mark.parametrize("codigo,palavra", [(0, "céu limpo"), (3, "nublado"), (61, "chuva"),
                                            (95, "trovoada"), (999, "")])
def test_descricao_do_tempo(codigo, palavra):
    assert clima.descrever(codigo) == palavra


def test_buscar_de_verdade_le_json(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": 1}).encode()
    vistos = []
    monkeypatch.setattr(clima.urllib.request, "urlopen",
                        lambda req, timeout: vistos.append(timeout) or Resp())
    assert clima._buscar_json("https://api.open-meteo.com/x") == {"ok": 1}
    assert vistos and vistos[0] <= 10
