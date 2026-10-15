#!/usr/bin/env python3
"""Mede a conversa natural pelo caminho de produção: árbitro REAL + motor gemini_live REAL.

Para cada caso monta a fala (os mesmos trechos e pausas de `scripts/medir_turno.py`),
entrega quadro a quadro de 30 ms, em tempo real, à `ConversaNatural` — com um microfone
falso e um player falso que só anota QUANDO cada som chegaria à caixa — e diz:

  - primeiro_som_apos_fim_s: do fim de verdade da fala até o primeiro som;
  - som_antes_do_fim: houve som antes do fim real? (nos casos de hesitação tem de ser não)

A trava de voz fica DESLIGADA (a fala é sintética, não há perfil). Ferramentas não fazem
nada de verdade: o dublê responde "fácil" e o primeiro som pode ser o sinal de feito.
Nunca imprime chave nem URL.

Uso:
  dervs-venv\\Scripts\\python.exe scripts\\medir_conversa_natural.py <pasta_com_wavs> [--repeticoes 5]
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import numpy as np                                    # noqa: E402

import dervs_config                                   # noqa: E402
import dervs_conversa as dc                           # noqa: E402
import dervs_conversa_natural as cn                   # noqa: E402
import dervs_turno as dt                              # noqa: E402
import medir_turno                                    # noqa: E402

ESPERA_RESPOSTA_S = 8.0


class PlayerGravador:
    """Não toca nada: anota o instante de cada pedaço e finge a duração dele."""

    def __init__(self):
        self.sons = []                 # (instante monotônico, segundos de áudio)
        self._fim = 0.0
        self._trava = threading.Lock()

    def tocar(self, pcm, taxa=cn.TAXA_SAIDA):
        agora = time.monotonic()
        with self._trava:
            self.sons.append((agora, len(pcm) / 2 / taxa))
            self._fim = max(self._fim, agora) + len(pcm) / 2 / taxa

    def tocando(self):
        with self._trava:
            return time.monotonic() < self._fim

    def parar(self):
        with self._trava:
            self._fim = 0.0

    def abaixar(self, frac=cn.ABAIXAR):
        pass

    def restaurar(self):
        pass

    def fechar(self):
        self.parar()


def rodar(nome, audio, fim_real, conf, arbitro):
    player = PlayerGravador()
    acoes, avisos, eventos = [], [], []

    def executar(pedido, papel, confirmado):
        acoes.append(pedido)
        return {"tipo": "facil"}

    def fabrica(cb):
        def espiar(ev):
            if not isinstance(ev, dc.AudioSaida):
                eventos.append(type(ev).__name__)
            cb(ev)
        return dc.Conversa(espiar, motores_ordem=["gemini_live"], conf=conf)

    arbitro.reset()
    conversa = cn.ConversaNatural(dict(conf, locutor_ligado=False), player, None, arbitro, fabrica,
                                  executar, avisos.append, sinal=cn.sinal_feito_pcm())
    if not conversa.iniciar():
        return {"caso": nome, "erro": "não subiu", "avisos": avisos}
    silencio = bytes(cn.QUADRO_BYTES)
    marca = time.monotonic()
    for _ in range(50):                              # 1,5 s de silêncio: a conexão sobe
        conversa.quadro(silencio)
        marca += cn.QUADRO_S
        time.sleep(max(0.0, marca - time.monotonic()))
    inicio = time.monotonic()
    pcm = audio.astype(np.int16).tobytes()
    n = 0
    for i in range(0, len(pcm) - cn.QUADRO_BYTES + 1, cn.QUADRO_BYTES):
        conversa.quadro(pcm[i:i + cn.QUADRO_BYTES])
        n += 1
        time.sleep(max(0.0, inicio + n * cn.QUADRO_S - time.monotonic()))
    limite = time.monotonic() + ESPERA_RESPOSTA_S
    while not player.sons and time.monotonic() < limite and not conversa.falhou:
        conversa.quadro(silencio)
        n += 1
        time.sleep(max(0.0, inicio + n * cn.QUADRO_S - time.monotonic()))
    time.sleep(0.5)
    conversa.encerrar()
    fim_abs = inicio + fim_real
    sons = [t - fim_abs for t, _ in player.sons]
    return {"caso": nome, "fim_real_s": round(fim_real, 2),
            "primeiro_som_apos_fim_s": round(sons[0], 2) if sons else None,
            "som_antes_do_fim": any(s < 0 for s in sons),
            "acoes": acoes, "erro": "motor caiu" if conversa.falhou else None,
            "eventos": sorted(set(eventos)), "avisos": avisos}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta")
    ap.add_argument("--repeticoes", type=int, default=5, help="quantas vezes a frase completa")
    a = ap.parse_args()
    conf = dervs_config.carregar()
    arbitro = dt.criar(conf)
    if not isinstance(arbitro, dt.Arbitro):
        sys.exit("árbitro real indisponível (modelos não baixaram)")
    casos = [("completa_%d" % (i + 1), medir_turno.CASOS["completa"]) for i in range(a.repeticoes)]
    casos += [(k, v) for k, v in medir_turno.CASOS.items() if k != "completa"]
    resultados = []
    for nome, partes in casos:
        audio, fim = medir_turno.montar(a.pasta, partes)
        r = rodar(nome, audio, fim, conf, arbitro)
        resultados.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    lat = [r["primeiro_som_apos_fim_s"] for r in resultados
           if r.get("primeiro_som_apos_fim_s") is not None]
    print(json.dumps({"resumo": {
        "casos": len(resultados), "com_resposta": len(lat),
        "mediana_primeiro_som_s": round(statistics.median(lat), 2) if lat else None,
        "pior_s": max(lat) if lat else None,
        "algum_som_antes_do_fim": any(r.get("som_antes_do_fim") for r in resultados)}},
        ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
