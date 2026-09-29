#!/usr/bin/env python3
"""Testes do registro de ações (onda C, critério 7 do briefing).

O registro é o que o dono abre no painel para ver o que o DERVS analisou,
propôs, aprovou, recusou, executou e desfez. Duas promessas:
  1. adulteração fica visível — cada linha guarda o hash da anterior;
  2. segredo nunca entra — chave, token, senha em endereço, valor de .env.

Rodar: python -m pytest test_dervs_log_acoes.py -q
"""
import json

import pytest

import dervs_log_acoes as la


@pytest.fixture
def log(tmp_path):
    return la.LogAcoes(str(tmp_path / "acoes.jsonl"))


def _linhas(log):
    with open(log.arquivo, encoding="utf-8") as f:
        return f.read().splitlines()


def _regravar(log, linhas):
    with open(log.arquivo, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(linhas) + "\n")


def _preencher(log):
    log.registrar("analisou", {"itens": 2})
    log.registrar("propos", {"alvo": r"C:\Users\x\a.tmp"})
    log.registrar("aprovou", {"ids": ["item-1"]})
    log.registrar("executou", {"desfazer_id": "20260929-abc"})


def test_cadeia_integra_e_verificada(log):
    _preencher(log)
    assert log.verificar_cadeia() == (True, "")
    linhas = [json.loads(l) for l in _linhas(log)]
    assert [l["seq"] for l in linhas] == [1, 2, 3, 4]
    assert linhas[1]["anterior"] == linhas[0]["hash"]


def test_log_vazio_ou_ausente_e_integro(log):
    assert log.verificar_cadeia() == (True, "")


def test_so_acrescenta_mesmo_com_outra_instancia(log):
    _preencher(log)
    outro = la.LogAcoes(log.arquivo)
    outro.registrar("desfez", {"desfazer_id": "x"})
    assert len(_linhas(log)) == 5
    assert outro.verificar_cadeia()[0] is True


def test_adulteracao_de_valor_e_detectada(log):
    _preencher(log)
    linhas = _linhas(log)
    linhas[1] = linhas[1].replace("a.tmp", "b.tmp")
    _regravar(log, linhas)
    ok, motivo = log.verificar_cadeia()
    assert ok is False and "2" in motivo


def test_linha_apagada_no_meio_e_detectada(log):
    _preencher(log)
    linhas = _linhas(log)
    del linhas[1]
    _regravar(log, linhas)
    assert log.verificar_cadeia()[0] is False


def test_linhas_trocadas_de_ordem_sao_detectadas(log):
    _preencher(log)
    linhas = _linhas(log)
    linhas[1], linhas[2] = linhas[2], linhas[1]
    _regravar(log, linhas)
    assert log.verificar_cadeia()[0] is False


def test_linha_recalculada_sem_refazer_o_resto_e_detectada(log):
    """Quem adultera e recalcula o hash daquela linha quebra o elo seguinte."""
    _preencher(log)
    linhas = [json.loads(l) for l in _linhas(log)]
    linhas[1]["dados"]["alvo"] = "outro"
    linhas[1]["hash"] = la.hash_da_linha(linhas[1])
    _regravar(log, [json.dumps(l, ensure_ascii=False) for l in linhas])
    assert log.verificar_cadeia()[0] is False


def test_lixo_no_arquivo_e_detectado(log):
    _preencher(log)
    with open(log.arquivo, "a", encoding="utf-8") as f:
        f.write("isto não é json\n")
    assert log.verificar_cadeia()[0] is False


def test_evento_desconhecido_e_recusado(log):
    with pytest.raises(ValueError):
        log.registrar("apagou_tudo", {})


SEGREDOS = [
    "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "sk-ant-api03-ZZZZZZZZZZZZZZZZZZZZZZZZZZ",
    "ghp_1234567890abcdefghijABCDEFGHIJ123456",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    "AKIAIOSFODNN7EXAMPLE",
    "xoxb-123456789012-abcdefghijkl",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "senhaSuperSecreta99",
]


