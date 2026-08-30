#!/usr/bin/env python3
"""Grimoire STT — o 'cérebro' de voz que fica ligado esperando fala.

Roda no ambiente isolado ~/voice/whisper-venv (que tem o faster-whisper).
Carrega o modelo Whisper large-v3-turbo UMA vez e depois transcreve rápido.

Protocolo simples de linha, para o app Qt conversar por stdin/stdout:
  - ao terminar de carregar o modelo, imprime:      READY
  - o app manda, por linha, o caminho de um .wav gravado
  - responde, por linha:                            RESULT <json-do-texto>
Assim o app (grimoire.py) nunca trava esperando a transcrição.
"""
import sys
import json


def main() -> None:
    from faster_whisper import WhisperModel

    # int8 = leve o bastante para rodar no processador (sem placa NVIDIA).
    #
    # cpu_threads=8: SEM isso, o ctranslate2 (motor por trás do faster-whisper)
    # decide sozinho quantas threads usar — e nesta máquina decidia mal. Medido:
    # threads=1 -> 13,8-15,0s | threads=4 -> 5,2-9,2s | threads=8 -> 4,8-5,1s |
    # threads=16 -> 5,0-8,6s | default (sem passar nada) -> 5,2-5,7s, mas
    # instável (variação de carga da máquina fez o mesmo teste chegar a 8,1s
    # sem cpu_threads fixo). O motivo: este AMD Ryzen 7 5700G tem 8 núcleos
    # FÍSICOS e 16 threads via SMT (`lscpu`); a carga do Whisper é pesada em
    # ponto flutuante/inteiro e usar as 16 threads (SMT) gera contenção — pior
    # que travar em 8. Fixar cpu_threads=8 evita o motor "adivinhar" errado e
    # dá o tempo mais baixo e mais estável dos testados.
    #
    # PISO FÍSICO que não dá pra descer daqui: o encoder do Whisper sempre
    # processa uma janela de 30s (arquitetura fixa — testado transcrevendo um
    # áudio de só 1s: mesmo tempo, ~4,5-5,6s, que os áudios de 11,55s e 3,6s).
    # Por isso beam_size não muda o tempo de forma relevante (afeta só a
    # decodificação, uma fração pequena do custo) — e por isso large-v3-turbo
    # NÃO chega a <2s neste hardware sem GPU: esse é o chão do modelo, não um
    # ajuste de parâmetro. Modelo menor (medium/small) chega a <2s mas troca
    # palavra ("pelo"->"pela" no áudio de calibração, sistemático) e o small
    # chega a comer palavra inteira — por isso NÃO entraram, reprovados no
    # critério de acerto. Detalhe completo no relatório da tarefa.
    model = WhisperModel(
        "large-v3-turbo", device="cpu", compute_type="int8", cpu_threads=8
    )

    sys.stdout.write("READY\n")
    sys.stdout.flush()

    # readline() em vez de 'for linha in sys.stdin' de propósito: o iterador do stdin
    # faz leitura antecipada em bloco e poderia SEGURAR a linha no buffer, travando a
    # transcrição até chegar mais dado. readline() devolve assim que vê a quebra de linha.
    while True:
        linha = sys.stdin.readline()
        if not linha:            # stdin fechado = app saiu
            break
        caminho = linha.strip()
        if not caminho:
            continue
        try:
            segmentos, _info = model.transcribe(
                caminho,
                language="pt",                 # português fixo — não deixa "adivinhar" idioma
                vad_filter=True,               # corta silêncio/ruído: menos alucinação
                beam_size=5,                   # busca mais cuidadosa = mais acerto
                condition_on_previous_text=False,  # cada ditado é independente, não arrasta erro
                # "cola" (initial_prompt): NÃO é dicionário — o Whisper só lê ~224 tokens
                # dela, e lista longa demais faz ele repetir/errar. É uma amostra do jeito
                # de falar, que ensina acento, pontuação e o formato de números em pt-BR.
                initial_prompt=(
                    "Transcrição em português do Brasil, com acentuação e pontuação "
                    "corretas. É uma pessoa falando com um assistente de voz chamado "
                    "Grimoire. Frases típicas: 'Grimoire, que horas são?', 'Grimoire, "
                    "que dia é hoje?', 'abre o Firefox', 'lista os arquivos', 'roda o "
                    "nmap no alvo'. O assunto varia entre o dia a dia, trabalho, "
                    "tecnologia, segurança da informação, negócios e finanças. "
                    "Vocabulário comum: e-mail, WhatsApp, site, aplicativo, reunião, "
                    "projeto, cliente, OSINT, subdomínio, domínio, DNS, certificado, "
                    "vulnerabilidade, Grimoire, Parrot. Números e valores aparecem como "
                    "2026, R$ 1.500,00 e 10%, com vírgula, ponto, interrogação e "
                    "exclamação usados naturalmente."
                ),
            )
            texto = "".join(seg.text for seg in segmentos).strip()
        except Exception as erro:  # nunca derruba o daemon por um áudio ruim
            texto = ""
            sys.stderr.write("grimoire_stt: erro ao transcrever %s (%s)\n" % (caminho, erro))
            sys.stderr.flush()

        sys.stdout.write("RESULT " + json.dumps(texto, ensure_ascii=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
