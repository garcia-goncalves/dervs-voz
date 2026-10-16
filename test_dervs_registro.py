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


# --- cópia da queda para o piloto automático ------------------------------

def test_colher_anterior_guarda_copia_em_quedas(tmp_path):
    caminho = str(tmp_path / "ultimo_erro.txt")
    pasta = str(tmp_path / "quedas")
    reg.anotar("ValueError: x", caminho=caminho)
    texto = reg.colher_anterior(caminho, pasta_quedas=pasta)
    copias = os.listdir(pasta)
    assert len(copias) == 1 and copias[0].startswith("queda-")
    with io.open(os.path.join(pasta, copias[0]), encoding="utf-8") as f:
        assert f.read() == texto


def test_quedas_guardadas_tem_teto_de_vinte(tmp_path):
    pasta = tmp_path / "quedas"
    pasta.mkdir()
    for i in range(25):
        (pasta / ("queda-20200101-0000%02d.txt" % i)).write_text("x")
    reg.guardar_copia("novo", str(pasta))
    nomes = sorted(os.listdir(pasta))
    assert len(nomes) == 20
    assert "queda-20200101-000000.txt" not in nomes


def test_guardar_copia_nunca_levanta(tmp_path):
    arquivo = tmp_path / "e_arquivo"
    arquivo.write_text("x")
    assert reg.guardar_copia("t", str(arquivo / "dentro")) is None


def test_diario_de_execucao_grava_com_hora_e_gira(tmp_path):
    # pythonw não tem stderr: sem isto, nenhuma decisão do app deixava rastro (teste de voz de 15/10)
    caminho = tmp_path / "execucao.log"
    caminho.write_text("x" * 50, encoding="utf-8")
    f = reg.abrir_diario_de_execucao(str(caminho), limite=10)
    f.write("dervs: conversa natural caiu (motivo)\n")
    f.flush()
    assert (tmp_path / "execucao.log.1").read_text(encoding="utf-8") == "x" * 50
    linha = caminho.read_text(encoding="utf-8")
    assert "dervs: conversa natural caiu (motivo)" in linha and linha[:2].isdigit()


def test_diario_de_execucao_sem_pasta_nao_explode(tmp_path):
    assert reg.abrir_diario_de_execucao(str(tmp_path / "nao" / "existe" / "\0x.log")) is None
