#!/usr/bin/env python3
"""DERVS — gera amostras de voz para o dono escolher.

Sintetiza a mesma frase nas 3 vozes do Kokoro em português, em 2 velocidades
cada (6 arquivos .wav no total), para ouvir e decidir qual combinação fica
melhor. Roda direto na venv principal do projeto (dervs-venv), sem precisar
do daemon nem de outra venv — é só uma síntese avulsa.

Rodar:
    dervs-venv\\Scripts\\python.exe amostras_de_voz.py
"""
import os
import sys
import wave

import numpy as np
from kokoro_onnx import Kokoro

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dervs_tts import _dir_modelos_kokoro  # mesma lógica de onde ficam os modelos

VOZES = {
    "pm_santa": "masculina grave (feiticeiro)",
    "pm_alex": "masculina",
    "pf_dora": "feminina",
}
VELOCIDADES = (1.0, 1.3)
FRASE = "Pronto, abri o Chrome pra você. Quer que eu procure alguma coisa?"
LANG = "pt-br"
PASTA_SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "amostras_voz")


def _gravar_wav(caminho: str, audio, sr: int) -> None:
    pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main() -> None:
    dir_modelos = _dir_modelos_kokoro()
    modelo = os.path.join(dir_modelos, "kokoro-v1.0.onnx")
    vozes_bin = os.path.join(dir_modelos, "voices-v1.0.bin")
    if not (os.path.exists(modelo) and os.path.exists(vozes_bin)):
        print(f"Não achei os modelos do Kokoro em {dir_modelos}.")
        print("Baixe-os antes, ou aponte a variável DERVS_MODELOS para a pasta certa.")
        sys.exit(1)

    print("Carregando o modelo Kokoro (alguns segundos)...")
    kokoro = Kokoro(modelo, vozes_bin)

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    print()
    print("Gerando as amostras — ouça e escolha a voz e a velocidade que preferir:")
    print()

    gerados = []
    for voz, rotulo in VOZES.items():
        for velocidade in VELOCIDADES:
            audio, sr = kokoro.create(FRASE, voice=voz, speed=velocidade, lang=LANG)
            nome_arquivo = f"{voz}_{velocidade:.1f}x.wav"
            caminho = os.path.join(PASTA_SAIDA, nome_arquivo)
            _gravar_wav(caminho, audio, sr)
            print(f"  {caminho}")
            print(f"      voz {voz} ({rotulo}), velocidade {velocidade:.1f}x")
            gerados.append(caminho)

    print()
    print(f"Prontos {len(gerados)} arquivos em: {PASTA_SAIDA}")
    print("Toque cada um e me diga qual voz e velocidade você prefere.")


if __name__ == "__main__":
    main()
