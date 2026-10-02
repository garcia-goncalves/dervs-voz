#!/usr/bin/env python3
"""DERVS — o registrador do "gasto do dia" (estimativa em dólar).

Cada chamada paga à nuvem (voz, transcrição, cérebro) vira UMA linha em
`%LOCALAPPDATA%\\dervs\\gasto.jsonl`. O painel grande soma as linhas de hoje.
É ESTIMATIVA local, calculada com preços de tabela — a fatura real da OpenAI
é a que vale. Nunca grava texto, áudio nem chave: só data, tipo e valor.

Preços (US$, tabela de 09/2026, arredondados para cima de propósito):
  - voz (gpt-4o-mini-tts):           0,015 por minuto de áudio gerado
  - transcrição (gpt-4o-transcribe): 0,006 por minuto de áudio enviado
  - cérebro: por tokens, tabela por modelo (padrão gpt-4.1-nano: 0,10 / 0,40
    por milhão de tokens de entrada / saída)

Além dessas três, o Claude Code (`dervs_claude_code.py`) grava linhas do tipo
"claude" com a etiqueta "assinatura (equivalente)": custo equivalente medido
pelo SDK, que NÃO é cobrança e por isso não entra no total do dia.

Regra de ouro do projeto: registrar gasto NUNCA derruba a fala nem a escuta.
Toda função pública engole erro. Sob pytest, sem `DERVS_GASTO_ARQUIVO`, nada é
gravado (o teste não pode sujar o arquivo real do dono).
"""
import datetime
import io
import json
import os
import sys
import threading
import wave

