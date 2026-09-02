#!/usr/bin/env python3
"""DERVS STT — o 'ouvido' que fica ligado esperando fala.

Este processo atende DUAS perguntas diferentes, e a diferença entre elas é a
decisão mais importante do projeto:

  PORTEIRO   "isso foi comigo?"  — decidido AQUI, na máquina, de graça.
  TRANSCREVER "o que ele disse?" — mandado para a nuvem, com precisão, pago.

A ordem importa: **nada vai para a nuvem antes de o porteiro abrir.** Antes
desta mudança o app transcrevia tudo na nuvem e só depois procurava o nome no
texto — o que, com o DERVS ligado o dia inteiro, mandava reunião e conversa de
família para um servidor de terceiro e custava ~US$ 43/mês. Ver `dervs_porteiro`
para o porquê e para os números medidos.

Transcrição precisa, dois caminhos escolhidos pela config (`stt`):
  - "openai" (PADRÃO se houver chave): manda o .wav para a OpenAI. O modelo
    padrão é `gpt-transcribe` (lançado em 28/07/2026, US$ 0,0045/min), que a
    própria OpenAI recomenda à frente do `gpt-4o-transcribe` (US$ 0,006/min) e
    do `whisper-1`. Não carrega o Whisper grande (economiza ~1,6 GB de RAM).
  - "local": Whisper large-v3-turbo no processador, offline e grátis (~4,7 s).

Se a OpenAI falhar numa transcrição, cai no local sozinho — nunca fica surdo.

Protocolo de linha, por stdin/stdout, para o app Qt conversar:
  - ao ficar pronto, imprime:            READY
  - o app manda:  PORTEIRO <caminho.wav>
    e recebe:     PORTEIRO {"acordou": true|false, "texto": "..."}
  - o app manda:  TRANSCREVER <caminho.wav>   (ou só o caminho, forma antiga)
    e recebe:     RESULT <json-do-texto>
"""
import os
import sys
import json
import uuid
import urllib.request
import urllib.error

COLA = (
    "Transcrição em português do Brasil, com acentuação e pontuação corretas. "
    "É uma pessoa falando com um assistente de voz chamado DERVS. Frases "
    "típicas: 'DERVS, que horas são?', 'DERVS, que dia é hoje?', 'abre o "
    "Firefox', 'lista os arquivos', 'abre o ChatGPT', 'roda o nmap no alvo'. "
    "Vocabulário comum: e-mail, WhatsApp, site, aplicativo, ChatGPT, navegador, "
    "OSINT, subdomínio, domínio, DNS, certificado, vulnerabilidade, DERVS, "
    "Parrot. Números como 2026, R$ 1.500,00 e 10%."
)


def _ler_config():
    try:
        import dervs_config as _cfg
        return _cfg.carregar()
    except Exception:
        return {}


def _carregar_chave_openai():
    v = os.environ.get("OPENAI_API_KEY")
    if v:
        return v.strip()
    try:
        for linha in open(os.path.expanduser("~/voice/.env"), encoding="utf-8"):
            linha = linha.strip()
            if linha.startswith("OPENAI_API_KEY="):
                return linha.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


_conf = _ler_config()
STT = _conf.get("stt", "openai")
# gpt-transcribe (lançado 28/07/2026, US$ 0,0045/min) é mais preciso E mais
# barato que o gpt-4o-transcribe (US$ 0,006). O valor efetivo vem da config;
# esta constante é a reserva de quem roda sem arquivo de configuração.
STT_MODELO_PADRAO = "gpt-transcribe"
STT_MODELO = _conf.get("stt_openai_modelo") or STT_MODELO_PADRAO
OPENAI_KEY = _carregar_chave_openai()

_local_model = None   # carregado sob demanda (só se precisar do fallback local)


def _carregar_local():
    """Carrega o Whisper local (~1,6 GB). Só é chamado quando o local é usado."""
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel
        # cpu_threads=8: os 8 núcleos físicos do Ryzen 7 5700G (SMT/16 piora por
        # contenção). int8 para rodar sem placa NVIDIA. Ver histórico no git.
        _local_model = WhisperModel(
            "large-v3-turbo", device="cpu", compute_type="int8", cpu_threads=8)
    return _local_model


