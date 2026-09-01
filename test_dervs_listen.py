#!/usr/bin/env python3
"""Testes da detecção de fim de fala (sem microfone).

Rodar: python -m pytest test_dervs_listen.py -q
"""
import array
from dervs_listen import Endpointer, rms, separar_chamada, FRAME_AMOSTRAS, FRAME_BYTES


def test_chamada_com_nome_e_pedido():
    tem, resto = separar_chamada("DERVS, que horas são")
    assert tem is True
    assert resto == "que horas são"


def test_chamada_com_saudacao():
    tem, resto = separar_chamada("ei DERVS abre o firefox")
    assert tem is True
    assert resto == "abre o firefox"


def test_so_o_nome():
    tem, resto = separar_chamada("DERVS")
    assert tem is True
    assert resto == ""


def test_sem_o_nome_nao_acorda():
    tem, resto = separar_chamada("que horas são")
    assert tem is False
    assert resto == "que horas são"


def test_variacoes_de_transcricao_do_nome():
    for t in ["dervis me ajuda", "Derves liga a luz", "derv roda o date"]:
        tem, _ = separar_chamada(t)
        assert tem is True, f"não reconheceu: {t!r}"


def test_variacoes_extras_de_pronuncia_brasileira():
    """Grafias que o Whisper produz para a pronúncia BR do nome."""
    for t in ["dérvis liga a luz", "dervz que horas são", "derbs abre o firefox",
              "dervys liga a luz", "derviz desliga o som", "derbis qual é a previsão"]:
        tem, _ = separar_chamada(t)
        assert tem is True, f"não reconheceu: {t!r}"


def test_nome_no_meio_da_frase_e_reconhecido_e_removido():
    """O nome não precisa estar no começo — 'por favor DERVS, liga a luz'."""
    tem, resto = separar_chamada("por favor dervs liga a luz")
    assert tem is True
    assert resto == "por favor liga a luz"


def test_nome_no_fim_da_frase():
    tem, resto = separar_chamada("qual é a previsão do tempo dervs")
    assert tem is True
    assert resto == "qual é a previsão do tempo"


def test_nome_quebrado_em_duas_palavras_der_vis():
    """O Whisper às vezes separa o nome em duas palavras: 'der vis'."""
    tem, resto = separar_chamada("der vis que horas são")
    assert tem is True
    assert resto == "que horas são"


def test_nome_quebrado_em_duas_palavras_derv_is():
    tem, resto = separar_chamada("derv is liga a luz")
    assert tem is True
    assert resto == "liga a luz"


def test_nome_quebrado_em_tres_palavras_der_vi_s():
    """Quebra em TRÊS pedaços: 'der' + 'vi' + 's' = 'dervis'."""
    tem, resto = separar_chamada("der vi s liga a luz")
    assert tem is True
    assert resto == "liga a luz"


def test_nome_quebrado_no_meio_da_frase():
    tem, resto = separar_chamada("ei der vis abre o firefox")
    assert tem is True
    assert resto == "abre o firefox"


def test_palavras_comuns_do_portugues_nao_acordam():
    """Prova de que o casamento tolerante não vira gatilho para o português comum.

    Cada uma destas foi escolhida por parecer com 'DERVS' de algum jeito:
    começa com "de" (deve, devo, depois, deixa, dentro, dez) — a trava do "der"
    corta essas — ou começa mesmo com "der" e sobrevive à trava, sendo então
    barrada só pelo limiar de parecença (derme, dermes, deriva, derruba,
    derrete, derrota, derrapa, derradeiro).
    """
    frases_comuns = [
        "que horas são",
        "você deve ir agora",
        "eu devo dinheiro pra ele",
        "depois eu te ligo",
        "deixa isso pra lá",
        "guarda dentro da gaveta",
        "são mais de dez pessoas",
        "a derme é a camada de baixo da pele",
        "estudei as dermes no curso",
        "o barco ficou à deriva",
        "ele derruba tudo que encosta",
        "o gelo derrete no sol",
        "foi uma derrota feia",
        "o carro derrapa na chuva",
        "esse foi o derradeiro aviso",
        "calcula a derivada da função",
    ]
    for frase in frases_comuns:
        tem, resto = separar_chamada(frase)
        assert tem is False, f"acordou à toa com: {frase!r}"
        assert resto == frase


def _frame(amplitude: int) -> bytes:
    """Um quadro de áudio com um tom simples de dada amplitude (0 = silêncio)."""
    a = array.array("h", [amplitude if i % 2 == 0 else -amplitude
                          for i in range(FRAME_AMOSTRAS)])
    return a.tobytes()


