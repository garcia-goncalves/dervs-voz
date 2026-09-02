"""O DERVS tem de ser UM só, e o segundo clique no ícone tem de trazer o que já
está aberto — não abrir outro.

Por que isto existe: em 02/09/2026 o dono relatou "o DERVS sumiu / bugou".
Medido: clicar duas vezes no ícone deixava DOIS DERVS vivos, empilhados no mesmo
ponto da tela, disputando o microfone, e o menu da bandeja não tinha "Sair" —
então não havia como fechar nenhum. O app piorava a cada uso, sem saída.
"""
import os
import json
import time
import socket
import threading
import tempfile

import pytest

import dervs_instancia as inst


@pytest.fixture
def registro(tmp_path):
    return str(tmp_path / "instancia.json")


def _esperar(condicao, limite=3.0):
    """Espera a condição virar verdadeira. Devolve se conseguiu."""
    fim = time.time() + limite
    while time.time() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return condicao()


def test_o_primeiro_toma_posse(registro):
    posse = inst.tomar_posse(lambda: None, caminho=registro)
    try:
        assert posse is not None
        assert os.path.exists(registro)
        assert posse.porta > 0
    finally:
        posse.soltar()


def test_o_segundo_nao_abre_e_acorda_o_primeiro(registro):
    chamados = []
    primeiro = inst.tomar_posse(lambda: chamados.append(1), caminho=registro)
    try:
        segundo = inst.tomar_posse(lambda: chamados.append(2), caminho=registro)
        assert segundo is None, "o segundo DERVS não pode subir"
        assert _esperar(lambda: chamados == [1]), (
            f"o primeiro devia ter sido acordado; chamados={chamados}")
    finally:
        primeiro.soltar()


def test_registro_de_um_dervs_que_morreu_nao_tranca_o_proximo(registro):
    """Queda de energia deixa o arquivo para trás com uma porta que não atende.
    Isso não pode impedir o DERVS de abrir nunca mais."""
    with open(registro, "w", encoding="utf-8") as f:
        json.dump({"porta": 1, "senha": "qualquer"}, f)
    posse = inst.tomar_posse(lambda: None, caminho=registro)
    try:
        assert posse is not None
    finally:
        posse.soltar()


def test_registro_corrompido_nao_derruba(registro):
    with open(registro, "w", encoding="utf-8") as f:
        f.write("isto não é json {{{")
    posse = inst.tomar_posse(lambda: None, caminho=registro)
    try:
        assert posse is not None
    finally:
        posse.soltar()


def test_quem_nao_sabe_a_senha_nao_acorda_o_dervs(registro):
    """A porta é local, mas qualquer programa da máquina pode bater nela. Só
    quem leu o arquivo de registro (isto é, o próprio dono) pode mandar aparecer."""
    chamados = []
    posse = inst.tomar_posse(lambda: chamados.append(1), caminho=registro)
    try:
        with socket.create_connection(("127.0.0.1", posse.porta), timeout=2) as s:
            s.sendall(b"MOSTRAR senha-errada\n")
            resposta = s.recv(64)
        assert b"OK" not in resposta
        time.sleep(0.3)
        assert chamados == [], "não podia ter acordado com senha errada"
    finally:
        posse.soltar()


def test_lixo_na_porta_nao_derruba_o_dervs(registro):
    chamados = []
    posse = inst.tomar_posse(lambda: chamados.append(1), caminho=registro)
    try:
        with socket.create_connection(("127.0.0.1", posse.porta), timeout=2) as s:
            s.sendall(b"\x00\x01lixo binario sem fim de linha")
        # continua vivo e atendendo de verdade depois do lixo
        segundo = inst.tomar_posse(lambda: None, caminho=registro)
        assert segundo is None
        assert _esperar(lambda: chamados == [1])
    finally:
        posse.soltar()


def test_soltar_libera_para_o_proximo(registro):
    primeiro = inst.tomar_posse(lambda: None, caminho=registro)
    primeiro.soltar()
    segundo = inst.tomar_posse(lambda: None, caminho=registro)
    try:
        assert segundo is not None, "depois de fechar, o DERVS tem de poder abrir"
    finally:
        segundo.soltar()


def test_erro_no_que_o_dono_pediu_nao_mata_o_atendente(registro):
    """Se mostrar a janela explodir, o DERVS não pode ficar surdo ao próximo clique."""
    chamados = []

    def acordar():
        chamados.append(1)
        raise RuntimeError("a tela explodiu")

    posse = inst.tomar_posse(acordar, caminho=registro)
    try:
        assert inst.tomar_posse(lambda: None, caminho=registro) is None
        assert _esperar(lambda: len(chamados) == 1)
        assert inst.tomar_posse(lambda: None, caminho=registro) is None
        assert _esperar(lambda: len(chamados) == 2), (
            f"devia ter atendido de novo; chamados={chamados}")
    finally:
        posse.soltar()


def test_so_escuta_no_proprio_computador(registro):
    """Nunca na rede: a porta é só para o clique do dono, nesta máquina."""
    posse = inst.tomar_posse(lambda: None, caminho=registro)
    try:
        assert posse.endereco == "127.0.0.1"
    finally:
        posse.soltar()


