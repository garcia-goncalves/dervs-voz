"""Testes da conversa natural (dervs_conversa_natural), com dublês e relógio simulado.

O relógio é o próprio microfone: cada quadro são 30 ms. A "voz" de cada pessoa é um tom
com amplitude própria, e o `quem_fala` falso reconhece a pessoa pela amplitude — assim
dá para conferir, byte a byte, o que chegou ao motor (o que iria para a nuvem).
Nada aqui abre microfone, caixa de som ou rede.
"""
import numpy as np
import pytest

import dervs_conversa as dc
import dervs_conversa_natural as cn
import dervs_locutor as L
import dervs_turno as dt

Q = cn.QUADRO_S
AMP = {"dono": 3000, "visita": 6000, "filha": 9000}


def quadro(quem):
    if quem == "sil":
        return bytes(cn.QUADRO_BYTES)
    t = np.arange(480) / 16000
    return (AMP[quem] * np.sin(2 * np.pi * 220 * t)).astype(np.int16).tobytes()


class ArbitroFalso:
    """Fala por energia; a vez só fecha nos instantes gravados (`fins`, em segundos) ou depois
    de `fim` quadros de silêncio. Replica as decisões do árbitro real nos casos de 15/10."""

    def __init__(self, fins=(), fim=None):
        self.fins = sorted(fins)
        self.fim = fim
        self.n = 0
        self.em_fala = False
        self.cand = self.sil = 0
        self.limiar_fala = 0.5

    def reset(self):
        self.em_fala = False
        self.cand = self.sil = 0

    def processar(self, q):
        self.n += 1
        voz = cn._rms(q) >= cn.LIMIAR_VOZ
        if not self.em_fala:
            self.cand = self.cand + 1 if voz else 0
            if self.cand >= 3:
                self.em_fala, self.sil = True, 0
                return [dt.InicioFala(self.n * Q)]
            return []
        self.sil = 0 if voz else self.sil + 1
        t = self.n * Q
        if (self.fins and t >= self.fins[0] - 1e-9) or (self.fim and self.sil >= self.fim):
            while self.fins and t >= self.fins[0] - 1e-9:
                self.fins.pop(0)
            self.em_fala, self.cand = False, 0
            return [dt.FimDeVez(t, b"")]
        return []


class PerfisFalsos:
    def __init__(self, perfis=(("André", "dono"),), ativos=None, disponivel=True, explode=False):
        self.lista = [L.Perfil(n, n.lower(), p, True if ativos is None else n in ativos)
                      for n, p in perfis]
        self._disp = disponivel
        self.explode = explode
        self.chamadas = 0

    def listar(self):
        return list(self.lista)

    def disponivel(self):
        return self._disp

    def quem_fala(self, audio):
        self.chamadas += 1
        if self.explode:
            raise RuntimeError("modelo quebrou")
        rms = float(np.sqrt(np.mean(np.square(audio)))) * 32768
        papel = "dono" if rms < 3000 else ("visita" if rms < 5000 else "filha")
        for p in self.lista:
            if p.ativo and (p.papel == papel or (papel == "filha" and p.papel == "convidado")):
                return p, 0.9
        return None, 0.1


class PlayerFalso:
    def __init__(self):
        self.log = []
        self._tocando = False
        self.relogio = lambda: 0.0

    def tocar(self, pcm, taxa=24000):
        self.log.append(("tocar", round(self.relogio(), 2), len(pcm)))
        self._tocando = True

    def abaixar(self, frac=0.3):
        self.log.append(("abaixar", round(self.relogio(), 2), frac))

    def restaurar(self):
        self.log.append(("restaurar", round(self.relogio(), 2)))

    def parar(self):
        self.log.append(("parar", round(self.relogio(), 2)))
        self._tocando = False

    def acabou(self):
        self._tocando = False

    def fechar(self):
        self.log.append(("fechar", round(self.relogio(), 2)))
        self._tocando = False

    def tocando(self):
        return self._tocando

    def primeiro(self, tipo):
        return next((e for e in self.log if e[0] == tipo), None)


class ConversaFalsa:
    """Motor dublê: responde `atraso` segundos depois do fim da vez (relógio dos quadros)."""

    def __init__(self, cb, atraso=0.8):
        self.cb = cb
        self.atraso = atraso
        self.log = []
        self.audio = bytearray()
        self.respostas = []
        self.agendada = None
        self.motor_ativo = "gemini_live"

    def iniciar(self, instrucoes, ferramentas):
        self.instrucoes, self.ferramentas = instrucoes, ferramentas

    def enviar_audio(self, pcm):
        self.audio += pcm
        self.log.append("audio")

    def fim_da_vez(self):
        self.log.append("fim")
        self.agendada = self.agora() + self.atraso

    def interromper(self):
        self.log.append("interromper")
        self.agendada = None

    def responder_ferramenta(self, id_, resultado):
        self.respostas.append((id_, resultado))

    def encerrar(self):
        self.log.append("encerrar")


class Cena:
    def __init__(self, perfis=None, fins=(), fim=None, atraso=0.8, executar=None, segurar_s=None,
                 conf=None):
        self.player = PlayerFalso()
        self.avisos, self.caidas, self.feitos, self.acoes = [], [], [], []
        self.pedidos = []
        self.perfis = PerfisFalsos() if perfis is None else perfis
        self.conv = None

        def fabrica(cb):
            self.conv = ConversaFalsa(cb, atraso)
            self.conv.agora = lambda: self.cn._t
            return self.conv

        def executar_padrao(pedido, papel, confirmado):
            self.acoes.append((pedido, papel, confirmado))
            return {"tipo": "facil"}

        self.cn = cn.ConversaNatural(
            conf or {}, self.player, self.perfis, ArbitroFalso(fins, fim), fabrica,
            executar or executar_padrao, self.avisos.append, ao_cair=self.caidas.append,
            ao_feito=lambda: self.feitos.append(self.cn._t), ao_pedido=self.pedidos.append,
            em_fundo=lambda f: f(),
            relogio=lambda: self.cn._t, sinal=b"\x01\x00" * 100,
            **({"segurar_s": segurar_s} if segurar_s is not None else {}))
        self.player.relogio = lambda: self.cn._t
        assert self.cn.iniciar()

    def responder(self, pcm=b"\x00\x10" * 2400):
        self.conv.cb(dc.AudioSaida(pcm, 24000))

    def falar(self, roteiro):
        """roteiro: [(quem, segundos)]. Entrega os quadros e as respostas agendadas do motor."""
        for quem, seg in roteiro:
            for _ in range(int(round(seg / Q))):
                self.cn.quadro(quadro(quem))
                if self.conv.agendada is not None and self.cn._t >= self.conv.agendada - 1e-9:
                    self.conv.agendada = None
                    self.responder()

    def enviado(self):
        return np.frombuffer(bytes(self.conv.audio), np.int16)


# ---- sem perfis: como hoje, com aviso ------------------------------------------------

def test_sem_perfis_tudo_vai_ao_motor_e_o_painel_pede_para_gravar_a_voz():
    c = Cena(perfis=PerfisFalsos(perfis=()), fim=10)
    c.falar([("sil", 0.3), ("visita", 1.0), ("sil", 0.6)])
    assert c.conv.log.count("fim") == 1
    assert np.abs(c.enviado()).max() > 5000
    e = c.cn.estado()
    assert e["locutor_ativo"] is False and e["locutor_aviso"] == "grave sua voz"
    assert e["motor_ativo"] == "gemini_live" and e["dono_confirmado"] is False


def test_sem_perfis_nao_ha_interrupcao_microfone_surdo_enquanto_ele_fala():
    c = Cena(perfis=PerfisFalsos(perfis=()), fim=10)
    c.player.tocar(b"\x00\x01" * 100)
    c.falar([("dono", 2.0), ("sil", 0.6)])
    assert "interromper" not in c.conv.log and len(c.conv.audio) == 0
    assert c.player.primeiro("abaixar") is None


# ---- trava de voz: outras pessoas -----------------------------------------------

def test_voz_nao_cadastrada_nunca_vira_pedido_nem_sai_do_pc():
    c = Cena(fim=10)
    c.falar([("sil", 0.3), ("visita", 3.0), ("sil", 0.6)])
    assert len(c.conv.audio) == 0 and "fim" not in c.conv.log
    assert c.perfis.chamadas >= 2


def test_perfil_inativo_e_tratado_como_outra_pessoa():
    c = Cena(perfis=PerfisFalsos(perfis=(("André", "dono"), ("Lia", "convidado")),
                                 ativos={"André"}), fim=10)
    c.falar([("sil", 0.3), ("filha", 2.0), ("sil", 0.6)])
    assert len(c.conv.audio) == 0 and "fim" not in c.conv.log


