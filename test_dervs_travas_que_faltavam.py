#!/usr/bin/env python3
"""Quatro travas que a revisão de 02/09/2026 mostrou não existirem.

Todas têm o mesmo pano de fundo: o DERVS aceita confirmar por VOZ o que ele
classifica como "reversível" (`dervs.py`, `nivel_do_plano`). Voz não precisa de
ninguém presente — a TV ligada na sala serve. Então tudo que é poderoso e está
marcado como manso é, na prática, um comando que o ambiente pode disparar.

  A. O daemon de transcrição falhava ABERTO: qualquer linha que não começasse
     com `PORTEIRO ` ia para a nuvem. É a promessa central do projeto (o
     porteiro decide NA MÁQUINA o que sai daqui) dependendo de ninguém nunca
     errar uma palavra do protocolo.
  B. Um plano só de navegador era "reversível" — e o navegador dirige o Chrome
     LOGADO do dono: e-mail, banco, compras.
  C. O comando que roda era lido do campo editável, mas o risco tinha sido
     calculado sobre o texto ANTES da edição.
  D. `navegador_ligado` existia na configuração, era validada, tinha teste —
     e não era lida por ninguém. O interruptor não desligava nada.

Rodar: python -m pytest test_dervs_travas_que_faltavam.py -q
"""
import types

import pytest

import dervs_config as cfg
import dervs_stt_daemon as daemon


# ---- A. o porteiro não pode falhar aberto ------------------------------

class PorteiroDeMentira:
    def __init__(self):
        self.perguntado = []

    def ouviu_o_nome(self, caminho):
        self.perguntado.append(caminho)
        return False, ""


@pytest.fixture
def sem_nuvem():
    """Um transcritor que ACUSA em vez de mandar áudio para fora de verdade."""
    mandou = []

    def transcrever(caminho):
        mandou.append(caminho)
        return "transcrito"

    transcrever.mandou = mandou
    return transcrever


def test_verbo_transcrever_manda_para_a_nuvem(sem_nuvem):
    """O caminho legítimo continua funcionando."""
    r = daemon.atender(r"TRANSCREVER C:\tmp\a.wav", PorteiroDeMentira(), sem_nuvem)
    assert r.startswith("RESULT")
    assert sem_nuvem.mandou == [r"C:\tmp\a.wav"]


def test_verbo_porteiro_nao_manda_para_a_nuvem(sem_nuvem):
    porteiro = PorteiroDeMentira()
    r = daemon.atender(r"PORTEIRO C:\tmp\a.wav", porteiro, sem_nuvem)
    assert r.startswith("PORTEIRO")
    assert sem_nuvem.mandou == []
    assert porteiro.perguntado == [r"C:\tmp\a.wav"]


@pytest.mark.parametrize("linha", [
    r"C:\tmp\a.wav",                 # forma antiga: caminho cru
    r"PORTEIROC:\tmp\a.wav",         # verbo sem espaço
    r"porteiro C:\tmp\a.wav",        # caixa trocada
    r"TRANSCREVE C:\tmp\a.wav",      # verbo quase certo
    "lixo qualquer",
])
def test_qualquer_outra_coisa_nao_vaza_audio(linha, sem_nuvem):
    """Uma porta que falha ABERTA transforma um erro de digitação em conversa
    de família indo para servidor de terceiro — e em conta paga."""
    daemon.atender(linha, PorteiroDeMentira(), sem_nuvem)
    assert sem_nuvem.mandou == [], f"{linha!r} mandou áudio para a nuvem"


def test_linha_desconhecida_devolve_erro_legivel(sem_nuvem):
    r = daemon.atender("lixo qualquer", PorteiroDeMentira(), sem_nuvem)
    assert r.startswith("ERRO")


def test_linha_vazia_continua_sendo_ignorada(sem_nuvem):
    assert daemon.atender("", PorteiroDeMentira(), sem_nuvem) == ""
    assert sem_nuvem.mandou == []


def test_caminho_com_espaco_no_nome_ainda_funciona(sem_nuvem):
    daemon.atender(r"TRANSCREVER C:\meus audios\a b.wav",
                   PorteiroDeMentira(), sem_nuvem)
    assert sem_nuvem.mandou == [r"C:\meus audios\a b.wav"]


# ---- B, C, D: dependem da tela, que é Qt -------------------------------

pytest.importorskip("PyQt6", reason="a tela do DERVS é Qt; rode no dervs-venv")

import dervs                                                       # noqa: E402


