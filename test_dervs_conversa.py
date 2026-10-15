"""Testes do motor de conversa trocável (dervs_conversa).

Sem rede externa: WebSocket por transporte injetado (FakeWS) e HTTP por um
servidor local numa thread, no estilo de test_dervs_ponte_web.py.
"""
import base64
import json
import logging
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

import dervs_config
import dervs_conversa as dc
import dervs_gasto

CHAVE = "CHAVE-DE-TESTE-ABC123-NAO-VAZAR"
PCM = (np.arange(1600, dtype=np.int16) % 100).tobytes()      # 0,05 s a 16 kHz


# --- apoio -------------------------------------------------------------------

class FakeWS:
    def __init__(self):
        self.entrada = queue.Queue()
        self.enviados = []
        self.fechado = False

    def send(self, texto):
        self.enviados.append(json.loads(texto))

    def recv(self):
        item = self.entrada.get(timeout=10)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        if not self.fechado:
            self.fechado = True
            self.entrada.put(dc.FechadoPeloServidor(1000, ""))

    def servidor(self, obj):
        self.entrada.put(json.dumps(obj))

    def tipos(self):
        return [next(iter(m)) if "type" not in m else m["type"] for m in self.enviados]


class Transporte:
    """Entrega os FakeWS na ordem; registra url e cabeçalhos; pode falhar ao conectar."""

    def __init__(self, *wss, falha=None):
        self.wss = list(wss)
        self.falha = falha
        self.chamadas = []

    def __call__(self, url, cabecalhos):
        self.chamadas.append((url, list(cabecalhos)))
        if self.falha:
            raise self.falha
        return self.wss.pop(0)


class Coletor:
    def __init__(self):
        self.eventos = []

    def __call__(self, ev):
        self.eventos.append(ev)

    def de(self, classe):
        return [e for e in self.eventos if isinstance(e, classe)]

    def esperar(self, classe, n=1, t=5):
        fim = time.time() + t
        while time.time() < fim:
            achados = self.de(classe)
            if len(achados) >= n:
                return achados
            time.sleep(0.01)
        raise AssertionError("não chegou %s: %r" % (classe.__name__, self.eventos))


def esperar_ate(cond, t=5):
    fim = time.time() + t
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.01)
    raise AssertionError("condição não cumprida")


class ErroComStatus(Exception):
    def __init__(self, status_code, texto=""):
        super().__init__(texto)
        self.status_code = status_code


@pytest.fixture
def gasto(monkeypatch):
    linhas = []
    monkeypatch.setattr(dervs_gasto, "registrar",
                        lambda tipo, usd, detalhe="", **k: linhas.append((tipo, usd, detalhe)) or True)
    return linhas


CONF = dict(dervs_config.PADRAO)
FERRAMENTA = {"name": "fazer", "description": "faz algo",
              "parameters": {"type": "object", "properties": {"pedido": {"type": "string"}}}}


def gemini(ws=None, **kw):
    ws = ws or FakeWS()
    ws.servidor({"setupComplete": {}})
    col = Coletor()
    tr = Transporte(ws, *kw.pop("mais", []))
    m = dc.MotorGeminiLive(col, dict(CONF), chave=CHAVE, transporte=tr, **kw)
    return m, ws, col, tr


# --- Gemini Live ---------------------------------------------------------------

