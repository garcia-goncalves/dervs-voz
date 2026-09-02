#!/usr/bin/env python3
"""Transcreve um arquivo de áudio do dono e grava o texto ao lado dele.

Para que serve: o DERVS já transcrevia o que o dono FALA ao vivo. Isto é o
outro pedido — pegar um áudio que já existe (gravação de reunião, áudio de
WhatsApp, entrevista) e virar texto preciso.

Por que não é o `dervs_stt_daemon`: aquele é um processo que fica de pé com
protocolo de linha próprio, assume `.wav` e usa timeout de 30 s — desenhado
para a frase curta da conversa ao vivo. Arquivo de reunião é outro problema:
formato qualquer, dezenas de MB, minutos de envio.

Usa o mesmo motor da fala ao vivo (`gpt-transcribe`), pelo mesmo motivo: é o
mais assertivo em português e custa US$ 0,0045 por minuto de áudio — uma hora
de gravação sai por cerca de US$ 0,27.

Dois problemas que este arquivo resolve sozinho:

  1. **A API aceita no máximo 25 MB.** Um áudio de reunião passa disso fácil.
     Antes de desistir, o arquivo é reconvertido para voz falada compactada
     (mp3 mono, 16 kHz, 32 kbps) — o que encolhe cerca de 10x sem perder
     inteligibilidade, porque fala não precisa de estéreo nem de agudo. Só se
     AINDA passar é que o áudio é partido em pedaços.

  2. **Corte no meio de uma palavra.** Os pedaços se sobrepõem alguns segundos e
     a emenda descarta a repetição, para não perder nem duplicar o que foi dito
     bem na hora do corte.

Rodar:
    dervs-venv\\Scripts\\python.exe dervs_transcrever.py            (abre o seletor)
    dervs-venv\\Scripts\\python.exe dervs_transcrever.py audio.mp3  (direto)
"""
import os
import sys
import uuid
import shutil
import difflib
import tempfile
import subprocess
import urllib.request

import dervs_config

# A API recusa acima de 25 MB. 24 deixa margem para o envelope do envio.
LIMITE_BYTES = 24 * 1024 * 1024

# Pedaço de 20 minutos: em mp3 mono 32 kbps dá ~4,8 MB, folgado no limite, e é
# curto o bastante para uma falha de rede não custar a transcrição inteira.
PEDACO_SEG = 20 * 60

# Sobreposição entre pedaços. 6 s cobre com sobra a frase mais longa que alguém
# fala sem respirar, então nenhuma palavra cai exatamente na emenda.
SOBREPOR_SEG = 6

# O que a API aceita. Fora desta lista, o arquivo é convertido antes.
FORMATOS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm", ".flac"}


def _ffmpeg() -> str:
    """Caminho do ffmpeg, ou erro dizendo o que fazer."""
    caminho = shutil.which("ffmpeg")
    if not caminho:
        raise RuntimeError(
            "o ffmpeg não está instalado nesta máquina — ele é quem compacta e "
            "corta o áudio. Instale com: winget install Gyan.FFmpeg")
    return caminho


def precisa_encolher(tamanho_bytes: int) -> bool:
    """Passa do que a API aceita?"""
    return tamanho_bytes > LIMITE_BYTES


def duracao_segundos(caminho: str) -> float:
    """Quanto tempo tem o áudio, perguntando ao ffmpeg."""
    r = subprocess.run([_ffmpeg(), "-i", caminho], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    # o ffmpeg escreve "Duration: 00:12:34.56" no stderr e sai com erro por não
    # ter recebido saída — é o jeito documentado de só perguntar.
    for linha in r.stderr.splitlines():
        if "Duration:" in linha:
            bruto = linha.split("Duration:")[1].split(",")[0].strip()
            h, m, s = bruto.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"não consegui ler a duração de {os.path.basename(caminho)}")


def planejar_pedacos(duracao: float, pedaco: int = PEDACO_SEG,
                     sobrepor: int = SOBREPOR_SEG) -> list:
    """Divide a duração em (início, quanto_dura), com sobreposição.

    Devolve uma lista só, sem cortes, quando o áudio já cabe num pedaço.
    O último pedaço nunca passa do fim do áudio.
    """
    if duracao <= pedaco:
        return [(0.0, duracao)]
    partes = []
    inicio = 0.0
    while inicio < duracao:
        dura = min(pedaco, duracao - inicio)
        partes.append((inicio, dura))
        if inicio + dura >= duracao:
            break
        inicio += pedaco - sobrepor
    return partes