def test_segredos_nunca_entram(log, monkeypatch):
    monkeypatch.setenv("DERVS_TESTE_API_KEY", "valor-de-ambiente-que-e-segredo-123")
    log.registrar("executou", {
        "comando": "curl -H 'Authorization: Bearer abcdef0123456789abcdef' https://x",
        "url": "https://dono:senhaSuperSecreta99@servidor.exemplo/x",
        "texto": " ".join(SEGREDOS[:-1]),
        "env": "OPENAI_API_KEY=sk-qualquer-coisa-bem-longa-aqui\nPORTA=8080",
        "ps": "$env:TOKEN='abc123def456ghi789'",
        "password": "hunter2hunter2",
        "config": {"api_key": "chave-em-dicionario-123", "cor": "azul"},
        "ambiente": "usei valor-de-ambiente-que-e-segredo-123 no teste",
        "consulta": "https://site/login?user=a&senha=abc12345&x=1",
    })
    texto = open(log.arquivo, encoding="utf-8").read()
    for segredo in SEGREDOS + ["abcdef0123456789abcdef", "sk-qualquer", "abc123def456ghi789",
                               "hunter2hunter2", "chave-em-dicionario-123",
                               "valor-de-ambiente-que-e-segredo-123", "abc12345"]:
        assert segredo not in texto, segredo
    assert "azul" in texto and "8080" in texto   # o que não é segredo continua legível
    assert log.verificar_cadeia()[0] is True


def test_impressao_digital_nao_e_confundida_com_segredo(log):
    impressao = "a" * 64
    log.registrar("propos", {"impressao": impressao})
    assert impressao in open(log.arquivo, encoding="utf-8").read()


def test_mais_segredos_pela_cara(log):
    # Montados por partes de propósito: são FALSOS, e o detector de segredo
    # do commit não deve confundi-los com chave de verdade.
    tipo = "RSA PRIVATE" + " KEY"
    pem = (f"-----BEGIN {tipo}-----\nMIIEowIBAAKCAQEAsegredoPEM1234567890\n"
           f"-----END {tipo}-----")
    log.registrar("executou", {"a": "sk_" + "live_51HxyzABCDEFGHIJKLMNOPQRS",
                               "b": "AI" + "zaSyA1234567890abcdefghijklmnopqrstuv",
                               "c": pem})
    texto = open(log.arquivo, encoding="utf-8").read()
    for segredo in ("51HxyzABCDEF", "SyA1234567890abc", "segredoPEM1234567890"):
        assert segredo not in texto, segredo


def test_nome_inocente_antes_nao_esconde_o_segredo_depois(log):
    log.registrar("executou", {"u": "https://site/x?token=abcdef123456&y=2",
                               "v": "modo: rapido senha: hunter2hunter2"})
    texto = open(log.arquivo, encoding="utf-8").read()
    assert "abcdef123456" not in texto and "hunter2hunter2" not in texto
    assert "rapido" in texto


def test_redator_nao_e_lento_com_texto_hostil(log):
    """Revisão de 29/09: o padrão antigo levava 21 s para 3000 caracteres."""
    import time
    hostil = {"a": "key-" * 750, "b": "token." * 500, "c": ("x=" * 1500), "d": "k" * 20000 + "="}
    inicio = time.monotonic()
    log.registrar("analisou", hostil)
    assert time.monotonic() - inicio < 1.0


def test_cauda_ilegivel_nao_impede_registrar(log):
    _preencher(log)
    with open(log.arquivo, "a", encoding="utf-8") as f:
        f.write('{"seq": 5, "cort')
    log.registrar("desfez", {"desfazer_id": "x"})
    linhas = _linhas(log)
    assert json.loads(linhas[-2])["evento"] == "alerta"
    assert json.loads(linhas[-1])["evento"] == "desfez"
    assert json.loads(linhas[-1])["seq"] == json.loads(linhas[-2])["seq"] + 1
    assert log.verificar_cadeia()[0] is False  # o trecho estragado continua visível


def test_escrita_por_fora_entre_duas_minhas_gera_alerta(log):
    """Quem recalcula os hashes passa pela corrente, mas não pela memória do
    processo: a próxima escrita avisa."""
    _preencher(log)
    ultima = json.loads(_linhas(log)[-1])
    forjada = {"seq": ultima["seq"] + 1, "quando": ultima["quando"], "evento": "aprovou",
               "dados": {"ids": ["item-9"]}, "anterior": ultima["hash"]}
    forjada["hash"] = la.hash_da_linha(forjada)
    with open(log.arquivo, "a", encoding="utf-8") as f:
        f.write(json.dumps(forjada, ensure_ascii=False, sort_keys=True) + "\n")
    log.registrar("executou", {"x": 1})
    eventos = [json.loads(l)["evento"] for l in _linhas(log)]
    assert eventos[-2:] == ["alerta", "executou"]


def test_linha_tem_limite_de_tamanho(log):
    log.registrar("analisou", {"texto": "x" * 200_000, "lista": ["y" * 1000] * 500})
    linha = _linhas(log)[0]
    assert len(linha.encode("utf-8")) <= la.LIMITE_LINHA
    assert log.verificar_cadeia()[0] is True
