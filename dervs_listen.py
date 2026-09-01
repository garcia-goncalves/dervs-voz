#!/usr/bin/env python3
"""DERVS — escuta contínua (saber quando você começou e parou de falar).

Sem dependência externa: mede a ENERGIA do áudio quadro a quadro. Silêncio tem
energia baixa; fala tem energia alta. Quando vê fala seguida de um tempo de
silêncio, entende que a frase acabou e devolve o trecho para transcrever.

É o que deixa conversar sem clicar em Gravar/Parar.

O 'Endpointer' abaixo é pura lógica (entra quadro, sai decisão) de propósito —
dá para testar sem microfone. Quem lê o microfone de verdade é a thread 'Escuta'
lá no dervs.py, que usa este Endpointer.
"""
import array
import difflib
import math
import re
import unicodedata
import wave

TAXA = 16000            # 16 kHz — o que o Whisper quer
FRAME_MS = 30           # cada quadro tem 30 ms
FRAME_AMOSTRAS = TAXA * FRAME_MS // 1000     # 480 amostras
FRAME_BYTES = FRAME_AMOSTRAS * 2             # 960 bytes (16 bits por amostra)


def rms(frame: bytes) -> float:
    """Energia (volume médio) de um quadro de áudio de 16 bits."""
    if not frame:
        return 0.0
    a = array.array("h")
    a.frombytes(frame[: len(frame) // 2 * 2])
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a) / len(a))


