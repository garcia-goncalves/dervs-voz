"""Testes da sessão do Claude Code (`dervs_claude_code.py`, onda B).

TUDO com cliente falso: nenhum teste aqui abre rede, roda o `claude` de verdade
ou gasta a assinatura do dono. O cliente falso imita o que importa do
`ClaudeSDKClient` (connect/query/receive_response/interrupt/disconnect) e cospe
mensagens REAIS do SDK (StreamEvent, AssistantMessage, ResultMessage...), então
o roteamento por tipo é exercitado de verdade.
"""
import asyncio
import inspect
import json
import os
import threading
import time
import types

import pytest

import dervs_claude_code as cc
import dervs_gasto

pytestmark = pytest.mark.skipif(cc.sdk is None, reason="claude-agent-sdk não instalado")

sdk = cc.sdk


# --- as travas ---------------------------------------------------------------

def test_o_modo_de_permissao_e_default_e_nunca_um_dos_proibidos():
    """Se alguém trocar por bypassPermissions/acceptEdits/auto, isto falha."""
    assert cc.PERMISSION_MODE == "default"
    assert cc.PERMISSION_MODE not in ("bypassPermissions", "acceptEdits", "auto")
    for proibido in ("bypassPermissions", "acceptEdits", "auto"):
        assert proibido in cc.MODOS_PROIBIDOS
    fonte = inspect.getsource(cc)
    assert "set_permission_mode" not in fonte, "o modo nunca muda depois de aberta a sessão"
    for perfil in ("dono", "equipe"):
        assert _opcoes(perfil).permission_mode == "default"


def _opcoes(perfil="dono", **extra):
    sessao = cc.SessaoClaudeCode(lambda v, d: None, perfil=perfil, arquivo_sessao=None,
                                 arquivo_propostas=None)
    servidor, _ = cc.criar_servidor_dervs(sessao)
    return cc.montar_opcoes(perfil, can_use_tool=sessao._can_use_tool,
                            gancho=cc.criar_gancho(), servidor_mcp=servidor,
                            cli_path="claude", **extra)


def test_fontes_de_configuracao_por_perfil():
    assert _opcoes("dono").setting_sources == ["user", "project", "local"]
    assert _opcoes("equipe").setting_sources == ["project"]
    assert _opcoes("perfil-inventado").setting_sources == ["project"], "desconhecido = o menor"


def test_opcoes_da_sessao():
    o = _opcoes("dono", resume="abc12345-def")
    assert o.include_partial_messages is True
    assert o.resume == "abc12345-def"
    assert o.can_use_tool is not None
    assert list(o.hooks) == ["PreToolUse"]
    assert set(o.mcp_servers) == {"dervs"}
    assert o.cli_path == "claude"
    if os.name == "nt":
        assert o.add_dirs and o.add_dirs[0].endswith("\\")
    assert "mcp__dervs__propor_acao" in o.allowed_tools
    assert all("Bash" != t for t in o.allowed_tools), "nada de comando liberado sem perguntar"


# --- caminhos protegidos ---------------------------------------------------------

@pytest.mark.parametrize("caminho", [
    r"C:\Windows\System32\drivers\etc\hosts", r"c:\windows", r"C:\Program Files\App\a.dll",
    r"C:\Program Files (x86)\App", r"C:\Users\x\projeto\.git\config",
    r"C:\Users\x\projeto\.claude\settings.json", r"~/.ssh/id_ed25519", ".git/HEAD",
])
def test_caminhos_protegidos(caminho):
    assert cc.esta_protegido(caminho) is True


@pytest.mark.parametrize("caminho", [
    r"C:\Users\x\Documents\a.txt", r"C:\Windowsfoo\a.txt", r"D:\dados\relatorio.md",
    r"C:\Users\x\projeto\.gitignore",
])
def test_caminhos_comuns_nao_sao_protegidos(caminho):
    assert cc.esta_protegido(caminho) is False


