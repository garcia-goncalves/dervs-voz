#!/usr/bin/env python3
"""Mede cada motor de conversa com a mesma pergunta gravada (poucos pedidos pagos).

Uso:  dervs-venv\\Scripts\\python.exe scripts\\medir_conversa.py [gemini_live cascata openai_realtime]

Manda a pergunta em tempo real (quadros de 100 ms), chama `fim_da_vez()` e mede
do fim da fala até o PRIMEIRO som e até o fim da resposta. Salva a resposta em
`amostras_voz/conversa_15-10/motor_<nome>.wav` e imprime uma linha JSON por motor.
Limite (429) é resultado válido: aparece como `"erro": "limite"`.

A pergunta é gerada uma vez pela voz da OpenAI e guardada em
`amostras_voz/conversa_15-10/pergunta_16k.wav` (a pasta não vai para o Git).
Nunca imprime chave nem URL.
"""
import json
import os
import sys
import time
import wave

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import numpy as np                                    # noqa: E402

import dervs_config                                   # noqa: E402
import dervs_conversa as dc                           # noqa: E402

PASTA = os.path.join(RAIZ, "amostras_voz", "conversa_15-10")
PERGUNTA = ("Opa DERVS, tô meio cansado hoje. Me fala rapidinho o que você acha "
            "de eu dar uma pausa de dez minutos antes de continuar o projeto?")
INSTRUCOES = ("Você é o DERVS, assistente pessoal. Fale sempre em português do Brasil, "
              "natural e caloroso, respostas de uma ou duas frases.")
LIMITE_S = 40


def pergunta_16k():
    """PCM int16 16 kHz da pergunta; gera com a voz da OpenAI na primeira vez."""
    os.makedirs(PASTA, exist_ok=True)
    arq = os.path.join(PASTA, "pergunta_16k.wav")
    if not os.path.exists(arq):
        import dervs_tts
        conf = dervs_config.carregar()
        tmp = dervs_tts.sintetizar_openai(PERGUNTA, "ash", conf["voz_openai_modelo"],
                                          "Fale em português do Brasil, como uma pessoa comum.",
                                          dervs_config.segredo("OPENAI_API_KEY"), 1.0)
        if not tmp:
            raise SystemExit("não consegui gerar a pergunta (voz da OpenAI falhou)")
        with wave.open(tmp) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64)
            taxa = w.getframerate()
        os.remove(tmp)
        n = int(len(x) * 16000 / taxa)
        y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.int16)
        with wave.open(arq, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(y.tobytes())
    with wave.open(arq) as w:
        return w.readframes(w.getnframes())


def medir(nome, pcm):
    eventos, pcm_saida = [], bytearray()
    primeiro = [None]
    t0 = [None]

    def cb(ev):
        eventos.append(ev)
        if isinstance(ev, dc.AudioSaida):
            if primeiro[0] is None and t0[0] is not None:
                primeiro[0] = time.monotonic() - t0[0]
            pcm_saida.extend(ev.pcm)

    conf = dervs_config.carregar()
    motor = dc._fabrica_padrao(nome, cb, conf)
    motor.iniciar(INSTRUCOES, [])
    time.sleep(1.0)                                   # conexão e setup
    passo = 3200                                      # 100 ms a 16 kHz
    inicio = time.monotonic()
    for i in range(0, len(pcm), passo):
        motor.enviar_audio(pcm[i:i + passo])
        time.sleep(max(0, inicio + (i + passo) / 32000.0 - time.monotonic()))
    t0[0] = time.monotonic()
    motor.fim_da_vez()
    fim = None
    while time.monotonic() - t0[0] < LIMITE_S:
        if any(isinstance(e, dc.FimResposta) for e in eventos):
            fim = time.monotonic() - t0[0]
            break
        if any(isinstance(e, dc.Erro) for e in eventos):
            break
        time.sleep(0.02)
    motor.encerrar()
    erros = [e for e in eventos if isinstance(e, dc.Erro)]
    saida = {"motor": nome}
    if erros:
        saida["erro"] = erros[0].tipo
    if primeiro[0] is not None:
        saida["primeiro_som_s"] = round(primeiro[0], 2)
    if fim is not None:
        saida["resposta_inteira_s"] = round(fim, 2)
    if pcm_saida:
        taxa = [e for e in eventos if isinstance(e, dc.AudioSaida)][0].taxa
        arq = os.path.join(PASTA, "motor_%s.wav" % nome)
        with wave.open(arq, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(bytes(pcm_saida))
        saida["audio_s"] = round(len(pcm_saida) / 2 / taxa, 1)
        saida["arquivo"] = os.path.relpath(arq, RAIZ)
    saida["texto"] = " ".join(e.texto for e in eventos if isinstance(e, dc.TextoSaida))[:120]
    saida["uso"] = dict(motor.uso)
    return saida


if __name__ == "__main__":
    motores = sys.argv[1:] or ["gemini_live", "cascata", "openai_realtime"]
    audio = pergunta_16k()
    print("pergunta: %.1f s" % (len(audio) / 32000.0), flush=True)
    for m in motores:
        try:
            print(json.dumps(medir(m, audio), ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({"motor": m, "erro": type(e).__name__}), flush=True)