def test_plano_de_navegador_nao_se_confirma_por_voz():
    """O navegador autônomo dirige o Chrome LOGADO do dono. "Reversível" quer
    dizer "só abre, lista, lê" — e isso não é."""
    plano = [{"tipo": "navegador", "objetivo": "comprar passagem"}]
    assert dervs.nivel_do_plano(plano) != "reversivel"


def test_plano_de_navegador_nao_vira_destrutivo_a_toa():
    """Subir demais também é defeito: cartão vermelho à toa treina o dono a
    confirmar no automático."""
    plano = [{"tipo": "navegador", "objetivo": "ver o clima"}]
    assert dervs.nivel_do_plano(plano) == "muda_estado"


def test_enriquecimento_passivo_continua_manso():
    """Fonte pública, não toca o alvo. Não é o mesmo caso do navegador."""
    plano = [{"tipo": "enriquecer", "dominio": "exemplo.com"}]
    assert dervs.nivel_do_plano(plano) == "reversivel"


def test_um_comando_destrutivo_no_plano_ainda_manda():
    plano = [{"tipo": "navegador", "objetivo": "x"},
             {"comando": "Remove-Item -Recurse -Force C:\\Windows"}]
    assert dervs.nivel_do_plano(plano) == "destrutivo"


def test_plano_vazio_continua_reversivel():
    assert dervs.nivel_do_plano([]) == "reversivel"
    assert dervs.nivel_do_plano(None) == "reversivel"


# ---- C. o comando editado é reclassificado -----------------------------

def _pop_para_confirmar(texto_no_campo, risco_calculado_antes):
    """A janela reduzida ao que `confirmar_passo` de fato usa."""
    rodados = []
    return types.SimpleNamespace(
        _aguardando_ok=False,
        _2conf=False,
        _risco_atual=risco_calculado_antes,
        plano=[{"comando": texto_no_campo}],
        passo_i=0,
        b_cmd=types.SimpleNamespace(text=lambda: texto_no_campo),
        b_confirmar=types.SimpleNamespace(setText=lambda t: None,
                                          setEnabled=lambda v: None),
        barra=types.SimpleNamespace(hide=lambda: None),
        _diz=lambda papel, texto, cor=None: None,
        rodados=rodados,
        _rodar_comando=lambda c, d, terminal=False: rodados.append((c, d)),
    )


def test_comando_editado_para_algo_perigoso_e_reclassificado():
    """O dono corrige o texto no campo; o risco tem de ser recalculado sobre o
    que VAI RODAR, não sobre o que foi proposto."""
    antes = dervs.seg.decidir_risco("ls")
    assert antes["nivel"] == "reversivel"
    pop = _pop_para_confirmar("Remove-Item -Recurse -Force C:\\Windows", antes)
    dervs.PopUp.confirmar_passo(pop)
    assert pop.rodados == [], "rodou destrutivo com a trava do comando manso"
    assert pop._2conf is True, "não pediu o segundo clique do trilho destrutivo"


def test_comando_nao_editado_roda_normalmente():
    antes = dervs.seg.decidir_risco("ls")
    pop = _pop_para_confirmar("ls", antes)
    dervs.PopUp.confirmar_passo(pop)
    assert len(pop.rodados) == 1
    assert pop.rodados[0][0] == "ls"


# ---- D. o interruptor do navegador desliga de verdade ------------------

def test_a_chave_do_navegador_existe_no_padrao():
    assert cfg.PADRAO["navegador_ligado"] is True


def test_com_o_navegador_desligado_o_passo_nao_roda(monkeypatch):
    monkeypatch.setattr(dervs.cfg, "carregar",
                        lambda: dict(cfg.PADRAO, navegador_ligado=False))
    ditos, rodou = [], []
    pop = types.SimpleNamespace(
        passo_i=0,
        plano=[{"tipo": "navegador", "objetivo": "abrir o gmail"}],
        _auto_seguidos=0,
        voz=types.SimpleNamespace(ligada=False, falar=lambda t: None),
        _diz=lambda papel, texto, cor=None: ditos.append(texto),
        _rodar_navegador=lambda o: rodou.append(o),
        _pensar=lambda: None,
        # pular o passo faz a janela chamar a si mesma para o próximo
        _processar_passo=lambda: None,
    )
    dervs.PopUp._processar_passo(pop)
    assert rodou == [], "o interruptor desligado não impediu nada"
    assert any("desligado" in t.lower() for t in ditos), ditos