def test_veredito_da_onda_c_soma_ao_piso_interno(monkeypatch):
    monkeypatch.setattr(cc, "_protegido_da_onda_c", lambda c: c.endswith("segredo.txt"))
    assert cc.esta_protegido(r"C:\Users\x\segredo.txt") is True
    assert cc.esta_protegido(r"C:\Windows\x") is True
    assert cc.esta_protegido(r"C:\Users\x\ok.txt") is False


def test_motor_da_onda_c_quebrado_fecha_em_vez_de_abrir(monkeypatch):
    def _quebra(c):
        raise RuntimeError("boom")
    monkeypatch.setattr(cc, "_protegido_da_onda_c", _quebra)
    assert cc.esta_protegido(r"C:\Users\x\ok.txt") is True


# --- o gancho PreToolUse ------------------------------------------------------------

def _gancho(nome, entrada, protegido=cc.esta_protegido):
    g = cc.criar_gancho(protegido)
    return asyncio.run(g({"tool_name": nome, "tool_input": entrada}, "id1", None))


def _negou(saida):
    h = saida.get("hookSpecificOutput", {})
    return h.get("permissionDecision") == "deny", h.get("permissionDecisionReason", "")


def test_gancho_deixa_passar_comando_inofensivo():
    assert _gancho("Bash", {"command": "dir C:\\Users"}) == {}
    assert _gancho("PowerShell", {"command": "Get-Date"}) == {}


def test_gancho_nega_comando_destrutivo_e_manda_usar_propor_acao():
    negou, motivo = _negou(_gancho("PowerShell",
                                   {"command": r"Remove-Item C:\Users\x\Docs -Recurse -Force"}))
    assert negou
    assert "mcp__dervs__propor_acao" in motivo


def test_gancho_nega_segredo_e_rede_alvo():
    assert _negou(_gancho("Bash", {"command": "type C:\\Users\\x\\.env"}))[0]
    assert _negou(_gancho("Bash", {"command": "nmap -sV 8.8.8.8"}))[0]


def test_gancho_nega_comando_que_muda_algo_em_pasta_protegida():
    negou, motivo = _negou(_gancho("PowerShell",
                                   {"command": r"Set-Content C:\Windows\hosts2 'x'"}))
    assert negou and "protegido" in motivo


def test_gancho_deixa_ler_pasta_protegida():
    assert _gancho("Bash", {"command": r"dir C:\Windows"}) == {}


def test_gancho_nega_escrita_em_caminho_protegido_e_sem_caminho():
    for nome in ("Edit", "Write", "MultiEdit"):
        assert _negou(_gancho(nome, {"file_path": r"C:\Windows\a.txt"}))[0]
        assert _negou(_gancho(nome, {"file_path": r"C:\proj\.git\config"}))[0]
    assert _negou(_gancho("Write", {"content": "x"}))[0], "sem caminho = nega"
    assert _gancho("Write", {"file_path": r"C:\Users\x\Docs\ok.txt"}) == {}


def test_gancho_usa_a_funcao_de_protegidos_injetada():
    proibe_tudo = lambda c: True
    assert _negou(_gancho("Write", {"file_path": r"C:\a.txt"}, proibe_tudo))[0]


def test_gancho_falha_fechada(monkeypatch):
    def _quebra(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(cc, "motivo_de_bloqueio", _quebra)
    assert _negou(_gancho("Bash", {"command": "dir"}))[0]


def test_gancho_so_e_registrado_nas_ferramentas_que_mexem():
    matcher = _opcoes().hooks["PreToolUse"][0].matcher
    for nome in ("Bash", "PowerShell", "Edit", "Write"):
        assert nome in matcher.split("|")
    assert "Read" not in matcher.split("|")


# --- a sessão, com cliente falso -----------------------------------------------------

def _resultado(custo=0.02, sid="sessao-1234567890", texto="Resposta final. Segunda frase.",
               erro=False, sub="success"):
    return sdk.ResultMessage(subtype=sub, duration_ms=1, duration_api_ms=1, is_error=erro,
                             num_turns=1, session_id=sid, total_cost_usd=custo, result=texto)


def _delta(texto):
    return sdk.StreamEvent(uuid="u", session_id="s", event={
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "text_delta", "text": texto}})


