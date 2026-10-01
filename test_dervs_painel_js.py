"""Roda os testes das funções puras do painel (JavaScript) com o Node.

Inclui `electron/janela-estado.test.js` (abrir/esconder/minimizar/fechar).

Formatação de dinheiro/rede/disco e a cadência da animação (10 quadros/s sem
foco) moram em `electron/renderer/painel-formato.js` e têm teste próprio no
formato `node --test`. Sem Node na máquina, o teste é pulado (não falha).
"""
import os
import shutil
import subprocess

import pytest

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "electron", "renderer")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node não instalado")
def test_funcoes_puras_do_painel_passam_no_node():
    janela_estado = os.path.join(os.path.dirname(PASTA), "janela-estado.test.js")
    r = subprocess.run(["node", "--test", PASTA, janela_estado], capture_output=True, text=True,
                       timeout=60, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-500:]


# --- Claude Code no painel (onda B): travas estáticas ---------------------------
# Não substituem olhar a tela, mas pegam as regressões que custam caro: texto do
# Claude entrando por innerHTML, console.log sujando o canal do protocolo, foco
# inicial em Permitir e a CSP afrouxada.

import re

RAIZ_ELECTRON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "electron")


def _fonte(*partes):
    with open(os.path.join(RAIZ_ELECTRON, *partes), encoding="utf-8") as f:
        return f.read()


def _sem_comentarios(js):
    return "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))


def test_main_js_nao_usa_console_log():
    """O stdout do Electron é o canal do protocolo; console.log o sujaria."""
    assert "console.log" not in _sem_comentarios(_fonte("main.js"))


@pytest.mark.parametrize("arquivo", [("renderer", "painel.js"), ("renderer", "painel-markdown.js"),
                                     ("renderer", "painel-integracao.js"),
                                     ("preload.js",), ("main.js",)])
def test_nada_do_claude_entra_por_innerhtml(arquivo):
    js = _sem_comentarios(_fonte(*arquivo))
    for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert proibido not in js, f"{proibido} em {'/'.join(arquivo)}"


def test_csp_do_painel_nao_mudou():
    html = _fonte("renderer", "painel.html")
    assert ("default-src 'none'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; font-src 'self'") in html


def test_dialogo_do_claude_nasce_com_foco_em_negar_nunca_em_permitir():
    html = _fonte("renderer", "painel.html")
    permitir = re.search(r'<button[^>]*id="claude-pedido-permitir"[^>]*>', html).group(0)
    negar = re.search(r'<button[^>]*id="claude-pedido-negar"[^>]*>', html).group(0)
    assert "autofocus" in negar and "autofocus" not in permitir
    js = _fonte("renderer", "painel.js")
    assert "botaoNegarClaude.focus()" in js
    assert "botaoPermitirClaude.focus()" not in js


def test_permitir_espera_um_atraso_a_cada_abertura_e_negar_nunca():
    js = _fonte("renderer", "painel.js")
    assert "ATRASO_PERMITIR_MS = 700" in js
    assert "botaoPermitirClaude.disabled = true;" in js
    assert "botaoNegarClaude.disabled = false;" in js
    # a fila abre o próximo pedido pela mesma função, então o atraso vale para todos
    assert js.count("claudeAbrirProximoPedido()") >= 3


def test_dialogo_mostra_corte_e_aviso_de_rede():
    js = _fonte("renderer", "painel.js")
    assert "caracteres escondidos" in js and "p.rede === true" in js
    assert "escondidos" in _fonte("main.js") and "rede: mensagem.rede === true" in _fonte("main.js")


def test_painel_carrega_o_formatador_antes_do_painel_js():
    html = _fonte("renderer", "painel.html")
    assert html.index("painel-markdown.js") < html.index('src="painel.js"')


def test_preload_expoe_so_a_lista_estreita_do_claude():
    js = _fonte("preload.js")
    expostos = set(re.findall(r"^\s{2}((?:aoClaude|claude)\w+)\s*:", js, re.MULTILINE))
    assert expostos == {"aoClaudeDelta", "aoClaudeFerramenta", "aoClaudePedido", "aoClaudeFim",
                        "claudePerguntar", "claudeParar", "claudeResponder",
                        "claudeNovaConversa"}


def test_main_valida_os_quatro_pedidos_da_tela_ao_claude():
    js = _fonte("main.js")
    for canal in ("dervs:claude-perguntar", "dervs:claude-parar", "dervs:claude-responder",
                  "dervs:claude-nova-conversa"):
        assert f'ipcMain.on("{canal}"' in js
    assert "texto.length > LIMITE_PERGUNTA" in js and "LIMITE_PERGUNTA = 8000" in js
    assert 'typeof dado.permitir === "boolean"' in js


