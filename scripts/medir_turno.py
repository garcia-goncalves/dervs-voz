"""Mede o árbitro de vez (`dervs_turno.py`) com os modelos de verdade nos casos de hesitação de 15/10.

Para cada caso monta o áudio (trechos de fala + pausas + 4 s de silêncio), entrega quadro a quadro
de 30 ms ao árbitro e diz: houve FimDeVez ANTES do fim real da fala? (tem de ser nenhum nos casos
de hesitação) e quanto tempo depois do fim real ele veio. Também mede o CPU de cada inferência
do Smart Turn.

Uso:
  python scripts/medir_turno.py <pasta_com_wavs> [--casos casos.json] [--prob 0.5] [--espera 3.0]

A pasta tem wavs mono 16 bits (qualquer taxa; é reamostrado para 16 kHz). Sem --casos usa os 4 casos
de hesitação + a frase completa do teste de 15/10; cada trecho é o wav `tts_<crc32 do texto>.wav`
(o cache que o teste da OpenAI gerou). Com --casos, o JSON é {"caso": [["arquivo.wav", pausa_s], ...]}:
a pausa vem DEPOIS do trecho; a da última parte vale 0.
"""
import argparse
import json
import os
import sys
import time
import wave
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np  # noqa: E402

import dervs_turno as T  # noqa: E402

CASOS = {
    "completa": [("Abre o Chrome pra mim.", 0)],
    "hesita_1,5s": [("Eu queria que você...", 1.5), ("éé... hum...", 1.0), ("abrisse o Chrome pra mim.", 0)],
    "hesita_2,5s": [("Me lembra de ligar pro...", 2.5), ("pro dentista amanhã cedo.", 0)],
    "gagueja": [("Cria uma, uma... uma pasta nova", 1.2), ("chamada fotos da viagem.", 0)],
}
SILENCIO_FINAL_S = 4.0


def ler_wav16k(caminho) -> np.ndarray:
    with wave.open(caminho) as w:
        taxa, bruto = w.getframerate(), w.readframes(w.getnframes())
    x = np.frombuffer(bruto, np.int16).astype(np.float64)
    if taxa != T.TAXA:                       # reamostra por FFT (sem scipy)
        n = int(round(len(x) * T.TAXA / taxa))
        espectro = np.fft.rfft(x)
        novo = np.zeros(n // 2 + 1, complex)
        k = min(len(novo), len(espectro))
        novo[:k] = espectro[:k]
        x = np.fft.irfft(novo, n) * (n / len(x))
    x = np.clip(x, -32768, 32767).astype(np.int16)
    # corta o silêncio que o TTS deixa no começo e no fim: a pausa do caso tem de ser só a combinada
    passo = T.TAXA // 100
    q = x[:len(x) // passo * passo].reshape(-1, passo).astype(float)
    rms = np.sqrt((q ** 2).mean(1))
    voz = np.where(rms > max(60, rms.max() * 0.08))[0]
    return x[max(0, voz[0] - 2) * passo:(voz[-1] + 3) * passo]


def arquivo_do_trecho(pasta, trecho) -> str:
    if trecho.lower().endswith(".wav"):
        return os.path.join(pasta, trecho)
    return os.path.join(pasta, "tts_%08x.wav" % zlib.crc32(trecho.encode()))


def montar(pasta, partes):
    """Devolve (áudio int16 16 kHz, instante em que a fala de verdade termina)."""
    audio, fim = [], 0.0
    for trecho, pausa in partes:
        audio.append(ler_wav16k(arquivo_do_trecho(pasta, trecho)))
        fim = sum(len(a) for a in audio) / T.TAXA
        audio.append(np.zeros(int(pausa * T.TAXA), np.int16))
    audio.append(np.zeros(int(SILENCIO_FINAL_S * T.TAXA), np.int16))
    return np.concatenate(audio), fim


def rodar_caso(arbitro, audio, fim):
    arbitro.reset()
    fins, probs = [], []
    for i in range(0, len(audio) - T.FRAME_AMOSTRAS + 1, T.FRAME_AMOSTRAS):
        for ev in arbitro.processar(audio[i:i + T.FRAME_AMOSTRAS]):
            if isinstance(ev, T.FimDeVez):
                fins.append(round(ev.t, 2))
        if getattr(arbitro, "ultima_prob", None) is not None:
            probs.append((arbitro.n, round(arbitro.ultima_prob, 2)))
            arbitro.ultima_prob = None
    cedo = [t for t in fins if t < fim - 0.05]
    depois = [round(t - fim, 2) for t in fins if t >= fim - 0.05]
    return {"fim_real_s": round(fim, 2), "cortes_antes_do_fim": cedo,
            "atraso_apos_fim_s": depois[0] if depois else None,
            "probs_smart_turn": [(round(n * 0.03, 2), p) for n, p in probs]}


def medir_cpu(modelo, n=20):
    audio = (np.random.default_rng(1).standard_normal(5 * T.TAXA) * 0.05).astype(np.float32)
    modelo(audio)                              # aquece
    t0, c0 = time.perf_counter(), time.process_time()
    for _ in range(n):
        modelo(audio)
    return (time.perf_counter() - t0) / n * 1000, (time.process_time() - c0) / n * 1000


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta")
    ap.add_argument("--casos")
    ap.add_argument("--prob", type=float, default=0.5)
    ap.add_argument("--espera", type=float, default=3.0)
    ap.add_argument("--silencio-ms", type=int, default=300)
    a = ap.parse_args()
    casos = CASOS
    if a.casos:
        with open(a.casos, encoding="utf-8") as f:
            casos = json.load(f)
    vad = T.garantir_modelo("silero_vad.onnx")
    turno = T.garantir_modelo("smart-turn-v3.2-cpu.onnx")
    if not (vad and turno):
        sys.exit("modelos indisponíveis (sem rede?)")
    modelo = T.ModeloTurno(turno)
    arbitro = T.Arbitro(T.VadSilero(vad), modelo, prob_fim=a.prob, espera_max_s=a.espera,
                        silencio_min_ms=a.silencio_ms)
    for nome, partes in casos.items():
        audio, fim = montar(a.pasta, partes)
        print(json.dumps({"caso": nome, **rodar_caso(arbitro, audio, fim)}, ensure_ascii=False), flush=True)
    relogio, cpu = medir_cpu(modelo)
    print(json.dumps({"smart_turn_ms_por_inferencia": {"relogio": round(relogio, 1), "cpu": round(cpu, 1)}}))


if __name__ == "__main__":
    main()