def _msg_inicio():
    return sdk.StreamEvent(uuid="u", session_id="s", event={"type": "message_start"})


def _assistente(*blocos):
    return sdk.AssistantMessage(content=list(blocos), model="m")


class ClienteFalso:
    def __init__(self, opcoes, roteiro):
        self.opcoes = opcoes
        self._roteiro = roteiro
        self.consultas = []
        self.interrompido = threading.Event()
        self.desconectado = False
        self.conectou = False
        self.processo = types.SimpleNamespace(pid=4242, returncode=None,
                                              kill=lambda: None)
        self._transport = types.SimpleNamespace(_process=self.processo)

    async def connect(self):
        self.conectou = True

    async def query(self, texto):
        self.consultas.append(texto)

    async def receive_response(self):
        async for m in self._roteiro(self):
            yield m

    async def interrupt(self):
        self.interrompido.set()

    async def disconnect(self):
        self.desconectado = True


class Cena:
    """Sessão + cliente falso + coletor de eventos."""

    def __init__(self, tmp_path, roteiro, **kw):
        self.eventos = []
        self.finais = []
        self.avisos = []
        self.clientes = []

        def _fabrica(opcoes):
            c = ClienteFalso(opcoes, roteiro)
            self.clientes.append(c)
            return c

        kw.setdefault("arquivo_sessao", str(tmp_path / "claude_sessao.json"))
        kw.setdefault("arquivo_propostas", str(tmp_path / "propostas.jsonl"))
        self.sessao = cc.SessaoClaudeCode(
            lambda v, d: self.eventos.append((v, d)),
            ao_texto_final=lambda t, o: self.finais.append((t, o)),
            ao_aviso=self.avisos.append, fabrica_cliente=_fabrica, **kw)

    def perguntar(self, texto="oi", origem="painel"):
        assert self.sessao.perguntar(texto, origem)
        assert self.sessao.aguardar_ocioso(10), "o turno não terminou"

    def verbos(self, verbo):
        return [d for v, d in self.eventos if v == verbo]

    def fechar(self):
        self.sessao.encerrar()


@pytest.fixture
def gasto(tmp_path, monkeypatch):
    arq = tmp_path / "gasto.jsonl"
    monkeypatch.setenv("DERVS_GASTO_ARQUIVO", str(arq))
    return arq


async def _roteiro_simples(c):
    yield _msg_inicio()
    yield _delta("Olá, ")
    yield _delta("mundo.")
    yield _assistente(sdk.TextBlock(text="Olá, mundo."))
    yield _resultado()


def test_turno_completo_streaming_ferramenta_fim_e_texto_final(tmp_path, gasto):
    async def roteiro(c):
        yield _msg_inicio()
        yield _delta("Vou olhar. ")
        yield _assistente(sdk.TextBlock(text="Vou olhar. "),
                          sdk.ToolUseBlock(id="t1", name="Bash", input={"command": "dir C:\\"}))
        yield _msg_inicio()
        yield _delta("Achei tudo.")
        yield _assistente(sdk.TextBlock(text="Achei tudo."))
        yield _resultado(texto="Achei tudo.")

    cena = Cena(tmp_path, roteiro)
    try:
        cena.perguntar("olha o disco", origem="voz")
    finally:
        cena.fechar()
    deltas = [d["texto"] for d in cena.verbos("claude_delta")]
    assert deltas == ["Vou olhar. ", "\n\nAchei tudo."], "texto duplicado ou sem separador"
    assert cena.verbos("claude_ferramenta") == [{"nome": "Bash", "resumo": "dir C:\\"}]
    fim = cena.verbos("claude_fim")
    assert len(fim) == 1 and fim[0]["ok"] is True and fim[0]["erro"] is None
    assert fim[0]["custo"] == pytest.approx(0.02)
    assert cena.finais == [("Achei tudo.", "voz")]
    assert cena.clientes[0].consultas == ["olha o disco"]


