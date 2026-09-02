"""O DERVS tem de anotar a própria morte e contar ao dono na vez seguinte.

Por que existe: o app abre com `pythonw`, sem terminal. Uma exceção escapando
de um sinal do Qt encerra o processo e o rastro vai para um `stderr` que não
existe — o app some da tela sem deixar uma linha. Foi o relato do dono em
02/09/2026 ("fechando sozinho quando eu aperto VOZ"), e sem registro o próximo
passo seria adivinhar.
"""
import io
import os
import sys
import threading

import pytest

import dervs_registro as reg


@pytest.fixture
def caminho(tmp_path):
    return str(tmp_path / "ultimo_erro.txt")


def test_anota_e_devolve_na_vez_seguinte(caminho):
    assert reg.anotar("ZeroDivisionError: division by zero", caminho=caminho)
    texto = reg.ler_e_limpar(caminho)
    assert "ZeroDivisionError" in texto
    assert "quando:" in texto


def test_o_aviso_aparece_uma_vez_so(caminho):
    """Depois de contado, some: senão o dono veria para sempre um aviso de uma
    queda que já passou."""
    reg.anotar("erro qualquer", caminho=caminho)
    assert reg.ler_e_limpar(caminho) is not None
    assert reg.ler_e_limpar(caminho) is None


def test_sem_queda_anterior_nao_inventa_aviso(caminho):
    assert reg.ler_e_limpar(caminho) is None


def test_resumo_pega_a_linha_do_motivo():
    rastro = ('Traceback (most recent call last):\n'
              '  File "dervs.py", line 695, in alternar_voz\n'
              '    self.voz.calar()\n'
              'AttributeError: sem atributo calar\n')
    assert reg.resumo(rastro) == "AttributeError: sem atributo calar"
    assert reg.resumo("") == ""
    assert reg.resumo("\n\n  \n") == ""


def test_anotar_nao_explode_quando_nao_da_para_gravar(tmp_path):
    """Anotar acontece no meio de algo JÁ dando errado: não pode ser a segunda
    coisa a explodir."""
    arquivo = tmp_path / "sou_um_arquivo"
    arquivo.write_text("nao sou pasta", encoding="utf-8")
    impossivel = str(arquivo / "sub" / "erro.txt")
    assert reg.anotar("qualquer coisa", caminho=impossivel) is False


def test_instalar_pega_excecao_da_thread_da_tela(caminho, monkeypatch):
    anterior = sys.excepthook
    try:
        reg.instalar(caminho=caminho)
        monkeypatch.setattr(sys, "__excepthook__", lambda *a: None)
        try:
            raise ValueError("o botao VOZ explodiu")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        texto = reg.ler_e_limpar(caminho)
        assert texto is not None
        assert "o botao VOZ explodiu" in texto
        assert "origem: tela" in texto
    finally:
        sys.excepthook = anterior


def test_instalar_pega_excecao_de_thread_de_fundo(caminho):
    anterior_sys, anterior_thread = sys.excepthook, threading.excepthook
    try:
        reg.instalar(caminho=caminho)

        def explodir():
            raise RuntimeError("a escuta caiu por baixo dos panos")

        t = threading.Thread(target=explodir, name="escuta")
        t.start()
        t.join(5)
        texto = reg.ler_e_limpar(caminho)
        assert texto is not None
        assert "a escuta caiu por baixo dos panos" in texto
        assert "origem: thread escuta" in texto
    finally:
        sys.excepthook, threading.excepthook = anterior_sys, anterior_thread


def test_o_rastro_e_cortado_para_nao_virar_arquivo_gigante(caminho):
    reg.anotar("x" * 50000, caminho=caminho)
    tamanho = os.path.getsize(caminho)
    assert tamanho < reg.LIMITE + 500


def test_nao_guarda_o_que_o_dono_falou(caminho):
    """O arquivo guarda erro, não conversa. Quem chama passa só o rastro — este
    teste trava o contrato para quem for mexer depois."""
    reg.anotar("KeyError: 'plano'", caminho=caminho)
    with io.open(caminho, encoding="utf-8") as f:
        conteudo = f.read()
    assert "quando:" in conteudo and "origem:" in conteudo
    assert conteudo.count("\n") < 12


def test_colher_anterior_le_antes_de_instalar_zerar_tudo(caminho):
    """instalar() zera o arquivo do faulthandler para escrever nele. Se a leitura
    viesse depois, a queda anterior se perdia — e o dono nunca saberia por quê."""
    reg.anotar("RuntimeError: morri ontem", caminho=caminho)
    assert "morri ontem" in reg.colher_anterior(caminho)
    reg.instalar(caminho=caminho)
    assert "morri ontem" in reg.QUEDA_ANTERIOR
    assert reg.ler_e_limpar(caminho) is None
