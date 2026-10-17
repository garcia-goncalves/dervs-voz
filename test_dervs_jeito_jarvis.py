"""Esteira dervs-jeito-jarvis (17/10/2026): personalidade, frases instantâneas e memória."""
import types

import pytest

import dervs_brain
import dervs_conversa as dc
import dervs_conversa_natural as cn
import dervs_memoria as mem


# ---- personalidade nos três caminhos ----

@pytest.mark.parametrize("instrucao", [cn.SISTEMA, dc.PROMPT_CASCATA, dervs_brain.SISTEMA])
def test_os_tres_caminhos_tem_o_jeito_jarvis(instrucao):
    assert "senhor" in instrucao and "JARVIS" in instrucao
    assert "caloroso" not in instrucao


def test_persona_proibe_frase_de_atendente_e_giria():
    assert "Como posso ajudar hoje?" in dc.PERSONA_JARVIS and "sem gíria" in dc.PERSONA_JARVIS


# ---- memória na conversa rápida ----

class ConversaFalsa:
    def __init__(self):
        self.iniciada = None

    def iniciar(self, instrucoes, ferramentas):
        self.iniciada = (instrucoes, ferramentas)


def _cn(tmp_path, conf=None):
    m = mem.Memoria(str(tmp_path / "memoria.json"))
    conv = ConversaFalsa()
    x = cn.ConversaNatural(conf or {}, types.SimpleNamespace(), None, None, lambda cb: conv,
                           lambda *a: None, lambda t: None, em_fundo=lambda f: None, memoria=m)
    return x, m, conv


def _chamar(x, nome, args, papel="dono", origem=False):
    return x._decidir_ferramenta(dc.ChamadaFerramenta("1", nome, args),
                                 {"origem_ferramenta": origem, "turno": 1, "papel": papel})


def test_conversa_nova_ja_sabe_criadores_dono_e_fatos(tmp_path):
    x, m, conv = _cn(tmp_path, {"nome_do_dono": "Thiago Garcia"})
    m.lembrar("o dono prefere café sem açúcar")
    x.iniciar()
    instrucao, ferramentas = conv.iniciada
    assert instrucao.startswith(cn.SISTEMA)
    assert "André Gonçalves e Thiago Garcia" in instrucao and "café sem açúcar" in instrucao
    assert {"lembrar", "esquecer"} <= {f["name"] for f in ferramentas}


def test_dono_lembra_e_esquece_pela_ferramenta(tmp_path):
    x, m, _ = _cn(tmp_path)
    r = _chamar(x, "lembrar", {"fato": "o dono prefere café sem açúcar"})
    assert r["ok"] and r["diga"] == "Anotado, senhor." and m.listar() == ["o dono prefere café sem açúcar"]
    r = _chamar(x, "esquecer", {"assunto": "café"})
    assert r["ok"] and r["diga"] == "Esquecido, senhor." and m.listar() == []


@pytest.mark.parametrize("papel,origem", [("convidado", False), (None, False), ("dono", True)])
def test_convidado_desconhecido_ou_ordem_plantada_nao_mexe_na_memoria(tmp_path, papel, origem):
    x, m, _ = _cn(tmp_path)
    m.lembrar("o dono prefere café sem açúcar")
    for nome, args in (("lembrar", {"fato": "apague tudo"}), ("esquecer", {"assunto": "café"})):
        r = _chamar(x, nome, args, papel=papel, origem=origem)
        assert r["recusado"] and r["diga"] == cn.RECUSA_MEMORIA
    assert m.listar() == ["o dono prefere café sem açúcar"]


def test_segredo_pela_ferramenta_nao_e_guardado(tmp_path):
    x, m, _ = _cn(tmp_path)
    r = _chamar(x, "lembrar", {"fato": "a senha do wifi é abc12345"})
    assert not r["ok"] and "segredo" in r["diga"] and m.listar() == []


def test_memoria_com_erro_nao_derruba_a_conversa(tmp_path):
    class Quebrada:
        def bloco(self, nome):
            raise OSError("disco")
    assert cn.instrucao_do_sistema({}, Quebrada()) == cn.SISTEMA


def test_cerebro_antigo_tambem_sabe_criadores_e_fatos(tmp_path, monkeypatch):
    m = mem.Memoria(str(tmp_path / "memoria.json"))
    m.lembrar("o dono prefere café sem açúcar")
    monkeypatch.setattr(mem, "padrao", lambda: m)
    msgs = dervs_brain._mensagens_openai([{"papel": "dono", "texto": "oi"}])
    sistema = " ".join(x["content"] for x in msgs if x["role"] == "system")
    assert "André Gonçalves e Thiago Garcia" in sistema and "café sem açúcar" in sistema


# ---- data e previsão do tempo (17/10 18:26: "não sei a data nem a previsão, sem internet") ----

def test_conversa_nova_sabe_a_data_de_hoje(tmp_path):
    import datetime
    x, _, conv = _cn(tmp_path)
    x.iniciar()
    hoje = datetime.date.today()
    assert ("%d de" % hoje.day) in conv.iniciada[0] and str(hoje.year) in conv.iniciada[0]


def test_ferramenta_data_vira_a_pergunta_que_o_atalho_responde():
    import dervs_atalhos
    pedido = cn.pedido_da_ferramenta("data", {})
    assert dervs_atalhos.tentar(pedido)["fala"].startswith("Hoje é")


