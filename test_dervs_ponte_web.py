"""Testes da ponte DERVS-VOZ <-> DERVS web (dervs_ponte_web).

Sobe um servidor HTTP de mentira numa thread (sem rede externa) que faz o papel
das três rotas `maquina` do painel web.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import dervs_ponte_web as pw

CRACHA = "CRACHA-DE-TESTE-NAO-E-SEGREDO-123"


@pytest.fixture(autouse=True)
def _seletor_sem_wsl(monkeypatch, tmp_path):
    """Nenhum teste da ponte pode acordar o WSL de verdade."""
    import dervs_cerebros as c
    seletor = c.Seletor({"claude_code": c.ClaudeCode(resolver=lambda: "claude.exe"),
                         "hermes": c.Hermes(executar=lambda *a, **k: (1, "")),
                         "jev": c.Jev(chave=None)}, arquivo=str(tmp_path / "cerebro.json"))
    monkeypatch.setattr(pw, "_SELETOR", seletor)


class FalsoPainel:
    """Guarda o que a ponte mandou e devolve os recados combinados."""

    def __init__(self):
        self.recados = []
        self.estados = []
        self.resultados = []
        self.tokens_vistos = []
        self.pedidos = []
        self.resposta_pedido = {"ok": True, "tarefa_id": "memoria_crlf:1:memoria_crlf:dervs",
                                "pedido": True, "aviso": ""}
        self.status = 200
        painel = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _corpo(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}")

            def _responder(self, codigo, obj):
                dados = json.dumps(obj).encode()
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_GET(self):
                painel.tokens_vistos.append(self.headers.get("Authorization"))
                if painel.status != 200:
                    return self._responder(painel.status, {"erro": "x"})
                if self.path == "/agente/voz/recados":
                    return self._responder(200, {"recados": painel.recados})
                self._responder(404, {})

            def do_POST(self):
                painel.tokens_vistos.append(self.headers.get("Authorization"))
                if painel.status != 200:
                    return self._responder(painel.status, {"erro": "x"})
                corpo = self._corpo()
                if self.path == "/agente/voz/pedido":
                    painel.pedidos.append(corpo)
                    return self._responder(200, painel.resposta_pedido)
                if self.path == "/agente/voz/estado":
                    painel.estados.append(corpo)
                elif self.path == "/agente/voz/resultado":
                    painel.resultados.append(corpo)
                else:
                    return self._responder(404, {})
                self._responder(200, {"ok": True})

        self.servidor = HTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.servidor.server_port
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()


class TratadorFalso:
    def __init__(self):
        self.lidos = []
        self.propostos = []

    def leitura(self, recado):
        self.lidos.append(recado)
        return ("feito", "tudo certo em " + str(recado.get("alvo")), 0.0)

    def propor(self, recado):
        self.propostos.append(recado)
        return "proposta criada, aguardando o seu clique"


@pytest.fixture
def painel():
    p = FalsoPainel()
    yield p
    p.fechar()


@pytest.fixture
def arquivo_token(tmp_path):
    def _montar(url):
        f = tmp_path / "agente.json"
        f.write_text(json.dumps({url: {"token": CRACHA, "maquina": "t"}}), encoding="utf-8")
        return str(f)
    return _montar


@pytest.fixture
def ponte(painel, arquivo_token, tmp_path):
    import dervs_log_acoes as la
    tr = TratadorFalso()
    log = la.LogAcoes(str(tmp_path / "log.jsonl"))
    p = pw.PonteWeb(painel.url, tr, arquivo_token=arquivo_token(painel.url), log=log,
                    estado_fn=lambda: {"cerebro_ativo": "claude_code"})
    p.tratador = tr
    p.log = log
    return p


def _recado(**kw):
    base = {"id": "r-1", "criado_em": "2026-09-30T10:00:00", "tipo": "status",
            "alvo": "dervs", "texto": "como vai?", "nivel": "leitura",
            "cerebro_pedido": "auto"}
    base.update(kw)
    return base


# ------------------------------------------------------------------ alvo e token

@pytest.mark.parametrize("alvo", ["http://example.com", "ftp://x.com", "https://u:p@x.com",
                                  "x.com", "", "https://"])
def test_alvo_ruim_e_recusado(alvo):
    with pytest.raises(pw.PonteIndisponivel):
        pw.conferir_alvo(alvo)


@pytest.mark.parametrize("alvo", ["https://dervs.com.br", "http://localhost:4790/",
                                  "http://127.0.0.1:4790"])
def test_alvo_bom_passa_sem_barra_final(alvo):
    assert not pw.conferir_alvo(alvo).endswith("/")


def test_sem_token_diz_o_motivo(tmp_path, painel):
    p = pw.PonteWeb(painel.url, TratadorFalso(), arquivo_token=str(tmp_path / "nao-existe.json"))
    r = p.ciclo()
    assert not r["ok"]
    assert "token" in r["motivo"].lower() and "pare" in r["motivo"].lower()
    assert painel.estados == []


def test_token_nao_aparece_no_repr_nem_no_log(ponte, painel):
    painel.recados = [_recado()]
    ponte.ciclo()
    assert CRACHA not in repr(ponte) and CRACHA not in str(ponte)
    assert CRACHA not in json.dumps(ponte.log.ler())
    assert ponte.motivo is None or CRACHA not in ponte.motivo


def test_token_vai_no_cabecalho(ponte, painel):
    ponte.ciclo()
    assert painel.tokens_vistos and all(t == "Token " + CRACHA for t in painel.tokens_vistos)


# ------------------------------------------------------------------ o ciclo

def test_ciclo_manda_estado_e_devolve_resultado(ponte, painel):
    painel.recados = [_recado()]
    r = ponte.ciclo()
    assert r["ok"] and r["recados"] == 1
    assert painel.estados[0]["versao"] == 1
    assert painel.estados[0]["cerebro_ativo"] == "claude_code"
    assert "enviado_em" in painel.estados[0]
    res = painel.resultados[0]
    assert res["id"] == "r-1" and res["estado"] == "feito" and res["cerebro"] == "claude_code"
    assert "terminado_em" in res


def test_leitura_roda_sozinha(ponte, painel):
    painel.recados = [_recado(tipo="analisar")]
    ponte.ciclo()
    assert len(ponte.tratador.lidos) == 1 and ponte.tratador.propostos == []


@pytest.mark.parametrize("tipo,nivel", [("status", "muda_estado"), ("analisar", "muda_estado"),
                                       ("propor", "muda_estado"), ("propor", "leitura")])
def test_o_que_muda_estado_so_vira_proposta(ponte, painel, tipo, nivel):
    painel.recados = [_recado(tipo=tipo, nivel=nivel)]
    ponte.ciclo()
    assert ponte.tratador.lidos == []
    assert len(ponte.tratador.propostos) == 1
    assert painel.resultados[0]["estado"] == "aguardando_clique"


def test_id_repetido_e_ignorado(ponte, painel):
    painel.recados = [_recado(), _recado()]
    ponte.ciclo()
    ponte.ciclo()
    assert len(ponte.tratador.lidos) == 1
    assert len(painel.resultados) == 1


@pytest.mark.parametrize("ruim", [
    {"tipo": "executar"}, {"nivel": "tudo"}, {"alvo": "..\\..\\Windows"},
    {"alvo": "C:/Windows"}, {"alvo": "a/b"}, {"cerebro_pedido": "gpt"},
    {"texto": "x" * 501}, {"texto": 5},
])
def test_recado_fora_do_contrato_e_recusado(ponte, painel, ruim):
    painel.recados = [_recado(**ruim)]
    ponte.ciclo()
    assert ponte.tratador.lidos == [] and ponte.tratador.propostos == []
    assert painel.resultados[0]["estado"] == "recusado"


def test_recado_sem_id_valido_e_descartado_sem_resposta(ponte, painel):
    painel.recados = [_recado(id=""), _recado(id="x" * 200), "lixo", None, 7]
    r = ponte.ciclo()
    assert r["ok"] and painel.resultados == []


def test_tratador_que_quebra_vira_falhou_sem_vazar_o_erro(ponte, painel):
    def quebra(recado):
        raise RuntimeError("caminho C:\\segredo\\senha.txt")
    ponte.tratador.leitura = quebra
    painel.recados = [_recado()]
    ponte.ciclo()
    res = painel.resultados[0]
    assert res["estado"] == "falhou" and "segredo" not in res["resumo"]


def test_resumo_tem_teto_e_tira_segredo(ponte, painel):
    ponte.tratador.leitura = lambda r: ("feito", "chave sk-ABCDEFGH12345678 " + "y" * 3000, 0.0)
    painel.recados = [_recado()]
    ponte.ciclo()
    resumo = painel.resultados[0]["resumo"]
    assert len(resumo) <= 1000 and "sk-ABCDEFGH" not in resumo


def test_cada_recado_deixa_rastro_no_registro(ponte, painel):
    painel.recados = [_recado(), _recado(id="r-2", nivel="muda_estado")]
    ponte.ciclo()
    eventos = [l["evento"] for l in ponte.log.ler()]
    assert "analisou" in eventos and "propos" in eventos


def test_recado_que_o_porteiro_recusa_volta_recusado(ponte, painel):
    ponte.tratador.leitura = lambda r: ("recusado", "caminho protegido", 0.0)
    painel.recados = [_recado()]
    ponte.ciclo()
    assert painel.resultados[0]["estado"] == "recusado"


# ------------------------------------------------------------------ falhas

@pytest.mark.parametrize("codigo,trecho", [(401, "token"), (403, "token"), (500, "fora do ar"),
                                           (404, "ainda não tem a ponte")])
def test_painel_recusando_ou_caindo_nao_levanta(ponte, painel, codigo, trecho):
    painel.status = codigo
    r = ponte.ciclo()
    assert not r["ok"] and trecho in r["motivo"].lower()


def test_painel_desligado_nao_levanta(arquivo_token, tmp_path):
    url = "http://127.0.0.1:9"
    p = pw.PonteWeb(url, TratadorFalso(), arquivo_token=arquivo_token(url))
    r = p.ciclo()
    assert not r["ok"] and "alcan" in r["motivo"].lower()


def test_redirecionamento_nao_leva_o_token(painel, arquivo_token):
    class Redir(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _volta(self):
            self.send_response(302)
            self.send_header("Location", painel.url + "/agente/voz/recados")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _volta

    srv = HTTPServer(("127.0.0.1", 0), Redir)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % srv.server_port
    try:
        p = pw.PonteWeb(url, TratadorFalso(), arquivo_token=arquivo_token(url))
        r = p.ciclo()
        assert not r["ok"]
        assert painel.tokens_vistos == []
    finally:
        srv.shutdown()
        srv.server_close()


def test_resposta_gigante_e_recusada(ponte, painel):
    painel.recados = [dict(_recado(id="g%d" % i), texto="b") for i in range(3000)]
    r = ponte.ciclo()
    assert not r["ok"] and "grande" in r["motivo"].lower()


def test_no_maximo_dez_recados_por_ciclo(ponte, painel):
    painel.recados = [_recado(id="m%d" % i) for i in range(10)]
    ponte.ciclo()
    assert len(ponte.tratador.lidos) == 10


# ------------------------------------------------------------------ a thread

def test_laco_liga_e_desliga(ponte, painel):
    ponte.intervalo_s = 0.05
    ponte.iniciar()
    try:
        import time
        for _ in range(100):
            if painel.estados:
                break
            time.sleep(0.02)
        assert painel.estados
    finally:
        ponte.parar()
    assert not ponte.ligada


def test_modulo_nao_abre_porta():
    import ast
    import pathlib
    fonte = pathlib.Path(pw.__file__).read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    usados = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
    assert not usados & {"bind", "listen", "serve_forever"}
    importados = {a.name.split(".")[0] for n in ast.walk(arvore)
                  if isinstance(n, (ast.Import,)) for a in n.names}
    importados |= {n.module.split(".")[0] for n in ast.walk(arvore)
                   if isinstance(n, ast.ImportFrom) and n.module}
    assert "socketserver" not in importados
    assert "http.server" not in fonte


# ------------------------------------------------------------------ ligação ao app

def test_estado_do_voz_nao_tem_segredo(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "chave-secreta-de-teste")
    e = pw.estado_do_voz()
    assert e["cerebros"]["jev"]["disponivel"] is True
    assert "chave-secreta" not in json.dumps(e)


def test_estado_do_voz_sem_chave_diz_o_motivo(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    j = pw.estado_do_voz()["cerebros"]["jev"]
    assert j["disponivel"] is False and "TYPESAFE_API_KEY" in j["motivo"]


def test_desligada_na_config_nao_liga():
    p, motivo = pw.iniciar_da_config({"ponte_web_ligada": False})
    assert p is None and "desligada" in motivo


def test_sem_token_nao_liga_e_diz_por_que(monkeypatch, tmp_path):
    monkeypatch.setenv("DERVS_AGENTE_ARQUIVO", str(tmp_path / "nada.json"))
    p, motivo = pw.iniciar_da_config({"ponte_web_alvo": "https://dervs.com.br"})
    assert p is None and "token" in motivo


def test_alvo_torto_na_config_nao_levanta():
    p, motivo = pw.iniciar_da_config({"ponte_web_alvo": "http://evil.example.com"})
    assert p is None and motivo


def test_com_token_liga_e_para(monkeypatch, painel, arquivo_token, tmp_path):
    import dervs_log_acoes as la
    monkeypatch.setenv("DERVS_AGENTE_ARQUIVO", arquivo_token(painel.url))
    p, motivo = pw.iniciar_da_config(
        {"ponte_web_alvo": painel.url, "ponte_web_intervalo_s": 60},
        tratador=TratadorFalso(), log=la.LogAcoes(str(tmp_path / "l.jsonl")))
    try:
        assert p is not None and motivo == ""
        import time
        for _ in range(100):
            if painel.estados:
                break
            time.sleep(0.02)
        assert painel.estados
    finally:
        if p is not None:
            p.parar()


def test_config_padrao_da_ponte_e_validada():
    import dervs_config as cfg
    c = cfg._validar({**cfg.PADRAO, "ponte_web_ligada": "sim", "ponte_web_alvo": "ftp://x",
                      "ponte_web_intervalo_s": 1})
    assert c["ponte_web_ligada"] is True
    assert c["ponte_web_alvo"].startswith("https://")
    assert c["ponte_web_intervalo_s"] == 60


# ------------------------------------------------------------------ rede que cai no meio

def test_resultado_que_nao_chegou_e_reenviado_sem_refazer(ponte, painel):
    painel.recados = [_recado()]
    original = ponte.devolver
    ponte.devolver = lambda r: (_ for _ in ()).throw(pw.PonteIndisponivel("rede caiu"))
    r1 = ponte.ciclo()
    assert not r1["ok"] and len(ponte.tratador.lidos) == 1 and painel.resultados == []
    ponte.devolver = original
    r2 = ponte.ciclo()          # o painel reenvia o mesmo recado
    assert r2["ok"] and len(ponte.tratador.lidos) == 1   # não refez
    assert [x["id"] for x in painel.resultados] == ["r-1"]


def test_falha_do_tratador_deixa_rastro_so_com_o_tipo(ponte, painel):
    def quebra(recado):
        raise PermissionError(r"C:\segredo\senha.txt")
    ponte.tratador.leitura = quebra
    painel.recados = [_recado()]
    ponte.ciclo()
    linhas = json.dumps(ponte.log.ler())
    assert "PermissionError" in linhas and "segredo" not in linhas


# ------------------------------------------------------------------ revisão de segurança

def test_teto_de_recados_por_hora(ponte, painel):
    painel.recados = [_recado(id="t%d" % i) for i in range(10)]
    for _ in range(pw.MAX_RECADOS_POR_HORA // 10 + 2):
        painel.recados = [_recado(id="t%d-%d" % (i, len(ponte._vistos))) for i in range(10)]
        ponte.ciclo()
    assert len(ponte.tratador.lidos) == pw.MAX_RECADOS_POR_HORA
    alertas = [l for l in ponte.log.ler() if l["evento"] == "alerta"]
    assert len(alertas) == 1        # um aviso só, não uma linha por recado


@pytest.mark.parametrize("texto", ["abre‮isto", "a​b", "x\x00y", "a\x1bb"])
def test_texto_com_caractere_de_controle_e_recusado(ponte, painel, texto):
    painel.recados = [_recado(texto=texto)]
    ponte.ciclo()
    assert ponte.tratador.lidos == [] and painel.resultados[0]["estado"] == "recusado"


@pytest.mark.parametrize("ruim", [{"alvo": "dervs-voz\n"}])
def test_quebra_de_linha_no_fim_nao_passa(ponte, painel, ruim):
    painel.recados = [_recado(**ruim), _recado(id="r-2\n")]
    ponte.ciclo()
    assert ponte.tratador.lidos == []
    assert [r["id"] for r in painel.resultados] == ["r-1"]


def test_resposta_que_goteja_estoura_o_prazo(monkeypatch):
    monkeypatch.setattr(pw, "PRAZO_DA_RESPOSTA_S", 0.05)

    class Lenta:
        def read(self, n):
            import time
            time.sleep(0.03)
            return b"x"

    with pytest.raises(TimeoutError):
        pw.PonteWeb._ler_com_prazo(Lenta())


def test_estado_tem_exatamente_as_chaves_do_contrato(painel, arquivo_token, tmp_path):
    import dervs_log_acoes as la
    p = pw.PonteWeb(painel.url, TratadorFalso(), arquivo_token=arquivo_token(painel.url),
                    log=la.LogAcoes(str(tmp_path / "l.jsonl")), estado_fn=pw.estado_do_voz)
    p.ciclo()
    assert set(painel.estados[0]) == {"versao", "enviado_em", "cerebro_ativo", "cerebros",
                                      "gasto_dia_usd"}


@pytest.mark.parametrize("cerebro", ["auto", "claude_code", "hermes"])
@pytest.mark.parametrize("tipo", ["status", "analisar", "propor"])
def test_muda_estado_nunca_executa_sem_clique_seja_qual_for_o_cerebro(ponte, painel, cerebro, tipo):
    painel.recados = [_recado(tipo=tipo, nivel="muda_estado", cerebro_pedido=cerebro)]
    ponte.ciclo()
    assert ponte.tratador.lidos == []
    assert len(ponte.tratador.propostos) == 1
    assert painel.resultados[0]["estado"] == "aguardando_clique"


@pytest.mark.parametrize("codigo", [401, 403, 404])
def test_painel_sem_a_ponte_e_calmo_e_espera_cinco_minutos(ponte, painel, codigo):
    painel.status = codigo
    r = ponte.ciclo()
    assert not r["ok"] and r["calma"] is True


def test_erro_de_verdade_nao_e_calmo(ponte, painel):
    painel.status = 500
    assert ponte.ciclo().get("calma") is not True


def test_laco_calmo_espera_cinco_minutos(ponte, painel, monkeypatch):
    esperas = []
    ponte.intervalo_s = 60
    painel.status = 404
    monkeypatch.setattr(ponte._parar, "wait", lambda s: esperas.append(s) or ponte._parar.set())
    ponte._laco()
    assert esperas == [pw.ESPERA_CALMA_S]


def test_aviso_de_leitura_e_entregue_ao_dono_e_nada_executa(painel, arquivo_token, tmp_path):
    import dervs_log_acoes as la
    import dervs_ponte_tratador as pt
    mostrados = []
    tr = pt.TratadorLocal(arquivo_propostas=str(tmp_path / "p.jsonl"),
                          aviso_fn=lambda texto, alvo: mostrados.append((texto, alvo)))
    p = pw.PonteWeb(painel.url, tr, arquivo_token=arquivo_token(painel.url),
                    log=la.LogAcoes(str(tmp_path / "l.jsonl")))
    painel.recados = [_recado(tipo="avisar", alvo="vigilia", texto="PC sem medir há 20 min")]
    p.ciclo()
    assert mostrados == [("PC sem medir há 20 min", "vigilia")]
    assert painel.resultados[0]["estado"] == "feito" and tr.pendentes() == []


def test_aviso_que_tenta_mudar_estado_e_recusado(ponte, painel):
    painel.recados = [_recado(tipo="avisar", nivel="muda_estado")]
    ponte.ciclo()
    assert ponte.tratador.lidos == [] and ponte.tratador.propostos == []
    assert painel.resultados[0]["estado"] == "recusado"


# ------------------------------------------------------------------ pedir conserto ao painel

def test_pedir_conserto_manda_so_as_tres_chaves_do_contrato(ponte, painel):
    r = ponte.pedir_conserto("memoria_crlf:dervs", r"CRLF em 3 arquivos C:\Users\Dono\x.py")
    assert r == {"ok": True, "tarefa_id": "memoria_crlf:1:memoria_crlf:dervs", "novo": True, "aviso": ""}
    corpo = painel.pedidos[0]
    assert set(corpo) == {"tipo", "alerta_id", "resumo"} and corpo["tipo"] == "enfileirar_conserto"
    assert "C:\\" not in corpo["resumo"]          # caminho do dono não sai


def test_pedido_repetido_diz_que_ja_existia(ponte, painel):
    painel.resposta_pedido = {"ok": True, "tarefa_id": "a:1:a:b", "pedido": False, "aviso": "já estava na fila"}
    r = ponte.pedir_conserto("a:b")
    assert r["ok"] and r["novo"] is False and r["aviso"] == "já estava na fila"


@pytest.mark.parametrize("codigo,trecho", [(404, "não conhece"), (403, "não conserta"),
                                           (429, "espere"), (400, "formato")])
def test_erros_do_pedido_tem_frase_propria(ponte, painel, codigo, trecho):
    painel.status = codigo
    r = ponte.pedir_conserto("a:b")
    assert not r["ok"] and trecho in r["motivo"]


@pytest.mark.parametrize("ruim", ["", "x" * 201, "a‮b", None, 7])
def test_alerta_id_invalido_nem_sai_do_computador(ponte, painel, ruim):
    assert not ponte.pedir_conserto(ruim)["ok"] and painel.pedidos == []


def test_resposta_estranha_do_pedido_nao_levanta(ponte, painel):
    painel.resposta_pedido = {"ok": True, "tarefa_id": 5}
    assert not ponte.pedir_conserto("a:b")["ok"]