USD_TTS_POR_MIN = 0.015
USD_STT_POR_MIN = 0.006
# modelo -> (US$ por 1M tokens de entrada, US$ por 1M de saída)
PRECOS_CEREBRO = {
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
PRECO_CEREBRO_PADRAO = (0.40, 1.60)     # modelo desconhecido: assume o do meio

_trava = threading.Lock()


def caminho_padrao():
    """`DERVS_GASTO_ARQUIVO` manda em tudo; sob pytest sem ele, `None` (não grava)."""
    forcado = os.environ.get("DERVS_GASTO_ARQUIVO")
    if forcado:
        return forcado
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        return os.path.join(base, "dervs", "gasto.jsonl")
    return os.path.expanduser("~/.local/state/dervs/gasto.jsonl")


# --- estimativas puras -------------------------------------------------------

def usd_voz(segundos) -> float:
    return max(0.0, float(segundos)) / 60.0 * USD_TTS_POR_MIN


def usd_transcricao(segundos) -> float:
    return max(0.0, float(segundos)) / 60.0 * USD_STT_POR_MIN


def usd_cerebro(modelo: str, tokens_entrada, tokens_saida) -> float:
    pin, pout = PRECOS_CEREBRO.get(modelo or "", PRECO_CEREBRO_PADRAO)
    return (max(0, int(tokens_entrada)) * pin + max(0, int(tokens_saida)) * pout) / 1_000_000


def segundos_do_wav_bytes(dados: bytes):
    """Duração de um wav em memória, ou None se não der para ler."""
    try:
        with wave.open(io.BytesIO(dados), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def segundos_do_wav_arquivo(caminho: str):
    try:
        with wave.open(caminho, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


# --- disco -------------------------------------------------------------------

def registrar(tipo: str, usd: float, detalhe: str = "", caminho=None, agora=None) -> bool:
    """Acrescenta uma linha. Devolve True se gravou. Nunca levanta."""
    try:
        caminho = caminho or caminho_padrao()
        if not caminho or not (usd > 0):
            return False
        agora = agora or datetime.datetime.now()
        linha = json.dumps({"quando": agora.isoformat(timespec="seconds"),
                            "tipo": str(tipo)[:16], "usd": round(float(usd), 6),
                            "detalhe": str(detalhe)[:40]}, ensure_ascii=False)
        with _trava:
            os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
            with open(caminho, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        return True
    except Exception:
        return False


_LIMITE_LEITURA = 512 * 1024          # ~4 mil linhas; um dia pesado não passa de 1 mil


def total_do_dia(caminho=None, hoje=None) -> dict:
    """`{"total": US$, "tts": ..., "stt": ..., "cerebro": ...}` de HOJE."""
    saida = {"total": 0.0, "tts": 0.0, "stt": 0.0, "cerebro": 0.0}
    try:
        caminho = caminho or caminho_padrao()
        if not caminho:
            return saida
        dia = (hoje or datetime.date.today()).strftime("%Y-%m-%d")
        # Só o FIM do arquivo: as linhas são cronológicas e o painel pergunta a
        # cada 5 s — reler meses de histórico à toa cresceria para sempre.
        with open(caminho, "rb") as fb:
            fb.seek(0, os.SEEK_END)
            tam = fb.tell()
            fb.seek(max(0, tam - _LIMITE_LEITURA))
            bruto = fb.read().decode("utf-8", errors="replace")
        linhas = bruto.splitlines()
        if tam > _LIMITE_LEITURA and linhas:
            linhas = linhas[1:]                  # a primeira pode estar cortada ao meio
        if linhas is not None:
            for linha in linhas:
                try:
                    r = json.loads(linha)
                    if r["quando"][:10] != dia:
                        continue
                    usd = float(r["usd"])
                except (ValueError, KeyError, TypeError):
                    continue
                if usd != usd or usd < 0:       # NaN ou negativo: ignora
                    continue
                if r.get("tipo") == "claude":
                    # Claude Code pela ASSINATURA: o valor é o equivalente em
                    # dólar (medida de uso), não cobrança. Fica no arquivo, mas
                    # não entra no "gasto de hoje" — senão o total mentiria.
                    continue
                saida["total"] += usd
                if r.get("tipo") in ("tts", "stt", "cerebro"):
                    saida[r["tipo"]] += usd
    except Exception:
        pass
    return {k: round(v, 6) for k, v in saida.items()}


def formatar_usd(valor: float) -> str:
    """'US$ 0,04' (duas casas; abaixo de 1 centavo mostra três, para o dono ver que mexe)."""
    casas = 3 if 0 < valor < 0.01 else 2
    return "US$ " + f"{valor:.{casas}f}".replace(".", ",")


# --- ganchos de registro (chamados pelo tts / stt / cérebro) ------------------

def registrar_voz(dados_wav: bytes, modelo: str = "") -> None:
    seg = segundos_do_wav_bytes(dados_wav)
    if seg:
        registrar("tts", usd_voz(seg), modelo)


def registrar_transcricao(segundos, modelo: str = "") -> None:
    try:
        if segundos:
            registrar("stt", usd_transcricao(segundos), modelo)
    except Exception:
        pass


def registrar_cerebro(modelo: str, usage) -> None:
    """`usage` é o dict `usage` da resposta da OpenAI; sem ele, não registra."""
    try:
        if not isinstance(usage, dict):
            return
        registrar("cerebro", usd_cerebro(modelo, usage.get("prompt_tokens", 0),
                                         usage.get("completion_tokens", 0)), modelo)
    except Exception:
        pass


# --- teto diário --------------------------------------------------------------

def _ler_total(caminho, hoje=None) -> float:
    """Total de API paga de hoje. Levanta se o arquivo existe e não abre: é o que
    deixa o teto falhar FECHADO (o `total_do_dia` engole erro de propósito)."""
    with open(caminho, "rb"):
        pass
    return total_do_dia(caminho, hoje)["total"]


def estourou(limite, caminho=None, hoje=None) -> bool:
    """True se o gasto de API paga de hoje (voz, transcrição, cérebro; nunca o
    Claude da assinatura) já chegou no teto. Sem arquivo = nada gasto. Medidor
    quebrado = estourou: erro de medição não pode liberar gasto ilimitado."""
    caminho = caminho or caminho_padrao()
    if not caminho or not os.path.exists(caminho):
        return False
    try:
        return _ler_total(caminho, hoje) >= float(limite)
    except Exception:
        return True


def pode_gastar(conf=None):
    """`(True, "")` ou `(False, motivo em português)`: a permissão "gastar com API"
    e o teto diário do dono. Lê a config na hora, então o painel vale sem reiniciar."""
    try:
        if conf is None:
            import dervs_config
            conf = dervs_config.carregar()
        nivel = (conf.get("permissoes") or {}).get("gastar_api", "sozinho")
        if nivel == "analisa":
            return False, "Você deixou o gasto com API só em análise: o DERVS não chama API paga."
        teto = conf.get("teto_gasto_dia_usd", 3.0)
        if estourou(teto):
            return False, f"O teto de gasto do dia (US$ {teto:.2f}) foi atingido; voltei para o Claude."
    except Exception:
        return False, "Não consegui conferir o teto de gasto; por segurança não chamei a API paga."
    return True, ""