def test_rms_silencio_e_baixo():
    assert rms(_frame(0)) == 0.0
    assert rms(_frame(5000)) > 1000


def test_frase_completa_e_devolvida_apos_silencio():
    ep = Endpointer(fim_ms=300, min_fala_ms=60)
    saida = None
    # 10 quadros de fala (alta energia)
    for _ in range(10):
        r = ep.processar(_frame(8000))
        assert r is None
    # silêncio suficiente para fechar (300ms = 10 quadros de 30ms)
    for _ in range(12):
        r = ep.processar(_frame(0))
        if r is not None:
            saida = r
    assert saida is not None
    assert len(saida) > 0


def test_ruido_curto_e_ignorado():
    ep = Endpointer(fim_ms=300, min_fala_ms=300)  # exige 10 quadros de fala
    saida = None
    for _ in range(2):            # só 2 quadros de "fala" — curto demais
        ep.processar(_frame(8000))
    for _ in range(12):
        r = ep.processar(_frame(0))
        if r is not None:
            saida = r
    assert saida is None          # descartado, não vira frase


def test_silencio_puro_nao_dispara():
    ep = Endpointer()
    for _ in range(50):
        assert ep.processar(_frame(0)) is None


def test_reset_limpa_estado():
    ep = Endpointer(fim_ms=300, min_fala_ms=60)
    ep.processar(_frame(8000))
    ep.reset()
    assert ep.em_fala is False
    assert ep.buf == []


# --- o que estava quebrando na prática (frase saindo pela metade) -------------

def test_pausa_natural_no_meio_da_frase_nao_corta():
    """Respirar 700 ms no meio de uma frase NÃO é fim de frase.

    Era a causa de 'Como eu posso ativar você? Eu tenho que te chamar pelo…':
    o fim_ms antigo (700) fechava a frase na primeira pausa para respirar.
    """
    ep = Endpointer()                       # valores de produção
    for _ in range(30):                     # ~0,9 s falando
        assert ep.processar(_frame(8000)) is None
    for _ in range(23):                     # 690 ms de pausa para respirar
        assert ep.processar(_frame(0)) is None, "cortou a frase numa pausa natural"
    assert ep.em_fala is True               # ainda dentro da mesma frase


def test_frase_muito_longa_e_entregue_por_teto_de_tempo():
    """Sem teto, ruído contínuo prendia a frase para sempre e nada era transcrito."""
    ep = Endpointer(max_ms=600)             # teto baixo só para o teste
    saida = None
    for _ in range(40):                     # 1,2 s de fala contínua, sem pausa
        r = ep.processar(_frame(8000))
        if r is not None:
            saida = r
            break
    assert saida is not None, "frase contínua nunca foi entregue"
    assert ep.em_fala is False              # e recomeça limpo


def test_falar_muito_tempo_nao_levanta_o_limiar():
    """O piso de ruído só aprende no SILÊNCIO.

    Antes ele subia durante a fala, então quanto mais você falava, mais alto
    ficava o 'isto é fala' — e o fim da frase caía abaixo da linha e sumia.
    """
    ep = Endpointer()
    piso_inicial = ep.piso
    for _ in range(200):                    # 6 s falando alto
        ep.processar(_frame(9000))
    assert ep.piso <= piso_inicial + 1.0, "o limiar subiu enquanto você falava"


def test_fala_baixinha_no_fim_da_frase_nao_e_cortada():
    """Histerese: entra na fala com limiar alto, mas só sai com limiar bem menor —
    o fim da palavra, que sempre é mais fraco, continua dentro da frase."""
    ep = Endpointer()
    for _ in range(20):
        ep.processar(_frame(8000))          # começo forte
    for _ in range(45):                     # 1,35 s de voz fraca (mas ainda voz)
        ep.processar(_frame(600))
    assert ep.em_fala is True, "cortou o fim da frase, que é sempre mais baixo"


def test_aquecer_mantem_o_pre_roll_durante_a_pausa():
    """Enquanto o DERVS fala, a escuta fica pausada. Se o pre-roll for zerado,
    a primeira sílaba da sua resposta se perde."""
    ep = Endpointer()
    for _ in range(20):
        ep.aquecer(_frame(0))
    assert len(ep.pre) == ep.pre_max, "pre-roll vazio: começo da fala seria cortado"
    assert ep.em_fala is False
