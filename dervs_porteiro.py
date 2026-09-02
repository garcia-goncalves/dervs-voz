#!/usr/bin/env python3
"""O PORTEIRO — decide, sem o áudio sair da máquina, se a fala foi com o DERVS.

Por que este módulo existe
--------------------------
Antes, a palavra de acordar era conferida DEPOIS da transcrição na nuvem
(`dervs.py` chamava `separar_chamada` sobre o texto que voltava da OpenAI). Com
o DERVS ligado o dia inteiro, isso mandava para a nuvem todo som que parecesse
fala — reunião, ligação, conversa de família — só para descobrir que não era
com ele. Medido em 01/09/2026: ~14.400 min/mês, cerca de US$ 43/mês, além do
problema óbvio de mandar a casa inteira para um servidor de terceiro.

O porteiro inverte a ordem: primeiro decide-se AQUI se o nome foi dito; só o
que passa por ele vai para a nuvem. Quem não é chamado é descartado e nunca sai
do computador.

O achado que definiu a implementação
------------------------------------
Transcrever para procurar o nome parece frágil, e é — mas por um motivo
específico e contornável. Medido nesta máquina em 01/09/2026: o Whisper não
erra ao acaso, ele CONSERTA o desconhecido para a palavra comum mais próxima.
"Dervs" virava "Deus" ("Ok, Deus abriu Chrome"), "Derros", "there's". Isso não
se resolve afrouxando o casador difuso de `dervs_listen.separar_chamada`:
aceitar "Deus" faria o DERVS acordar toda vez que alguém dissesse "meu Deus".

A correção é avisar o modelo, por `initial_prompt`, de que a palavra existe.
Com o aviso, o modelo `tiny` acertou 14 de 14 (6 frases que deviam acordar, 8
que não deviam — incluindo "meu Deus, que susto você me deu" e "Deus me livre
disso aí") em 0,49 s médios. Sem o aviso: 10 de 14. O `base` empata em acerto e
é o dobro mais lento; o `small` é pior nos dois eixos. Números em
`docs/esteira/windows-tempo-real/verificacao.md`.

Limite honesto: aquela medição usou voz sintetizada, não a voz do dono num
ambiente com ruído. Se na prática o porteiro falhar, o encaixe para trocar por
um detector dedicado (Picovoice Porcupine, com menos de 1 alarme falso a cada
10 horas documentado) está pronto — ver `criar_porteiro` no fim do arquivo.

Viés desta peça: ERRAR PARA O LADO DE NÃO ACORDAR. Deixar de acordar custa ao
dono repetir a frase; acordar à toa custa o DERVS falar no meio de uma reunião
e ainda mandar o áudio para a nuvem.
"""
import sys

from dervs_listen import separar_chamada

# O aviso de vocabulário. É a peça que faz o porteiro funcionar: sem ela o
# modelo troca "Dervs" por "Deus". Curto de propósito — prompt longo demais
# empurra o modelo a inventar frase em vez de transcrever o que ouviu.
COLA_PORTEIRO = "Dervs. Ok Dervs. Ei Dervs. O assistente se chama Dervs."

# Medido: 'tiny' acerta igual ao 'base' e é o dobro mais rápido. Ver o docstring.
MODELO_PADRAO = "tiny"


class PorteiroLocal:
    """Ouve um trecho de fala e responde só uma coisa: 'foi comigo?'.

    Transcreve localmente com um Whisper pequeno e passa o texto pelo casador
    difuso que já existe (`separar_chamada`), que tolera as grafias que o
    modelo produz para o nome ('dervis', 'derves', 'dervz'...).

    O modelo é carregado na primeira chamada e fica na memória. São ~75 MB em
    int8 — cabe folgado ao lado do resto, e é por isso que dá para deixar
    ligado o dia inteiro.
    """

    def __init__(self, tamanho: str = MODELO_PADRAO, threads: int = 8,
                 transcritor=None):
        self.tamanho = tamanho
        self.threads = threads
        # `transcritor` existe para o teste injetar um dublê e não precisar do
        # modelo de verdade. Em produção fica None e o modelo é carregado.
        self._transcritor = transcritor
        self._modelo = None

    def _carregar(self):
        if self._modelo is None:
            from faster_whisper import WhisperModel
            # int8 porque esta máquina não tem placa NVIDIA. 8 threads = os 8
            # núcleos físicos do Ryzen 7 5700G (usar os 16 lógicos piora por
            # contenção — mesma conclusão já registrada no daemon de STT).
            self._modelo = WhisperModel(
                self.tamanho, device="cpu", compute_type="int8",
                cpu_threads=self.threads)
        return self._modelo

    def aquecer(self) -> None:
        """Carrega o modelo agora, para a primeira frase de verdade não pagar
        o 1,2 s de carregamento."""
        if self._transcritor is None:
            self._carregar()

    def transcrever_local(self, caminho_wav: str) -> str:
        """Transcrição rápida e barata, só para o porteiro decidir. NÃO serve
        para virar o pedido: para isso existe a transcrição precisa, que só
        roda depois que este portão abre."""
        if self._transcritor is not None:
            return self._transcritor(caminho_wav)
        modelo = self._carregar()
        segmentos, _info = modelo.transcribe(
            caminho_wav, language="pt",
            # beam_size=1: o porteiro não precisa da melhor transcrição, só de
            # uma boa o bastante para achar o nome. É o que segura os 0,49 s.
            beam_size=1,
            condition_on_previous_text=False,
            initial_prompt=COLA_PORTEIRO)
        return "".join(seg.text for seg in segmentos).strip()

    def ouviu_o_nome(self, caminho_wav: str):
        """Devolve (acordou, texto_provisorio).

        `texto_provisorio` é a transcrição local, que é grosseira de propósito.
        Ela serve para registro e depuração — o pedido de verdade vem da
        transcrição precisa, depois. Em qualquer erro devolve (False, "").
        """
        try:
            texto = self.transcrever_local(caminho_wav)
        except Exception as erro:      # áudio ruim não pode derrubar a escuta
            sys.stderr.write("dervs_porteiro: falhei ao ouvir %s (%s)\n"
                             % (caminho_wav, erro))
            sys.stderr.flush()
            return False, ""
        acordou, _resto = separar_chamada(texto)
        return bool(acordou), texto


def criar_porteiro(conf=None):
    """Escolhe o porteiro pela configuração. É o encaixe para trocar depois.

    `porteiro: "local"` (padrão) — o medido, não custa nada e não pede cadastro.
    `porteiro: "porcupine"` — detector dedicado da Picovoice. Ainda NÃO
    implementado: exige que o dono crie uma conta gratuita e gere a palavra
    "DERVS" no console deles, o que ninguém pode fazer no lugar dele. Quando
    for a hora, basta uma classe com o mesmo `ouviu_o_nome(caminho)` aqui.
    """
    conf = conf or {}
    qual = conf.get("porteiro", "local")
    if qual == "porcupine":
        raise NotImplementedError(
            "O porteiro Porcupine ainda não foi implementado. Para ligá-lo é "
            "preciso criar uma conta gratuita em picovoice.ai, gerar a palavra "
            "'DERVS' no console e guardar a chave de acesso. Enquanto isso, "
            "use porteiro: \"local\".")
    tamanho = conf.get("porteiro_modelo", MODELO_PADRAO)
    threads = int(conf.get("porteiro_threads", 8))
    return PorteiroLocal(tamanho=tamanho, threads=threads)
