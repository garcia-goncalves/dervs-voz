#!/usr/bin/env python3
"""DERVS — conferir se o microfone está bom para ele te ouvir.

Guia por BIPE, não por texto: rodando pelo `!` da conversa a tela só aparece no
fim, e você não veria a hora de falar. Então:

    1 bipe curto  ->  fique CALADO (3s, medindo o barulho da sala)
    2 bipes       ->  FALE AGORA (12s)
    1 bipe grave  ->  acabou

No fim ele mede, transcreve, e imprime o comando exato do ganho certo — calculado
da sua voz, não chutado.

Rodar:   ~/voice/whisper-venv/bin/python ~/voice/calibrar_microfone.py
"""
import array
import math
import os
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dervs_listen import Endpointer, rms, salvar_wav, FRAME_BYTES  # noqa: E402

SEGUNDOS_FALA = 12
SEGUNDOS_SIL = 3
PLACA = "1"                 # placa de som com o microfone (Ryzen HD Audio)
DB_POR_PASSO = 0.75         # 'Capture' vai de 0 a 63, de -17,25 dB a +30 dB
ALVO_RMS = 1800.0           # volume médio que a voz deve ter (sai do chiado)
ALVO_PICO = 22000.0         # teto do pico (67% da escala): espaço para você falar mais alto


def bipe(freq=880, ms=180, volume=0.35):
    """Toca um tom curto. É o que te diz a hora de falar."""
    taxa = 16000
    n = taxa * ms // 1000
    amostras = array.array(
        "h", [int(volume * 22000 * math.sin(2 * math.pi * freq * i / taxa)
                  * min(1.0, min(i, n - i) / 200.0))      # sobe/desce suave: sem estalo
              for i in range(n)])
    caminho = "/tmp/dervs_bipe.wav"
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa)
        w.writeframes(amostras.tobytes())
    for tocador in (["paplay", caminho], ["aplay", "-q", caminho]):
        try:
            if subprocess.run(tocador, capture_output=True, timeout=5).returncode == 0:
                return
        except Exception:
            continue


def gravar(segundos):
    return subprocess.run(
        ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw",
         "-d", str(segundos)], capture_output=True).stdout


def perfil(pcm):
    """Lista de RMS por quadro de 30 ms."""
    return [rms(pcm[i:i + FRAME_BYTES])
            for i in range(0, len(pcm) - FRAME_BYTES, FRAME_BYTES)]


def q(ordenados, quantil):
    if not ordenados:
        return 0.0
    return ordenados[int(quantil * (len(ordenados) - 1))]


def _valor_do_canal(saida, prefixo=""):
    """Lê o número na linha 'Front Left: [Capture ]N [x%] …' do amixer.

    Cuidado: a saída tem outras linhas com a mesma palavra ('Limits: Capture 0 - 63'),
    então a âncora TEM que ser a linha do canal, não a palavra solta.
    """
    for linha in saida.splitlines():
        linha = linha.strip()
        if linha.startswith(("Front Left:", "Mono:")):
            resto = linha.split(":", 1)[1].strip()
            if prefixo and resto.startswith(prefixo):
                resto = resto[len(prefixo):].strip()
            try:
                return int(resto.split(" ")[0])
            except ValueError:
                return None
    return None


def ganho_atual_db():
    try:
        cap = subprocess.run(["amixer", "-c", PLACA, "sget", "Capture"],
                             capture_output=True, text=True).stdout
        bst = subprocess.run(["amixer", "-c", PLACA, "sget", "Front Mic Boost"],
                             capture_output=True, text=True).stdout
        return _valor_do_canal(cap, "Capture"), _valor_do_canal(bst)
    except Exception:
        return None, None


def receita_de_ganho(capture, boost, fator):
    """Traduz 'preciso multiplicar por FATOR' nos controles reais da placa."""
    if capture is None:
        return None
    precisa_db = 20 * math.log10(max(fator, 1e-3))
    novo_boost = boost
    novo_capture = capture + precisa_db / DB_POR_PASSO
    while novo_capture > 63 and novo_boost < 3:      # estourou o Capture: usa o Boost
        novo_boost += 1
        novo_capture -= 10 / DB_POR_PASSO
    while novo_capture < 0 and novo_boost > 0:       # sobrou ganho: tira do Boost
        novo_boost -= 1
        novo_capture += 10 / DB_POR_PASSO
    novo_capture = max(0, min(63, int(round(novo_capture))))
    if (novo_capture, novo_boost) == (capture, boost):
        return None
    return novo_capture, novo_boost


