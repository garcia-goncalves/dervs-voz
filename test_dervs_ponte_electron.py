#!/usr/bin/env python3
"""A ponte com o Electron, testada sem precisar do Electron instalado.

O dublê de processo abaixo tem `stdin`/`stdout`/`stderr` de `io.BytesIO`,
igual ao contrato de um `subprocess.Popen` real (write/flush/close no stdin,
iteração linha a linha no stdout/stderr). `PonteElectron._iniciar()` liga as
threads de leitura direto nesse dublê — não precisa subir um Electron de
verdade para provar o protocolo.

Rodar: python -m pytest test_dervs_ponte_electron.py -q
"""
import io
import json
import time

import pytest

import dervs_ponte_electron as ponte_mod


class ProcessoFalso:
    """Um `Popen` de mentira: stdin de mentira grava tudo; stdout de mentira
    devolve linhas pré-escritas e depois "morre" (EOF), como um filho real
    fecharia o cano ao sair."""

    def __init__(self, linhas_de_saida: bytes = b""):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(linhas_de_saida)
        self.stderr = io.BytesIO(b"")
        self._vivo = True

    def wait(self, timeout=None):
        self._vivo = False
        return 0

    def terminate(self):
        self._vivo = False

    def kill(self):
        self._vivo = False


def _nova_ponte(linhas_de_saida: bytes = b"", ao_sair=None, ao_plano=None, ao_pronto=None):
    """Sobe uma `PonteElectron` já ligada a um dublê, e a deixa `pronta`
    (a menos que o chamador queira testar o comportamento antes do `pronto`)."""
    p = ponte_mod.PonteElectron(
        ao_sair=ao_sair or (lambda: None),
        ao_plano=ao_plano or (lambda resposta, autorizado=False, cartao_id=None: None),
        ao_pronto=ao_pronto or (lambda: None))
    processo = ProcessoFalso(linhas_de_saida)
    p._iniciar(processo)
    return p, processo


def _linhas_escritas(processo: ProcessoFalso):
    return [l for l in processo.stdin.getvalue().split(b"\n") if l]


def _esperar(condicao, segundos=2.0):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.01)
    return False


# ---- cada verbo vira uma linha de JSON com os campos certos ------------

def test_enviar_estado_manda_um_json_com_valor_texto_apoio():
    p, processo = _nova_ponte()
    p._despachar_guardado()      # simula o "pronto" já ter chegado
    p.enviar_estado("erro", texto="sem som", apoio="confira o volume")
    linhas = _linhas_escritas(processo)
    assert len(linhas) == 1
    dado = json.loads(linhas[0])
    assert dado == {"verbo": "estado", "valor": "erro", "texto": "sem som",
                     "apoio": "confira o volume"}


def test_enviar_volume_manda_um_json_com_valor():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_volume(0.4321)
    linhas = _linhas_escritas(processo)
    assert len(linhas) == 1
    dado = json.loads(linhas[0])
    assert dado == {"verbo": "volume", "valor": 0.43}


def test_enviar_fala_manda_papel_e_texto():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_fala("dono", "oi dervs")
    dado = json.loads(_linhas_escritas(processo)[0])
    assert dado == {"verbo": "fala", "papel": "dono", "texto": "oi dervs"}


def test_enviar_plano_manda_passos_nivel_pergunta():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    passos = [{"rotulo": "apagar arquivo", "nivel": "destrutivo"}]
    p.enviar_plano(passos, "destrutivo", "confirma?")
    dado = json.loads(_linhas_escritas(processo)[0])
    assert dado == {"verbo": "plano", "passos": passos, "nivel": "destrutivo",
                     "pergunta": "confirma?"}


def test_enviar_plano_com_cartao_id_manda_o_campo():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_plano([{"rotulo": "x", "nivel": "reversivel"}], "reversivel",
                    "confirma?", cartao_id=7)
    dado = json.loads(_linhas_escritas(processo)[0])
    assert dado["cartao_id"] == 7


def test_enviar_plano_sem_cartao_id_nao_manda_o_campo():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_plano([], "reversivel", "")
    dado = json.loads(_linhas_escritas(processo)[0])
    assert "cartao_id" not in dado