def test_gemini_setup_e_chave_no_cabecalho():
    m, ws, col, tr = gemini()
    m.iniciar("seja breve", [FERRAMENTA])
    esperar_ate(lambda: ws.enviados)
    url, cab = tr.chamadas[0]
    assert url == dc.URL_GEMINI_LIVE and CHAVE not in url      # a chave não vai na URL (log de proxy)
    assert cab == ["x-goog-api-key: " + CHAVE]
    s = ws.enviados[0]["setup"]
    assert s["model"] == "models/gemini-3.8-live"
    assert s["generationConfig"]["responseModalities"] == ["AUDIO"]
    voz = s["generationConfig"]["speechConfig"]
    assert voz["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Charon"
    assert voz["languageCode"] == "pt-BR"
    assert s["realtimeInputConfig"]["automaticActivityDetection"]["disabled"] is True
    assert s["tools"] == [{"functionDeclarations": [FERRAMENTA]}]
    assert s["systemInstruction"]["parts"][0]["text"] == "seja breve"
    m.encerrar()


def test_gemini_voz_vem_da_config():
    ws = FakeWS()
    ws.servidor({"setupComplete": {}})
    m = dc.MotorGeminiLive(Coletor(), dict(CONF, voz_gemini="Kore"), chave=CHAVE,
                           transporte=Transporte(ws))
    m.iniciar("x", [])
    esperar_ate(lambda: ws.enviados)
    voz = ws.enviados[0]["setup"]["generationConfig"]["speechConfig"]["voiceConfig"]
    assert voz["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert "tools" not in ws.enviados[0]["setup"]
    m.encerrar()


def test_gemini_sinais_de_atividade():
    m, ws, col, _ = gemini()
    m.iniciar("x", [])
    m.enviar_audio(PCM)
    m.enviar_audio(PCM)
    m.fim_da_vez()
    esperar_ate(lambda: len(ws.enviados) >= 5)
    corpo = [e["realtimeInput"] for e in ws.enviados[1:5]]
    assert "activityStart" in corpo[0]
    assert corpo[1]["audio"]["mimeType"] == "audio/pcm;rate=16000"
    assert base64.b64decode(corpo[1]["audio"]["data"]) == PCM
    assert "audio" in corpo[2] and "activityEnd" in corpo[3]
    m.encerrar()


def test_gemini_mapeia_eventos():
    m, ws, col, _ = gemini()
    m.iniciar("x", [])
    pcm = b"\x01\x00" * 480
    ws.servidor({"serverContent": {"modelTurn": {"parts": [
        {"inlineData": {"data": base64.b64encode(pcm).decode(), "mimeType": "audio/pcm;rate=24000"}}]},
        "outputTranscription": {"text": "Oi!"}}})
    ws.servidor({"serverContent": {"inputTranscription": {"text": "olá"}}})
    ws.servidor({"serverContent": {"turnComplete": True}})
    a = col.esperar(dc.AudioSaida)[0]
    assert a.pcm == pcm and a.taxa == 24000
    assert col.esperar(dc.TextoSaida)[0].texto == "Oi!"
    assert col.esperar(dc.TextoEntrada)[0].texto == "olá"
    col.esperar(dc.FimResposta)
    m.encerrar()


def test_gemini_ferramenta_ida_e_volta():
    m, ws, col, _ = gemini()
    m.iniciar("x", [FERRAMENTA])
    ws.servidor({"toolCall": {"functionCalls": [{"id": "c1", "name": "fazer", "args": {"pedido": "abre o chrome"}}]}})
    c = col.esperar(dc.ChamadaFerramenta)[0]
    assert (c.id, c.nome, c.args) == ("c1", "fazer", {"pedido": "abre o chrome"})
    m.responder_ferramenta("c1", {"ok": True})
    esperar_ate(lambda: any("toolResponse" in e for e in ws.enviados))
    r = [e for e in ws.enviados if "toolResponse" in e][0]["toolResponse"]["functionResponses"][0]
    assert r == {"id": "c1", "name": "fazer", "response": {"ok": True}}
    m.encerrar()


def test_gemini_interromper_descarta_audio_na_fila_e_na_volta():
    m, ws, col, _ = gemini()
    # sem iniciar: a fila não é consumida, dá para inspecionar o que sobra
    m.enviar_audio(PCM)
    m.enviar_audio(PCM)
    m.interromper()
    restantes = [json.loads(x[1]) for x in m._fila._itens]
    assert all("audio" not in r.get("realtimeInput", {}) for r in restantes)
    assert any("activityStart" in r.get("realtimeInput", {}) for r in restantes)
    m.iniciar("x", [])
    # o modelo ainda manda áudio da fala velha: tem de ser jogado fora até "interrupted"
    velho = base64.b64encode(b"\x02\x00" * 10).decode()
    ws.servidor({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": velho}}]}}})
    ws.servidor({"serverContent": {"interrupted": True}})
    novo = base64.b64encode(b"\x03\x00" * 10).decode()
    ws.servidor({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": novo}}]}}})
    esperar_ate(lambda: len(col.de(dc.AudioSaida)) >= 1)
    time.sleep(0.1)
    assert [a.pcm for a in col.de(dc.AudioSaida)] == [b"\x03\x00" * 10]
    m.encerrar()


def test_gemini_barge_in_com_vez_aberta_nao_repete_activity_start():
    m, ws, col, _ = gemini()
    m.enviar_audio(PCM)
    m.interromper()
    inicios = [json.loads(x[1]) for x in m._fila._itens
               if "activityStart" in json.loads(x[1]).get("realtimeInput", {})]
    assert len(inicios) == 1


@pytest.mark.parametrize("falha,tipo", [
    (ErroComStatus(429), "limite"), (ErroComStatus(401), "chave"), (ErroComStatus(403), "chave"),
    (ErroComStatus(503), "rede"), (ConnectionRefusedError("x"), "rede"), (TimeoutError(), "rede"),
    (ValueError("estranho"), "outro")])
def test_gemini_erro_ao_conectar_vira_tipo(falha, tipo):
    col = Coletor()
    m = dc.MotorGeminiLive(col, dict(CONF), chave=CHAVE, transporte=Transporte(falha=falha))
    m.iniciar("x", [])
    e = col.esperar(dc.Erro)[0]
    assert e.tipo == tipo


@pytest.mark.parametrize("msg,tipo", [
    ({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "cota"}}, "limite"),
    ({"error": {"code": 403, "status": "PERMISSION_DENIED"}}, "chave"),
    ({"error": {"code": 500, "status": "INTERNAL"}}, "rede")])
def test_gemini_erro_vindo_do_servidor(msg, tipo):
    m, ws, col, _ = gemini()
    m.iniciar("x", [])
    ws.servidor(msg)
    assert col.esperar(dc.Erro)[0].tipo == tipo


def test_gemini_fechamento_por_cota_vira_limite():
    m, ws, col, _ = gemini()
    m.iniciar("x", [])
    ws.entrada.put(dc.FechadoPeloServidor(1011, "Resource has been exhausted (e.g. check quota)."))
    assert col.esperar(dc.Erro)[0].tipo == "limite"


def test_chave_ausente_vira_erro_chave(monkeypatch):
    monkeypatch.setattr(dervs_config, "segredo", lambda nome: None)
    col = Coletor()
    m = dc.MotorGeminiLive(col, dict(CONF), transporte=Transporte(FakeWS()))
    m.iniciar("x", [])
    assert col.esperar(dc.Erro)[0].tipo == "chave"


def test_chave_nunca_aparece_em_erro_log_ou_excecao(caplog):
    caplog.set_level(logging.DEBUG)
    perigosa = ErroComStatus(401, "falha em wss://x/?key=" + CHAVE)
    col = Coletor()
    m = dc.MotorGeminiLive(col, dict(CONF), chave=CHAVE, transporte=Transporte(falha=perigosa))
    m.iniciar("x", [])
    erro = col.esperar(dc.Erro)[0]
    # o transporte real levanta com a URL na mensagem; a camada de cima nunca a repassa
    assert CHAVE not in repr(erro) and CHAVE not in repr(col.eventos)
    assert CHAVE not in caplog.text
    # e a exceção que sobe de _abrir tampouco carrega a chave nem encadeia a original
    m2 = dc.MotorGeminiLive(Coletor(), dict(CONF), chave=CHAVE, transporte=Transporte(falha=perigosa))
    with pytest.raises(dc.ErroTransporte) as info:
        m2._abrir()
    assert CHAVE not in str(info.value) and CHAVE not in repr(info.value.__cause__)
    assert info.value.__suppress_context__ is True


def test_gemini_go_away_reconecta_com_handle():
    ws1, ws2 = FakeWS(), FakeWS()
    ws2.servidor({"setupComplete": {}})
    m, _, col, tr = gemini(ws1, mais=[ws2])
    m.iniciar("x", [])
    ws1.servidor({"sessionResumptionUpdate": {"newHandle": "H-1", "resumable": True}})
    ws1.servidor({"goAway": {"timeLeft": "30s"}})
    esperar_ate(lambda: ws2.enviados)
    assert ws2.enviados[0]["setup"]["sessionResumption"] == {"handle": "H-1"}
    assert ws1.fechado
    # depois da troca, o áudio sai pela sessão nova
    m.enviar_audio(PCM)
    esperar_ate(lambda: any("audio" in e.get("realtimeInput", {}) for e in ws2.enviados))
    m.encerrar()


def test_gemini_go_away_sem_handle_semeia_ultimas_falas():
    ws1, ws2 = FakeWS(), FakeWS()
    ws2.servidor({"setupComplete": {}})
    m, _, col, tr = gemini(ws1, mais=[ws2])
    m.iniciar("x", [])
    ws1.servidor({"serverContent": {"inputTranscription": {"text": "oi"}}})
    ws1.servidor({"serverContent": {"outputTranscription": {"text": "olá!"}, "turnComplete": True}})
    col.esperar(dc.FimResposta)
    ws1.servidor({"goAway": {"timeLeft": "30s"}})
    esperar_ate(lambda: len(ws2.enviados) >= 2)
    assert "handle" not in ws2.enviados[0]["setup"]["sessionResumption"]
    turnos = ws2.enviados[1]["clientContent"]["turns"]
    assert [(t["role"], t["parts"][0]["text"]) for t in turnos] == [("user", "oi"), ("model", "olá!")]
    m.encerrar()


def test_gemini_gasto_registra_segundos_com_usd_zero(gasto):
    m, ws, col, _ = gemini()
    m.iniciar("x", [])
    m.enviar_audio(b"\x00\x00" * 32000)                      # 2 s
    pcm = base64.b64encode(b"\x00\x00" * 24000).decode()     # 1 s a 24 kHz
    ws.servidor({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": pcm}}]}}})
    ws.servidor({"serverContent": {"turnComplete": True}})
    col.esperar(dc.FimResposta)
    assert gasto == [("conversa", 0.0, "gemini_live 2s/1s")]
    assert m.uso["seg_in"] == pytest.approx(2.0) and m.uso["seg_out"] == pytest.approx(1.0)
    m.encerrar()


# --- transporte: corrida com encerrar(), escritor, reconexões ----------------------------

class TransporteLento:
    """Bloqueia no connect até `liberar`; entrega os FakeWS depois."""

    def __init__(self, *wss):
        self.wss = list(wss)
        self.liberar = threading.Event()
        self.entrou = threading.Event()

    def __call__(self, url, cabecalhos):
        self.entrou.set()
        assert self.liberar.wait(5)
        return self.wss.pop(0)


def test_encerrar_durante_a_conexao_fecha_o_ws_que_chega_depois():
    ws = FakeWS()
    ws.servidor({"setupComplete": {}})
    tr = TransporteLento(ws)
    m = dc.MotorGeminiLive(Coletor(), dict(CONF), chave=CHAVE, transporte=tr)
    m.iniciar("x", [])
    assert tr.entrou.wait(5)
    m.encerrar()
    tr.liberar.set()
    esperar_ate(lambda: ws.fechado)
    assert m._ws is None


def test_encerrar_durante_a_reconexao_fecha_o_ws_novo():
    ws1, ws2 = FakeWS(), FakeWS()
    ws1.servidor({"setupComplete": {}})
    ws2.servidor({"setupComplete": {}})
    tr = TransporteLento(ws1, ws2)
    tr.liberar.set()
    m = dc.MotorGeminiLive(Coletor(), dict(CONF), chave=CHAVE, transporte=tr)
    m.iniciar("x", [])
    esperar_ate(lambda: ws1.enviados)
    tr.liberar.clear()
    tr.entrou.clear()
    ws1.servidor({"goAway": {"timeLeft": "30s"}})
    assert tr.entrou.wait(5)
    m.encerrar()
    tr.liberar.set()
    esperar_ate(lambda: ws2.fechado)
    assert m._ws is None


def test_ws_real_so_tira_o_timeout_depois_do_handshake(monkeypatch):
    import websocket
    visto = []

    class Cru:
        def settimeout(self, t):
            visto.append(t)

    def cria(url, header=None, timeout=None):
        visto.append(timeout)
        return Cru()

    monkeypatch.setattr(websocket, "create_connection", cria)
    ws = dc._WsReal("wss://x", [])
    assert visto == [30]                       # sem settimeout(None) enquanto o handshake roda
    ws.pronto()
    assert visto == [30, None]


class WsEnvioFalha(FakeWS):
    """O primeiro envio de áudio estoura (socket trocado no meio); os outros passam."""

    def __init__(self):
        super().__init__()
        self.falhou = False

    def send(self, texto):
        if "audio" in texto and not self.falhou:
            self.falhou = True
            raise ConnectionResetError("socket velho")
        super().send(texto)


def test_escritor_descarta_item_se_o_envio_falha_e_nao_mata_a_sessao():
    ws = WsEnvioFalha()
    m, _, col, _ = gemini(ws)
    m.iniciar("x", [])
    m.enviar_audio(PCM)
    esperar_ate(lambda: ws.falhou)
    m.enviar_audio(PCM)
    esperar_ate(lambda: any("audio" in e.get("realtimeInput", {}) for e in ws.enviados))
    assert not col.de(dc.Erro) and not m._encerrado
    m.encerrar()


def test_reconexoes_so_contam_falhas_seguidas():
    wss = [FakeWS() for _ in range(6)]
    for w in wss:
        w.servidor({"setupComplete": {}})
    m, _, col, _ = gemini(wss[0], mais=wss[1:])
    m.iniciar("x", [])
    for i in range(5):                          # MAX_RECONEXOES = 3: a 4a goAway não pode matar
        wss[i].servidor({"goAway": {"timeLeft": "30s"}})
        esperar_ate(lambda: wss[i + 1].enviados)
    assert not col.de(dc.Erro)
    m.encerrar()


# --- OpenAI Realtime -------------------------------------------------------------

def openai(**kw):
    ws = FakeWS()
    col = Coletor()
    tr = Transporte(ws)
    m = dc.MotorOpenAIRealtime(col, dict(CONF), chave=CHAVE, transporte=tr, **kw)
    return m, ws, col, tr


def test_realtime_sessao_url_e_cabecalho():
    m, ws, col, tr = openai()
    m.iniciar("seja breve", [FERRAMENTA])
    esperar_ate(lambda: ws.enviados)
    url, cab = tr.chamadas[0]
    assert url == "wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1-mini"
    assert cab == ["Authorization: Bearer " + CHAVE] and CHAVE not in url
    s = ws.enviados[0]["session"]
    assert s["type"] == "realtime" and s["output_modalities"] == ["audio"]
    assert s["audio"]["input"]["turn_detection"] is None
    assert s["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert s["audio"]["output"]["voice"] == "cedar"
    assert s["tools"] == [dict(FERRAMENTA, type="function")]
    m.encerrar()


def test_realtime_reamostra_16k_para_24k():
    saida = dc.reamostrar_16k_para_24k(PCM)
    assert len(saida) == len(PCM) * 3 // 2
    m, ws, col, _ = openai()
    m.iniciar("x", [])
    m.enviar_audio(PCM)
    esperar_ate(lambda: len(ws.enviados) >= 2)
    assert base64.b64decode(ws.enviados[1]["audio"]) == saida
    m.encerrar()


def test_realtime_vez_e_eventos(gasto):
    m, ws, col, _ = openai()
    m.iniciar("x", [])
    m.fim_da_vez()
    esperar_ate(lambda: len(ws.enviados) >= 3)
    assert ws.tipos()[1:3] == ["input_audio_buffer.commit", "response.create"]
    pcm = b"\x05\x00" * 240
    ws.servidor({"type": "response.output_audio.delta", "item_id": "it1",
                 "delta": base64.b64encode(pcm).decode()})
    ws.servidor({"type": "response.output_audio_transcript.done", "transcript": "Claro!"})
    ws.servidor({"type": "response.done", "response": {"status": "completed", "usage": {
        "input_tokens": 1000, "output_tokens": 500, "input_token_details": {"cached_tokens": 200}}}})
    assert col.esperar(dc.AudioSaida)[0].pcm == pcm
    assert col.esperar(dc.TextoSaida)[0].texto == "Claro!"
    col.esperar(dc.FimResposta)
    esperado = 800 * 10e-6 + 200 * 0.30e-6 + 500 * 20e-6
    assert gasto[0][0] == "conversa" and gasto[0][1] == pytest.approx(esperado)
    assert gasto[0][2] == "openai_realtime 1500tok"
    m.encerrar()


def test_realtime_interromper_cancela_trunca_e_descarta():
    m, ws, col, _ = openai()
    m.iniciar("x", [])
    ws.servidor({"type": "response.output_audio.delta", "item_id": "it1",
                 "delta": base64.b64encode(b"\x00\x00" * 2400).decode()})      # 100 ms
    col.esperar(dc.AudioSaida)
    m.enviar_audio(PCM)
    m.interromper()
    esperar_ate(lambda: "input_audio_buffer.clear" in ws.tipos())
    t = ws.tipos()
    assert t.index("response.cancel") < t.index("conversation.item.truncate")
    trunc = [e for e in ws.enviados if e.get("type") == "conversation.item.truncate"][0]
    assert trunc["item_id"] == "it1" and trunc["audio_end_ms"] == 100
    ws.servidor({"type": "response.output_audio.delta", "item_id": "it1",
                 "delta": base64.b64encode(b"\x00\x00" * 10).decode()})
    ws.servidor({"type": "response.done", "response": {"status": "cancelled"}})
    time.sleep(0.15)
    assert len(col.de(dc.AudioSaida)) == 1 and not col.de(dc.FimResposta)
    m.encerrar()


def test_realtime_ferramenta_ida_e_volta():
    m, ws, col, _ = openai()
    m.iniciar("x", [FERRAMENTA])
    ws.servidor({"type": "response.function_call_arguments.done", "call_id": "k1",
                 "name": "fazer", "arguments": '{"pedido": "hora"}'})
    c = col.esperar(dc.ChamadaFerramenta)[0]
    assert (c.id, c.nome, c.args) == ("k1", "fazer", {"pedido": "hora"})
    m.responder_ferramenta("k1", {"hora": "10:00"})
    esperar_ate(lambda: ws.tipos().count("response.create") == 1)
    item = [e for e in ws.enviados if e.get("type") == "conversation.item.create"][0]["item"]
    assert item["type"] == "function_call_output" and item["call_id"] == "k1"
    assert json.loads(item["output"]) == {"hora": "10:00"}
    m.encerrar()


@pytest.mark.parametrize("codigo,tipo", [("rate_limit_exceeded", "limite"),
                                         ("insufficient_quota", "limite"),
                                         ("invalid_api_key", "chave"), ("server_error", "outro")])
def test_realtime_erro_do_servidor(codigo, tipo):
    m, ws, col, _ = openai()
    m.iniciar("x", [])
    ws.servidor({"type": "error", "error": {"code": codigo, "type": codigo,
                                            "message": "texto bruto " + CHAVE}})
    e = col.esperar(dc.Erro)[0]
    assert e.tipo == tipo and CHAVE not in e.msg


# --- Cascata (servidor HTTP local) -------------------------------------------------

class ServidorFalso:
    def __init__(self):
        self.pedidos = []
        self.groq = (200, {"text": "que horas são"})
        self.cerebro = ["Agora são ", "dez horas. ", "Posso ajudar em mais algo?"]
        self.tts_gemini = (200, [b"\x01\x00" * 2400])
        self.tts_openai = (200, b"\x02\x00" * 4800)
        yo = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _resp(self, codigo, corpo, tipo="application/json"):
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(n)
                yo.pedidos.append((self.path, {k.lower(): v for k, v in self.headers.items()}, corpo))
                if self.path.startswith("/groq"):
                    cod, obj = yo.groq
                    return self._resp(cod, json.dumps(obj).encode())
                if "streamGenerateContent" in self.path:
                    cod, blocos = yo.tts_gemini
                    if cod != 200:
                        return self._resp(cod, b'{"error":{"status":"RESOURCE_EXHAUSTED"}}')
                    sse = b"".join(b"data: " + json.dumps({"candidates": [{"content": {"parts": [
                        {"inlineData": {"mimeType": "audio/L16;rate=24000",
                                        "data": base64.b64encode(b).decode()}}]}}]}).encode() + b"\n\n"
                                   for b in blocos)
                    return self._resp(200, sse, "text/event-stream")
                if self.path.endswith("/chat/completions"):
                    sse = b"".join(b"data: " + json.dumps({"choices": [{"delta": {"content": p}}]}).encode()
                                   + b"\n\n" for p in yo.cerebro)
                    sse += (b"data: " + json.dumps({"choices": [], "usage": {
                        "prompt_tokens": 10, "completion_tokens": 5}}).encode() + b"\n\ndata: [DONE]\n\n")
                    return self._resp(200, sse, "text/event-stream")
                if self.path.endswith("/audio/speech"):
                    cod, dados = yo.tts_openai
                    return self._resp(cod, dados if cod == 200 else b"{}", "application/octet-stream")
                self._resp(404, b"{}")

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def srv():
    s = ServidorFalso()
    yield s
    s.fechar()


def cascata(srv, **kw):
    col = Coletor()
    m = dc.MotorCascata(col, dict(CONF, stt_dica_vocabulario="DICA DERVS"),
                        chave_groq=CHAVE, chave_gemini=CHAVE + "g", chave_openai=CHAVE + "o",
                        url_groq=srv.base + "/groq", url_gemini=srv.base + "/gemini",
                        url_openai=srv.base + "/openai", **kw)
    return m, col


def fala(m, col, segundos=1.0):
    m.iniciar("seja breve", [FERRAMENTA])
    m.enviar_audio(b"\x01\x00" * int(16000 * segundos))
    m.fim_da_vez()


def test_cascata_turno_completo(srv, gasto):
    m, col = cascata(srv)
    fala(m, col)
    col.esperar(dc.FimResposta)
    assert col.de(dc.TextoEntrada)[0].texto == "que horas são"
    assert [t.texto for t in col.de(dc.TextoSaida)] == ["Agora são dez horas.", "Posso ajudar em mais algo?"]
    assert len(col.de(dc.AudioSaida)) == 2 and col.de(dc.AudioSaida)[0].taxa == 24000
    # Groq: parâmetros e cabeçalhos
    p = [x for x in srv.pedidos if x[0].startswith("/groq")][0]
    assert b"whisper-large-v3-turbo" in p[2] and b"DICA DERVS" in p[2] and b'name="language"' in p[2]
    assert p[1]["authorization"] == "Bearer " + CHAVE and "dervs" in p[1]["user-agent"]
    # chave do Gemini no cabeçalho, nunca na URL
    g = [x for x in srv.pedidos if "streamGenerateContent" in x[0]][0]
    assert CHAVE not in g[0] and g[1]["x-goog-api-key"] == CHAVE + "g"
    # gasto: só o Groq tem valor (> 0); cérebro vai pelo registrador de cérebro
    groq = [x for x in gasto if x[2].startswith("cascata groq")]
    assert groq and groq[0][1] == pytest.approx(1.0 / 3600 * 0.04)
    m.encerrar()


def test_cascata_gemini_tts_com_limite_cai_no_openai_pcm(srv, gasto):
    srv.tts_gemini = (429, [])
    m, col = cascata(srv)
    fala(m, col)
    col.esperar(dc.FimResposta)
    assert not col.de(dc.Erro)
    corpo = json.loads([x for x in srv.pedidos if x[0].endswith("/audio/speech")][0][2])
    assert corpo["response_format"] == "pcm" and corpo["model"] == "gpt-4o-mini-tts"
    assert sum(len(a.pcm) for a in col.de(dc.AudioSaida)) == 2 * 9600
    tts = [x for x in gasto if x[2].startswith("cascata tts")]
    assert tts and tts[0][1] == pytest.approx(dervs_gasto.usd_voz(0.2))
    # depois do 429 a segunda frase nem tenta o Gemini de novo (60 s de pausa)
    assert len([x for x in srv.pedidos if "streamGenerateContent" in x[0]]) == 1
    m.encerrar()


def test_cascata_sem_teto_nao_chama_openai_tts(srv, monkeypatch):
    srv.tts_gemini = (429, [])
    monkeypatch.setattr(dervs_gasto, "pode_gastar", lambda conf=None: (False, "teto"))
    m, col = cascata(srv)
    fala(m, col)
    assert col.esperar(dc.Erro)[0].tipo == "limite"
    assert not [x for x in srv.pedidos if x[0].endswith("/audio/speech")]
    m.encerrar()


def test_cascata_groq_429_vira_erro_limite(srv):
    srv.groq = (429, {"error": "rate"})
    m, col = cascata(srv)
    fala(m, col)
    e = col.esperar(dc.Erro)[0]
    assert e.tipo == "limite" and CHAVE not in e.msg
    m.encerrar()


def test_cascata_groq_401_vira_erro_chave(srv):
    srv.groq = (401, {"error": "x"})
    m, col = cascata(srv)
    fala(m, col)
    assert col.esperar(dc.Erro)[0].tipo == "chave"
    m.encerrar()


def test_cascata_servidor_fora_vira_rede(srv):
    m, col = cascata(srv)
    m._urls["groq"] = "http://127.0.0.1:1/groq"
    fala(m, col)
    assert col.esperar(dc.Erro)[0].tipo == "rede"
    m.encerrar()


def test_cascata_ferramenta_por_linha_json(srv):
    srv.cerebro = ['{"ferramenta": "fazer", ', '"args": {"pedido": "abre o chrome"}}']
    m, col = cascata(srv)
    fala(m, col)
    col.esperar(dc.FimResposta)
    c = col.de(dc.ChamadaFerramenta)[0]
    assert (c.nome, c.args) == ("fazer", {"pedido": "abre o chrome"}) and c.id
    assert not col.de(dc.TextoSaida) and not col.de(dc.AudioSaida)
    m.encerrar()


def test_cascata_cerebro_injetado_recebe_texto_e_historico(srv):
    vistos = []

    def cerebro(texto, historico):
        vistos.append((texto, list(historico)))
        yield "Resposta curta."

    m, col = cascata(srv, cerebro=cerebro)
    m.iniciar("x", [], contexto=[("user", "oi"), ("model", "olá")])
    m.enviar_audio(b"\x01\x00" * 16000)
    m.fim_da_vez()
    col.esperar(dc.FimResposta)
    assert vistos == [("que horas são", [{"role": "user", "content": "oi"},
                                          {"role": "assistant", "content": "olá"}])]
    assert not [x for x in srv.pedidos if x[0].endswith("/chat/completions")]
    m.encerrar()


def test_cascata_interromper_cala_o_turno_velho(srv):
    liberar = threading.Event()

    def cerebro(texto, historico):
        yield "Primeira frase. "
        liberar.wait(3)
        yield "Segunda frase."

    m, col = cascata(srv, cerebro=cerebro)
    fala(m, col)
    col.esperar(dc.AudioSaida)
    m.interromper()
    liberar.set()
    time.sleep(0.3)
    assert len(col.de(dc.AudioSaida)) == 1 and not col.de(dc.FimResposta)
    m.encerrar()


def test_cascata_silencio_curto_nao_chama_groq(srv):
    m, col = cascata(srv)
    m.iniciar("x", [])
    m.enviar_audio(b"\x00\x00" * 100)
    m.fim_da_vez()
    col.esperar(dc.FimResposta)
    assert not srv.pedidos
    m.encerrar()


# --- orquestrador ---------------------------------------------------------------------

class MotorFalso(dc.MotorConversa):
    def __init__(self, nome, callback, log):
        super().__init__(callback)
        self.nome = nome
        self.log = log
        self.contexto = None

    def iniciar(self, instrucoes, ferramentas, contexto=None):
        self.contexto = contexto
        self.log.append((self.nome, "iniciar", instrucoes))

    def enviar_audio(self, pcm):
        self.log.append((self.nome, "audio", len(pcm)))

    def fim_da_vez(self):
        self.log.append((self.nome, "fim_da_vez"))

    def interromper(self):
        self.log.append((self.nome, "interromper"))

    def responder_ferramenta(self, id_, resultado):
        self.log.append((self.nome, "ferramenta", id_))

    def encerrar(self):
        self.log.append((self.nome, "encerrar"))


def conversa(ordem=("gemini_live", "cascata"), pode=lambda: (True, "")):
    col, log, motores = Coletor(), [], {}

    def fabrica(nome, cb, conf):
        motores[nome] = MotorFalso(nome, cb, log)
        return motores[nome]

    c = dc.Conversa(col, motores_ordem=list(ordem), fabrica=fabrica, conf=dict(CONF), pode_gastar=pode)
    return c, col, log, motores


@pytest.mark.parametrize("tipo", ["limite", "rede", "chave"])
def test_conversa_troca_no_erro_e_mantem_contexto(tipo):
    c, col, log, mot = conversa()
    c.iniciar("instr", [])
    assert c.motor_ativo == "gemini_live"
    g = mot["gemini_live"]
    g._callback(dc.TextoEntrada("que horas são"))
    g._callback(dc.TextoSaida("São dez "))
    g._callback(dc.TextoSaida("horas."))
    g._callback(dc.FimResposta())
    g._callback(dc.Erro(tipo, "x"))
    assert c.motor_ativo == "cascata"
    troca = col.de(dc.Troca)[0]
    assert (troca.de, troca.para, troca.motivo) == ("gemini_live", "cascata", tipo)
    assert mot["cascata"].contexto == [("user", "que horas são"), ("model", "São dez horas.")]
    assert ("gemini_live", "encerrar") in log
    assert not col.de(dc.Erro)                      # o erro foi absorvido pela troca


def test_conversa_so_guarda_as_ultimas_6_falas():
    c, col, log, mot = conversa()
    c.iniciar("i", [])
    g = mot["gemini_live"]
    for i in range(5):
        g._callback(dc.TextoEntrada("p%d" % i))
        g._callback(dc.TextoSaida("r%d" % i))
        g._callback(dc.FimResposta())
    g._callback(dc.Erro("limite", "x"))
    ctx = mot["cascata"].contexto
    assert len(ctx) == 6 and ctx[0] == ("user", "p2") and ctx[-1] == ("model", "r4")


def test_conversa_ultimo_motor_falhando_repassa_o_erro():
    c, col, log, mot = conversa()
    c.iniciar("i", [])
    mot["gemini_live"]._callback(dc.Erro("limite", "x"))
    mot["cascata"]._callback(dc.Erro("rede", "y"))
    assert col.de(dc.Erro)[0].tipo == "rede"


def test_conversa_erro_outro_nao_troca():
    c, col, log, mot = conversa()
    c.iniciar("i", [])
    mot["gemini_live"]._callback(dc.Erro("outro", "z"))
    assert c.motor_ativo == "gemini_live" and col.de(dc.Erro)[0].tipo == "outro"


def test_conversa_ignora_evento_de_motor_antigo():
    c, col, log, mot = conversa()
    c.iniciar("i", [])
    velho = mot["gemini_live"]
    velho._callback(dc.Erro("limite", "x"))
    velho._callback(dc.TextoSaida("fantasma"))
    assert not col.de(dc.TextoSaida)


def test_conversa_teto_estourado_pula_motor_pago():
    c, col, log, mot = conversa(ordem=("cascata", "gemini_live"), pode=lambda: (False, "teto"))
    c.iniciar("i", [])
    assert c.motor_ativo == "gemini_live" and "cascata" not in mot


def test_conversa_sem_motor_disponivel_avisa():
    c, col, log, mot = conversa(ordem=("cascata",), pode=lambda: (False, "teto"))
    c.iniciar("i", [])
    assert col.de(dc.Erro)[0].tipo == "limite"


def test_conversa_teto_estoura_no_meio_troca_apos_a_resposta():
    estado = {"ok": True}
    c, col, log, mot = conversa(ordem=("cascata", "gemini_live"), pode=lambda: (estado["ok"], ""))
    c.iniciar("i", [])
    estado["ok"] = False
    mot["cascata"]._callback(dc.FimResposta())
    assert c.motor_ativo == "gemini_live"
    assert col.de(dc.Troca)[0].motivo == "gasto" and col.de(dc.FimResposta)


def test_conversa_refaz_o_turno_em_andamento_no_motor_novo():
    c, col, log, mot = conversa()
    c.iniciar("i", [])
    c.enviar_audio(PCM)
    c.fim_da_vez()
    mot["gemini_live"]._callback(dc.Erro("limite", "x"))
    novo = [x for x in log if x[0] == "cascata"]
    assert ("cascata", "audio", len(PCM)) in novo and ("cascata", "fim_da_vez") in novo


def test_conversa_delega_o_contrato():
    c, col, log, mot = conversa()
    c.iniciar("i", [])
    c.enviar_audio(PCM)
    c.interromper()
    c.responder_ferramenta("k", {"ok": 1})
    c.encerrar()
    assert [x[1] for x in log if x[0] == "gemini_live"] == [
        "iniciar", "audio", "interromper", "ferramenta", "encerrar"]


def test_conversa_integrada_gemini_com_limite_cai_na_cascata(srv):
    """Ponta a ponta com motores reais: Gemini devolve 429 na conexão, cascata responde."""
    ws_cota = Transporte(falha=ErroComStatus(429))
    col = Coletor()

    def fabrica(nome, cb, conf):
        if nome == "gemini_live":
            return dc.MotorGeminiLive(cb, conf, chave=CHAVE, transporte=ws_cota)
        return dc.MotorCascata(cb, dict(conf, stt_dica_vocabulario="d"), chave_groq=CHAVE,
                               chave_gemini=CHAVE, chave_openai=CHAVE, url_groq=srv.base + "/groq",
                               url_gemini=srv.base + "/gemini", url_openai=srv.base + "/openai")

    c = dc.Conversa(col, motores_ordem=["gemini_live", "cascata"], fabrica=fabrica,
                    conf=dict(CONF), pode_gastar=lambda: (True, ""))
    c.iniciar("i", [])
    c.enviar_audio(b"\x01\x00" * 16000)
    c.fim_da_vez()
    col.esperar(dc.FimResposta)
    assert [(t.de, t.para) for t in col.de(dc.Troca)] == [("gemini_live", "cascata")]
    assert col.de(dc.AudioSaida) and col.de(dc.TextoSaida)
    c.encerrar()


# --- config ---------------------------------------------------------------------------

def test_config_padrao_da_conversa():
    assert dervs_config.PADRAO["conversa_motores"] == ["gemini_live", "cascata"]
    assert dervs_config.PADRAO["voz_gemini"] == "Charon"
    assert dervs_config.PADRAO["conversa_realtime_modelo"] == "gpt-realtime-2.1-mini"
    assert dervs_config.PADRAO["voz_realtime"] == "cedar"


@pytest.mark.parametrize("campo,ruim", [
    ("conversa_motores", "gemini_live"), ("conversa_motores", []), ("conversa_motores", ["xyz"]),
    ("voz_gemini", 5), ("voz_gemini", "Char on; rm"), ("voz_gemini", ""),
    ("conversa_realtime_modelo", ""), ("conversa_realtime_modelo", None),
    ("voz_realtime", "fable"), ("voz_realtime", 3)])
def test_config_valor_torto_volta_ao_padrao(campo, ruim, monkeypatch, tmp_path):
    arq = tmp_path / "config.json"
    arq.write_text(json.dumps({campo: ruim}), encoding="utf-8")
    monkeypatch.setattr(dervs_config, "CONFIG_PATH", str(arq))
    assert dervs_config.carregar()[campo] == dervs_config.PADRAO[campo]


def test_config_motores_filtra_e_remove_repetidos(monkeypatch, tmp_path):
    arq = tmp_path / "config.json"
    arq.write_text(json.dumps({"conversa_motores": ["cascata", "xyz", "cascata", "openai_realtime"],
                               "voz_gemini": "Kore", "voz_realtime": "marin"}), encoding="utf-8")
    monkeypatch.setattr(dervs_config, "CONFIG_PATH", str(arq))
    c = dervs_config.carregar()
    assert c["conversa_motores"] == ["cascata", "openai_realtime"]
    assert c["voz_gemini"] == "Kore" and c["voz_realtime"] == "marin"
