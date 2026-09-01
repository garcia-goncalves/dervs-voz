#!/usr/bin/env python3
"""DERVS STT — o 'ouvido' que fica ligado esperando fala.

Roda no ambiente isolado ~/voice/whisper-venv (que tem o faster-whisper).

DOIS caminhos, escolhidos pela config (stt):
  - "openai" (PADRÃO se houver chave): manda o .wav para a OpenAI
    (gpt-4o-mini-transcribe) — mais rápido e preciso que o local, e ~US$ 0,003
    por minuto de áudio. Não carrega o modelo local (economiza ~1,6 GB de RAM);
    o Whisper local só é carregado se a OpenAI falhar (sem internet).
  - "local": Whisper large-v3-turbo no processador, offline e grátis (~4,7 s).

Se a OpenAI falhar numa transcrição, cai no local sozinho — nunca fica surdo.

Protocolo de linha, para o app Qt conversar por stdin/stdout:
  - ao ficar pronto, imprime:      READY
  - o app manda, por linha, o caminho de um .wav gravado
  - responde, por linha:           RESULT <json-do-texto>
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
STT_MODELO = _conf.get("stt_openai_modelo", "gpt-4o-mini-transcribe")
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


def main() -> None:
    # Se o local é o padrão, carrega já (custa alguns segundos) para o READY só
    # sair quando estiver pronto. Se a OpenAI é o padrão, READY sai na hora e o
    # local fica adormecido até ser preciso.
    if not (STT == "openai" and OPENAI_KEY):
        _carregar_local()

    sys.stdout.write("READY\n")
    sys.stdout.flush()

    while True:
        linha = sys.stdin.readline()
        if not linha:            # stdin fechado = app saiu
            break
        caminho = linha.strip()
        if not caminho:
            continue
        try:
            texto = _transcrever(caminho)
        except Exception as erro:  # nunca derruba o daemon por um áudio ruim
            texto = ""
            sys.stderr.write("dervs_stt: erro ao transcrever %s (%s)\n" % (caminho, erro))
            sys.stderr.flush()
        sys.stdout.write("RESULT " + json.dumps(texto, ensure_ascii=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