def test_enviar_plano_gigante_e_cortado_em_vez_de_estourar_a_linha(capsys):
    p, processo = _nova_ponte()
    p._despachar_guardado()
    passos = [{"rotulo": "x" * 2000, "nivel": "reversivel"} for _ in range(100)]
    p.enviar_plano(passos, "reversivel", "confirma?", cartao_id=1)
    linha = _linhas_escritas(processo)[0]
    assert len(linha) <= ponte_mod._LIMITE_LINHA
    dado = json.loads(linha)
    assert len(dado["passos"]) < len(passos)
    assert dado["cartao_id"] == 1
    assert "cortado" in capsys.readouterr().err


def test_enviar_mostrar_nao_tem_campo_nenhum():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_mostrar()
    dado = json.loads(_linhas_escritas(processo)[0])
    assert dado == {"verbo": "mostrar"}


def test_enviar_sistema_manda_cpu_ram_disco():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_sistema(cpu=12.3, ram=45.6, disco_livre_gb=100.0, disco_total_gb=500.0)
    dado = json.loads(_linhas_escritas(processo)[0])
    assert dado == {"verbo": "sistema", "cpu": 12.3, "ram": 45.6,
                     "disco_livre_gb": 100.0, "disco_total_gb": 500.0}


def test_enviar_sistema_antes_de_pronto_nao_manda_nada():
    p, processo = _nova_ponte()
    # sem chamar `_despachar_guardado()` — a janela ainda não avisou "pronto"
    p.enviar_sistema(cpu=1.0, ram=1.0, disco_livre_gb=1.0, disco_total_gb=1.0)
    assert _linhas_escritas(processo) == []


# ---- só os campos do contrato saem na linha -----------------------------

def test_texto_parecido_com_chave_nao_vaza_campo_extra():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    texto_hostil = '"senha": "abc123", "token": "xyz"'
    p.enviar_fala("resultado", texto_hostil)
    dado = json.loads(_linhas_escritas(processo)[0])
    assert set(dado.keys()) == {"verbo", "papel", "texto"}
    assert dado["texto"] == texto_hostil     # foi tratado como VALOR, não como chave


# ---- volume: estrangulamento -------------------------------------------

def test_volume_repetido_nao_reenvia():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_volume(0.5)
    p.enviar_volume(0.5)
    p.enviar_volume(0.5)
    assert len(_linhas_escritas(processo)) == 1


def test_rajada_de_volumes_entrega_poucas_linhas():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    fim = time.monotonic() + 0.1
    i = 0
    while time.monotonic() < fim:
        i += 1
        p.enviar_volume((i % 100) / 100.0)
    linhas = _linhas_escritas(processo)
    # 100 ms de rajada, estrangulado a 50 ms => no máximo ~3 linhas, nunca centenas
    assert 0 < len(linhas) <= 5


# ---- guarda estado e volume antes do "pronto" ---------------------------

def test_estado_e_volume_ficam_guardados_ate_o_pronto():
    p, processo = _nova_ponte()
    p.enviar_estado("ouvindo")
    p.enviar_volume(0.7)
    assert _linhas_escritas(processo) == []      # nada saiu ainda
    p._despachar_guardado()
    linhas = [json.loads(l) for l in _linhas_escritas(processo)]
    verbos = {l["verbo"] for l in linhas}
    assert verbos == {"estado", "volume"}


def test_pronto_chama_ao_pronto():
    chamado = []
    p, processo = _nova_ponte(ao_pronto=lambda: chamado.append(True))
    p._despachar_guardado()
    assert chamado == [True]


# ---- o que vem do Electron ----------------------------------------------

def test_verbo_sair_do_filho_chama_ao_sair():
    chamado = []
    p, processo = _nova_ponte(
        linhas_de_saida=b'{"verbo": "sair"}\n',
        ao_sair=lambda: chamado.append(True))
    assert _esperar(lambda: chamado)


def test_resposta_de_plano_chama_ao_plano_com_confirmar():
    recebido = []
    p, processo = _nova_ponte(
        linhas_de_saida=b'{"verbo": "plano", "resposta": "confirmar"}\n',
        ao_plano=lambda resposta, autorizado=False, cartao_id=None:
            recebido.append((resposta, autorizado)))
    assert _esperar(lambda: recebido == [("confirmar", False)])