def test_fila_de_pedidos_cheia_nega_o_excedente_e_mostra_quantos_esperam():
    """O pedido que não cabe na fila não pode sumir em silêncio: o Python ficaria
    esperando 5 min e o dono nem saberia."""
    js = _fonte("renderer", "painel.js")
    assert "window.dervs.claudeResponder(p.id, false, p.id)" in js
    assert "pedido(s) aguardando" in js and "recusado(s) por excesso" in js
    html = _fonte("renderer", "painel.html")
    assert 'id="claude-pedido-fila"' in html


# --- tela Integração: travas estáticas --------------------------------------------
# A tela mostra texto de terceiro (pedido do painel web, saída de comando no servidor) e
# tem um botão que confirma comando em servidor. O que tem de continuar verdade:

def test_preload_da_integracao_expoe_so_a_lista_estreita():
    js = _fonte("preload.js")
    expostos = set(re.findall(r"^\s{2}((?:aoIntegracao|integracao)\w*)\s*:", js, re.MULTILINE))
    assert expostos == {"aoIntegracao", "integracaoPedir", "integracaoEscolherCerebro",
                        "integracaoDispensar", "integracaoPedirConserto", "integracaoSshRodar",
                        "integracaoSshConfirmar", "integracaoSshCancelar"}


def test_main_valida_os_pedidos_da_integracao_e_manda_segunda_true_so_no_confirmar():
    js = _fonte("main.js")
    for canal in ("pedir", "cerebro", "dispensar", "conserto", "ssh-rodar", "ssh-confirmar", "ssh-cancelar"):
        assert f'ipcMain.on("dervs:integracao-{canal}"' in js
    assert "LIMITE_COMANDO_SSH = 400" in js and "dado.comando.length <= LIMITE_COMANDO_SSH" in js
    assert 'verbo: "integracao_ssh_confirmar", proposta_id: propostaId, segunda: true' in js
    assert js.count("segunda: true") == 1      # nenhum outro caminho confirma


def test_a_tela_so_confirma_pelo_botao_do_cartao_e_nunca_manda_cartao_nem_senha():
    js = _sem_comentarios(_fonte("renderer", "painel-integracao.js"))
    assert js.count("integracaoSshConfirmar(") == 1
    assert not re.search(r"d\.integracao\w+\([^)]*(cartao|senha|token)", js)   # só o id da proposta sai
    assert not re.search(r"\bsenha\b", js.lower())
    assert "$(\"integ-cartao-confirmar\").disabled" in js      # o botão nasce apagado (atraso de 700 ms)
    assert "integracaoPedirConserto(" in js and js.count("integracaoPedirConserto(") == 1


def test_a_integracao_nao_tem_botao_de_executar_nos_pedidos_do_painel_web():
    js = _sem_comentarios(_fonte("renderer", "painel-integracao.js"))
    assert "DISPENSAR" in js and "EXECUTAR" in js       # o EXECUTAR é só o do terminal, no HTML/JS do formulário
    trecho = js[js.index("function desenharFila"):js.index("function desenharAvisos")]
    assert "integracaoSsh" not in trecho and "Executar" not in trecho and "EXECUTAR" not in trecho


def test_html_da_integracao_carrega_o_script_e_nao_afrouxa_nada():
    html = _fonte("renderer", "painel.html")
    assert 'src="painel-integracao.js"' in html and 'href="painel-integracao.css"' in html
    assert 'id="p-dialogo-integracao"' in html and 'id="p-abrir-integracao"' in html
    assert "style=" not in html[html.index('id="p-dialogo-integracao"'):html.index('src="painel-formato.js"')]
    assert "unsafe-inline" not in html


def test_nenhum_js_fala_do_ssh_pelo_nome_do_modulo():
    for arquivo in (("renderer", "painel-integracao.js"), ("main.js",), ("preload.js",)):
        assert "dervs_ssh" not in _fonte(*arquivo)


def test_confirmacao_ssh_exige_gesto_real_e_a_janela_do_painel():
    """Trava estática: a segunda confirmação do SSH só sai do preload com ativação
    de usuário verdadeira, e o main só a aceita vinda da janela do painel."""
    preload = open(os.path.join("electron", "preload.js"), encoding="utf-8").read()
    main = open(os.path.join("electron", "main.js"), encoding="utf-8").read()
    corpo = preload.split("integracaoSshConfirmar:")[1].split("integracaoSshCancelar:")[0]
    assert "navigator.userActivation.isActive" in corpo
    handler = main.split('"dervs:integracao-ssh-confirmar"')[1].split("ipcMain.on(")[0]
    assert "evento.sender !== painel.webContents" in handler
