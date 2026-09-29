"""Roda os testes das funções puras do painel grande (JavaScript) com o Node.

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
    r = subprocess.run(["node", "--test", PASTA], capture_output=True, text=True,
                       timeout=60, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-500:]
