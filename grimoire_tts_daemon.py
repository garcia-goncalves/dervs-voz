#!/usr/bin/env python3
"""Grimoire XTTS — daemon da voz humana.

Roda no ambiente isolado ~/voice/xtts-venv (que tem o coqui-tts/torch). Carrega o
modelo XTTS v2 UMA vez (são ~2 GB) e depois sintetiza rápido. Sem isto, cada fala
recarregaria o modelo inteiro e demoraria uma eternidade.

Protocolo de linha, igual ao dos ouvidos (grimoire_stt_daemon):
  - ao terminar de carregar:                       imprime  READY
  - recebe, por linha, o texto a falar (JSON de uma string)
  - responde, por linha:                           WAV <caminho-do-wav>
                                                    ou ERRO
"""
import os
import sys
import json
import tempfile

# aceita a licença do modelo sem prompt interativo (o dono já optou por esta voz)
os.environ.setdefault("COQUI_TOS_AGREED", "1")

# Falante embutido do XTTS v2 e idioma. Trocável por variável de ambiente.
FALANTE = os.environ.get("GRIMOIRE_XTTS_SPEAKER", "Damien Black")
IDIOMA = os.environ.get("GRIMOIRE_XTTS_LANG", "pt")


def main() -> None:
    # usa todos os núcleos do processador (sem isto o torch às vezes usa poucos)
    try:
        import torch
        torch.set_num_threads(os.cpu_count() or 8)
    except Exception:
        pass
    from TTS.api import TTS
    modelo = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

    sys.stdout.write("READY\n")
    sys.stdout.flush()

    while True:
        linha = sys.stdin.readline()
        if not linha:                 # stdin fechado = app saiu
            break
        bruto = linha.strip()
        if not bruto:
            continue
        try:
            texto = json.loads(bruto) if bruto[:1] == '"' else bruto
            saida = tempfile.NamedTemporaryFile(prefix="grimoire_xtts_",
                                                suffix=".wav", delete=False).name
            modelo.tts_to_file(text=texto, speaker=FALANTE, language=IDIOMA,
                               file_path=saida)
            sys.stdout.write("WAV " + saida + "\n")
        except Exception as erro:      # nunca derruba o daemon por uma fala ruim
            sys.stderr.write("grimoire_xtts: erro (%s)\n" % erro)
            sys.stderr.flush()
            sys.stdout.write("ERRO\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
