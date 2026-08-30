#!/usr/bin/env python3
"""Testes da lógica pura do enriquecimento de lead.

O recon de verdade (enriquecer) precisa de rede e leva minutos — esse a gente
prova na máquina, à mão. Aqui cobrimos o que é função pura: validar domínio,
agregar eventos NDJSON do bbot, resumir, e a diferença passivo/ativo no comando
(que é a trava de LEI — passivo nunca pode virar ativo por acidente)."""
import json
import grimoire_enrich as en


# --- dominio_valido: barra lixo de transcrição ------------------------------
def test_dominio_valido_aceita_bons():
    assert en.dominio_valido("empresa.com.br")
    assert en.dominio_valido("sub.dominio.io")


def test_dominio_valido_recusa_lixo():
    assert not en.dominio_valido("que horas são")
    assert not en.dominio_valido("localhost")
    assert not en.dominio_valido("")
    assert not en.dominio_valido("http://x.com/path")


# --- agregar_eventos: NDJSON do bbot vira lead estruturado ------------------
def _nd(*eventos):
    return [json.dumps(e) for e in eventos]


def test_agregar_classifica_por_tipo():
    linhas = _nd(
        {"type": "DNS_NAME", "data": "mail.empresa.com"},
        {"type": "DNS_NAME", "data": "MAIL.EMPRESA.COM"},   # dup case-insensitive
        {"type": "EMAIL_ADDRESS", "data": "contato@empresa.com"},
        {"type": "TECHNOLOGY", "data": {"technology": "nginx", "host": "x"}},
        {"type": "STORAGE_BUCKET", "data": {"name": "empresa-backups"}},
        {"type": "FINDING", "data": {"description": "painel admin exposto"}},
        {"type": "VULNERABILITY", "data": {"severity": "HIGH", "description": "RCE"}},
        {"type": "SCAN", "data": "ruído que deve ser ignorado"},
    )
    lead = en.agregar_eventos(linhas)
    assert lead["subdominios"] == ["mail.empresa.com"]         # dedup
    assert lead["emails"] == ["contato@empresa.com"]
    assert lead["tecnologias"] == ["nginx"]
    assert lead["buckets"] == ["empresa-backups"]
    assert lead["achados"] == ["painel admin exposto"]
    assert lead["vulnerabilidades"][0][0] == "HIGH"


def test_agregar_ignora_linha_torta():
    lead = en.agregar_eventos(["não é json", "", "{quebrado", '{"type":"DNS_NAME","data":"a.b.com"}'])
    assert lead["subdominios"] == ["a.b.com"]


def test_texto_do_dado_string_e_objeto():
    assert en._texto_do_dado("x.com") == "x.com"
    assert en._texto_do_dado({"host": "y.com"}) == "y.com"
    assert en._texto_do_dado({"description": "algo"}) == "algo"
    assert en._texto_do_dado(None) == ""


def test_agregar_descarta_dado_nulo():
    # evento sem 'data' e evento com data=None não podem virar 'None' na lista
    linhas = _nd(
        {"type": "TECHNOLOGY"},                 # sem 'data'
        {"type": "FINDING", "data": None},      # data nula
        {"type": "TECHNOLOGY", "data": {"technology": "nginx"}},
    )
    lead = en.agregar_eventos(linhas)
    assert lead["tecnologias"] == ["nginx"]     # nada de "None"
    assert lead["achados"] == []


# --- resumir: conta e dá exemplos, nunca a lista inteira --------------------
def test_resumir_mostra_contagem_e_amostra():
    lead = en.agregar_eventos(_nd(
        *[{"type": "DNS_NAME", "data": f"s{i}.x.com"} for i in range(8)]))
    txt = en.resumir(lead, "x.com", ativo=False)
    assert "passivo" in txt
    assert "subdomínios: 8" in txt
    assert "(+3)" in txt  # mostra 5, indica que há mais 3


def test_resumir_vazio_avisa():
    txt = en.resumir(en.agregar_eventos([]), "x.com", ativo=False)
    assert "nada de público" in txt


# --- _comando: a trava passivo/ativo ---------------------------------------
def test_comando_passivo_tranca_em_passive():
    cmd = en._comando("x.com", "/tmp/o", ativo=False)
    assert "passive" in cmd
    assert "safe" not in cmd
    assert "-t" in cmd and "x.com" in cmd


def test_comando_ativo_usa_safe_nao_passive():
    cmd = en._comando("x.com", "/tmp/o", ativo=True)
    assert "safe" in cmd
    # ativo NÃO deve trancar em passive (senão não seria ativo)
    assert cmd.count("passive") == 0


def test_rodar_para_app_dominio_invalido_nao_roda():
    r = en.rodar_para_app("isso não é domínio")
    assert r["codigo"] == 1 and "válido" in r["saida"]