class Endpointer:
    """Decide onde a frase começa e termina, olhando a energia dos quadros.

    Três cuidados que existem por causa de bug real, não por capricho:

    1. `fim_ms` é a pausa que fecha a frase. Curto demais (era 700 ms) corta você
       no meio da frase quando você respira — e a segunda metade vira outra frase.
    2. O piso de ruído só aprende no SILÊNCIO. Se aprendesse durante a fala, a
       linha do "isto é fala" subiria enquanto você fala e o fim da frase sumiria.
    3. Histerese: entra na fala com a linha cheia, mas só sai com metade dela.
       Fim de palavra é sempre mais fraco que o começo; sem isso ele é cortado.
    """

    def __init__(self, fim_ms=1100, min_fala_ms=300, limiar_abs=380.0,
                 pre_roll=10, max_ms=20000, saida_frac=0.5):
        self.fim_frames = max(1, fim_ms // FRAME_MS)      # silêncio que fecha a frase
        self.min_fala = max(1, min_fala_ms // FRAME_MS)   # frase curta demais = ignora (tosse)
        self.max_frames = max(1, max_ms // FRAME_MS)      # teto: entrega o que tem e recomeça
        self.limiar_abs = limiar_abs                      # piso absoluto de "isto é fala"
        self.saida_frac = saida_frac                      # histerese: linha para CONTINUAR falando
        self.piso = 200.0                                 # ruído de fundo estimado
        self.pre = []                                     # quadros antes da fala (não cortar o início)
        self.pre_max = pre_roll
        self._reset()

    def _reset(self):
        self.buf = []
        self.em_fala = False
        self.sil = 0
        self.n_fala = 0

    def reset(self):
        """Zera tudo (usado quando a escuta é pausada — enquanto o DERVS fala)."""
        self._reset()
        self.pre = []

    def _aprender_ruido(self, e: float) -> None:
        """Atualiza o piso de ruído. Só é chamado fora da fala, de propósito."""
        if e < self.piso:
            self.piso = 0.9 * self.piso + 0.1 * e      # desce rápido
        else:
            self.piso = 0.995 * self.piso + 0.005 * e  # sobe devagar

    def aquecer(self, frame: bytes) -> None:
        """Quadro que chega enquanto a escuta está pausada (o DERVS está falando).

        Não detecta fala, mas mantém o pre-roll cheio e o piso de ruído em dia —
        assim, quando a escuta volta, a primeira sílaba da sua resposta não se perde.
        """
        e = rms(frame)
        if e <= max(self.limiar_abs, self.piso * 3.5):
            self._aprender_ruido(e)          # a voz do próprio DERVS não vira "ruído de fundo"
        self.pre.append(frame)
        if len(self.pre) > self.pre_max:
            self.pre.pop(0)

    def _entregar(self):
        """Fecha a frase atual: devolve o áudio se valeu a pena, senão descarta."""
        pcm = b"".join(self.buf)
        falou = self.n_fala
        self._reset()
        return pcm if falou >= self.min_fala else None

    def processar(self, frame: bytes):
        """Recebe um quadro. Devolve o áudio (bytes PCM) quando a frase termina,
        ou None enquanto ainda está no meio."""
        e = rms(frame)

        if not self.em_fala:
            limiar = max(self.limiar_abs, self.piso * 3.5)
            if e <= limiar:
                self._aprender_ruido(e)      # só aprende ruído com quadro que NÃO é fala
            # ainda em silêncio: guarda um pouco de áudio para não cortar o início
            self.pre.append(frame)
            if len(self.pre) > self.pre_max:
                self.pre.pop(0)
            if e > limiar:
                self.em_fala = True
                self.buf = list(self.pre)
                self.pre = []
                self.sil = 0
                self.n_fala = 1
            return None

        # já estamos dentro de uma frase: a linha para CONTINUAR é mais baixa
        limiar_saida = max(self.limiar_abs, self.piso * 3.5) * self.saida_frac
        self.buf.append(frame)
        if e > limiar_saida:
            self.sil = 0
            self.n_fala += 1
        else:
            self.sil += 1
            if self.sil >= self.fim_frames:
                return self._entregar()      # pausa longa = frase acabou
        if len(self.buf) >= self.max_frames:
            return self._entregar()          # teto de tempo: não segura para sempre
        return None


# --- palavra de acordar ("DERVS") ------------------------------------------
#
# Por que casamento por SUBSTRING não bastava: o Whisper escreve o nome do
# jeito que ouviu foneticamente, e a pronúncia brasileira gera grafia que a
# lista fixa antiga não previa ("grimoiri", "grimoari", "grimoare", "grimuar",
# "grimoá", "grimuá"...) — cada grafia nova era outro bug até alguém notar.
#
# A troca: em vez de decorar toda grafia possível, comparamos a DISTÂNCIA entre
# a palavra ouvida e um punhado de grafias-âncora, usando difflib.SequenceMatcher
# (biblioteca padrão, sem instalar nada). Isso cobre qualquer variação de vogal
# no fim do nome ("derv", "derves", "dervis", "dervz") de graça, porque a
# métrica mede o quanto duas strings se parecem, não se são substrings exatas.
#
# Duas travas contra falso positivo (tão ruim quanto não acordar):
#   1. a palavra tem que COMEÇAR com "der" — corta de cara "de", "deve",
#      "devo", "deixa", "depois", "dentro", sem nem calcular distância. Só
#      "de" não bastaria: "deve" é comuníssimo e marca 0,80 contra o nome;
#   2. o comprimento tem que ficar perto do nome real (4 a 7 letras) — corta
#      "der" sozinho (curto demais para confirmar) e "derradeiro"/"derivada".
# Só depois dessas duas o limiar de parecença (0.87) decide. Esse número não é
# chute: medido contra as palavras do português que sobrevivem à trava do
# "der", a pior confusão real ("dermes") fica em 0,83 — e a pior grafia
# aceitável do nome ("derv" sozinho) fica em 0,89. O limiar mora no meio dessa
# folga, que é estreita: mexer nas âncoras exige remedir os dois lados.
# "derv" NÃO entra: como âncora exata ele venceria "dervis" colado e deixaria
# o "is" sobrando dentro do pedido. Fora da lista ele ainda acorda por
# parecença (0,89), que é o certo.
NOMES = ("dervs", "dervis", "derves", "dervz", "derbs", "dervys")
_SAUDACOES = ("ei ", "ê ", "ô ", "o ", "oi ", "olá ", "ola ", "alô ", "alo ")
_LIMIAR_PARECENCA = 0.87
_TAM_MIN, _TAM_MAX = 4, 7           # "dervs" tem 5; damos folga pra menos e pra mais
_PALAVRA_RE = re.compile(r"[^\W\d_]+", re.UNICODE)   # sequência de letras (sem número/underline)


def _sem_acento(s: str) -> str:
    """Tira acento (dérvis -> dervis) para comparar sem depender da grafia exata."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _canon(nomes=NOMES):
    """Grafias-âncora, normalizadas e sem repetição — a base da comparação por parecença."""
    return tuple(sorted({_sem_acento(n.lower()) for n in nomes}))


def _pontuar_nome(palavra: str, canon):
    """Quanto essa palavra (ou palavra colada) se parece com 'DERVS'?

    Devolve a pontuação (0 a 1) se passar nas duas travas baratas, ou None se
    nem chegar a valer a pena calcular a distância de edição. As travas vêm
    primeiro de propósito: cortam a esmagadora maioria das palavras do
    português sem gastar SequenceMatcher, e sozinhas já eliminam "deve"/
    "depois"/"deixa" (não começam com "der") e "der" isolado (curto demais).

    Devolver a pontuação — não só sim/não — é o que permite ao chamador
    escolher, entre juntar 1, 2 ou 3 palavras, a combinação que bate MELHOR
    com o nome, em vez da primeira que passa no limiar (ver comentário em
    `separar_chamada` sobre por que "maior pedaço primeiro" sozinho falha).
    """
    p = _sem_acento(palavra.lower())
    if not (_TAM_MIN <= len(p) <= _TAM_MAX):
        return None
    if not p.startswith("der"):
        return None
    return max(difflib.SequenceMatcher(None, p, c).ratio() for c in canon)


def separar_chamada(texto: str, nomes=NOMES):
    """Vê se a frase chama o DERVS pelo nome e separa o pedido do nome.

    Devolve (tem_nome, resto): tem_nome=True se a palavra de acordar apareceu
    (em qualquer posição da frase, e mesmo se o Whisper a quebrou em duas
    palavras, tipo "der vis" ou "derv is"); resto = o pedido sem o nome nem
    a saudação que vier colada nele.
    """
    t = (texto or "").strip()
    if not t:
        return False, t

    canon = _canon(nomes)
    tokens = list(_PALAVRA_RE.finditer(t))

    # O Whisper pode quebrar "dervs" em 2 ou até 3 "palavras" separadas
    # ("der vis", "derv is", "der vi s"...). Por isso, em cada posição,
    # testamos colar 1, 2 e 3 tokens e ficamos com a MELHOR pontuação, não
    # com o primeiro tamanho que passa no limiar. As duas armadilhas que só
    # aparecem assim:
    #   - "maior primeiro" falha pra menos: em "derv is" o pedaço isolado
    #     "derv" (prefixo de "dervs") já passa sozinho no limiar; se ele
    #     vencesse por ser tentado primeiro, o "is" sobraria colado no pedido.
    #   - "maior primeiro" falha pra mais também: colar palavras demais gruda
    #     o começo do pedido dentro do nome e come um pedaço do que foi pedido.
    # Comparando a pontuação, o casamento mais "redondo" sempre ganha: "dervis"
    # (pontuação 1.0, k=2) vence "derv" isolado (k=1) e vence qualquer colagem
    # de 3 pedaços que arraste a palavra seguinte junto.
    span = None
    MAX_PEDACOS = 3
    for i in range(len(tokens)):
        restantes = min(MAX_PEDACOS, len(tokens) - i)
        melhor_k, melhor_pontos = None, 0.0
        for k in range(1, restantes + 1):
            grupo = tokens[i:i + k]
            colada = "".join(g.group() for g in grupo)
            pontos = _pontuar_nome(colada, canon)
            if pontos is not None and pontos >= _LIMIAR_PARECENCA and pontos > melhor_pontos:
                melhor_k, melhor_pontos = k, pontos
        if melhor_k is not None:
            grupo = tokens[i:i + melhor_k]
            span = (grupo[0].start(), grupo[-1].end())
            break
    if span is None:
        return False, t

    ini, fim = span
    prefixo, sufixo = t[:ini], t[fim:]

    # a saudação ("ei", "oi"...) só existe no INÍCIO da frase inteira — se
    # estiver lá e vier antes do nome, tira só ela do prefixo, não o resto
    low = t.lower()
    for saud in _SAUDACOES:
        if low.startswith(saud) and len(saud) <= ini:
            prefixo = prefixo[len(saud):]
            break

    prefixo = prefixo.rstrip(" ,.!?:;-")
    sufixo = sufixo.lstrip(" ,.!?:;-")
    resto = " ".join(parte for parte in (prefixo.strip(), sufixo.strip()) if parte)
    return True, resto


def salvar_wav(pcm: bytes, caminho: str):
    """Grava o trecho de fala num .wav 16 kHz mono — pronto para o Whisper."""
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(pcm)