def test_o_audio_do_dono_so_sai_depois_de_confirmado_e_inteiro_desde_o_comeco():
    c = Cena(fim=10)
    c.cn.quadro(quadro("sil"))
    for _ in range(40):                                 # 1,2 s de fala: ainda não deu a janela
        c.cn.quadro(quadro("dono"))
    assert len(c.conv.audio) == 0                       # nada sai antes de confirmar
    c.falar([("dono", 0.6), ("sil", 0.6)])
    enviado = c.enviado()
    assert len(enviado) >= int(1.8 * 16000)             # do começo (com o pre-roll), sem perder
    assert c.conv.log[-1] == "fim"


def test_janela_de_outra_pessoa_no_meio_do_turno_vira_silencio():
    c = Cena(fim=10)
    c.falar([("sil", 0.3), ("dono", 1.5), ("visita", 1.5), ("dono", 1.5), ("sil", 0.6)])
    enviado = c.enviado()
    assert np.abs(enviado).max() <= AMP["dono"]          # nenhuma amostra da visita saiu
    zeros = np.sum(enviado == 0)
    assert zeros >= int(1.4 * 16000)                     # a janela dela virou silêncio
    assert c.conv.log.count("fim") == 1


def test_frase_curta_do_dono_e_conferida_no_fim_e_vai():
    c = Cena(fim=10)
    c.falar([("sil", 0.3), ("dono", 0.9), ("sil", 0.6)])
    assert len(c.conv.audio) > 0 and c.conv.log[-1] == "fim"


# ---- fail-closed ------------------------------------------------------------------

@pytest.mark.parametrize("perfis, aviso", [
    (PerfisFalsos(disponivel=False), cn.AVISO_TRAVA),          # sem modelo / hash errado
    (PerfisFalsos(ativos=set()), cn.AVISO_SEM_ATIVO),           # nenhum perfil ativo
    (PerfisFalsos(explode=True), cn.AVISO_TRAVA),               # erro no quem_fala
])
def test_com_perfil_gravado_a_trava_fecha_e_avisa(perfis, aviso):
    c = Cena(perfis=perfis, fim=10)
    c.falar([("sil", 0.3), ("dono", 3.0), ("sil", 0.6), ("dono", 2.0), ("sil", 0.6)])
    assert len(c.conv.audio) == 0 and "fim" not in c.conv.log
    assert c.avisos == [aviso]                                  # avisa uma vez só
    assert c.cn.estado()["locutor_ativo"] is True


def test_erro_ao_listar_perfis_tambem_fecha():
    class Quebrado(PerfisFalsos):
        def listar(self):
            raise OSError("disco")
    c = Cena(perfis=Quebrado(), fim=10)
    c.falar([("sil", 0.3), ("dono", 2.0), ("sil", 0.6)])
    assert c.cn.trava == "ligada" and len(c.conv.audio) == 0


# ---- pausa para pensar: nenhum som antes do fim real ----------------------------------
# Decisões do árbitro REAL nos clipes de 15/10 (`scripts/medir_turno.py`): a vez fecha
# 0,34-0,64 s depois do fim; no "gagueja" ele fecha 0,33 s depois de "uma pasta nova" e a
# pessoa retoma 1,2 s depois da pausa começar.

CASOS = {
    "completa": ([("dono", 2.2)], [2.2 + 0.36]),
    "hesita_1,5s": ([("dono", 1.6), ("sil", 1.5), ("dono", 0.8), ("sil", 1.0), ("dono", 1.6)],
                    [6.5 + 0.34]),
    "hesita_2,5s": ([("dono", 1.8), ("sil", 2.5), ("dono", 1.6)], [5.9 + 0.64]),
    "gagueja": ([("dono", 3.3), ("sil", 1.2), ("dono", 2.0)], [3.3 + 0.33, 6.5 + 0.38]),
}


@pytest.mark.parametrize("caso", list(CASOS))
def test_nenhum_som_antes_do_fim_real_da_fala(caso):
    roteiro, fins = CASOS[caso]
    c = Cena(fins=[f + 0.3 for f in fins])              # + 0,3 s de silêncio inicial
    c.falar([("sil", 0.3)] + roteiro + [("sil", 3.0)])
    fim_real = 0.3 + sum(s for _, s in roteiro)
    sons = [e for e in c.player.log if e[0] == "tocar"]
    assert sons, "ele tem de responder"
    assert sons[0][1] >= fim_real                       # nada antes do fim de verdade
    assert sons[0][1] - fim_real <= 1.5


def test_gagueira_retomada_descarta_a_resposta_calado_e_segue_o_mesmo_pedido():
    roteiro, fins = CASOS["gagueja"]
    c = Cena(fins=[f + 0.3 for f in fins])
    c.falar([("sil", 0.3)] + roteiro + [("sil", 3.0)])
    assert c.conv.log.count("fim") == 2 and c.conv.log.count("interromper") == 1
    assert c.conv.log.index("interromper") < len(c.conv.log) - 1
    assert len([e for e in c.player.log if e[0] == "tocar"]) == 1


# ---- interrupção ----------------------------------------------------------------

def _tocando_resposta(c):
    c.falar([("sil", 0.3), ("dono", 2.0), ("sil", 2.0)])
    assert c.player.tocando()
    return c.cn._t


def test_dono_por_cima_abaixa_em_ate_0_3s_e_para_em_ate_0_9s():
    c = Cena(fim=10)
    inicio = _tocando_resposta(c)
    n_fim = c.conv.log.count("fim")
    c.falar([("dono", 1.5), ("sil", 0.6)])
    abaixou = [e for e in c.player.log if e[0] == "abaixar" and e[1] > inicio][0]
    parou = [e for e in c.player.log if e[0] == "parar" and e[1] > inicio][0]
    assert abaixou[1] - inicio <= 0.3 and abaixou[2] == cn.ABAIXAR
    assert parou[1] - inicio <= 0.9
    # interrompe ANTES de mandar a fala nova, e a fala nova vira a próxima vez
    log = c.conv.log
    i = log.index("interromper")
    assert "audio" in log[i:] and log.count("fim") == n_fim + 1


def test_outra_pessoa_por_cima_so_abaixa_e_o_volume_volta():
    c = Cena(fim=10)
    inicio = _tocando_resposta(c)
    audio_antes = len(c.conv.audio)
    c.falar([("visita", 2.0), ("sil", 0.6)])
    assert "interromper" not in c.conv.log
    assert not [e for e in c.player.log if e[0] == "parar"]
    voltou = [e for e in c.player.log if e[0] == "restaurar" and e[1] > inicio][0]
    assert voltou[1] - inicio <= cn.ESPERA_CONFIRMAR_S + 0.15     # contado do começo da fala
    assert len(c.conv.audio) == audio_antes            # nada da visita foi enviado


def test_fala_curta_de_outra_pessoa_que_acaba_restaura_o_volume():
    c = Cena(fim=10)
    _tocando_resposta(c)
    c.falar([("visita", 0.4), ("sil", 0.4)])
    assert c.player.log[-1][0] == "restaurar"


# ---- ferramentas: fácil, dúvida, grave, convidado -----------------------------------

def _chamar(c, nome, args, id_="1"):
    c.conv.cb(dc.ChamadaFerramenta(id_, nome, args))
    return c.conv.respostas[-1][1]


def _turno_do(c, quem="dono"):
    c.falar([("sil", 0.3), (quem, 2.0), ("sil", 0.6)])


def test_facil_faz_calado_toca_o_sinal_e_corta_o_que_ele_falaria():
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    r = _chamar(c, "abrir_app", {"nome": "Chrome"})
    assert r == {"ok": True, "silencioso": True}
    assert c.acoes == [("abre o Chrome", "dono", False)]
    assert c.feitos and c.player.log[-1][0] == "tocar"     # o sinal
    n = len(c.player.log)
    c.responder()                                          # "Pronto, abri o Chrome!"
    assert len(c.player.log) == n                          # não tocou
    c.conv.cb(dc.FimResposta())
    assert c.cn._mudo is False


@pytest.mark.parametrize("args", [{"pedido": "apaga aquilo", "clareza": "duvida"}])
def test_duvida_nao_faz_nada_e_manda_perguntar(args):
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    r = _chamar(c, "fazer", args)
    assert r["ok"] is False and "Pergunte" in r["diga"] and c.acoes == []


@pytest.mark.parametrize("nome, args", [
    ("rodar_powershell", {"comando": "rm -rf C:/"}),         # fora da lista
    ("fazer", "abre o chrome"),                              # args não é dict
    ("fazer", {"pedido": "abre", "clareza": "clara", "papel": "dono"}),   # campo a mais
    ("volume", {"nivel": 500}),
    ("volume", {"nivel": True}),
    ("abrir_app", {"nome": ""}),
    ("confirmar", {"resposta": "talvez"}),
])
def test_ferramenta_fora_da_lista_ou_com_args_invalidos_e_descartada(nome, args):
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    r = _chamar(c, nome, args)
    assert r["ok"] is False and c.acoes == []


