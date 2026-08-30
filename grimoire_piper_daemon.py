#!/usr/bin/env python3
"""Grimoire Piper — daemon da voz rápida (síntese frase a frase).

Roda no ambiente isolado ~/voice/tts-venv (onde o pacote "piper-tts" está
instalado — o venv principal do Grimoire não tem onnxruntime).

O motivo de existir: gerar a fala pelo Piper na linha de comando (um processo
novo por frase) mede ~0,7 s SÓ para o processo subir e carregar o modelo .onnx
— antes mesmo de sintetizar qualquer coisa. Este daemon carrega o modelo UMA
vez e fica vivo, então esse custo é pago só na inicialização do Grimoire; cada
fala depois disso paga só o tempo de síntese em si (dezenas de ms por frase).

Devolve o áudio FRASE POR FRASE — o método `PiperVoice.synthesize()` já separa
o texto em sentenças e gera uma de cada vez — para quem chama poder tocar a
primeira frase enquanto este daemon ainda gera a segunda (é isso que derruba o
"tempo até o primeiro som" num texto longo).

Protocolo de linha, no mesmo espírito do daemon do XTTS (grimoire_tts_daemon.py):
  - ao subir, carrega o modelo padrão (argv[1], se vier) e imprime      READY
  - recebe, por linha, um JSON:
        {"texto": "...", "modelo": "/caminho/voz.onnx",
         "length_scale": 0.95, "noise_w": 0.9}
    (só "texto" é obrigatório — o resto cai no padrão do próprio modelo)
  - responde, por linha, uma vez PARA CADA FRASE reconhecida dentro do texto,
    na ordem em que vai gerando (não espera juntar todas):
                                                    WAV <caminho-do-wav>
    e ao fim de toda a requisição:                  FIM
    (ou, se a requisição inteira falhar:             ERRO <motivo>)

Importante: mesmo se quem chamou perder o interesse na fala no meio do caminho
(barge-in), ele PRECISA continuar lendo as linhas até o FIM antes de mandar o
próximo pedido — senão a resposta de um pedido velho se mistura com a do novo.
Isso é responsabilidade de quem lê (grimoire_tts.py), não deste daemon.
"""
import os
import sys
import json
import wave
import tempfile

# só existem nesta venv (tts-venv) — de propósito, isolados do app principal.
from piper import PiperVoice
from piper.config import SynthesisConfig

# pequeno silêncio colado no fim de cada frase: sem isto, como cada frase vira
# um arquivo/processo de reprodução separado, uma fala grudaria na outra.
SILENCIO_ENTRE_FRASES_S = 0.12

_VOZES = {}  # cache: caminho do .onnx -> PiperVoice já carregado na memória


def _carregar(caminho: str) -> PiperVoice:
    voz = _VOZES.get(caminho)
    if voz is None:
        voz = PiperVoice.load(caminho)
        _VOZES[caminho] = voz
    return voz


def _gravar_wav(chunk) -> str:
    """Grava um pedaço de áudio (uma frase) num wav próprio e devolve o caminho."""
    tmp = tempfile.NamedTemporaryFile(prefix="grimoire_piper_", suffix=".wav", delete=False)
    caminho = tmp.name
    tmp.close()
    amostras = chunk.audio_int16_array
    silencio_n = int(chunk.sample_rate * SILENCIO_ENTRE_FRASES_S)
    if silencio_n > 0:
        import numpy as np
        amostras = np.concatenate([amostras, np.zeros(silencio_n, dtype=amostras.dtype)])
    with wave.open(caminho, "wb") as w:
        w.setnchannels(chunk.sample_channels)
        w.setsampwidth(chunk.sample_width)
        w.setframerate(chunk.sample_rate)
        w.writeframes(amostras.tobytes())
    return caminho


def main() -> None:
    modelo_padrao = sys.argv[1] if len(sys.argv) > 1 else None
    if modelo_padrao:
        try:
            _carregar(modelo_padrao)   # aquece já na subida — some o custo depois
        except Exception as erro:
            sys.stderr.write("grimoire_piper: falha ao carregar %s (%s)\n" % (modelo_padrao, erro))
            sys.stderr.flush()

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
            caminho_modelo = pedido.get("modelo") or modelo_padrao
            if not caminho_modelo:
                raise ValueError("nenhum modelo informado")
            cfg = SynthesisConfig(
                length_scale=pedido.get("length_scale"),
                noise_w_scale=pedido.get("noise_w"),
            )
            voz = _carregar(caminho_modelo)
            for chunk in voz.synthesize(texto, cfg):
                caminho = _gravar_wav(chunk)
                sys.stdout.write("WAV " + caminho + "\n")
                sys.stdout.flush()    # manda JÁ, frase por frase — não junta tudo
            sys.stdout.write("FIM\n")
        except Exception as erro:     # nunca derruba o daemon por uma fala ruim
            sys.stderr.write("grimoire_piper: erro (%s)\n" % erro)
            sys.stderr.flush()
            sys.stdout.write("ERRO " + str(erro).replace("\n", " ") + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