# ---------------------------------------------------------------------------
# Achados da revisao de 02/09/2026, cada um com sua reproducao.
# ---------------------------------------------------------------------------

def _servidor_falso(resposta: bytes):
    """Sobe um servidor bobo que responde sempre a mesma coisa. Devolve a porta
    e uma funcao para desligar."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(4)
    porta = s.getsockname()[1]
    parar = []

    def laco():
        while not parar:
            try:
                c, _ = s.accept()
            except OSError:
                return
            with c:
                try:
                    c.recv(200)
                    c.sendall(resposta)
                except OSError:
                    pass

    t = threading.Thread(target=laco, daemon=True)
    t.start()

    def desligar():
        parar.append(1)
        s.close()
    return porta, desligar


def test_servidor_qualquer_respondendo_200_ok_nao_tranca_o_dervs(registro):
    """A porta de um DERVS morto pode ser reaproveitada pelo Windows para outro
    programa. Um servidor web local responde 'HTTP/1.1 200 OK' — e procurar
    'OK' solto fazia o DERVS achar que ja estava aberto e NAO ABRIR NUNCA MAIS,
    calado, que e o proprio defeito que esta peca veio consertar."""
    porta, desligar = _servidor_falso(b"HTTP/1.1 200 OK\r\n\r\n")
    try:
        with open(registro, "w", encoding="utf-8") as f:
            json.dump({"porta": porta, "senha": "velha", "pid": os.getpid()}, f)
        posse = inst.tomar_posse(lambda: None, caminho=registro)
        assert posse is not None, "um servidor estranho nao pode impedir o DERVS de abrir"
        posse.soltar()
    finally:
        desligar()


def test_registro_de_processo_morto_e_ignorado(registro):
    """Queda deixa o arquivo para tras. Se aquele processo nao existe mais, o
    registro nao vale nada — nem vale a pena bater na porta dele."""
    morto = 999999          # pid que nao existe nesta maquina
    with open(registro, "w", encoding="utf-8") as f:
        json.dump({"porta": 65000, "senha": "x", "pid": morto}, f)
    assert inst._ler_registro(registro) is None
    assert inst.chamar_quem_ja_esta_aberto(registro) is False


def test_processo_vivo_reconhece_este_processo():
    assert inst._processo_vivo(os.getpid()) is True
    assert inst._processo_vivo(999999) is False
    assert inst._processo_vivo(None) is False
    assert inst._processo_vivo("nao e numero") is False


def test_se_a_reserva_falhar_o_dervs_ABRE_do_mesmo_jeito(tmp_path):
    """Instancia unica e conveniencia, nao pre-requisito. Pasta sem permissao
    ou disco cheio nao podem impedir o app de abrir — muito menos em silencio."""
    impossivel = os.path.join(str(tmp_path / "arquivo_comum"), "sub", "i.json")
    with open(str(tmp_path / "arquivo_comum"), "w", encoding="utf-8") as f:
        f.write("sou um arquivo, nao uma pasta")
    r = inst.tomar_posse(lambda: None, caminho=impossivel)
    assert r is not None, "sem trava o DERVS ainda tem de abrir"
    assert isinstance(r, inst.SemTrava)
    r.soltar()          # nao pode explodir


def test_conexao_calada_nao_segura_a_fila(registro):
    """Um programa qualquer da maquina abrindo conexoes e ficando mudo nao pode
    fazer o clique de verdade estourar o tempo — se estourasse, um SEGUNDO
    DERVS subia inteiro, que e exatamente o bug que isto conserta."""
    chamados = []
    posse = inst.tomar_posse(lambda: chamados.append(1), caminho=registro)
    mudos = []
    try:
        for _ in range(6):
            m = socket.create_connection(("127.0.0.1", posse.porta), timeout=2)
            mudos.append(m)          # conecta e nao fala nada
        inicio = time.time()
        assert inst.tomar_posse(lambda: None, caminho=registro) is None
        assert time.time() - inicio < 2.0, "o clique de verdade demorou demais"
        assert _esperar(lambda: chamados == [1])
    finally:
        for m in mudos:
            m.close()
        posse.soltar()


def test_soltar_leva_junto_o_arquivo_temporario(registro):
    posse = inst.tomar_posse(lambda: None, caminho=registro)
    with open(registro + ".tmp", "w", encoding="utf-8") as f:
        f.write("sobra de uma queda no meio da gravacao")
    posse.soltar()
    assert not os.path.exists(registro)
    assert not os.path.exists(registro + ".tmp")


def test_a_senha_nunca_aparece_no_registro_em_texto_previsivel(registro):
    """Nao e segredo de servidor, mas tambem nao pode ser adivinhavel."""
    posse = inst.tomar_posse(lambda: None, caminho=registro)
    try:
        with open(registro, encoding="utf-8") as f:
            dado = json.load(f)
        assert len(dado["senha"]) >= 30
        assert dado["pid"] == os.getpid()
    finally:
        posse.soltar()
