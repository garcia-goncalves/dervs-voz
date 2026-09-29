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