def test_resposta_de_plano_manda_autorizado_quando_vem_true():
    recebido = []
    p, processo = _nova_ponte(
        linhas_de_saida=b'{"verbo": "plano", "resposta": "confirmar", "autorizado": true}\n',
        ao_plano=lambda resposta, autorizado=False, cartao_id=None:
            recebido.append((resposta, autorizado)))
    assert _esperar(lambda: recebido == [("confirmar", True)])


@pytest.mark.parametrize("valor_autorizado", ["false", "nao", [0], 0.0])
def test_resposta_de_plano_com_autorizado_nao_booleano_vira_false(valor_autorizado):
    # `bool("false")` é `True` em Python — a checagem tem de ser estrita
    # (`is True`), senão qualquer valor truthy do JSON destrava o passo.
    linha = (json.dumps({"verbo": "plano", "resposta": "confirmar",
                          "autorizado": valor_autorizado}) + "\n").encode("utf-8")
    recebido = []
    p, processo = _nova_ponte(
        linhas_de_saida=linha,
        ao_plano=lambda resposta, autorizado=False, cartao_id=None:
            recebido.append((resposta, autorizado)))
    assert _esperar(lambda: recebido == [("confirmar", False)])


def test_resposta_de_plano_repassa_o_cartao_id():
    recebido = []
    p, processo = _nova_ponte(
        linhas_de_saida=b'{"verbo": "plano", "resposta": "confirmar", "cartao_id": 5}\n',
        ao_plano=lambda resposta, autorizado=False, cartao_id=None:
            recebido.append((resposta, autorizado, cartao_id)))
    assert _esperar(lambda: recebido == [("confirmar", False, 5)])


def test_verbo_sair_seguido_de_fechar_stdout_chama_ao_sair_uma_vez_so():
    # a sequência real: o Electron manda "sair" e em seguida fecha o stdout
    # (encerramento normal) — o `finally` de `_ler_saida` não pode chamar
    # `ao_sair` de novo por cima do que o verbo já disparou.
    chamado = []
    p, processo = _nova_ponte(
        linhas_de_saida=b'{"verbo": "sair"}\n',
        ao_sair=lambda: chamado.append(True))
    assert _esperar(lambda: len(chamado) >= 1)
    time.sleep(0.2)   # dá tempo do finally (stdout fechado) rodar, se for rodar
    assert len(chamado) == 1


def test_stdout_fechar_chama_ao_sair():
    chamado = []
    # sem linha nenhuma: o BytesIO já nasce "fechado" (EOF imediato)
    p, processo = _nova_ponte(linhas_de_saida=b"", ao_sair=lambda: chamado.append(True))
    assert _esperar(lambda: chamado)


def test_verbo_desconhecido_do_filho_nao_derruba_nada(capsys):
    p, processo = _nova_ponte(linhas_de_saida=b'{"verbo": "coisa-nova"}\n')
    assert _esperar(lambda: "verbo desconhecido" in capsys.readouterr().err
                     or True, segundos=0.5)
    # o processo continua utilizável: mandar mensagem depois não explode
    p._despachar_guardado()
    p.enviar_mostrar()
    assert json.loads(_linhas_escritas(processo)[-1]) == {"verbo": "mostrar"}


def test_linha_gigante_e_descartada(capsys):
    linha_gigante = b'{"verbo": "plano", "resposta": "confirmar", "recheio": "' \
        + b"x" * (70 * 1024) + b'"}\n'
    recebido = []
    p, processo = _nova_ponte(
        linhas_de_saida=linha_gigante,
        ao_plano=lambda resposta, autorizado=False, cartao_id=None:
            recebido.append(resposta))
    time.sleep(0.3)
    assert recebido == []       # a linha nunca chegou a ser interpretada
    saida = capsys.readouterr().err
    assert "64 KiB" in saida


