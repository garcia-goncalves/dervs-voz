#!/usr/bin/env python3
"""DERVS — a tela "O que o DERVS pode fazer": a cola entre a tela LOCAL (Electron) e a
política de permissões (`dervs_permissoes`) guardada no config.

A tela só PEDE; quem decide é este módulo. Ele nunca grava um nível que a política
não aceita para aquela categoria (apagar e servidor jamais chegam a "sozinho"): em vez
de deixar `normalizar` rebaixar em silêncio, devolve uma frase de erro em português.
O que a tela mostra de rótulo e de níveis permitidos vem daqui, nunca duplicado no JS.
"""
import json
import math
import os

import dervs_config
import dervs_gasto
import dervs_permissoes as perm

TETO_MIN = 0.01
TETO_MAX = 1000.0
MAX_RECENTES = 10
_LER_FIM = 64 * 1024          # só o fim do registro: ele cresce para sempre


def ler_recentes(caminho=None, quantas=MAX_RECENTES) -> list:
    """As últimas ações feitas SEM perguntar (mais nova primeiro), do `permissoes.jsonl`."""
    saida = []
    try:
        caminho = caminho or os.environ.get("DERVS_PERMISSOES_LOG") or perm._arquivo_log()
        with open(caminho, "rb") as f:
            f.seek(0, os.SEEK_END)
            tam = f.tell()
            f.seek(max(0, tam - _LER_FIM))
            bruto = f.read().decode("utf-8", errors="replace")
        for linha in reversed(bruto.splitlines()):
            try:
                r = json.loads(linha)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("acao") != "permitir":
                continue
            saida.append({"quando": str(r.get("quando", ""))[:19],
                          "categoria": str(r.get("categoria", ""))[:30],
                          "ferramenta": str(r.get("ferramenta", ""))[:40],
                          "resumo": str(r.get("resumo", ""))[:200]})
            if len(saida) >= quantas:
                break
    except OSError:
        pass
    return saida


class PermissoesLocal:
    def __init__(self, ponte, *, config=dervs_config, gasto=dervs_gasto, ler_log=ler_recentes):
        """`ponte` só usa `enviar_permissoes(dados)`. `config` precisa de `carregar()` e
        `gravar(chave, valor)`; `gasto` de `total_do_dia()`; `ler_log()` devolve a lista."""
        self._ponte = ponte
        self._config = config
        self._gasto = gasto
        self._ler_log = ler_log

    def tratar(self, verbo: str, dados: dict):
        """Ponto único dos verbos `permissoes_*` (já validados pela ponte)."""
        try:
            dados = dados or {}
            if verbo == "permissoes_pedir":
                self.enviar_estado()
            elif verbo == "permissoes_definir":
                self._definir(dados.get("categoria"), dados.get("nivel"))
            elif verbo == "permissoes_teto":
                self._teto(dados.get("valor"))
        except Exception as erro:   # a tela nunca fica esperando em silêncio
            self._mensagem(False, f"Algo falhou por dentro ({type(erro).__name__}). Nada foi mudado.")

    # ------------------------------------------------------------------ saída
    def _mensagem(self, ok: bool, texto: str):
        self._ponte.enviar_permissoes({"parte": "mensagem", "ok": ok, "texto": texto})

    def estado(self) -> dict:
        conf = self._config.carregar()
        try:
            gasto_hoje = float(self._gasto.total_do_dia().get("total", 0.0))
        except Exception:
            gasto_hoje = 0.0
        try:
            recentes = list(self._ler_log())[:MAX_RECENTES]
        except Exception:
            recentes = []
        return {
            "parte": "estado",
            "categorias": list(perm.CATEGORIAS),
            "niveis": perm.normalizar(conf.get("permissoes")),
            "rotulos": dict(perm.ROTULOS),
            "permitidos": {c: list(n) for c, n in perm.PERMITIDOS.items()},
            "teto": conf.get("teto_gasto_dia_usd"),
            "gasto_hoje": round(gasto_hoje, 4),
            "recentes": recentes,
        }

    def enviar_estado(self):
        self._ponte.enviar_permissoes(self.estado())

    # ------------------------------------------------------------------ ações
    def _definir(self, categoria, nivel):
        if not isinstance(categoria, str) or categoria not in perm.CATEGORIAS:
            self._mensagem(False, "Não conheço essa permissão. Nada foi mudado.")
            return
        rotulo = perm.ROTULOS[categoria]
        if not isinstance(nivel, str) or nivel not in perm.PERMITIDOS[categoria]:
            self._mensagem(False, f"Para \"{rotulo}\" esse nível não é permitido: "
                                  "é uma trava do DERVS. Nada foi mudado.")
            return
        atual = perm.normalizar(self._config.carregar().get("permissoes"))
        novo = perm.normalizar({**atual, categoria: nivel})
        if novo.get(categoria) != nivel:   # normalizar rebaixaria: não aceita calado
            self._mensagem(False, f"Esse nível não vale para \"{rotulo}\". Nada foi mudado.")
            return
        if not self._config.gravar("permissoes", novo):
            self._mensagem(False, "Não consegui salvar a configuração agora. Nada foi mudado.")
            return
        self.enviar_estado()
        self._mensagem(True, f"Salvo: {rotulo}.")

    def _teto(self, valor):
        if (isinstance(valor, bool) or not isinstance(valor, (int, float))
                or not math.isfinite(valor) or not TETO_MIN <= valor <= TETO_MAX):
            self._mensagem(False, "O teto diário precisa ficar entre US$ 0,01 e US$ 1000. "
                                  "Nada foi mudado.")
            return
        valor = round(float(valor), 2)
        if not self._config.gravar("teto_gasto_dia_usd", valor):
            self._mensagem(False, "Não consegui salvar a configuração agora. Nada foi mudado.")
            return
        self.enviar_estado()
        self._mensagem(True, "Teto diário salvo.")