def test_sem_streaming_o_texto_do_assistente_vira_delta(tmp_path, gasto):
    async def roteiro(c):
        yield _assistente(sdk.TextBlock(text="Sem streaming."))
        yield _resultado(texto="Sem streaming.")

    cena = Cena(tmp_path, roteiro)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    assert [d["texto"] for d in cena.verbos("claude_delta")] == ["Sem streaming."]


def test_segunda_pergunta_reusa_o_mesmo_cliente(tmp_path, gasto):
    cena = Cena(tmp_path, _roteiro_simples)
    try:
        cena.perguntar("um")
        cena.perguntar("dois")
    finally:
        cena.fechar()
    assert len(cena.clientes) == 1, "reconectou à toa"
    assert cena.clientes[0].consultas == ["um", "dois"]


def test_pergunta_vazia_ou_grande_demais_e_recusada(tmp_path):
    cena = Cena(tmp_path, _roteiro_simples)
    try:
        assert cena.sessao.perguntar("   ") is False
        assert cena.sessao.perguntar("x" * (cc.LIMITE_PERGUNTA + 1)) is False
        assert cena.sessao.perguntar("x" * cc.LIMITE_PERGUNTA) is True
        assert cena.sessao.aguardar_ocioso(10)
    finally:
        cena.fechar()


def test_pergunta_com_turno_em_andamento_e_recusada(tmp_path, gasto):
    solta = threading.Event()

    async def roteiro(c):
        while not solta.is_set():
            await asyncio.sleep(0.01)
        yield _resultado()

    cena = Cena(tmp_path, roteiro)
    try:
        assert cena.sessao.perguntar("primeira")
        assert cena.sessao.perguntar("segunda") is False
        solta.set()
        assert cena.sessao.aguardar_ocioso(10)
    finally:
        cena.fechar()


def test_session_id_e_gravado_e_a_proxima_abertura_retoma(tmp_path, gasto):
    cena = Cena(tmp_path, _roteiro_simples)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    salvo = json.loads((tmp_path / "claude_sessao.json").read_text(encoding="utf-8"))
    assert salvo["session_id"] == "sessao-1234567890" and salvo["perfil"] == "dono"
    assert cena.clientes[0].opcoes.resume is None

    outra = Cena(tmp_path, _roteiro_simples)          # "reabriu o app"
    try:
        outra.perguntar()
    finally:
        outra.fechar()
    assert outra.clientes[0].opcoes.resume == "sessao-1234567890"


def test_sessao_de_outro_perfil_ou_torta_nao_e_retomada(tmp_path):
    arq = tmp_path / "claude_sessao.json"
    cc.gravar_sessao(str(arq), "sessao-1234567890", "equipe")
    assert cc.ler_sessao(str(arq), "dono") is None
    arq.write_text("{isto nao e json", encoding="utf-8")
    assert cc.ler_sessao(str(arq), "dono") is None
    arq.write_text(json.dumps({"session_id": "; rm -rf /", "perfil": "dono"}), encoding="utf-8")
    assert cc.ler_sessao(str(arq), "dono") is None, "id fora do formato não vai para o --resume"


def test_nova_conversa_apaga_a_sessao_e_o_proximo_cliente_nasce_limpo(tmp_path, gasto):
    cena = Cena(tmp_path, _roteiro_simples)
    try:
        cena.perguntar()
        assert (tmp_path / "claude_sessao.json").exists()
        cena.sessao.nova_conversa()
        assert cena.sessao.aguardar_ocioso(10)
        assert not (tmp_path / "claude_sessao.json").exists()
        cena.perguntar()
    finally:
        cena.fechar()
    assert cena.clientes[0].desconectado is True
    assert len(cena.clientes) == 2
    assert cena.clientes[1].opcoes.resume is None