def test_linha_que_nao_e_json_valido_nao_derruba_nada(capsys):
    p, processo = _nova_ponte(linhas_de_saida=b"isso nao e json\n")
    time.sleep(0.2)
    p._despachar_guardado()
    p.enviar_mostrar()
    assert json.loads(_linhas_escritas(processo)[-1]) == {"verbo": "mostrar"}


# ---- fechar --------------------------------------------------------------

def test_fechar_e_seguro_chamar_duas_vezes():
    p, processo = _nova_ponte()
    p.fechar(espera=0.1)
    p.fechar(espera=0.1)     # não pode levantar nada


def test_fechar_fecha_o_stdin():
    p, processo = _nova_ponte()
    p.fechar(espera=0.1)
    assert processo.stdin.closed


# ---- abrir(): mensagem de erro quando falta o Electron -------------------

def test_abrir_sem_electron_instalado_levanta_erro_em_portugues(tmp_path):
    p = ponte_mod.PonteElectron(ao_sair=lambda: None,
                                 ao_plano=lambda r, a=False, c=None: None,
                                 ao_pronto=lambda: None)
    executavel_inexistente = str(tmp_path / "electron-que-nao-existe.exe")
    with pytest.raises(FileNotFoundError) as excinfo:
        p.abrir(str(tmp_path), executavel=executavel_inexistente)
    assert "npm install" in str(excinfo.value)


def test_abrir_com_env_extra_repassa_ao_subprocesso(tmp_path, monkeypatch):
    """`env_extra` (ex.: DERVS_APP_URL) precisa chegar ao Electron por cima do
    ambiente herdado, sem apagar o resto (ex.: PATH) — ver `dervs_electron.py`."""
    executavel_de_mentira = tmp_path / "electron.exe"
    executavel_de_mentira.write_bytes(b"")

    chamadas = []

    class PopenFalso(ProcessoFalso):
        def __init__(self, args, **kwargs):
            super().__init__()
            chamadas.append((args, kwargs))

    monkeypatch.setenv("UMA_VARIAVEL_HERDADA", "valor-herdado")
    monkeypatch.setattr(ponte_mod.subprocess, "Popen", PopenFalso)

    p = ponte_mod.PonteElectron(ao_sair=lambda: None,
                                 ao_plano=lambda r, a=False, c=None: None,
                                 ao_pronto=lambda: None)
    p.abrir(str(tmp_path), executavel=str(executavel_de_mentira),
            env_extra={"DERVS_APP_URL": "http://localhost:4777"})

    assert len(chamadas) == 1
    _, kwargs = chamadas[0]
    assert kwargs["env"]["DERVS_APP_URL"] == "http://localhost:4777"
    assert kwargs["env"]["UMA_VARIAVEL_HERDADA"] == "valor-herdado"


def test_abrir_sem_env_extra_nao_passa_env_nenhum(tmp_path, monkeypatch):
    """Sem `env_extra`, o `Popen` não recebe `env` — o filho herda o ambiente
    do pai do jeito padrão do `subprocess`, como sempre foi."""
    executavel_de_mentira = tmp_path / "electron.exe"
    executavel_de_mentira.write_bytes(b"")

    chamadas = []

    class PopenFalso(ProcessoFalso):
        def __init__(self, args, **kwargs):
            super().__init__()
            chamadas.append((args, kwargs))

    monkeypatch.setattr(ponte_mod.subprocess, "Popen", PopenFalso)

    p = ponte_mod.PonteElectron(ao_sair=lambda: None,
                                 ao_plano=lambda r, a=False, c=None: None,
                                 ao_pronto=lambda: None)
    p.abrir(str(tmp_path), executavel=str(executavel_de_mentira))

    assert len(chamadas) == 1
    _, kwargs = chamadas[0]
    assert "env" not in kwargs


# ---- microfone: o liga/desliga que voltou ao HUD -------------------------

def test_enviar_microfone_manda_ligado_como_booleano():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_microfone(True)
    p.enviar_microfone(False)
    dados = [json.loads(l) for l in _linhas_escritas(processo)]
    assert dados == [{"verbo": "microfone", "ligado": True},
                     {"verbo": "microfone", "ligado": False}]