def test_clara_nao_autoriza_sozinha_o_que_a_politica_manda_confirmar():
    def executar(pedido, papel, confirmado):
        return {"tipo": "confirmar", "fala": "Quer que eu peça ao Claude Code?"}
    c = Cena(fim=10, atraso=99, executar=executar)
    _turno_do(c)
    r = _chamar(c, "fazer", {"pedido": "pede pro Claude revisar o projeto", "clareza": "clara"})
    assert r["precisa_confirmacao"] is True and r["feito"] is False


def test_pedido_gerado_por_resultado_de_ferramenta_sempre_pede_confirmacao():
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    _chamar(c, "hora", {})
    r = _chamar(c, "abrir_app", {"nome": "Chrome"}, id_="2")
    assert r["precisa_confirmacao"] is True
    assert c.acoes == [("que horas são", "dono", False)]   # o segundo não rodou


def test_confirmacao_so_vale_com_um_sim_novo_do_dono():
    def executar(pedido, papel, confirmado):
        acoes.append((pedido, papel, confirmado))
        return {"tipo": "delegado"} if confirmado else {"tipo": "confirmar"}
    acoes = []
    c = Cena(fim=10, atraso=99, executar=executar)
    _turno_do(c)
    r = _chamar(c, "fazer", {"pedido": "pede pro Codex olhar o projeto", "clareza": "clara"})
    assert r["precisa_confirmacao"]
    # o modelo "confirma" sozinho, sem o dono falar de novo: nada
    assert _chamar(c, "confirmar", {"resposta": "sim"}, id_="2")["ok"] is False
    assert acoes == [("pede pro Codex olhar o projeto", "dono", False)]
    # de novo, agora com o dono dizendo sim numa vez nova
    _chamar(c, "fazer", {"pedido": "pede pro Codex olhar o projeto", "clareza": "clara"}, id_="3")
    _turno_do(c)
    c.conv.cb(dc.TextoEntrada("sim, pode"))
    r = _chamar(c, "confirmar", {"resposta": "sim"}, id_="4")
    assert r == {"ok": True, "silencioso": True, "encaminhado": True}
    assert acoes[-1] == ("pede pro Codex olhar o projeto", "dono", True)


def test_sim_que_a_transcricao_nao_confirma_nao_vale():
    c = Cena(fim=10, atraso=99, executar=lambda p, pa, conf: {"tipo": "confirmar"})
    _turno_do(c)
    _chamar(c, "fazer", {"pedido": "pede pro Claude apagar a pasta", "clareza": "clara"})
    _turno_do(c)
    c.conv.cb(dc.TextoEntrada("o que você acha disso"))
    assert _chamar(c, "confirmar", {"resposta": "sim"}, id_="2")["ok"] is False


def test_convidado_so_faz_o_facil_e_recebe_recusa_no_resto():
    perfis = PerfisFalsos(perfis=(("André", "dono"), ("Lia", "convidado")))
    respostas = {"abre o Chrome": {"tipo": "facil"}, "pede pro Claude revisar": {"tipo": "confirmar"},
                 "apaga a pasta fotos": {"tipo": "grave"}, "entra no servidor": {"tipo": "recusado"}}
    vistos = []

    def executar(pedido, papel, confirmado):
        vistos.append(papel)
        return respostas[pedido]
    c = Cena(perfis=perfis, fim=10, atraso=99, executar=executar)
    _turno_do(c, "filha")
    assert _chamar(c, "abrir_app", {"nome": "Chrome"})["silencioso"] is True
    for i, pedido in enumerate(["pede pro Claude revisar", "apaga a pasta fotos",
                                "entra no servidor"]):
        _turno_do(c, "filha")
        r = _chamar(c, "fazer", {"pedido": pedido, "clareza": "clara"}, id_=str(i + 2))
        assert r["ok"] is False and r["diga"] == cn.RECUSA_CONVIDADO
    assert set(vistos) == {"convidado"}                    # o papel veio da voz, não do modelo


def test_grave_pela_voz_direta_vai_para_o_cartao_com_clique():
    import dervs
    mostrados, rodados = [], []
    ficha = {"modo": "planejar", "fala": "Vou apagar.", "passos": [
        {"descricao": "x", "comando": "rm -rf C:/Users/x/Documents", "risco": "destrutivo",
         "toca_alvo": False}]}

    def executar(pedido, papel, confirmado):
        return cn.acao_por_texto(
            pedido, papel, confirmado, atalho=lambda t: None, especial=lambda t: False,
            planejar=lambda t: ficha,
            pede_confirmacao=lambda p: dervs.plano_pede_confirmacao(p, "grave"),
            rodar_plano=rodados.append, mostrar_plano=mostrados.append, delegar=None)
    c = Cena(fim=10, atraso=99, executar=executar)
    _turno_do(c)
    r = _chamar(c, "fazer", {"pedido": "apaga meus documentos", "clareza": "clara"})
    assert r["aguardando_clique"] is True and rodados == []
    assert mostrados and mostrados[0]["fala"] == ""


# ---- política pura (o adaptador do app) ------------------------------------------

def _acao(pedido, papel="dono", confirmado=False, atalho=None, especial=False, ficha=None,
          grave=False):
    log = []
    r = cn.acao_por_texto(
        pedido, papel, confirmado, atalho=lambda t: atalho,
        especial=lambda t: especial, planejar=lambda t: log.append("cerebro") or ficha,
        pede_confirmacao=lambda p: grave, rodar_plano=lambda f: log.append(("rodar", f)),
        mostrar_plano=lambda f: log.append(("mostrar", f)),
        delegar=lambda t: log.append(("delegar", t)))
    return r, log


PLANO = {"modo": "planejar", "fala": "Beleza, abrindo.", "passos": [{"comando": "explorer"}]}


def test_acao_facil_roda_o_plano_calado_e_sem_o_cerebro_comentar():
    r, log = _acao("abre o chrome", atalho=PLANO)
    assert r["tipo"] == "facil" and log[0][0] == "rodar"
    assert log[0][1]["fala"] == "" and log[0][1]["local"] is True


def test_acao_hora_e_resposta_falada():
    r, _ = _acao("que horas são", atalho={"modo": "conversar", "fala": "São três horas."})
    assert r == {"tipo": "resposta", "fala": "São três horas."}


def test_acao_especial_claude_codex_so_com_confirmacao():
    r, log = _acao("pede pro Claude revisar", especial=True)
    assert r["tipo"] == "confirmar" and log == []
    r, log = _acao("pede pro Claude revisar", especial=True, confirmado=True)
    assert r["tipo"] == "delegado" and log == [("delegar", "pede pro Claude revisar")]


def test_acao_convidado_nao_chega_ao_cerebro_nem_ao_roteador():
    r, log = _acao("cria uma pasta", papel="convidado", ficha=PLANO, especial=True)
    assert r["tipo"] == "recusado" and log == []
    r, log = _acao("abre o chrome", papel="convidado", atalho=PLANO, grave=True)
    assert r["tipo"] == "recusado" and not [x for x in log if x[0] in ("rodar", "mostrar")]


def test_acao_papel_desconhecido_e_recusado():
    assert _acao("abre", papel=None, atalho=PLANO)[0]["tipo"] == "recusado"


# ---- troca e queda do motor -----------------------------------------------------

def test_troca_de_motor_vira_aviso_curto():
    c = Cena(fim=10)
    c.conv.cb(dc.Troca("gemini_live", "cascata", "limite"))
    assert c.avisos == ["Mudei a voz para o modo econômico."]


def test_motor_caido_volta_ao_caminho_antigo_com_aviso():
    c = Cena(fim=10)
    c.conv.cb(dc.Erro("limite", "Nenhum motor de conversa disponível agora."))
    assert c.caidas == ["limite"] and cn.AVISO_CAIU in c.avisos
    assert c.cn.quadro(quadro("dono")) is False          # o quadro volta para o Endpointer
    assert "encerrar" in c.conv.log


def test_motor_que_nem_sobe_cai_para_o_antigo():
    caidas = []
    x = cn.ConversaNatural({}, PlayerFalso(), PerfisFalsos(), ArbitroFalso(),
                           lambda cb: (_ for _ in ()).throw(RuntimeError("sem rede")),
                           lambda *a: None, lambda t: None, ao_cair=caidas.append)
    assert x.iniciar() is False and caidas == ["não subiu"]


# ---- perfis pelo painel -------------------------------------------------------------

def extrator_falso(audio):
    esp = np.abs(np.fft.rfft(audio))
    f = np.fft.rfftfreq(len(audio), 1 / 16000)
    return np.array([esp[(f >= a) & (f < b)].sum() for a, b in
                     [(0, 200), (200, 300), (300, 400), (400, 600), (600, 900), (900, 1500),
                      (1500, 3000), (3000, 8000)]], np.float32) + 1e-3