def test_custo_do_resultado_vai_para_o_gasto_com_a_etiqueta(tmp_path, gasto):
    async def roteiro(c):
        yield _resultado(custo=0.05)

    cena = Cena(tmp_path, roteiro)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    linhas = [json.loads(l) for l in gasto.read_text(encoding="utf-8").splitlines()]
    assert len(linhas) == 1
    assert linhas[0]["tipo"] == "claude"
    assert linhas[0]["detalhe"] == "assinatura (equivalente)"
    assert linhas[0]["usd"] == pytest.approx(0.05)


def test_custo_acumulado_do_sdk_vira_diferenca_por_turno(tmp_path, gasto):
    totais = iter([0.05, 0.08])

    async def roteiro(c):
        yield _resultado(custo=next(totais))

    cena = Cena(tmp_path, roteiro)
    try:
        cena.perguntar()
        cena.perguntar()
    finally:
        cena.fechar()
    custos = [d["custo"] for d in cena.verbos("claude_fim")]
    assert custos == [pytest.approx(0.05), pytest.approx(0.03)]
    usd = [json.loads(l)["usd"] for l in gasto.read_text(encoding="utf-8").splitlines()]
    assert usd == [pytest.approx(0.05), pytest.approx(0.03)]


def test_gasto_do_dia_nao_soma_o_equivalente_da_assinatura(tmp_path):
    arq = str(tmp_path / "g.jsonl")
    dervs_gasto.registrar("cerebro", 0.01, "gpt", caminho=arq)
    dervs_gasto.registrar("claude", 0.50, cc.ETIQUETA_GASTO, caminho=arq)
    assert dervs_gasto.total_do_dia(caminho=arq)["total"] == pytest.approx(0.01)


def test_erro_do_cliente_vira_fim_com_erro_e_o_proximo_turno_reconecta(tmp_path, gasto):
    chamadas = []

    async def roteiro(c):
        chamadas.append(1)
        if len(chamadas) == 1:
            raise ConnectionError("o CLI caiu")
        yield _resultado()
        return

    cena = Cena(tmp_path, roteiro)
    try:
        cena.perguntar()
        cena.perguntar()
    finally:
        cena.fechar()
    fim = cena.verbos("claude_fim")
    assert fim[0]["ok"] is False and "ConnectionError" in fim[0]["erro"]
    assert fim[1]["ok"] is True
    assert len(cena.clientes) == 2 and cena.clientes[0].desconectado


def test_resultado_com_erro_mostra_o_motivo(tmp_path, gasto):
    async def roteiro(c):
        yield _resultado(erro=True, texto="Credit balance too low", sub="success")

    cena = Cena(tmp_path, roteiro)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    fim = cena.verbos("claude_fim")[0]
    assert fim["ok"] is False and "Credit balance" in fim["erro"]
    assert cena.finais == []


def test_limite_do_plano_vira_aviso_com_a_hora(tmp_path, gasto):
    volta = time.mktime((2030, 1, 1, 14, 30, 0, 0, 0, -1))

    async def roteiro(c):
        yield sdk.RateLimitEvent(uuid="u", session_id="s", rate_limit_info=sdk.RateLimitInfo(
            status="rejected", resets_at=int(volta), rate_limit_type="five_hour"))
        yield _resultado()

    cena = Cena(tmp_path, roteiro)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    assert cena.avisos == ["Atingi o limite do plano, volta às 14:30."]


# --- permissão (can_use_tool) -----------------------------------------------------------

def _responder_quando_chegar(cena, permitir, origem="clique", **kw):
    """Thread que espera o `claude_pedido` e responde, como a ponte faria."""
    resultado = {}

    def _rodar():
        fim = time.time() + 10
        while time.time() < fim:
            pedidos = cena.verbos("claude_pedido")
            if pedidos:
                resultado["pedido"] = pedidos[0]
                resultado["aceito"] = cena.sessao.responder(
                    pedidos[0]["id"], permitir, origem=origem, **kw)
                return
            time.sleep(0.01)

    t = threading.Thread(target=_rodar, daemon=True)
    t.start()
    return t, resultado


