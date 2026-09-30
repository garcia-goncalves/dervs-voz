"""Testes do seletor de cérebro (dervs_cerebros): Claude Code, Hermes e JEV."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import dervs_cerebros as c

CHAVE = "chave-falsa-de-teste"


class FalsoJev:
    def __init__(self, status=200, resposta=None):
        self.pedidos = []
        self.status = status
        self.resposta = resposta if resposta is not None else {
            "answers": {"urgencia": {"type": "noul", "noul": 0.9}}}
        jev = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                jev.pedidos.append((self.path, self.headers.get("Authorization"),
                                    json.loads(self.rfile.read(n))))
                dados = json.dumps(jev.resposta).encode()
                self.send_response(jev.status)
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def jev_falso():
    j = FalsoJev()
    yield j
    j.fechar()


# ------------------------------------------------------------------ JEV

def test_jev_sem_chave_fica_desligado_e_diz_o_motivo():
    j = c.Jev(chave="")
    ok, motivo = j.disponivel()
    assert not ok and "TYPESAFE_API_KEY" in motivo
    with pytest.raises(c.CerebroIndisponivel):
        j.triar("x", {"urgencia": {"type": "noul", "instructions": "urgente?"}})


def test_jev_manda_bearer_e_corpo_do_contrato(jev_falso):
    j = c.Jev(chave=CHAVE, url=jev_falso.url + "/v1/systemone", permitir_http_local=True)
    r = j.triar("disco em 95%", {"urgencia": {"type": "noul", "instructions": "urgente?"}})
    caminho, auth, corpo = jev_falso.pedidos[0]
    assert caminho == "/v1/systemone" and auth == "Bearer " + CHAVE
    assert corpo["model"] == "jev-latest" and corpo["state"] == "disco em 95%"
    assert corpo["questions"]["urgencia"]["type"] == "noul"
    assert r["urgencia"] == pytest.approx(0.9)


def test_jev_nao_manda_segredo_nem_caminho(jev_falso):
    j = c.Jev(chave=CHAVE, url=jev_falso.url + "/v1/systemone", permitir_http_local=True)
    j.triar("erro em C:\\Users\\Dono\\Documents\\paciente.pdf com sk-ABCDEFGH12345678",
            {"u": {"type": "noul", "instructions": "x"}})
    enviado = jev_falso.pedidos[0][2]["state"]
    assert "paciente.pdf" not in enviado and "sk-ABCDEFGH" not in enviado
    assert "C:\\" not in enviado


def test_jev_chave_nunca_aparece_em_repr_nem_em_erro():
    j = c.Jev(chave=CHAVE, url="http://127.0.0.1:9/v1/systemone", permitir_http_local=True)
    assert CHAVE not in repr(j)
    with pytest.raises(c.CerebroIndisponivel) as e:
        j.triar("x", {"u": {"type": "noul", "instructions": "x"}})
    assert CHAVE not in str(e.value)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_jev_erro_http_vira_indisponivel(status):
    f = FalsoJev(status=status)
    try:
        j = c.Jev(chave=CHAVE, url=f.url + "/v1/systemone", permitir_http_local=True)
        with pytest.raises(c.CerebroIndisponivel):
            j.triar("x", {"u": {"type": "noul", "instructions": "x"}})
    finally:
        f.fechar()


def test_jev_so_fala_https_fora_da_propria_maquina():
    with pytest.raises(c.CerebroIndisponivel):
        c.Jev(chave=CHAVE, url="http://api.typesafe.ai/v1/systemone")


def test_jev_resposta_torta_nao_derruba():
    f = FalsoJev(resposta={"answers": "lixo"})
    try:
        j = c.Jev(chave=CHAVE, url=f.url + "/v1/systemone", permitir_http_local=True)
        assert j.triar("x", {"u": {"type": "noul", "instructions": "x"}}) == {}
    finally:
        f.fechar()


def test_jev_disponivel_quando_tem_chave():
    assert c.Jev(chave=CHAVE).disponivel() == (True, "")


# ------------------------------------------------------------------ Hermes

def test_hermes_desligado_diz_o_motivo():
    h = c.Hermes(executar=lambda *a, **k: (1, ""))
    ok, motivo = h.disponivel()
    assert not ok and "hermes" in motivo.lower()


def test_hermes_no_wsl_fica_disponivel():
    h = c.Hermes(executar=lambda args, **k: (0, "/usr/local/bin/hermes\n"))
    assert h.disponivel() == (True, "")


def test_hermes_sem_wsl_instalado_nao_levanta():
    def sem(args, **k):
        raise FileNotFoundError("wsl")
    ok, motivo = c.Hermes(executar=sem).disponivel()
    assert not ok and motivo


def test_hermes_perguntar_ainda_nao_executa_nada():
    chamadas = []
    h = c.Hermes(executar=lambda args, **k: chamadas.append(args) or (0, "/x/hermes"))
    with pytest.raises(c.CerebroIndisponivel):
        h.perguntar("faça algo")
    assert all("chat" not in " ".join(a) for a in chamadas)


# ------------------------------------------------------------------ Claude Code e o seletor

def test_claude_code_disponivel_quando_o_cli_existe():
    assert c.ClaudeCode(resolver=lambda: "claude.exe").disponivel() == (True, "")
    ok, motivo = c.ClaudeCode(resolver=lambda: "").disponivel()
    assert not ok and "claude" in motivo.lower()


def _seletor(tmp_path, **kw):
    cerebros = {
        "claude_code": c.ClaudeCode(resolver=lambda: "claude.exe"),
        "hermes": c.Hermes(executar=lambda *a, **k: (1, "")),
        "jev": c.Jev(chave=""),
    }
    return c.Seletor(cerebros, arquivo=str(tmp_path / "cerebro.json"), **kw)


def test_seletor_comeca_no_claude_code(tmp_path):
    assert _seletor(tmp_path).ativo == "claude_code"


def test_seletor_recusa_cerebro_indisponivel_e_diz_por_que(tmp_path):
    s = _seletor(tmp_path)
    ok, motivo = s.escolher("hermes")
    assert not ok and "hermes" in motivo.lower() and s.ativo == "claude_code"


def test_jev_nunca_vira_o_cerebro_ativo(tmp_path):
    f = FalsoJev()
    try:
        cerebros = {"claude_code": c.ClaudeCode(resolver=lambda: "x"),
                    "jev": c.Jev(chave=CHAVE, url=f.url + "/v1/systemone", permitir_http_local=True)}
        s = c.Seletor(cerebros, arquivo=str(tmp_path / "c.json"))
        ok, motivo = s.escolher("jev")
        assert not ok and "triagem" in motivo.lower() and s.ativo == "claude_code"
    finally:
        f.fechar()


def test_escolha_persiste_e_cerebro_que_some_volta_ao_claude(tmp_path):
    cerebros = {"claude_code": c.ClaudeCode(resolver=lambda: "x"),
                "hermes": c.Hermes(executar=lambda *a, **k: (0, "/x/hermes"))}
    s = c.Seletor(cerebros, arquivo=str(tmp_path / "c.json"))
    assert s.escolher("hermes") == (True, "")
    assert c.Seletor(cerebros, arquivo=str(tmp_path / "c.json")).ativo == "hermes"
    sumiu = {"claude_code": cerebros["claude_code"],
             "hermes": c.Hermes(executar=lambda *a, **k: (1, ""))}
    assert c.Seletor(sumiu, arquivo=str(tmp_path / "c.json")).ativo == "claude_code"


def test_arquivo_de_escolha_estragado_nao_derruba(tmp_path):
    (tmp_path / "cerebro.json").write_text("{lixo", encoding="utf-8")
    assert _seletor(tmp_path).ativo == "claude_code"


def test_estado_para_o_painel_tem_so_o_que_o_servidor_aceita(tmp_path):
    e = _seletor(tmp_path).estado()
    assert set(e) == {"cerebro_ativo", "cerebros"}
    assert set(e["cerebros"]) == {"claude_code", "hermes", "jev"}
    for v in e["cerebros"].values():
        assert set(v) == {"disponivel", "motivo"} and isinstance(v["disponivel"], bool)
        assert len(v["motivo"]) <= 200


# ------------------------------------------------------------------ triagem de recado

def test_triagem_sem_jev_usa_regra_simples_e_nunca_libera_nada(tmp_path):
    s = _seletor(tmp_path)
    t = s.triar_recado({"tipo": "propor", "nivel": "muda_estado", "texto": "apagar"})
    assert t["origem"] == "regra" and t["pode_agir_sozinho"] is False
    t2 = s.triar_recado({"tipo": "status", "nivel": "leitura", "texto": "como vai?"})
    assert t2["origem"] == "regra" and t2["pode_agir_sozinho"] is True


def test_triagem_do_jev_so_aumenta_a_urgencia_nunca_libera(tmp_path, jev_falso):
    cerebros = {"claude_code": c.ClaudeCode(resolver=lambda: "x"),
                "jev": c.Jev(chave=CHAVE, url=jev_falso.url + "/v1/systemone",
                             permitir_http_local=True)}
    s = c.Seletor(cerebros, arquivo=str(tmp_path / "c.json"))
    t = s.triar_recado({"tipo": "propor", "nivel": "muda_estado", "texto": "x"})
    assert t["origem"] == "jev" and t["urgencia"] == pytest.approx(0.9)
    assert t["pode_agir_sozinho"] is False      # JEV nunca destrava o clique