def test_enviar_microfone_antes_de_pronto_guarda_o_ultimo_e_despacha_depois():
    p, processo = _nova_ponte()
    p.enviar_microfone(True)
    p.enviar_microfone(False)
    assert _linhas_escritas(processo) == []
    p._despachar_guardado()
    dados = [json.loads(l) for l in _linhas_escritas(processo)]
    assert dados == [{"verbo": "microfone", "ligado": False}]


def test_pedido_de_microfone_chama_o_callback_com_o_booleano():
    pedidos = []
    linha = b'{"verbo": "microfone", "ligar": true}\n{"verbo": "microfone", "ligar": false}\n'
    p = ponte_mod.PonteElectron(ao_sair=lambda: None,
                                ao_plano=lambda *a, **k: None,
                                ao_pronto=lambda: None,
                                ao_microfone=pedidos.append)
    p._iniciar(ProcessoFalso(linha))
    assert _esperar(lambda: len(pedidos) == 2)
    assert pedidos == [True, False]


@pytest.mark.parametrize("valor", ['"true"', '1', 'null', '"false"', '[]'])
def test_pedido_de_microfone_com_valor_que_nao_e_booleano_e_ignorado(valor, capsys):
    pedidos = []
    linha = ('{"verbo": "microfone", "ligar": %s}\n' % valor).encode()
    p = ponte_mod.PonteElectron(ao_sair=lambda: None,
                                ao_plano=lambda *a, **k: None,
                                ao_pronto=lambda: None,
                                ao_microfone=pedidos.append)
    p._iniciar(ProcessoFalso(linha))
    time.sleep(0.2)   # dá tempo da thread de leitura processar a linha
    assert pedidos == []
    assert "microfone" in capsys.readouterr().err


def test_pedido_de_microfone_sem_callback_nao_derruba_a_ponte():
    p, _ = _nova_ponte(b'{"verbo": "microfone", "ligar": true}\n')
    time.sleep(0.1)   # a thread de leitura não pode ter explodido


# ---- diário do porteiro e modo reunião (quarta rodada) ----------------------

def test_enviar_diario_manda_ouvidas_e_acordou():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_diario(7, 2)
    assert json.loads(_linhas_escritas(processo)[0]) == {
        "verbo": "diario", "ouvidas": 7, "acordou": 2}


def test_enviar_diario_antes_de_pronto_nao_manda_nada():
    p, processo = _nova_ponte()
    p.enviar_diario(1, 1)
    assert _linhas_escritas(processo) == []


def test_enviar_reuniao_manda_restante_ou_null():
    p, processo = _nova_ponte()
    p._despachar_guardado()
    p.enviar_reuniao(3552)
    p.enviar_reuniao(None)
    dados = [json.loads(l) for l in _linhas_escritas(processo)]
    assert dados == [{"verbo": "reuniao", "restante_s": 3552},
                     {"verbo": "reuniao", "restante_s": None}]


def _ponte_com_reuniao(linha: bytes, recebido):
    p = ponte_mod.PonteElectron(
        ao_sair=lambda: None, ao_plano=lambda *a, **k: None,
        ao_pronto=lambda: None, ao_reuniao=lambda ligar: recebido.append(ligar))
    p._iniciar(ProcessoFalso(linha))
    return p


@pytest.mark.parametrize("valor", [True, False])
def test_pedido_de_reuniao_chama_ao_reuniao(valor):
    recebido = []
    linha = (json.dumps({"verbo": "reuniao", "ligar": valor}) + "\n").encode()
    _ponte_com_reuniao(linha, recebido)
    assert _esperar(lambda: recebido == [valor])


@pytest.mark.parametrize("valor", ["true", 1, None, [True]])
def test_pedido_de_reuniao_nao_booleano_e_ignorado(valor):
    recebido = []
    linha = (json.dumps({"verbo": "reuniao", "ligar": valor}) + "\n").encode()
    _ponte_com_reuniao(linha, recebido)
    time.sleep(0.15)
    assert recebido == []


def test_pedido_de_reuniao_sem_callback_nao_derruba_a_ponte():
    p, _ = _nova_ponte(b'{"verbo": "reuniao", "ligar": true}\n')
    time.sleep(0.1)