def main():
    capture, boost = ganho_atual_db()
    print("=" * 64)
    print("CALIBRAÇÃO DO MICROFONE — siga pelos BIPES, não pela tela.")
    print("  1 bipe  = fique calado   |   2 bipes = FALE   |   1 bipe grave = fim")
    if capture is not None:
        print("  ganho agora: Capture %d, Front Mic Boost %d" % (capture, boost))
    print("=" * 64)
    sys.stdout.flush()

    bipe(880, 200)
    silencio = perfil(gravar(SEGUNDOS_SIL))

    bipe(1320, 140); bipe(1320, 140)
    fala_pcm = gravar(SEGUNDOS_FALA)
    bipe(440, 260)

    silencio.sort()
    ruido_tipico, ruido_pico = q(silencio, 0.5), q(silencio, 1.0)

    todos = perfil(fala_pcm)
    # A "voz" é só a parte alta da gravação — você não falou os 12 segundos inteiros.
    altos = sorted(todos)[int(0.65 * len(todos)):] if todos else []
    voz_tipica = q(altos, 0.5)
    voz_pico = q(sorted(todos), 1.0)

    ep = Endpointer()
    limiar = ep.limiar_abs
    frases = []
    for i in range(0, len(fala_pcm) - FRAME_BYTES, FRAME_BYTES):
        pcm = ep.processar(fala_pcm[i:i + FRAME_BYTES])
        if pcm:
            frases.append(pcm)
    if ep.em_fala and ep.buf:
        frases.append(b"".join(ep.buf))

    print()
    print("BARULHO DA SALA (você calado)   típico %6.0f   pico %6.0f" % (ruido_tipico, ruido_pico))
    print("SUA VOZ (parte alta da fala)    típico %6.0f   pico %6.0f" % (voz_tipica, voz_pico))
    print("LINHA DE CORTE do DERVS      %6.0f" % limiar)
    print()

    # 1) O sinal está estourando? Áudio estourado é áudio distorcido — o Whisper
    #    erra as palavras mesmo com o volume "bom". Isto vem ANTES do resto.
    amostras = array.array("h"); amostras.frombytes(fala_pcm)
    pico_amostra = max((abs(x) for x in amostras), default=0)
    print("  pico da gravação: %d de 32768 (%.0f%% da escala)%s"
          % (pico_amostra, 100 * pico_amostra / 32768,
             "  ← ESTOURANDO, som distorcido" if pico_amostra >= 32700 else ""))

    # 2) A folga entre a sua voz e o barulho da sala. Ganho NÃO conserta folga
    #    ruim: ele levanta a voz e o chiado juntos.
    folga = voz_tipica / max(ruido_tipico, 1.0)
    print("  sua voz está %.1f× acima do barulho da sala" % folga)
    if folga < 2.0:
        print("    ✗ folga péssima. Ou você não falou na hora dos DOIS bipes, ou o")
        print("      ganho está tão baixo que sua voz sumiu no chiado do conversor.")
    elif folga < 4.0:
        print("    ✗ pouca folga: chegue mais perto do microfone ou reduza o ruído da sala.")

    # 3) O ganho. Sempre calculado, mesmo com folga ruim — é justamente com ganho
    #    baixo demais que a folga fica ruim.
    # DUAS restrições, e vale a mais apertada das duas:
    #   - volume médio: a voz precisa ficar perto do alvo para sair do chiado;
    #   - teto: o pico não pode encostar em 32768, senão distorce.
    # Olhar só a média foi um erro real: com a voz em 1209 e o pico já em 88% da
    # escala, o cálculo pela média mandava SUBIR — e subir faria estourar.
    fator_volume = ALVO_RMS / max(voz_tipica, 1.0)
    fator_teto = ALVO_PICO / max(pico_amostra, 1)
    fator = min(fator_volume, fator_teto)
    if abs(20 * math.log10(max(fator, 1e-3))) < 2.0:
        fator = 1.0                       # menos de 2 dB de diferença: não mexe
    receita = receita_de_ganho(capture, boost, fator)
    if receita is None:
        print("  ✓ ganho no ponto (voz %d, pico %.0f%% — sem estourar e fora do chiado)"
              % (voz_tipica, 100 * pico_amostra / 32768))
    else:
        c, b = receita
        verbo = "SUBA" if fator > 1 else "BAIXE"
        if fator_teto < fator_volume:
            print("  (limitado pelo pico, não pelo volume médio: falta espaço no topo)")
        print("  ➜ %s o ganho (alvo: voz em %d, sem estourar):" % (verbo, int(ALVO_RMS)))
        print("      amixer -c %s -q sset 'Front Mic Boost' %d" % (PLACA, b))
        print("      amixer -c %s -q sset Capture %d" % (PLACA, c))
        print("    para valer sempre, troque os dois ExecStartPre em")
        print("      ~/.config/systemd/user/dervs.service")
    print()

    print("=" * 64)
    print("FRASES SEPARADAS: %d" % len(frases))
    if len(frases) > 2:
        print("  ✗ demais para uma fala só — ele ainda está te picotando.")
    if not frases:
        print("  ✗ nenhuma — nada passou da linha de corte.")
        return

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("\n(rode com ~/voice/whisper-venv/bin/python para ver a transcrição)")
        return
    print("\nO QUE ELE ENTENDEU (carregando o Whisper, ~20s na primeira vez)…\n")
    sys.stdout.flush()
    m = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    for n, pcm in enumerate(frases, 1):
        caminho = "/tmp/dervs_calib_%d.wav" % n
        salvar_wav(pcm, caminho)
        segs, _ = m.transcribe(caminho, language="pt", vad_filter=True, beam_size=5,
                               condition_on_previous_text=False)
        texto = "".join(s.text for s in segs).strip()
        print("  frase %d (%.1fs): %s" % (n, len(pcm) / 32000, texto or "(vazio — era ruído)"))
    print("\nSe cada frase saiu inteira e certa, o ouvido está bom.")
    print("Guardei os arquivos em /tmp/dervs_calib_*.wav.")


if __name__ == "__main__":
    main()
