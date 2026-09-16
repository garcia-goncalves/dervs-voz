#!/usr/bin/env python3
"""DERVS — o nível que a onda desenha (0.0 a 1.0), sem Qt e sem Electron.

A onda de voz na interface não pode carregar Qt para calcular um número: precisa
de uma função pura, testável sem microfone, que qualquer tela (PySide hoje,
Electron amanhã) consiga chamar. Este módulo faz só isso — reusa o `rms()` já
existente em `dervs_listen.py` (não reimplementa a energia do áudio) e traduz o
resultado para uma escala de 0.0 (silêncio) a 1.0 (fala no teto).
"""
import sys
import wave

from dervs_listen import rms

TETO_NIVEL = 6000.0
"""Rms de fala normal bate perto deste teto. É o parafuso de ajuste da onda:
suba para uma onda mais "contida", desça para uma onda mais sensível — sempre
neste lugar só, nunca espalhado pelas telas que consomem o nível."""


def nivel_do_frame(frame: bytes) -> float:
    """Converte um quadro de áudio em nível de 0.0 a 1.0 para a onda desenhar."""
    return min(1.0, rms(frame) / TETO_NIVEL)


def envelope_do_wav(caminho: str, passo_ms: int = 30) -> list[float]:
    """Lê um `.wav` em blocos de `passo_ms` e devolve o nível de cada bloco.

    Só entende PCM de 16 bits (o formato que o resto do DERVS usa). Arquivo que
    não abre ou que está em outro formato devolve lista vazia — nunca explode
    calado, o motivo vai para `sys.stderr`.
    """
    try:
        with wave.open(caminho, "rb") as w:
            if w.getsampwidth() != 2:
                print(
                    f"envelope_do_wav: {caminho!r} não é PCM de 16 bits "
                    f"(sampwidth={w.getsampwidth()})",
                    file=sys.stderr,
                )
                return []
            taxa = w.getframerate()
            amostras_por_bloco = max(1, taxa * passo_ms // 1000)
            niveis = []
            while True:
                bloco = w.readframes(amostras_por_bloco)
                if not bloco:
                    break
                niveis.append(nivel_do_frame(bloco))
            return niveis
    except (OSError, wave.Error) as erro:
        print(f"envelope_do_wav: não deu para abrir {caminho!r}: {erro}", file=sys.stderr)
        return []
