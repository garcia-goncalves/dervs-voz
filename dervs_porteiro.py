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
import json
import os
import sys
import time
import wave

from dervs_listen import separar_chamada

# O aviso de vocabulário. É a peça que faz o porteiro funcionar: sem ela o
# modelo troca "Dervs" por "Deus". Curto de propósito — prompt longo demais
# empurra o modelo a inventar frase em vez de transcrever o que ouviu.
COLA_PORTEIRO = "Dervs. Ok Dervs. Ei Dervs. O assistente se chama Dervs."

# Medido: 'tiny' acerta igual ao 'base' e é o dobro mais rápido. Ver o docstring.
MODELO_PADRAO = "tiny"

# O diário: uma linha por decisão, para poder provar onde uma frase sumiu. Sem
# ele, "não era comigo" apaga o texto e o wav e não sobra pista nenhuma — se o
# porteiro errar com o dono, ninguém consegue investigar.
# POR PADRÃO NÃO GUARDA O TEXTO: o que foi dito na sala (reunião, família) é
# justamente o que o porteiro existe para não deixar sair. Só hora, se acordou,
# quantas palavras e a duração do áudio. Guardar o texto é escolha do dono
# (`porteiro_registrar_texto`), para uma semana de investigação, não para sempre.
LIMITE_DIARIO_BYTES = 256 * 1024


def caminho_do_diario() -> str:
    """DERVS_DIARIO_PORTEIRO sobrepõe tudo; senão %LOCALAPPDATA%/dervs/porteiro.jsonl
    (mesma pasta dos modelos); em Linux, ~/.local/state/dervs."""
    if os.environ.get("DERVS_DIARIO_PORTEIRO"):
        return os.environ["DERVS_DIARIO_PORTEIRO"]
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        return os.path.join(base, "dervs", "porteiro.jsonl")
    return os.path.expanduser("~/.local/state/dervs/porteiro.jsonl")


def _duracao_s(caminho_wav: str):
    try:
        with wave.open(caminho_wav, "rb") as w:
            return round(w.getnframes() / float(w.getframerate()), 2)
    except (OSError, EOFError, wave.Error, ZeroDivisionError):
        return None


def _registrar(diario, registro: dict) -> None:
    """Acrescenta uma linha ao diário. NUNCA levanta: telemetria que derruba a
    escuta é pior que não ter telemetria."""
    try:
        os.makedirs(os.path.dirname(diario) or ".", exist_ok=True)
        try:
            if os.path.getsize(diario) > LIMITE_DIARIO_BYTES:
                os.replace(diario, diario + ".1")     # guarda só a geração anterior
        except OSError:
            pass    # não girou (arquivo em uso?): ainda assim registra esta decisão
        with open(diario, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
                 transcritor=None, diario=None, registrar_texto: bool = False):
        self.tamanho = tamanho
        self.threads = threads
        # `diario` é o caminho do arquivo, ou None para não registrar nada
        # (o padrão de quem constrói na mão, como os testes). `criar_porteiro`
        # é quem liga o diário de verdade.
        self.diario = diario
        self.registrar_texto = registrar_texto
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
            # beam_size=3 e vad_filter: o porteiro NÃO precisa da melhor
            # transcrição, mas precisa achar o nome — e quando ele erra a frase
            # é DESCARTADA em silêncio, sem nada na tela e sem registro. Era
            # beam_size=1 e sem VAD (o STT local já usava os dois). Custa ~0,2 s
            # numa etapa de 0,49 s, e o que se compra é falso-negativo a menos:
            # frase do dono sumindo calada é o pior resultado possível aqui.
            beam_size=3,
            vad_filter=True,
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
            self._anotar(caminho_wav, False, "", erro=True)
            return False, ""
        acordou, _resto = separar_chamada(texto)
        self._anotar(caminho_wav, bool(acordou), texto)
        return bool(acordou), texto

    def _anotar(self, caminho_wav, acordou, texto, erro=False):
        if not self.diario:
            return
        registro = {"quando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "acordou": acordou,
                    "palavras": len(texto.split()),
                    "duracao_s": _duracao_s(caminho_wav)}
        if erro:
            registro["erro"] = True
        if self.registrar_texto and texto:
            registro["texto"] = texto
        _registrar(self.diario, registro)


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
    return PorteiroLocal(tamanho=tamanho, threads=threads,
                         diario=caminho_do_diario(),
                         registrar_texto=conf.get("porteiro_registrar_texto") is True)