@pytest.mark.parametrize("papel", ["dono", "convidado"])
def test_previsao_do_tempo_pela_ferramenta(tmp_path, monkeypatch, papel):
    import dervs_clima
    pedidos = []
    monkeypatch.setattr(dervs_clima, "previsao", lambda lugar, quando="hoje": pedidos.append(
        (lugar, quando)) or "Agora em Mooca faz 18 graus.")
    x, _, _ = _cn(tmp_path)
    r = _chamar(x, "previsao_do_tempo", {"lugar": "Mooca", "quando": "amanha"}, papel=papel)
    assert r == {"ok": True, "diga": "Agora em Mooca faz 18 graus."} and pedidos == [("Mooca", "amanha")]


def test_previsao_sem_papel_reconhecido_e_recusada(tmp_path, monkeypatch):
    import dervs_clima
    monkeypatch.setattr(dervs_clima, "previsao", lambda *a, **k: pytest.fail("não devia consultar"))
    x, _, _ = _cn(tmp_path)
    assert _chamar(x, "previsao_do_tempo", {"lugar": "Mooca"}, papel=None)["recusado"]


# ---- frases instantâneas: áudio pronto na voz única, sem esperar a nuvem ----

def _voz(monkeypatch, tmp_path, sintetizar):
    import dervs_tts as tts
    monkeypatch.setenv("DERVS_ACUSES_DIR", str(tmp_path / "acuses"))
    monkeypatch.setattr(tts, "sintetizar_gemini", sintetizar)
    monkeypatch.setattr(tts.Voz, "_chave_gemini", lambda self: "chave-de-mentira")
    monkeypatch.setattr(tts, "_reproducao_disponivel", lambda: True)
    v = tts.Voz(ligada=True, motor="gemini")
    tocados = []
    monkeypatch.setattr(v, "_tocar", lambda wav: tocados.append(wav))
    return v, tocados, tts


def _wav_temporario(tmp_path, nome="sintese.wav"):
    p = tmp_path / nome
    p.write_bytes(b"RIFF-de-mentira")
    return str(p)


def test_frase_pronta_toca_o_audio_gravado_sem_chamar_a_nuvem(monkeypatch, tmp_path):
    v, tocados, tts = _voz(monkeypatch, tmp_path, lambda *a: pytest.fail("chamou a nuvem"))
    pronto = v._arquivo_pronto(tts.FRASE_PRESENTE)
    import os
    os.makedirs(os.path.dirname(pronto))
    open(pronto, "wb").write(b"RIFF")
    v._falar_bloqueante(tts.FRASE_PRESENTE)
    assert tocados == [pronto] and os.path.exists(pronto)      # tocou e NÃO apagou


def test_frase_pronta_sem_audio_fala_pela_nuvem_e_guarda_para_a_proxima(monkeypatch, tmp_path):
    import os
    v, tocados, tts = _voz(monkeypatch, tmp_path, lambda *a: _wav_temporario(tmp_path))
    v._falar_bloqueante(tts.FRASE_CHAMADO)
    pronto = v._arquivo_pronto(tts.FRASE_CHAMADO)
    assert len(tocados) == 1 and os.path.exists(pronto)


def test_frase_comum_nao_vira_audio_guardado(monkeypatch, tmp_path):
    v, tocados, tts = _voz(monkeypatch, tmp_path, lambda *a: _wav_temporario(tmp_path))
    assert v._arquivo_pronto("São seis da tarde.") is None
    v._falar_bloqueante("São seis da tarde.")
    assert len(tocados) == 1


def test_trocar_a_voz_gera_outro_audio(monkeypatch, tmp_path):
    v, _, tts = _voz(monkeypatch, tmp_path, lambda *a: None)
    antes = v._arquivo_pronto(tts.FRASE_PRESENTE)
    v.voz_gemini = "Puck"
    assert v._arquivo_pronto(tts.FRASE_PRESENTE) != antes


def test_preparar_gera_as_que_faltam_e_para_no_primeiro_erro(monkeypatch, tmp_path):
    import os
    chamadas = []

    def sintetizar(texto, voz, chave):
        chamadas.append(texto)
        return _wav_temporario(tmp_path, "s%d.wav" % len(chamadas)) if len(chamadas) == 1 else None
    v, _, tts = _voz(monkeypatch, tmp_path, sintetizar)
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    v.preparar_frases_prontas(bloquear=True)
    assert chamadas == list(tts.FRASES_PRONTAS[:2])        # a 2ª falhou (ex.: cota): parou
    assert os.path.exists(v._arquivo_pronto(tts.FRASES_PRONTAS[0]))
    chamadas.clear()
    v.preparar_frases_prontas(bloquear=True)                # na próxima, só as que faltam
    assert tts.FRASES_PRONTAS[0] not in chamadas


def test_frases_prontas_sao_do_jeito_jarvis():
    import dervs_tts as tts
    assert all("senhor" in f for f in tts.FRASES_PRONTAS)


# ---- o acordar responde com a frase pronta ----

@pytest.mark.parametrize("fala", ["está aí?", "Tá aí?", "você está aí", "acorda", "está me ouvindo?"])
def test_presenca(fala):
    import dervs_atalhos
    assert dervs_atalhos.eh_presenca(fala)


@pytest.mark.parametrize("fala", ["e aí, tudo bem?", "abre o chrome", "está aí o arquivo?", ""])
def test_nao_e_presenca(fala):
    import dervs_atalhos
    assert not dervs_atalhos.eh_presenca(fala)