def _converter(entrada: str, saida: str, inicio: float = None, dura: float = None) -> str:
    """Reconverte para mp3 mono 16 kHz 32 kbps, opcionalmente só um trecho.

    Mono e 16 kHz porque fala não usa estéreo nem agudo — e é exatamente o que
    os modelos de transcrição esperam. Encolhe cerca de 10x."""
    cmd = [_ffmpeg(), "-y", "-loglevel", "error"]
    if inicio is not None:
        cmd += ["-ss", f"{inicio:.3f}"]
    cmd += ["-i", entrada]
    if dura is not None:
        cmd += ["-t", f"{dura:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", saida]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0 or not os.path.exists(saida):
        raise RuntimeError(f"o ffmpeg falhou: {r.stderr.strip()[:300]}")
    return saida


# Tirado das pontas de cada palavra antes de comparar. O modelo fecha a frase
# num pedaço e não no outro ("equipe." x "equipe"), e começo de pedaço vem com
# maiúscula ("Os números" x "os números") — comparando cru, a emenda nunca casa.
_PONTUACAO = ".,;:!?…\"'()[]{}«»—–-"


def _comparavel(palavras: list) -> list:
    """As palavras como o comparador as vê: sem pontuação nas pontas, minúsculas."""
    return [p.strip(_PONTUACAO).lower() for p in palavras]


def emendar(anterior: str, proximo: str, janela: int = 60,
            minimo: int = 5, folga: int = 2) -> str:
    """Junta dois trechos descartando o que se repete por causa da sobreposição.

    Acha o maior trecho que aparece nos dois e, se ele TERMINA no fim do
    anterior, corta do próximo tudo até onde esse trecho acaba. Terminar no fim
    do anterior é o que prova que aquilo é a sobreposição, e não o assunto
    voltando lá na frente.

    Três frouxidões, todas por comportamento medido do transcritor:

      - compara sem pontuação e sem caixa (`_comparavel`), senão "equipe." nunca
        casa com "equipe" e a emenda inteira é descartada por uma palavra;
      - `folga` de 2 palavras na borda, porque o mesmo trecho sai "12 meses" num
        pedaço e "doze meses" no outro, e essa divergência quebra o bloco perto
        da emenda;
      - exige `minimo` de 5 palavras seguidas, porque 2 ou 3 iguais acontecem por
        acaso em português ("a gente", "que a") e cortar ali comeria texto.

    Não achou emenda convincente? Junta os dois inteiros. Melhor uma frase
    repetida do que uma frase perdida: quem lê percebe a repetição, mas não tem
    como perceber o que sumiu.
    """
    ant = anterior.strip().split()
    prox = proximo.strip().split()
    if not ant:
        return proximo.strip()
    if not prox:
        return anterior.strip()

    teto = min(janela, len(ant), len(prox))
    fim = _comparavel(ant[-teto:])
    comeco = _comparavel(prox[:teto])
    m = difflib.SequenceMatcher(None, fim, comeco).find_longest_match(
        0, len(fim), 0, len(comeco))
    termina_no_fim = (len(fim) - (m.a + m.size)) <= folga
    if m.size >= minimo and termina_no_fim:
        return _colar(ant, prox[m.b + m.size:])
    return _colar(ant, prox)


def _colar(ant: list, resto: list) -> str:
    """Junta as duas metades tirando o ponto que sobrou no meio de uma frase.

    O pedaço acaba no meio da frase e o modelo fecha com ponto assim mesmo:
    "...da equipe." + "de campo." vira "da equipe. de campo." — ponto seguido de
    minúscula, que é frase partida ao meio. Some com o ponto só nesse caso; se o
    resto começa com maiúscula, a frase acabou de verdade e o ponto fica.
    """
    if not resto:
        return " ".join(ant).strip()
    if not ant:
        return " ".join(resto).strip()
    ant = list(ant)
    primeira = resto[0].lstrip("\"'(")
    if ant[-1].endswith(".") and primeira[:1].islower():
        ant[-1] = ant[-1][:-1]
    return (" ".join(ant) + " " + " ".join(resto)).strip()


