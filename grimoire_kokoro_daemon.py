#!/usr/bin/env python3
"""Grimoire Kokoro — daemon da voz humana e rápida (síntese frase a frase).

Roda no ambiente isolado ~/voice/kokoro-venv (onde estão kokoro-onnx e
soundfile). O Kokoro é um modelo aberto (82M, Apache-2.0) que gera voz bem mais
humana que o Piper e ainda roda 3–4× o tempo real no processador desta máquina
(sem GPU) — o meio-termo que faltava entre o Piper (instantâneo, robótico) e o
XTTS (humano, mas lento demais no CPU).

Mesmo motivo de existir do daemon do Piper: carregar o modelo (~325 MB) custa
alguns segundos; feito UMA vez aqui, cada fala depois paga só a síntese.

Protocolo de linha, IGUAL ao do Piper (grimoire_piper_daemon.py) para o
grimoire_tts.py falar com os dois do mesmo jeito:
  - ao subir, carrega o modelo e imprime                 READY
  - recebe, por linha, um JSON:
        {"texto":"...", "voz":"pm_santa", "speed":1.0, "lang":"pt-br"}
    (só "texto" é obrigatório; o resto cai no padrão)
  - responde uma linha PARA CADA FRASE, na ordem:        WAV <caminho-do-wav>
    e ao fim de toda a requisição:                       FIM
    (ou, se a requisição inteira falhar:                 ERRO <motivo>)
"""
import os
import re
import sys
import json
import wave
import tempfile

import numpy as np
from kokoro_onnx import Kokoro

MODELO = os.path.expanduser("~/voice/kokoro-model/kokoro-v1.0.onnx")
VOZES = os.path.expanduser("~/voice/kokoro-model/voices-v1.0.bin")

VOZ_PADRAO = "pm_santa"   # masculina grave (feiticeiro); troca no pedido
LANG_PADRAO = "pt-br"
SILENCIO_ENTRE_FRASES_S = 0.12

# quebra o texto em frases para tocar a 1ª enquanto gera a 2ª (menor tempo até
# o primeiro som). Corta em . ! ? ; mantendo pausa natural.
_FIM_FRASE = re.compile(r"(?<=[.!?;:])\s+")


def _frases(texto: str):
    partes = [p.strip() for p in _FIM_FRASE.split(texto.strip()) if p.strip()]
    return partes or ([texto.strip()] if texto.strip() else [])


def _gravar_wav(audio, sr: int) -> str:
    """Grava um trecho (uma frase) num wav int16 e devolve o caminho."""
    tmp = tempfile.NamedTemporaryFile(prefix="grimoire_kokoro_", suffix=".wav", delete=False)
    caminho = tmp.name
    tmp.close()
    a = np.asarray(audio, dtype=np.float32)
    sil = int(sr * SILENCIO_ENTRE_FRASES_S)
    if sil > 0:
        a = np.concatenate([a, np.zeros(sil, dtype=np.float32)])
    pcm = np.clip(a, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return caminho


def main() -> None:
    try:
        kokoro = Kokoro(MODELO, VOZES)
    except Exception as erro:
        sys.stderr.write("grimoire_kokoro: falha ao carregar modelo (%s)\n" % erro)
        sys.stderr.flush()
        sys.stdout.write("ERRO carga do modelo: %s\n" % str(erro).replace("\n", " "))
        sys.stdout.flush()
        return

    sys.stdout.write("READY\n")
    sys.stdout.flush()

    while True:
        linha = sys.stdin.readline()
        if not linha:              # stdin fechado = app saiu
            break
        bruto = linha.strip()
        if not bruto:
            continue
        try:
            pedido = json.loads(bruto)
            texto = pedido["texto"]
            voz = pedido.get("voz") or VOZ_PADRAO
            speed = float(pedido.get("speed") or 1.0)
            lang = pedido.get("lang") or LANG_PADRAO
            for frase in _frases(texto):
                audio, sr = kokoro.create(frase, voice=voz, speed=speed, lang=lang)
                caminho = _gravar_wav(audio, sr)
                sys.stdout.write("WAV " + caminho + "\n")
                sys.stdout.flush()    # manda JÁ, frase por frase
            sys.stdout.write("FIM\n")
        except Exception as erro:     # nunca derruba o daemon por uma fala ruim
            sys.stderr.write("grimoire_kokoro: erro (%s)\n" % erro)
            sys.stderr.flush()
            sys.stdout.write("ERRO " + str(erro).replace("\n", " ") + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
