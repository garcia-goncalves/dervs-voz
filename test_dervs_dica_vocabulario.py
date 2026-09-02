#!/usr/bin/env python3
"""A dica de vocabulário precisa chegar até a nuvem — ela não chegava.

Por que existe: em 02/09/2026 o dono disse "não está me entendendo direito,
minha transcrição não está boa". Medido no código: `dervs_transcrever.py`
LIA `conf.get("stt_dica_vocabulario")` para mandar como `prompt` à OpenAI,
mas essa chave não existia em lugar nenhum — nem no `PADRAO` de
`dervs_config.py`, nem no `config.json` da máquina do dono. `carregar()` só
copia do disco as chaves que existem no `PADRAO`, então a dica era sempre `""`
e o campo `prompt` NUNCA era enviado.

Resultado prático: o áudio ia para a nuvem sem nenhuma pista de que a pessoa
fala português do Brasil com um assistente chamado DERVS. O modelo transcrevia
"DERVS" como "Dervis", "Ders", "the RVS" — justamente as palavras que mais
importam. Havia uma cola boa escrita em `dervs_stt_daemon.py`, mas ela só valia
para o caminho local, que não é o que a máquina do dono usa.

Estes testes travam as duas pontas: a chave existe com conteúdo útil, e ela
chega de verdade ao corpo da requisição.
"""
import io
import json
import os

import pytest

import dervs_config
import dervs_transcrever


# ---------------------------------------------------------------- a chave existe

def test_o_padrao_tem_a_dica_de_vocabulario():
    """Sem isto, `carregar()` nunca devolve a chave e a dica some."""
    assert "stt_dica_vocabulario" in dervs_config.PADRAO


def test_a_dica_padrao_ensina_o_essencial_ao_modelo():
    """Precisa dizer o idioma e o nome do assistente: é o que mais erra."""
    dica = dervs_config.PADRAO["stt_dica_vocabulario"]
    assert isinstance(dica, str) and dica.strip()
    baixo = dica.lower()
    assert "português" in baixo or "portugues" in baixo
    assert "dervs" in baixo


def test_config_antiga_sem_a_chave_ganha_a_dica_padrao(tmp_path, monkeypatch):
    """A máquina do dono tem um config.json SEM esta chave, escrito antes dela.

    É o caso real: se `carregar()` não completasse com o padrão, a correção não
    chegaria à máquina dele sem alguém reescrever a configuração na mão.
    """
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"stt": "openai", "cerebro": "openai"}),
                       encoding="utf-8")
    monkeypatch.setattr(dervs_config, "CONFIG_PATH", str(caminho))

    conf = dervs_config.carregar()

    assert conf["stt_dica_vocabulario"] == dervs_config.PADRAO["stt_dica_vocabulario"]


def test_dica_vazia_ou_torta_no_disco_cai_no_padrao(tmp_path, monkeypatch):
    """Dica apagada por engano não pode deixar a transcrição pior que o padrão."""
    for lixo in ("", "   ", 123, None, []):
        caminho = tmp_path / "config.json"
        caminho.write_text(json.dumps({"stt_dica_vocabulario": lixo}),
                           encoding="utf-8")
        monkeypatch.setattr(dervs_config, "CONFIG_PATH", str(caminho))

        conf = dervs_config.carregar()

        assert conf["stt_dica_vocabulario"] == dervs_config.PADRAO["stt_dica_vocabulario"], (
            "dica %r no disco deveria cair no padrão" % (lixo,))


def test_a_dica_do_dono_e_respeitada(tmp_path, monkeypatch):
    """Quando ele acrescenta os nomes dos clientes dele, valem os dele."""
    minha = "Fala com o DERVS em português. Nomes: Zacareli, Camargo e Soares."
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"stt_dica_vocabulario": minha}),
                       encoding="utf-8")
    monkeypatch.setattr(dervs_config, "CONFIG_PATH", str(caminho))

    assert dervs_config.carregar()["stt_dica_vocabulario"] == minha


# ------------------------------------------------- a dica chega até a requisição

class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capturar_envio(monkeypatch, caminho_wav, dica):
    """Roda `_enviar` sem tocar na rede e devolve o corpo que teria ido."""
    capturado = {}

    def urlopen_falso(req, timeout=None):
        capturado["corpo"] = req.data
        capturado["url"] = req.full_url
        return RespostaFalsa(b"texto transcrito")

    monkeypatch.setattr(dervs_transcrever.urllib.request, "urlopen", urlopen_falso)
    dervs_transcrever._enviar(str(caminho_wav), "chave-de-teste",
                              "gpt-transcribe", dica)
    return capturado


def test_a_dica_vai_no_campo_prompt_da_requisicao(tmp_path, monkeypatch):
    """O defeito em uma linha: sem isto o `prompt` não era enviado."""
    wav = tmp_path / "fala.wav"
    wav.write_bytes(b"RIFF0000WAVEfmt ")
    dica = "Português do Brasil. O assistente se chama DERVS."

    envio = _capturar_envio(monkeypatch, wav, dica)

    assert b'name="prompt"' in envio["corpo"]
    assert dica.encode("utf-8") in envio["corpo"]
    assert b'name="model"' in envio["corpo"]
    assert b"gpt-transcribe" in envio["corpo"]


def test_sem_dica_a_requisicao_continua_valida(tmp_path, monkeypatch):
    """Dica vazia não pode virar um campo `prompt` vazio: piora o resultado."""
    wav = tmp_path / "fala.wav"
    wav.write_bytes(b"RIFF0000WAVEfmt ")

    envio = _capturar_envio(monkeypatch, wav, "")

    assert b'name="prompt"' not in envio["corpo"]
    assert b'name="model"' in envio["corpo"]


def test_o_caminho_local_usa_a_mesma_dica_da_nuvem():
    """Duas colas divergentes viram dois DERVS diferentes ouvindo.

    O daemon local tinha a sua própria, boa, e a nuvem não tinha nenhuma. Uma
    fonte só: quando o dono acrescentar os nomes dele, valem nos dois caminhos.
    """
    import dervs_stt_daemon

    assert dervs_stt_daemon.COLA == dervs_config.PADRAO["stt_dica_vocabulario"]


if __name__ == "__main__":            # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