def _enviar(caminho: str, chave: str, modelo: str, dica: str) -> str:
    """Manda um arquivo para a API e devolve o texto."""
    with open(caminho, "rb") as f:
        audio = f.read()
    limite = "----dervs" + uuid.uuid4().hex
    campos = {"model": modelo, "language": "pt", "response_format": "text"}
    if dica:
        campos["prompt"] = dica
    partes = []
    for k, v in campos.items():
        partes.append((f"--{limite}\r\nContent-Disposition: form-data; "
                       f'name="{k}"\r\n\r\n{v}\r\n').encode("utf-8"))
    nome = os.path.basename(caminho)
    partes.append((f'--{limite}\r\nContent-Disposition: form-data; name="file"; '
                   f'filename="{nome}"\r\nContent-Type: application/octet-stream\r\n\r\n'
                   ).encode("utf-8"))
    partes.append(audio)
    partes.append(f"\r\n--{limite}--\r\n".encode("utf-8"))
    corpo = b"".join(partes)
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions", data=corpo,
        headers={"Authorization": "Bearer " + chave,
                 "Content-Type": "multipart/form-data; boundary=" + limite})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read().decode("utf-8", "replace").strip()


def transcrever(caminho: str, avisar=print) -> str:
    """Transcreve o arquivo inteiro e devolve o texto. `avisar` recebe o andamento."""
    chave = dervs_config.segredo("OPENAI_API_KEY")
    if not chave:
        raise RuntimeError(
            "a chave da OpenAI não está nesta máquina. Ela mora em "
            f"{dervs_config.caminhos_do_segredo()[0]}, na linha OPENAI_API_KEY=")
    conf = dervs_config.carregar()
    modelo = conf.get("stt_openai_modelo") or "gpt-transcribe"
    dica = conf.get("stt_dica_vocabulario") or ""

    if not os.path.exists(caminho):
        raise RuntimeError(f"não achei o arquivo {caminho}")
    tamanho = os.path.getsize(caminho)
    ext = os.path.splitext(caminho)[1].lower()

    # Cabe e a API entende o formato? Manda direto, sem tocar no arquivo.
    if not precisa_encolher(tamanho) and ext in FORMATOS:
        avisar(f"enviando {os.path.basename(caminho)} ({tamanho/1024/1024:.1f} MB)...")
        return _enviar(caminho, chave, modelo, dica)

    temp = tempfile.mkdtemp(prefix="dervs_tr_")
    try:
        avisar("compactando o áudio (mono, 16 kHz) para caber no envio...")
        menor = _converter(caminho, os.path.join(temp, "inteiro.mp3"))
        novo = os.path.getsize(menor)
        avisar(f"  {tamanho/1024/1024:.1f} MB -> {novo/1024/1024:.1f} MB")

        if not precisa_encolher(novo):
            return _enviar(menor, chave, modelo, dica)

        dur = duracao_segundos(menor)
        partes = planejar_pedacos(dur)
        avisar(f"áudio de {dur/60:.0f} min: enviando em {len(partes)} pedaços")
        texto = ""
        for i, (inicio, dura) in enumerate(partes, 1):
            avisar(f"  pedaço {i}/{len(partes)} ({inicio/60:.0f}–{(inicio+dura)/60:.0f} min)")
            trecho = _converter(menor, os.path.join(temp, f"p{i}.mp3"), inicio, dura)
            texto = emendar(texto, _enviar(trecho, chave, modelo, dica))
        return texto
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _escolher_arquivo() -> str:
    """Abre o seletor de arquivos do Windows. Devolve "" se o dono cancelar."""
    from PyQt6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    caminho, _ = QtWidgets.QFileDialog.getOpenFileName(
        None, "Qual áudio você quer transcrever?", os.path.expanduser("~"),
        "Áudio e vídeo (*.mp3 *.m4a *.wav *.ogg *.opus *.flac *.mp4 *.webm *.mkv);;"
        "Todos os arquivos (*)")
    return caminho


def main() -> int:
    caminho = sys.argv[1] if len(sys.argv) > 1 else _escolher_arquivo()
    if not caminho:
        print("nenhum arquivo escolhido.")
        return 0
    try:
        texto = transcrever(caminho)
    except Exception as erro:
        print("NÃO DEU:", erro)
        return 1

    destino = os.path.splitext(caminho)[0] + ".txt"
    with open(destino, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    print(f"\npronto — {len(texto.split())} palavras")
    print("texto salvo em:", destino)
    try:
        os.startfile(destino)   # abre no Bloco de Notas
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
