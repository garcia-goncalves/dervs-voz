#!/usr/bin/env python3
"""DERVS — o cartão "HOJE: N ouvidas · M acordei" do HUD.

Lê o diário do porteiro (`porteiro.jsonl`, ver `dervs_porteiro.py`) e conta, do
dia de hoje, quantas frases o porteiro ouviu e em quantas ele acordou o DERVS.

Privacidade: só os METADADOS entram na conta (`quando` e `acordou`). O campo
`texto` — que só existe se o dono ligou `porteiro_registrar_texto` — nunca é
lido para fora daqui: a saída tem exatamente dois números.

Regra de ouro do projeto: um recurso novo nunca deixa o DERVS mudo. Arquivo
ausente, linha torta, byte inválido ou qualquer erro de leitura viram zero ou
são ignorados; a thread nunca levanta.
"""
import datetime
import json
import threading

INTERVALO_PADRAO_SEG = 30.0


def _dia(hoje) -> str:
    """Aceita `date`/`datetime` ou uma string ISO; devolve 'AAAA-MM-DD'."""
    if isinstance(hoje, (datetime.date, datetime.datetime)):
        return hoje.strftime("%Y-%m-%d")
    return str(hoje)[:10]


def _contar_arquivo(caminho: str, dia: str):
    ouvidas = 0
    acordou = 0
    try:
        # errors="replace": um byte torto não pode custar o arquivo inteiro.
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            for linha in f:
                try:
                    reg = json.loads(linha)
                except ValueError:
                    continue
                if not isinstance(reg, dict):
                    continue
                quando = reg.get("quando")
                if not isinstance(quando, str) or quando[:10] != dia:
                    continue
                ouvidas += 1
                if reg.get("acordou") is True:
                    acordou += 1
    except OSError:
        pass    # arquivo ausente (ou em uso): conta zero
    return ouvidas, acordou


def resumo_do_dia(caminho: str, hoje) -> dict:
    """`{"ouvidas": N, "acordou": M}` do dia `hoje`, somando a rotação `.1`
    (o porteiro gira o diário a 256 KiB e guarda a geração anterior — o
    começo do dia pode estar lá)."""
    dia = _dia(hoje)
    o1, a1 = _contar_arquivo(caminho + ".1", dia)
    o2, a2 = _contar_arquivo(caminho, dia)
    return {"ouvidas": o1 + o2, "acordou": a1 + a2}


def _um_passo(ponte, caminho: str, hoje=datetime.date.today) -> None:
    """Uma leitura + um envio. Separado do laço para testar sem thread."""
    r = resumo_do_dia(caminho, hoje())
    ponte.enviar_diario(r["ouvidas"], r["acordou"])


def iniciar_loop_diario(ponte, parar_evento: threading.Event,
                        intervalo: float = INTERVALO_PADRAO_SEG,
                        caminho: str | None = None) -> threading.Thread:
    """Sobe a thread (daemon) que manda o resumo do dia pela ponte a cada
    `intervalo` segundos, até `parar_evento` ser marcado — mesmo estilo de
    `dervs_sistema.iniciar_loop_sistema`."""
    if caminho is None:
        from dervs_porteiro import caminho_do_diario
        caminho = caminho_do_diario()

    def _laco():
        while not parar_evento.is_set():
            try:
                _um_passo(ponte, caminho)
            except Exception:
                pass    # cartão decorativo nunca derruba nada
            parar_evento.wait(intervalo)
    t = threading.Thread(target=_laco, daemon=True)
    t.start()
    return t
