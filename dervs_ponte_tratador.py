#!/usr/bin/env python3
"""DERVS — o que o DERVS-VOZ faz com os recados que chegam do painel web.

Duas portas, e só duas:
  - `leitura`: responde `status` (estado do VOZ) e `analisar` (branch e commits sem
    push de um projeto). Lê SÓ as referências do git, como a Central do PC: nunca
    `git status`, que executa o que o `.git/config` do projeto mandar.
  - `propor`: GUARDA o pedido numa fila local para o dono ver e decidir aqui.
    Não executa nada, não chama IA, não toca em arquivo de projeto. Executar é
    trabalho da Fachada de aprovação (clique do dono), nunca deste arquivo.

O nome do projeto é procurado entre os repositórios já monitorados (`_achar`); ele
nunca vira caminho.
"""
import datetime
import json
import os
import threading

import dervs_config
from dervs_central import repositorios

MAX_PENDENTES = 50
_TRAVA = threading.Lock()


def arquivo_padrao() -> str:
    return os.path.join(dervs_config.CONFIG_DIR, "propostas_web.jsonl")


def _usd(valor) -> str:
    try:
        return ("%.2f" % float(valor)).replace(".", ",")
    except (TypeError, ValueError):
        return "0,00"


class TratadorLocal:
    def __init__(self, raizes=None, arquivo_propostas=None, estado_fn=None, git_fn=None):
        self._raizes = raizes
        self._arquivo = arquivo_propostas or arquivo_padrao()
        self._estado_fn = estado_fn or (lambda: {})
        self._git = git_fn or repositorios.rodar_git

    def _raizes_ou_padrao(self):
        return self._raizes or [os.path.join(os.path.expanduser("~"), "source", "repos")]

    def _repos(self):
        for raiz in self._raizes_ou_padrao():
            yield from repositorios._achar(raiz)

    # ------------------------------------------------------------ leitura

    def leitura(self, recado):
        if recado.get("tipo") == "status":
            e = self._estado_fn() or {}
            return ("feito", "DERVS-VOZ de pé. Cérebro ativo: %s. Gasto de hoje: US$ %s." % (
                e.get("cerebro_ativo", "claude_code"), _usd(e.get("gasto_dia_usd", 0))), 0.0)
        alvo = recado.get("alvo")
        if alvo:
            return ("feito", self._resumo_do_projeto(alvo), 0.0)
        return ("feito", self._resumo_geral(), 0.0)

    def _resumo_do_projeto(self, nome: str) -> str:
        for repo in self._repos():
            if os.path.basename(repo) == nome:
                try:
                    d = repositorios.interpretar(self._git(repo))
                except Exception:
                    return "Não consegui ler o repositório %s." % nome
                extra = "sem upstream" if d["sem_upstream"] else (
                    "%d commit(s) sem push, %d atrás" % (d["ahead"], d["behind"]))
                return "%s: branch %s, %s." % (nome, d["branch"] or "?", extra)
        return "Não achei o projeto %s entre os que o DERVS-VOZ monitora." % nome

    def _resumo_geral(self) -> str:
        itens = repositorios.coletar(self._raizes_ou_padrao(), rodar_git_fn=self._git).get("itens")
        if not itens:
            return "Nenhum projeto com commit sem push."
        nomes = ", ".join(i["nome"] for i in itens[:15])
        return "%d projeto(s) com commit sem push: %s." % (len(itens), nomes)

    # ------------------------------------------------------------ proposta

    def pendentes(self) -> list:
        saida = []
        try:
            with open(self._arquivo, "r", encoding="utf-8") as f:
                for linha in f:
                    try:
                        item = json.loads(linha)
                    except ValueError:
                        continue
                    if isinstance(item, dict) and item.get("estado") == "pendente":
                        saida.append(item)
        except OSError:
            pass
        return saida

    def propor(self, recado) -> str:
        import dervs_log_acoes
        with _TRAVA:
            if len(self.pendentes()) >= MAX_PENDENTES:
                return "A fila de pedidos do painel web está cheia; decida os pendentes antes."
            item = dervs_log_acoes.redigir({
                "id": recado.get("id"),
                "quando": datetime.datetime.now().isoformat(timespec="seconds"),
                "tipo": recado.get("tipo"), "alvo": recado.get("alvo"),
                "texto": recado.get("texto"), "estado": "pendente"})
            os.makedirs(os.path.dirname(self._arquivo), exist_ok=True)
            with open(self._arquivo, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return "Guardei o pedido do painel web; ele espera o seu clique no DERVS-VOZ."