def _roteiro_que_pede(comando, guardar):
    async def roteiro(c):
        r = await c.opcoes.can_use_tool("Bash", {"command": comando},
                                        sdk.ToolPermissionContext())
        guardar.append(r)
        yield _resultado()
    return roteiro


def test_pedido_de_permissao_permitido_pelo_clique(tmp_path, gasto):
    guardado = []
    cena = Cena(tmp_path, _roteiro_que_pede("pip install rich", guardado))
    t, r = _responder_quando_chegar(cena, True)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    t.join(2)
    p = r["pedido"]
    assert p["ferramenta"] == "Bash" and p["resumo"] == "pip install rich"
    assert p["nivel"] == "muda_estado"
    assert "pip install rich" in p["entrada_cortada"] and p["id"]
    assert isinstance(guardado[0], sdk.PermissionResultAllow)


def test_pedido_negado_pelo_clique(tmp_path, gasto):
    guardado = []
    cena = Cena(tmp_path, _roteiro_que_pede("pip install rich", guardado))
    t, _ = _responder_quando_chegar(cena, False)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    t.join(2)
    assert isinstance(guardado[0], sdk.PermissionResultDeny)


def test_pedido_sem_resposta_em_5_minutos_nega(tmp_path, gasto):
    """O prazo real é 300 s (constante); aqui se prova a lógica com prazo curto."""
    assert cc.TIMEOUT_PEDIDO_S == 300
    guardado = []
    cena = Cena(tmp_path, _roteiro_que_pede("pip install rich", guardado), timeout_pedido=0.2)
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    assert isinstance(guardado[0], sdk.PermissionResultDeny)


def test_voz_nao_aprova_pedido_que_muda_estado(tmp_path, gasto):
    guardado = []
    cena = Cena(tmp_path, _roteiro_que_pede("pip install rich", guardado), timeout_pedido=0.4)
    t, r = _responder_quando_chegar(cena, True, origem="voz")
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    t.join(2)
    assert r["aceito"] is False, "a voz aprovou algo que muda o estado"
    assert isinstance(guardado[0], sdk.PermissionResultDeny)


def test_voz_pode_negar_e_aprovar_o_que_e_so_leitura(tmp_path, gasto):
    guardado = []
    cena = Cena(tmp_path, _roteiro_que_pede("dir C:\\", guardado))
    t, r = _responder_quando_chegar(cena, True, origem="voz")
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    t.join(2)
    assert r["pedido"]["nivel"] == "reversivel" and r["aceito"] is True
    assert isinstance(guardado[0], sdk.PermissionResultAllow)


def test_resposta_duplicada_desconhecida_ou_com_cartao_errado_e_ignorada(tmp_path, gasto):
    guardado = []
    cena = Cena(tmp_path, _roteiro_que_pede("pip install rich", guardado))
    respostas = {}

    def _rodar():
        fim = time.time() + 10
        while time.time() < fim and not cena.verbos("claude_pedido"):
            time.sleep(0.01)
        id_ = cena.verbos("claude_pedido")[0]["id"]
        respostas["desconhecido"] = cena.sessao.responder("nao-existe", True)
        respostas["cartao_errado"] = cena.sessao.responder(id_, True, cartao_id="outro")
        respostas["nao_booleano"] = cena.sessao.responder(id_, "true")     # string não vale
        respostas["primeira"] = cena.sessao.responder(id_, True, cartao_id=id_)
        respostas["duplicada"] = cena.sessao.responder(id_, False)

    t = threading.Thread(target=_rodar, daemon=True)
    t.start()
    try:
        cena.perguntar()
    finally:
        cena.fechar()
    t.join(2)
    assert respostas == {"desconhecido": False, "cartao_errado": False, "nao_booleano": True,
                         "primeira": False, "duplicada": False}
    # "true" (string) NÃO é o booleano True: vira negação e consome o pedido.
    assert isinstance(guardado[0], sdk.PermissionResultDeny)


# --- interromper -----------------------------------------------------------------------------