def tom(freq, seg):
    t = np.arange(int(16000 * seg)) / 16000
    return (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class CnFalsa:
    def __init__(self, recente):
        self.recente = recente
        self.atualizou = 0
        self.janelas = []

    def dono_confirmado_recente(self, janela_s=None):
        self.janelas.append(janela_s)
        return self.recente

    def atualizar_trava(self):
        self.atualizou += 1


def test_vozes_gravar_listar_ativar_apagar(tmp_path):
    perfis = L.Perfis(str(tmp_path / "vozes"), extrator=extrator_falso)
    progresso = []
    v = cn.Vozes(perfis, gravar_audio=lambda s, p: (p(1.0), tom(250, 20))[1])
    assert v.gravar("André", "dono", progresso=progresso.append)["ok"] is True   # 1º dono
    assert progresso == [1.0]
    assert v.listar() == [{"nome": "André", "papel": "dono", "ativo": True}]
    v._conversa = lambda: CnFalsa(recente=True)         # mexer em dono exige dono confirmado
    assert v.ativar("André", False)["perfil"]["ativo"] is False
    v._conversa = lambda: None
    assert v.estado()["locutor_aviso"] == "nenhum perfil ativo"
    assert v.estado()["dono_confirmado"] is False       # sem conversa, ninguém confirmou o dono
    assert sorted(p.name for p in (tmp_path / "vozes" / "andre").iterdir()) == \
        ["perfil.json", "voz.bin"]                         # só a impressão (cifrada)
    v._conversa = lambda: CnFalsa(recente=True)
    assert v.apagar("André") == {"ok": True}
    v._conversa = lambda: None
    assert not (tmp_path / "vozes" / "andre").exists()
    # já houve perfil: zerar NÃO abre a trava (antes voltava a "grave sua voz" e ouvia todo mundo)
    e = v.estado()
    assert e["locutor_aviso"] == "grave sua voz de novo" and e["locutor_ativo"] is True


def test_novo_dono_so_de_sessao_confirmada_como_dono(tmp_path):
    perfis = L.Perfis(str(tmp_path / "vozes"), extrator=extrator_falso)
    perfis.gravar("André", "dono", tom(250, 20))
    sessao = CnFalsa(recente=False)
    v = cn.Vozes(perfis, conversa=lambda: sessao, gravar_audio=lambda s, p: tom(700, 20))
    r = v.gravar("Outro", "dono")
    assert r["ok"] is False and "dono já cadastrado" in r["erro"]
    assert v.gravar("Lia", "convidado")["ok"] is True     # convidado pode
    sessao.recente = True
    assert v.gravar("Outro", "dono")["ok"] is True
    assert sessao.atualizou == 2


def test_dono_confirmado_recente_vem_da_trava_de_voz():
    c = Cena(fim=10)
    assert c.cn.dono_confirmado_recente() is False
    _turno_do(c)
    assert c.cn.dono_confirmado_recente() is True


def test_gravador_junta_os_quadros_e_avisa_o_progresso():
    prog = []
    g = cn.Gravador(segundos=0.3, progresso=prog.append)
    for _ in range(12):
        g.quadro(quadro("dono"))
    assert g.pronto.is_set() and prog[-1] == 1.0
    assert len(g.audio()) == 10 * 480


# ---- player em fluxo ------------------------------------------------------------

class StreamFalso:
    def __init__(self, cb):
        self.cb = cb
        self.fechado = False

    def bloco(self, n=480):
        buf = bytearray(n * 2)
        self.cb(memoryview(buf), n, None, None)
        return np.frombuffer(bytes(buf), np.int16)

    def abort(self):
        pass

    def close(self):
        self.fechado = True


def test_player_toca_conforme_chega_abaixa_na_hora_e_para():
    fluxos = []
    p = cn.PlayerFluxo(stream_fabrica=lambda cb: fluxos.append(StreamFalso(cb)) or fluxos[-1])
    p.tocar((np.ones(4800, np.int16) * 1000).tobytes())
    s = fluxos[0]
    assert p.tocando() and s.bloco()[-1] == 1000
    p.abaixar(0.3)
    assert s.bloco()[-1] == 300                           # vale no bloco seguinte (20 ms)
    p.restaurar()
    assert s.bloco()[-1] == 1000
    p.parar()
    assert not p.tocando() and s.bloco().max() == 0
    p.fechar()
    assert s.fechado


def test_player_reamostra_16k_para_24k():
    fluxos = []
    p = cn.PlayerFluxo(stream_fabrica=lambda cb: fluxos.append(StreamFalso(cb)) or fluxos[-1])
    p.tocar(np.ones(1600, np.int16).tobytes(), taxa=16000)
    assert sum(len(x) for x in p._fila) == 2400


def test_sinal_feito_e_curto_suave_e_fica_em_cache(tmp_path):
    arq = tmp_path / "sons" / "sinal_feito.wav"
    pcm = cn.carregar_sinal(str(arq))
    x = np.frombuffer(pcm, np.int16)
    assert arq.exists() and 0.15 <= len(x) / 24000 <= 0.35 and np.abs(x).max() < 8000
    assert cn.carregar_sinal(str(arq)) == pcm


def test_motor_disponivel_so_olha_se_a_chave_existe():
    conf = {"conversa_motores": ["gemini_live", "cascata"]}
    assert cn.motor_disponivel(conf, segredo=lambda n: "x" if n == "GROQ_API_KEY" else None)
    assert not cn.motor_disponivel(conf, segredo=lambda n: None)


def test_sistema_pede_frases_curtas_pergunta_na_duvida_e_proibe_o_entendi_vou():
    s = cn.SISTEMA
    assert "português do Brasil" in s and "curtas" in s and "Entendi: vou" in s
    assert "pergunte" in s and "silencioso=true" in s
    assert {f["name"] for f in cn.FERRAMENTAS} == {"fazer", "abrir_app", "hora", "volume",
                                                    "abrir_pasta", "confirmar"}


def test_calar_do_atalho_interrompe_a_resposta_em_curso():
    c = Cena(fim=10)
    _tocando_resposta(c)
    c.cn.calar()
    assert c.conv.log[-1] == "interromper" and not c.player.tocando()


def test_resposta_retida_sai_pelo_tique_quando_o_microfone_para():
    relogio = [0.0]
    c = Cena(fim=10, atraso=99)
    c.cn._relogio = lambda: relogio[0]
    _turno_do(c)
    c.responder()                                          # chegou no meio da espera
    assert not [e for e in c.player.log if e[0] == "tocar"]
    relogio[0] += 1.0                                      # o atalho fechou o microfone
    c.cn.tique()
    assert [e for e in c.player.log if e[0] == "tocar"]


# ---- dentro do app (Qt): ligar, cair, ganchos da escuta, painel -------------------

_APP = []


def _qt():
    """A QApplication fica viva até o fim da suíte (coletada, o Qt derruba o processo)."""
    pytest.importorskip("PyQt6", reason="o motor é Qt")
    from PyQt6 import QtWidgets
    if not _APP:
        _APP.append(QtWidgets.QApplication.instance() or QtWidgets.QApplication([]))
    return _APP[0]


class _SinalNulo:
    def connect(self, *a, **k):
        pass


class EscutaFalsa:
    def __init__(self):
        self.fala = self.mudo = self.som_voltou = self.nivel = self.finished = _SinalNulo()
        self.pausado = False
        self.desvio = self.gravacao = None

    def start(self):
        pass

    def parar(self):
        pass


class PonteFalsa:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        if nome.startswith("__"):
            raise AttributeError(nome)
        return lambda *a, **k: self.chamadas.append((nome, a))


@pytest.fixture
def motor_app(monkeypatch):
    _qt()
    import dervs
    import dervs_electron
    monkeypatch.setattr(dervs.cfg, "gravar", lambda chave, valor: True)
    m = dervs_electron.Motor(PonteFalsa())
    m.voz.ligada = False
    m.escuta = EscutaFalsa()
    yield m
    m.escuta = None
    dervs.encerrar_tudo(m)


def _acordar_app(m):
    """O que o app faz ao ouvir o nome (ou o atalho apertado): acorda e liga a voz direta."""
    m._acordar(novo=True)
    m._cn_ligar()


def _cn_do_app(monkeypatch, cena_kw=None):
    cenas = []

    def criar(conf, executar_acao, avisar, arbitro=None, **kw):
        c = Cena(fim=10, **(cena_kw or {}))
        c.cn._avisar, c.cn._ao_cair, c.cn._ao_turno = avisar, kw["ao_cair"], kw["ao_turno"]
        cenas.append(c)
        return c.cn
    monkeypatch.setattr(cn, "motor_disponivel", lambda conf: True)
    monkeypatch.setattr(cn, "criar_padrao", criar)
    return cenas


def test_app_ao_acordar_a_voz_direta_assume_o_microfone(motor_app, monkeypatch):
    cenas = _cn_do_app(monkeypatch)
    _acordar_app(motor_app)
    assert motor_app._cn is cenas[0].cn and motor_app.escuta.desvio == cenas[0].cn.quadro


def test_app_sem_chave_de_motor_fica_no_caminho_antigo(motor_app, monkeypatch):
    monkeypatch.setattr(cn, "motor_disponivel", lambda conf: False)
    _acordar_app(motor_app)
    assert motor_app._cn is None and motor_app.escuta.desvio is None


def test_app_motor_caido_volta_ao_caminho_antigo_com_aviso(motor_app, monkeypatch):
    import time as _time
    cenas = _cn_do_app(monkeypatch)
    _acordar_app(motor_app)
    cenas[0].conv.cb(dc.Erro("rede", "sem rede"))
    assert motor_app._cn is None and motor_app.escuta.desvio is None
    assert motor_app._cn_bloqueada_ate > _time.time() + 500
    falas = [a for nome, a in motor_app.ponte.chamadas if nome == "enviar_fala"]
    assert any(cn.AVISO_CAIU in str(a) for a in falas)
    _acordar_app(motor_app)                         # não tenta de novo logo em seguida
    assert motor_app._cn is None


def test_app_dormiu_desliga_a_voz_direta(motor_app, monkeypatch):
    cenas = _cn_do_app(monkeypatch)
    _acordar_app(motor_app)
    motor_app._desperto_ate = 0.0
    motor_app._cn_vigiar()
    assert motor_app._cn is None and "encerrar" in cenas[0].conv.log


def test_app_frase_que_acordou_vira_a_primeira_vez_da_conversa(motor_app, monkeypatch):
    cenas = _cn_do_app(monkeypatch, {"perfis": PerfisFalsos(perfis=())})
    motor_app._cn_pcm = quadro("dono") * 40
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert cenas and cenas[0].conv.log[-1] == "fim" and len(cenas[0].conv.audio) == 960 * 40


def test_app_plano_grave_da_voz_direta_vai_para_o_cartao(motor_app, monkeypatch):
    cartoes, rodados = [], []
    monkeypatch.setattr(motor_app, "_confirmar_plano", lambda: cartoes.append(list(motor_app.plano)))
    monkeypatch.setattr(motor_app, "_processar_passo", lambda: rodados.append(1))
    grave = {"modo": "planejar", "fala": "", "local": True, "passos": [
        {"descricao": "x", "comando": "rm -rf C:/Users/x/Documents", "risco": "destrutivo",
         "toca_alvo": False}]}
    motor_app._cn_tratar("plano", grave)
    assert cartoes and rodados == []
    facil = {"modo": "planejar", "fala": "", "local": True, "passos": [
        {"descricao": "x", "comando": "notepad", "risco": "reversivel", "toca_alvo": False}]}
    motor_app._cn_tratar("plano", facil)
    assert rodados == [1]


def test_app_slot_da_conversa_natural_nao_derruba_o_app(motor_app, monkeypatch):
    monkeypatch.setattr(motor_app, "_cerebro_respondeu", lambda f: 1 / 0)
    motor_app._cn_tratar("plano", {})                      # exceção engolida e registrada


def test_app_especial_claude_codex_pede_confirmacao(motor_app):
    assert motor_app._cn_especial("pede pro claude code revisar o projeto dervs") is True
    assert motor_app._cn_especial("abre o bloco de notas") is False


def test_escuta_entrega_o_quadro_ao_gancho_e_volta_ao_endpointer_se_ele_cair(monkeypatch):
    _qt()
    import dervs
    quadros = [quadro("dono")] * 60 + [quadro("sil")] * 60

    class MicFalso:
        def __init__(self):
            self.i = 0

        def abrir(self):
            pass

        def ler(self):
            if self.i >= len(quadros):
                escuta._rodando = False
                return b""
            self.i += 1
            return quadros[self.i - 1]

        def motivo_da_queda(self):
            return ""

        def fechar(self):
            pass

    monkeypatch.setattr(dervs, "Microfone", MicFalso)
    monkeypatch.setattr(dervs, "salvar_wav", lambda pcm, caminho: None)
    escuta = dervs.Escuta()
    vistos, falas = [], []
    escuta.fala.connect(falas.append)
    escuta.desvio = lambda q: vistos.append(q) or True
    escuta.run()
    assert len(vistos) == 120 and falas == []              # nada foi para o caminho antigo
    escuta.desvio = lambda q: False                        # a conversa caiu
    escuta.run()
    assert len(falas) == 1                                 # o Endpointer fechou a frase


def test_painel_vozes_vai_e_volta_pela_ponte(motor_app, monkeypatch):
    import time as _time
    monkeypatch.setattr(motor_app, "vozes_apagar", lambda nome: {"ok": True})
    monkeypatch.setattr(motor_app, "vozes_listar", lambda: [])
    monkeypatch.setattr(motor_app, "conversa_estado", lambda: {"locutor_aviso": "grave sua voz"})
    motor_app.tratar_vozes("vozes_apagar", {"nome": "Lia"})
    fim = _time.monotonic() + 2
    while _time.monotonic() < fim and not any(n == "enviar_vozes" for n, _ in motor_app.ponte.chamadas):
        _time.sleep(0.01)
    msg = [a for n, a in motor_app.ponte.chamadas if n == "enviar_vozes"][0][0]
    assert msg["resultado"] == {"ok": True} and msg["estado"]["locutor_aviso"] == "grave sua voz"


def test_conversa_estado_sem_sessao_vem_dos_perfis(motor_app, tmp_path):
    motor_app._vozes = cn.Vozes(L.Perfis(str(tmp_path / "vozes"), extrator=extrator_falso))
    assert motor_app.conversa_estado() == {"motor_ativo": None, "motor_nome": None,
                                           "locutor_ativo": False, "perfis_ativos": [],
                                           "locutor_aviso": "grave sua voz",
                                           "dono_confirmado": False}


@pytest.mark.parametrize("linha, esperado", [
    ({"verbo": "vozes_pedir"}, ("vozes_pedir", {})),
    ({"verbo": "vozes_gravar", "nome": " Lia ", "papel": "convidado"},
     ("vozes_gravar", {"nome": "Lia", "papel": "convidado"})),
    ({"verbo": "vozes_ativar", "nome": "Lia", "ativo": False},
     ("vozes_ativar", {"nome": "Lia", "ativo": False})),
    ({"verbo": "vozes_apagar", "nome": "Lia"}, ("vozes_apagar", {"nome": "Lia"})),
    ({"verbo": "vozes_gravar", "nome": "Lia", "papel": "admin"}, None),
    ({"verbo": "vozes_ativar", "nome": "Lia", "ativo": "false"}, None),
    ({"verbo": "vozes_apagar", "nome": "x" * 41}, None),
    ({"verbo": "vozes_apagar", "nome": 3}, None),
])
def test_ponte_valida_os_verbos_de_vozes(linha, esperado):
    import json
    import dervs_ponte_electron as ponte_mod
    vistos = []
    p = ponte_mod.PonteElectron(ao_sair=lambda: None, ao_plano=lambda *a: None,
                                ao_pronto=lambda: None, ao_vozes=lambda v, d: vistos.append((v, d)))
    p._processar_linha(json.dumps(linha).encode())
    assert vistos == ([esperado] if esperado else [])


def test_ponte_enviar_vozes_escreve_o_verbo():
    import dervs_ponte_electron as ponte_mod
    p = ponte_mod.PonteElectron(ao_sair=lambda: None, ao_plano=lambda *a: None,
                                ao_pronto=lambda: None)
    escritos = []
    p._escrever = escritos.append
    p.enviar_vozes({"gravando": 0.5, "lista": [{"nome": "Lia", "papel": "convidado", "ativo": True}]})
    assert escritos == [{"verbo": "vozes", "gravando": 0.5,
                         "lista": [{"nome": "Lia", "papel": "convidado", "ativo": True}]}]


def test_chamada_marcada_pelo_motor_como_vinda_de_ferramenta_pede_confirmacao():
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    c.conv.cb(dc.ChamadaFerramenta("9", "abrir_app", {"nome": "Chrome"}, "ferramenta"))
    r = c.conv.respostas[-1][1]
    assert r["precisa_confirmacao"] is True and c.acoes == []


# ---- revisão de 15/10: saída de áudio, stream depois do desligamento ------------------

def _fabrica_que_quebra(cb):
    raise OSError("sem dispositivo de saída")


def _tocar_que_quebra(pcm, taxa=24000):
    raise OSError("sem dispositivo de saída")


def test_player_que_nao_abre_limpa_a_fila_e_propaga_o_erro():
    p = cn.PlayerFluxo(stream_fabrica=_fabrica_que_quebra)
    with pytest.raises(OSError):
        p.tocar(b"\x01\x00" * 100)
    assert not p._fila and not p.tocando()


def test_player_so_esta_tocando_com_o_stream_aberto():
    p = cn.PlayerFluxo(stream_fabrica=lambda cb: StreamFalso(cb))
    p._fila.append(np.ones(10, np.int16))               # fila cheia, mas ninguém para tocar
    assert p.tocando() is False


def test_player_fechado_ignora_o_pcm_e_nao_reabre_o_stream():
    abertos = []
    p = cn.PlayerFluxo(stream_fabrica=lambda cb: abertos.append(1) or StreamFalso(cb))
    p.fechar()
    p.tocar(b"\x01\x00" * 100)
    assert abertos == [] and not p.tocando()


def test_saida_de_audio_quebrada_derruba_para_o_caminho_antigo():
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    c.falar([("sil", 1.5)])                             # passou a pausa para pensar
    c.player.tocar = _tocar_que_quebra
    c.responder()
    assert c.caidas == ["saída de áudio"] and c.cn.falhou
    assert cn.AVISO_CAIU in c.avisos


def test_saida_quebrada_na_resposta_retida_tambem_derruba():
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    c.responder()                                       # retida: ele ainda "pensa"
    assert c.cn._retido
    c.player.tocar = _tocar_que_quebra
    c.cn._relogio = lambda: 99.0
    c.cn.tique()
    assert c.caidas == ["saída de áudio"]


def test_conversa_que_falhou_nao_fica_ocupada_para_sempre():
    c = Cena(fim=10, atraso=99)
    _turno_do(c)
    assert c.cn.ocupado() is True                       # esperando a resposta
    c.cn._cair("teste")
    assert c.cn.ocupado() is False


def test_ferramenta_que_termina_depois_do_desligamento_nao_toca_o_sinal():
    c = Cena(fim=10, atraso=99, executar=lambda p, pa, conf: (c.cn.encerrar(), {"tipo": "facil"})[1])
    _turno_do(c)
    antes = len(c.player.log)
    c.conv.cb(dc.ChamadaFerramenta("1", "abrir_app", {"nome": "Chrome"}))
    assert not [e for e in c.player.log[antes:] if e[0] == "tocar"]
    assert c.feitos == []


# ---- revisão de segurança de 15/10: trava de voz, papel do turno, confirmação ---------

class PerfisPorMistura(PerfisFalsos):
    """Reconhece o dono quando há pouco som de visita na amostra: a mistura 50/50 (janela da
    visita + o contexto do dono) ainda passa, a visita sozinha não."""

    def quem_fala(self, audio):
        self.chamadas += 1
        visita = float(np.mean(np.abs(audio) * 32768 > 4500))
        return (self.lista[0], 0.9) if visita < 0.3 else (None, 0.1)


class PerfisPeloFim(PerfisFalsos):
    """Julga só os últimos 1,4 s: o contexto de antes não pesa (cada janela vale por si)."""

    def quem_fala(self, audio):
        return super().quem_fala(audio[-int(1.4 * 16000):])


def test_janela_de_visita_colada_na_do_dono_nao_passa_pelo_contexto():
    c = Cena(perfis=PerfisPorMistura(), fim=10)
    c.falar([("sil", 0.3), ("dono", 1.5), ("visita", 1.5), ("sil", 0.6)])
    enviado = c.enviado()
    assert len(enviado) > 0 and np.abs(enviado).max() <= AMP["dono"]    # nada da visita saiu
    assert np.sum(enviado == 0) >= int(1.4 * 16000)                      # virou silêncio


PERFIS_DONO_E_CONVIDADO = (("André", "dono"), ("Lia", "convidado"))


@pytest.mark.parametrize("roteiro", [
    [("dono", 1.5), ("filha", 1.5), ("sil", 0.6)],
    [("filha", 1.5), ("dono", 1.5), ("sil", 0.6)],
    [("filha", 1.5), ("sil", 0.4), ("dono", 1.5), ("sil", 0.6)],     # retoma antes de ele soar
])
def test_papel_do_turno_e_o_de_menor_privilegio_entre_as_janelas(roteiro):
    c = Cena(perfis=PerfisPeloFim(perfis=PERFIS_DONO_E_CONVIDADO), fim=10, atraso=99)
    c.falar([("sil", 0.3)] + roteiro)
    c.conv.cb(dc.ChamadaFerramenta("1", "abrir_app", {"nome": "Chrome"}))
    assert c.acoes[-1][1] == "convidado"
    assert c.cn.dono_confirmado_recente() is False


def test_turno_novo_comeca_de_novo_o_papel_nao_herda_o_do_anterior():
    c = Cena(perfis=PerfisPeloFim(perfis=PERFIS_DONO_E_CONVIDADO), fim=10, atraso=99)
    c.falar([("sil", 0.3), ("filha", 1.5), ("sil", 0.6)])
    c.conv.cb(dc.FimResposta())                               # a resposta dele já acabou
    c.falar([("sil", 1.0), ("dono", 1.5), ("sil", 0.6)])
    c.conv.cb(dc.ChamadaFerramenta("1", "abrir_app", {"nome": "Chrome"}))
    assert c.acoes[-1][1] == "dono"


def _pedido_codex(acoes):
    def executar(pedido, papel, confirmado):
        acoes.append((pedido, papel, confirmado))
        return {"tipo": "delegado"} if confirmado else {"tipo": "confirmar"}
    return executar


def test_pedido_que_espera_confirmacao_aparece_no_pc_com_o_texto_exato():
    c = Cena(fim=10, atraso=99, executar=_pedido_codex([]))
    _turno_do(c)
    _chamar(c, "fazer", {"pedido": "pede pro Codex apagar a pasta fotos", "clareza": "clara"})
    assert c.pedidos == ["pede pro Codex apagar a pasta fotos"]


def test_sim_so_vale_na_vez_logo_depois_do_pedido():
    acoes = []
    c = Cena(fim=10, atraso=99, executar=_pedido_codex(acoes))
    _turno_do(c)
    _chamar(c, "fazer", {"pedido": "pede pro Codex olhar o projeto", "clareza": "clara"})
    _turno_do(c)                                              # outra conversa no meio
    _turno_do(c)
    c.conv.cb(dc.TextoEntrada("sim, pode"))
    r = _chamar(c, "confirmar", {"resposta": "sim"}, id_="2")
    assert r["ok"] is False and all(a[2] is False for a in acoes)


def test_sim_transcrito_durante_a_fala_nao_se_perde_no_fim_da_vez():
    acoes = []
    c = Cena(fim=10, atraso=99, executar=_pedido_codex(acoes))
    _turno_do(c)
    _chamar(c, "fazer", {"pedido": "pede pro Codex olhar o projeto", "clareza": "clara"})
    c.falar([("sil", 0.3), ("dono", 1.0)])
    c.conv.cb(dc.TextoEntrada("sim, pode"))                   # a transcrição chega antes do fim
    c.falar([("dono", 1.0), ("sil", 0.6)])
    r = _chamar(c, "confirmar", {"resposta": "sim"}, id_="2")
    assert r == {"ok": True, "silencioso": True, "encaminhado": True}


def test_transcricao_de_um_turno_antigo_nao_confirma_o_turno_novo():
    acoes = []
    c = Cena(fim=10, atraso=99, executar=_pedido_codex(acoes))
    _turno_do(c)
    c.conv.cb(dc.TextoEntrada("sim"))                         # sobra do turno do pedido
    _chamar(c, "fazer", {"pedido": "pede pro Codex olhar o projeto", "clareza": "clara"})
    c.conv.cb(dc.FimResposta())
    _turno_do(c)                                              # a pessoa não disse sim
    r = _chamar(c, "confirmar", {"resposta": "sim"}, id_="2")
    assert r["ok"] is False and all(a[2] is False for a in acoes)


# ---- mexer em perfil de dono e zerar os perfis ----------------------------------------

def _vozes_com_dono_e_convidado(tmp_path, sessao, conf=None):
    perfis = L.Perfis(str(tmp_path / "vozes"), extrator=extrator_falso)
    perfis.gravar("André", "dono", tom(250, 20))
    perfis.gravar("Lia", "convidado", tom(700, 20))
    return perfis, cn.Vozes(perfis, conversa=lambda: sessao, conf=conf)


@pytest.mark.parametrize("sessao", [None, CnFalsa(recente=False)])
def test_apagar_ou_desativar_dono_exige_dono_confirmado_recente(tmp_path, sessao):
    perfis, v = _vozes_com_dono_e_convidado(tmp_path, sessao)
    r = v.apagar("André")
    assert r["ok"] is False and "dono" in r["erro"] and "fale comigo" in r["erro"]
    r = v.ativar("André", False)
    assert r["ok"] is False and "dono" in r["erro"]
    assert [(p.nome, p.ativo) for p in perfis.listar()] == [("André", True), ("Lia", True)]


def test_dono_confirmado_nos_ultimos_5_minutos_pode_apagar_e_desativar(tmp_path):
    sessao = CnFalsa(recente=True)
    perfis, v = _vozes_com_dono_e_convidado(tmp_path, sessao)
    assert v.ativar("André", False)["ok"] is True
    assert v.apagar("André") == {"ok": True}
    assert set(sessao.janelas) == {300}                  # a janela é de 5 min, não os 10 min


def test_convidado_e_ativar_nao_pedem_dono(tmp_path):
    perfis, v = _vozes_com_dono_e_convidado(tmp_path, CnFalsa(recente=False))
    assert v.ativar("Lia", False)["ok"] is True
    assert v.ativar("Lia", True)["ok"] is True
    assert v.apagar("Lia") == {"ok": True}


def test_trava_explicitamente_desligada_na_config_libera_mexer_em_dono(tmp_path):
    perfis, v = _vozes_com_dono_e_convidado(tmp_path, None, conf={"locutor_ligado": False})
    assert v.apagar("André") == {"ok": True}


class PerfisZerados(PerfisFalsos):
    """Já teve perfil, hoje não tem nenhum."""

    def ja_teve_perfil(self):
        return True


def test_zerar_os_perfis_mantem_a_trava_fechada_e_pede_para_gravar_de_novo():
    c = Cena(perfis=PerfisZerados(perfis=()), fim=10)
    c.falar([("sil", 0.3), ("dono", 3.0), ("sil", 0.6)])
    assert len(c.conv.audio) == 0 and "fim" not in c.conv.log
    assert c.avisos == [cn.AVISO_REGRAVAR]
    e = c.cn.estado()
    assert e["locutor_ativo"] is True and e["locutor_aviso"] == "grave sua voz de novo"


def test_zerar_os_perfis_com_a_trava_desligada_na_config_abre():
    c = Cena(perfis=PerfisZerados(perfis=()), fim=10, conf={"locutor_ligado": False})
    c.falar([("sil", 0.3), ("dono", 1.0), ("sil", 0.6)])
    assert len(c.conv.audio) > 0 and c.cn.estado()["locutor_aviso"] == "trava de voz desligada"


def test_perfis_lembra_que_ja_teve_perfil_mesmo_depois_de_apagar(tmp_path):
    perfis = L.Perfis(str(tmp_path / "vozes"), extrator=extrator_falso)
    assert perfis.ja_teve_perfil() is False
    perfis.gravar("André", "dono", tom(250, 20))
    assert perfis.apagar("André") is True
    assert perfis.listar() == [] and perfis.ja_teve_perfil() is True
    assert L.Perfis(str(tmp_path / "vozes")).ja_teve_perfil() is True     # sobrevive ao reinício


def test_perfil_de_antes_do_marcador_tambem_conta_como_ja_teve(tmp_path):
    perfis = L.Perfis(str(tmp_path / "vozes"), extrator=extrator_falso)
    perfis.gravar("André", "dono", tom(250, 20))
    (tmp_path / "vozes" / ".ja_teve_perfil").unlink()          # gravado por versão antiga
    assert L.Perfis(str(tmp_path / "vozes")).listar() != []
    perfis.apagar("André")
    assert L.Perfis(str(tmp_path / "vozes")).ja_teve_perfil() is True


# ---- revisão de 15/10 dentro do app: queda sem resposta, gancho, plano grave -----------

def test_app_queda_antes_de_qualquer_som_refaz_a_frase_que_acordou_no_caminho_antigo(
        motor_app, monkeypatch):
    cenas = _cn_do_app(monkeypatch, {"perfis": PerfisFalsos(perfis=())})
    rodados = []
    monkeypatch.setattr(motor_app, "executar", lambda: rodados.append(motor_app.entrada.toPlainText()))
    motor_app._cn_pcm = quadro("dono") * 40
    motor_app._entrada_continua("DERVS, abre o Chrome")
    cenas[0].conv.cb(dc.Erro("rede", "sem rede"))          # o motor caiu antes de qualquer som
    assert motor_app._cn is None and rodados == ["abre o Chrome"]


def test_app_queda_depois_de_resposta_nao_repete_a_frase(motor_app, monkeypatch):
    cenas = _cn_do_app(monkeypatch, {"perfis": PerfisFalsos(perfis=())})
    rodados = []
    monkeypatch.setattr(motor_app, "executar", lambda: rodados.append(1))
    motor_app._cn_pcm = quadro("dono") * 40
    motor_app._entrada_continua("DERVS, abre o Chrome")
    cenas[0].responder()                                   # ele já respondeu algo
    cenas[0].conv.cb(dc.Erro("rede", "caiu no meio"))
    assert motor_app._cn is None and rodados == []


def test_app_frase_que_acordou_sem_audio_legivel_cai_uma_vez_e_segue_no_antigo(
        motor_app, monkeypatch):
    cenas = _cn_do_app(monkeypatch)
    rodados = []
    monkeypatch.setattr(motor_app, "executar", lambda: rodados.append(motor_app.entrada.toPlainText()))
    motor_app._cn_pcm = None                               # o .wav não deu para ler
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == ["abre o Chrome"]                    # o caminho antigo atende...
    assert motor_app._cn is None and "encerrar" in cenas[0].conv.log     # ...e a voz direta saiu
    falas = [a for nome, a in motor_app.ponte.chamadas if nome == "enviar_fala"]
    assert any(cn.AVISO_CAIU in str(a) for a in falas)


def test_app_pedido_pendente_aparece_com_o_texto_exato(motor_app, monkeypatch):
    mostrados = []
    monkeypatch.setattr(motor_app, "_toast", mostrados.append)
    vistos = []
    monkeypatch.setattr(motor_app, "_diz", lambda papel, texto, cor=None: vistos.append((papel, texto)))
    motor_app._cn_tratar("pedido", "pede pro Codex apagar a pasta fotos")
    assert any("pede pro Codex apagar a pasta fotos" in t for t in mostrados)
    assert any("pede pro Codex apagar a pasta fotos" in t for _, t in vistos)


def _passo(**kw):
    return {"descricao": "x", "comando": "notepad", "risco": "reversivel", "toca_alvo": False, **kw}


def test_app_cartao_grave_nao_aceita_ok_por_voz_no_caminho_antigo(motor_app, monkeypatch):
    rodados = []
    monkeypatch.setattr(motor_app, "_processar_passo", lambda: rodados.append(1))
    motor_app.plano = [_passo(toca_alvo=True)]             # grave pelo cartão, "reversível" no nível
    motor_app._cerebro_respondeu({"modo": "planejar", "fala": "", "passos": motor_app.plano})
    assert motor_app._aguardando_ok is True
    motor_app.confirmar_plano_ok(por_voz=True)
    assert rodados == [] and motor_app._aguardando_ok is True      # só o clique vale
    motor_app.confirmar_plano_ok(por_voz=False)
    assert rodados == [1]


def test_app_cartao_reversivel_continua_aceitando_ok_por_voz(motor_app, monkeypatch):
    import dervs
    rodados = []
    monkeypatch.setattr(motor_app, "_processar_passo", lambda: rodados.append(1))
    monkeypatch.setattr(dervs.cfg, "carregar", lambda: {"confirmar_plano": "sempre"})
    motor_app._cerebro_respondeu({"modo": "planejar", "fala": "", "passos": [_passo()]})
    assert motor_app._aguardando_ok is True
    motor_app.confirmar_plano_ok(por_voz=True)
    assert rodados == [1]


def test_app_vozes_api_nasce_uma_vez_so_mesmo_com_threads_juntas(motor_app, monkeypatch):
    import threading
    import time as _time
    criadas = []

    def lenta(*a, **k):
        _time.sleep(0.05)
        criadas.append(1)
        return object()
    monkeypatch.setattr(cn, "Vozes", lenta)
    motor_app._vozes = None
    ths = [threading.Thread(target=motor_app._vozes_api) for _ in range(6)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert len(criadas) == 1


def test_escuta_gancho_que_quebra_20_vezes_seguidas_aciona_a_queda(monkeypatch):
    _qt()
    import dervs
    quadros = [quadro("dono")] * 60 + [quadro("sil")] * 60

    class MicFalso:
        def __init__(self):
            self.i = 0

        def abrir(self):
            pass

        def ler(self):
            if self.i >= len(quadros):
                escuta._rodando = False
                return b""
            self.i += 1
            return quadros[self.i - 1]

        def motivo_da_queda(self):
            return ""

        def fechar(self):
            pass

    monkeypatch.setattr(dervs, "Microfone", MicFalso)
    monkeypatch.setattr(dervs, "salvar_wav", lambda pcm, caminho: None)
    escuta = dervs.Escuta()
    chamadas, quebrou, falas = [], [], []
    escuta.fala.connect(falas.append)

    def gancho(q):
        chamadas.append(1)
        raise RuntimeError("quadro quebrou")
    escuta.desvio = gancho
    escuta.desvio_quebrou = lambda: quebrou.append(1)
    escuta.run()
    assert len(chamadas) == dervs.Escuta.GANCHO_FALHAS_MAX and quebrou == [1]
    assert escuta.desvio is None


# ---- revisão de 15/10: o caminho antigo também confere a voz; pedido não se perde calado ----

LONGO = quadro("dono") * 80          # 2,4 s de fala do dono
CURTO = quadro("dono") * 40          # 1,2 s: pouco para o quem_fala decidir
ESTRANHO = quadro("filha") * 80      # voz que não é de nenhum perfil do dono


def _caminho_antigo(motor_app, monkeypatch, perfis):
    """Voz direta fora (sem motor) e perfis dublês no porteiro do caminho antigo."""
    import types
    monkeypatch.setattr(cn, "motor_disponivel", lambda conf: False)
    if perfis is not None:
        motor_app._vozes = types.SimpleNamespace(perfis=perfis)
    rodados, ditos = [], []
    monkeypatch.setattr(motor_app, "executar", lambda: rodados.append(motor_app.entrada.toPlainText()))
    monkeypatch.setattr(motor_app, "_diz", lambda papel, texto, cor=None: ditos.append((papel, texto)))
    return rodados, ditos


def test_antigo_com_perfil_e_frase_sem_audio_nunca_atende(motor_app, monkeypatch):
    rodados, ditos = _caminho_antigo(motor_app, monkeypatch, PerfisFalsos())
    motor_app._cn_pcm = None
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == [] and not motor_app._esta_desperto()
    assert any("não reconheci" in t.lower() for _, t in ditos)


def test_antigo_com_perfil_voz_estranha_nao_acorda_nem_atende(motor_app, monkeypatch):
    rodados, ditos = _caminho_antigo(motor_app, monkeypatch, PerfisFalsos())
    motor_app._cn_pcm = ESTRANHO
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == [] and not motor_app._esta_desperto()
    assert any("não reconheci" in t.lower() for _, t in ditos)


def test_antigo_com_perfil_voz_do_dono_atende(motor_app, monkeypatch):
    rodados, _ = _caminho_antigo(motor_app, monkeypatch, PerfisFalsos())
    motor_app._cn_pcm = LONGO
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == ["abre o Chrome"] and motor_app._esta_desperto()


def test_antigo_fala_curta_com_o_nome_acorda_mas_nao_atende_o_pedido(motor_app, monkeypatch):
    rodados, ditos = _caminho_antigo(motor_app, monkeypatch, PerfisFalsos())
    motor_app._cn_pcm = CURTO
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == [] and motor_app._esta_desperto()      # acordou, mas o pedido não passou
    assert any("Pode falar" in t for _, t in ditos)


def test_antigo_fala_curta_sem_o_nome_e_recusada_mesmo_desperto(motor_app, monkeypatch):
    rodados, ditos = _caminho_antigo(motor_app, monkeypatch, PerfisFalsos())
    motor_app._acordar(novo=True)
    motor_app._cn_pcm = CURTO
    motor_app._entrada_continua("abre o Chrome")
    assert rodados == [] and any("não reconheci" in t.lower() for _, t in ditos)


def test_antigo_sem_perfil_nenhum_continua_como_sempre(motor_app, monkeypatch):
    rodados, _ = _caminho_antigo(motor_app, monkeypatch, PerfisFalsos(perfis=()))
    motor_app._cn_pcm = None
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == ["abre o Chrome"]


def test_antigo_perfis_zerados_depois_de_ter_existido_seguem_trancados(motor_app, monkeypatch):
    perfis = PerfisFalsos(perfis=())
    perfis.ja_teve_perfil = lambda: True
    rodados, _ = _caminho_antigo(motor_app, monkeypatch, perfis)
    motor_app._cn_pcm = LONGO
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == []


def test_antigo_trava_de_voz_desligada_na_config_nao_confere(motor_app, monkeypatch):
    rodados, _ = _caminho_antigo(motor_app, monkeypatch, PerfisFalsos())
    import dervs
    monkeypatch.setattr(dervs.cfg, "carregar", lambda: dict(dervs.cfg.PADRAO, locutor_ligado=False))
    motor_app._cn_pcm = None
    motor_app._entrada_continua("DERVS, abre o Chrome")
    assert rodados == ["abre o Chrome"]


def test_antigo_convidado_so_faz_o_facil_e_reversivel(motor_app, monkeypatch):
    perfis = PerfisFalsos(perfis=(("André", "dono"), ("Filha", "convidado")))
    rodados, ditos = _caminho_antigo(motor_app, monkeypatch, perfis)
    respondidos = []
    monkeypatch.setattr(motor_app, "_cerebro_respondeu", respondidos.append)
    motor_app._cn_pcm = ESTRANHO                        # no dublê, amplitude 9000 = a convidada
    motor_app._entrada_continua("DERVS, que horas são")
    assert rodados == [] and len(respondidos) == 1      # o atalho local respondeu, sem o cérebro
    motor_app._cn_pcm = ESTRANHO
    motor_app._entrada_continua("DERVS, apaga a pasta de fotos")
    assert rodados == [] and len(respondidos) == 1      # o resto é só do dono
    assert any("dono" in t.lower() for _, t in ditos)


def test_antigo_replay_da_frase_que_acordou_exige_ter_passado_na_trava(motor_app, monkeypatch):
    cenas = _cn_do_app(monkeypatch, {"perfis": PerfisFalsos(perfis=())})
    import types
    motor_app._vozes = types.SimpleNamespace(perfis=PerfisFalsos())
    rodados, ditos = [], []
    monkeypatch.setattr(motor_app, "executar", lambda: rodados.append(motor_app.entrada.toPlainText()))
    monkeypatch.setattr(motor_app, "_diz", lambda papel, texto, cor=None: ditos.append((papel, texto)))
    _acordar_app(motor_app)                              # a voz direta já está de pé
    motor_app._cn_pcm = ESTRANHO
    motor_app._entrada_continua("DERVS, abre o Chrome")
    cenas[0].conv.cb(dc.Erro("rede", "sem rede"))        # caiu antes de responder
    assert rodados == []                                 # voz que não passou NÃO é refeita
    cenas = _cn_do_app(monkeypatch, {"perfis": PerfisFalsos(perfis=())})
    motor_app._cn_bloqueada_ate = 0.0
    _acordar_app(motor_app)
    motor_app._cn_pcm = LONGO
    motor_app._entrada_continua("DERVS, abre o Chrome")
    cenas[-1].conv.cb(dc.Erro("rede", "sem rede"))
    assert rodados == ["abre o Chrome"]                  # a do dono é


def test_pedido_durante_tarefa_ocupada_vai_para_a_fila_e_roda_depois(motor_app, monkeypatch):
    ditos = []
    monkeypatch.setattr(motor_app, "_diz", lambda papel, texto, cor=None: ditos.append((papel, texto)))
    pensados = []
    monkeypatch.setattr(motor_app, "_pensar", lambda: pensados.append(motor_app.conversa[-1]["texto"]))
    monkeypatch.setattr(motor_app, "_tentar_cofre_voz", lambda t: False)
    motor_app._atalhos_ligados = False
    motor_app._tarefa = object()                          # o cérebro está no meio de um pedido
    motor_app.entrada.setPlainText("abre o bloco de notas")
    motor_app.executar()
    assert motor_app.entrada.toPlainText() == "" and pensados == []
    assert any("fila" in t.lower() for _, t in ditos)
    motor_app._tarefa = None
    motor_app._atender_pedidos_em_espera()
    assert pensados == ["abre o bloco de notas"]


def test_fila_de_pedidos_tem_no_maximo_tres_e_o_quarto_e_avisado_nao_calado(motor_app, monkeypatch):
    ditos = []
    monkeypatch.setattr(motor_app, "_diz", lambda papel, texto, cor=None: ditos.append((papel, texto)))
    motor_app._tarefa = object()
    for n in range(4):
        motor_app.entrada.setPlainText("pedido %d" % n)
        motor_app.executar()
    assert list(motor_app._pedidos_em_espera) == ["pedido 0", "pedido 1", "pedido 2"]
    assert any("cheia" in t.lower() for _, t in ditos)


def test_sim_solto_com_tarefa_ocupada_nao_entra_na_fila(motor_app, monkeypatch):
    """Um 'sim' dito antes do plano existir não pode virar a confirmação de um plano futuro."""
    ditos = []
    monkeypatch.setattr(motor_app, "_diz", lambda papel, texto, cor=None: ditos.append((papel, texto)))
    motor_app._tarefa = object()
    motor_app.entrada.setPlainText("sim")
    motor_app.executar()
    assert list(motor_app._pedidos_em_espera) == [] and any("de novo" in t.lower() for _, t in ditos)


def test_pedido_delegado_ja_confirmado_com_tarefa_ocupada_nao_some(motor_app, monkeypatch):
    monkeypatch.setattr(motor_app, "_diz", lambda *a, **k: None)
    motor_app._tarefa = object()
    motor_app._cn_tratar("delegar", "pede pro Codex analisar a ponte")
    assert list(motor_app._pedidos_em_espera) == ["pede pro Codex analisar a ponte"]