def _transcrever_local(caminho: str) -> str:
    model = _carregar_local()
    segmentos, _info = model.transcribe(
        caminho, language="pt", vad_filter=True, beam_size=5,
        condition_on_previous_text=False, initial_prompt=COLA)
    return "".join(seg.text for seg in segmentos).strip()


def _transcrever_openai(caminho: str) -> str:
    """Manda o .wav para a OpenAI e devolve o texto. Levanta exceção em falha
    (o chamador cai no local)."""
    with open(caminho, "rb") as f:
        audio = f.read()
    boundary = "----dervs" + uuid.uuid4().hex
    campos = {"model": STT_MODELO, "language": "pt", "response_format": "text",
              "prompt": COLA}
    partes = []
    for k, v in campos.items():
        partes.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                       % (boundary, k, v)).encode("utf-8"))
    partes.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
                   "filename=\"fala.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
                   % boundary).encode("utf-8"))
    partes.append(audio)
    partes.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    corpo = b"".join(partes)
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions", data=corpo,
        headers={"Authorization": "Bearer " + OPENAI_KEY,
                 "Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace").strip()


def _transcrever(caminho: str) -> str:
    """OpenAI primeiro (se configurado e com chave); local de reserva."""
    if STT == "openai" and OPENAI_KEY:
        try:
            return _transcrever_openai(caminho)
        except Exception as erro:
            sys.stderr.write("dervs_stt: OpenAI falhou (%s), caindo no local\n" % erro)
            sys.stderr.flush()
    return _transcrever_local(caminho)


def atender(linha: str, porteiro, transcrever_preciso) -> str:
    """Atende UMA linha do protocolo e devolve a linha de resposta.

    Esta função existe separada do laço principal por um motivo só: é aqui que
    se prova, com teste automatizado, que **áudio não vai para a nuvem antes de
    o porteiro abrir**. Com o verbo PORTEIRO, `transcrever_preciso` não é
    chamado — e o teste falha se alguém inverter isso um dia.

    Nunca levanta exceção: áudio ruim vira resposta vazia, não daemon morto.
    """
    linha = (linha or "").strip()
    if not linha:
        return ""
    verbo, _, resto = linha.partition(" ")

    if verbo == "PORTEIRO":
        acordou, texto = porteiro.ouviu_o_nome(resto.strip())
        return "PORTEIRO " + json.dumps(
            {"acordou": bool(acordou), "texto": texto}, ensure_ascii=True)

    # TRANSCREVER <caminho>, ou só o caminho cru (forma antiga do protocolo).
    caminho = resto.strip() if verbo == "TRANSCREVER" else linha
    try:
        texto = transcrever_preciso(caminho)
    except Exception as erro:  # nunca derruba o daemon por um áudio ruim
        texto = ""
        sys.stderr.write("dervs_stt: erro ao transcrever %s (%s)\n" % (caminho, erro))
        sys.stderr.flush()
    return "RESULT " + json.dumps(texto, ensure_ascii=True)


def main() -> None:
    from dervs_porteiro import criar_porteiro
    porteiro = criar_porteiro(_conf)
    # O porteiro é carregado ANTES do READY: ele decide toda primeira frase, e
    # pagar 1,2 s de carregamento na primeira vez que o dono fala seria sentido
    # como "o DERVS demorou". Aqui o custo cai no boot, onde ninguém espera.
    porteiro.aquecer()

    # Se o local é o padrão da transcrição precisa, carrega já (custa alguns
    # segundos) para o READY só sair quando estiver pronto. Se a OpenAI é o
    # padrão, READY sai na hora e o Whisper grande fica adormecido.
    if not (STT == "openai" and OPENAI_KEY):
        _carregar_local()

    sys.stdout.write("READY\n")
    sys.stdout.flush()

    while True:
        linha = sys.stdin.readline()
        if not linha:            # stdin fechado = app saiu
            break
        resposta = atender(linha, porteiro, _transcrever)
        if not resposta:
            continue
        sys.stdout.write(resposta + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