def test_parar_interrompe_o_turno_pelo_cliente(tmp_path, gasto):
    async def roteiro(c):
        yield _delta("começando...")
        while not c.interrompido.is_set():
            await asyncio.sleep(0.01)
        yield _resultado(erro=True, texto="interrompido", sub="error_during_execution")

    cena = Cena(tmp_path, roteiro, espera_interrupt=5)
    mortes = []
    cena.sessao._encerrar_arvore = mortes.append
    try:
        assert cena.sessao.perguntar("longo")
        fim = time.time() + 5
        while time.time() < fim and not cena.verbos("claude_delta"):
            time.sleep(0.01)
        assert cena.sessao.parar() is True
        assert cena.sessao.aguardar_ocioso(10)
    finally:
        cena.fechar()
    fim_ev = cena.verbos("claude_fim")[0]
    assert fim_ev["ok"] is False and fim_ev["erro"] == "interrompido"
    assert cena.clientes[0].interrompido.is_set()
    assert mortes == [], "obedeceu em tempo: não pode matar processo"


def test_parar_sem_turno_nao_faz_nada(tmp_path):
    cena = Cena(tmp_path, _roteiro_simples)
    try:
        assert cena.sessao.parar() is False
    finally:
        cena.fechar()


def test_se_nao_obedecer_em_5s_mata_a_arvore_do_processo(tmp_path, gasto):
    parou = threading.Event()

    async def roteiro(c):
        # ignora o interrupt: só termina quando a árvore for morta
        while not parou.is_set():
            await asyncio.sleep(0.01)
        raise ConnectionError("processo morto")
        yield

    cena = Cena(tmp_path, roteiro, espera_interrupt=0.3)
    mortos = []

    def _matar(proc):
        mortos.append(proc.pid)
        parou.set()

    cena.sessao._encerrar_arvore = _matar
    try:
        assert cena.sessao.perguntar("trava")
        time.sleep(0.2)
        assert cena.sessao.parar()
        assert cena.sessao.aguardar_ocioso(10)
    finally:
        cena.fechar()
    assert mortos == [4242]
    assert cena.clientes[0].interrompido.is_set(), "tentou interromper antes de matar"
    assert cena.verbos("claude_fim")[0]["ok"] is False


def test_espera_padrao_do_interrupt_e_5_segundos():
    assert cc.ESPERA_INTERRUPT_S == 5


# --- o servidor MCP `dervs` ---------------------------------------------------------------------

def _ferramentas(tmp_path):
    eventos = []
    sessao = cc.SessaoClaudeCode(lambda v, d: eventos.append((v, d)), arquivo_sessao=None,
                                 arquivo_propostas=str(tmp_path / "prop.jsonl"))
    _, f = cc.criar_servidor_dervs(sessao)
    return sessao, f, eventos


def _texto(r):
    return r["content"][0]["text"]


def test_o_servidor_dervs_nao_tem_ferramenta_de_executar(tmp_path):
    _, f, _ = _ferramentas(tmp_path)
    assert set(f) == {"central_coletar", "propor_acao", "status_aprovacao"}


def test_central_coletar_e_um_stub_honesto(tmp_path):
    _, f, _ = _ferramentas(tmp_path)
    r = asyncio.run(f["central_coletar"].handler({"coletor": "temporarios"}))
    assert "ainda não instalado" in _texto(r)


def test_propor_acao_so_registra_e_avisa_o_painel(tmp_path):
    sessao, f, eventos = _ferramentas(tmp_path)
    itens = [{"acao": "lixeira", "alvo": r"C:\Users\x\AppData\Local\Temp\a.tmp",
              "o_que_e": "temporário", "por_que_seguro": "o Windows recria"}]
    r = asyncio.run(f["propor_acao"].handler({"itens": itens}))
    assert "NADA foi executado" in _texto(r) and not r.get("is_error")
    id_ = _texto(r).split()[1]
    assert sessao.estado_da_proposta(id_) == "pendente"
    linha = json.loads((tmp_path / "prop.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert linha["id"] == id_ and linha["itens"][0]["acao"] == "lixeira"
    assert eventos[0][0] == "claude_ferramenta" and eventos[0][1]["nome"] == "propor_acao"
    assert os.path.exists(itens[0]["alvo"]) is False        # nada foi tocado no disco


def test_propor_acao_nao_grava_segredo_no_log(tmp_path):
    _, f, _ = _ferramentas(tmp_path)
    asyncio.run(f["propor_acao"].handler({"itens": [{"acao": "lixeira",
                                                     "alvo": r"C:\Users\x\.ssh\id_rsa"}]}))
    bruto = (tmp_path / "prop.jsonl").read_text(encoding="utf-8")
    assert "id_rsa" not in bruto and "redigido" in bruto


@pytest.mark.parametrize("entrada", [{}, {"itens": []}, {"itens": "x"}, {"itens": ["a"]}])
def test_propor_acao_recusa_entrada_torta(tmp_path, entrada):
    _, f, _ = _ferramentas(tmp_path)
    r = asyncio.run(f["propor_acao"].handler(entrada))
    assert r.get("is_error") is True


def test_status_aprovacao(tmp_path):
    sessao, f, _ = _ferramentas(tmp_path)
    assert "Não conheço" in _texto(asyncio.run(
        f["status_aprovacao"].handler({"relatorio_id": "p-nada"})))
    id_ = sessao.registrar_proposta([{"acao": "lixeira"}])
    r = asyncio.run(f["status_aprovacao"].handler({"relatorio_id": id_}))
    assert "pendente" in _texto(r)


# --- voz -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("fala,esperado", [
    ("pede pro Claude analisar o disco", "analisar o disco"),
    ("Pede para o Claude olhar meu Downloads", "olhar meu Downloads"),
    ("DERVS, pergunta ao Claude por que o PC está lento", "por que o PC está lento"),
    ("manda o Claude revisar esse script", "revisar esse script"),
    ("Claude, resume a pasta de projetos", "resume a pasta de projetos"),
    ("analisa o uso de memória do meu PC", "analisa o uso de memória do meu PC"),
    ("verifica meu PC", "verifica meu PC"),
    ("Verifica o computador, por favor", "Verifica o computador, por favor"),
    ("investiga esse erro no log", "investiga esse erro no log"),
])
def test_frases_que_pedem_trabalho(fala, esperado):
    assert cc.frase_de_trabalho(fala) == esperado


@pytest.mark.parametrize("fala", [
    "que horas são", "abre o firefox", "verifica a hora", "analisa", "", "   ",
    "o Claude é uma boa ideia", "pede pizza", "me lembra em 10 minutos",
])
def test_frases_comuns_nao_viram_trabalho(fala):
    assert cc.frase_de_trabalho(fala) is None


@pytest.mark.parametrize("fala,eh", [
    ("para", True), ("Para!", True), ("DERVS, para", True), ("para tudo", True),
    ("cancela isso", True), ("para de tocar música", False), ("parabéns", False),
    ("abre o chrome", False),
])
def test_palavra_para(fala, eh):
    assert cc.eh_comando_parar(fala) is eh


def test_resumo_para_fala_tem_no_maximo_duas_frases_e_sem_markdown():
    texto = ("## Resultado\n\n**Achei** três coisas. A primeira é o `Temp` cheio. "
             "A segunda é o cache.\n\n- item um\n- item dois\n\n```\ncodigo grande\n```\n"
             "Veja [aqui](http://x.com) também.")
    fala = cc.resumir_para_fala(texto)
    assert fala == "Resultado Achei três coisas. A primeira é o Temp cheio."
    assert "*" not in fala and "`" not in fala and "#" not in fala


def test_resumo_para_fala_corta_frase_gigante_e_aceita_vazio():
    assert len(cc.resumir_para_fala("palavra " * 200)) <= 242
    assert cc.resumir_para_fala("") == ""
    assert cc.resumir_para_fala("```\nso codigo\n```") == ""
