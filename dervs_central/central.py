"""Orquestra os coletores, guarda o resultado e devolve nota + resumo.

Guarda em `<pasta do DERVS>\\central\\`: `ultima.json` (a leitura mais recente) e
`historico.jsonl` (uma linha resumida por análise, para a tendência). Nada em
laço contínuo: a análise roda sob demanda (botão "Analisar agora") e uma vez
por dia com o PC ocioso — é o que mantém o gasto de CPU perto de zero.
"""
import concurrent.futures
import datetime
import json
import os
import threading

import dervs_caminhos_protegidos as cp
from dervs_central import (atualizacoes, disco, drivers, energia, eventos, inicializacao, nota,
                           processos, repositorios, resumo, seguranca, temporarios, tendencia, winget)

LIMITE_HISTORICO = 400
INTERVALO_DIARIO_H = 24
OCIOSO_ATE_CPU_PCT = 25.0

# `processos` mede CPU por amostragem: roda sozinho, antes dos demais, para que
# as consultas do PowerShell não entrem na medição.
PRIMEIRO = ("processos", processos.coletar)
DEMAIS = (
    ("espaco", disco.coletar_espaco), ("saude", disco.coletar_saude),
    ("eventos", eventos.coletar), ("atualizacoes", atualizacoes.coletar),
    ("winget", winget.coletar), ("inicializacao", inicializacao.coletar),
    ("defender", seguranca.coletar_defender), ("firewall", seguranca.coletar_firewall),
    ("temporarios", temporarios.coletar), ("repositorios", repositorios.coletar),
    ("drivers", drivers.coletar), ("energia", energia.coletar),
)


def _seguro(nome, funcao):
    try:
        r = funcao()
        return r if isinstance(r, dict) and "ok" in r else {
            "ok": False, "itens": [], "precisa_admin": False, "erro": "coletor devolveu formato inválido"}
    except Exception as erro:  # um coletor quebrado nunca derruba a análise
        return {"ok": False, "itens": [], "precisa_admin": False,
                "erro": f"{nome}: {type(erro).__name__}"}


def mascarar_para_envio(dado, extras: list | None = None):
    """Troca por '[caminho protegido]' todo texto que cita uma pasta de
    `caminhos_protegidos_extra` (onde moram os programas com dado de paciente)
    ANTES de qualquer envio ao Claude ou à OpenAI."""
    if extras is None:
        try:
            extras = cp.carregar_extras()
        except (OSError, ValueError):
            extras = []
    chaves = [e.casefold().replace("/", "\\").rstrip("\\") for e in extras if e]
    if not chaves:
        return dado

    def varrer(v):
        if isinstance(v, str):
            baixo = v.casefold().replace("/", "\\")
            return "[caminho protegido]" if any(c in baixo for c in chaves) else v
        if isinstance(v, dict):
            return {k: varrer(x) for k, x in v.items()}
        if isinstance(v, list):
            return [varrer(x) for x in v]
        return v
    return varrer(dado)


class Central:
    def __init__(self, pasta: str, *, coletores: dict | None = None, agora=datetime.datetime.now):
        self.pasta = os.path.join(pasta, "central")
        os.makedirs(self.pasta, exist_ok=True)
        self.arquivo_ultima = os.path.join(self.pasta, "ultima.json")
        self.arquivo_historico = os.path.join(self.pasta, "historico.jsonl")
        self._coletores = coletores
        self._agora = agora
        self._trava = threading.Lock()

    @property
    def em_andamento(self) -> bool:
        return self._trava.locked()

    # ------------------------------------------------------------ leitura
    def ultima(self) -> dict | None:
        try:
            with open(self.arquivo_ultima, encoding="utf-8") as f:
                dado = json.load(f)
            return dado if isinstance(dado, dict) else None
        except (OSError, ValueError):
            return None

    def historico(self, limite: int = 90) -> list:
        linhas = []
        try:
            with open(self.arquivo_historico, encoding="utf-8") as f:
                for bruta in f:
                    try:
                        l = json.loads(bruta)
                        if isinstance(l, dict):
                            linhas.append(l)
                    except ValueError:
                        continue
        except OSError:
            return []
        return linhas[-limite:]

    def visao(self) -> dict:
        """Tudo que a tela e a voz precisam, sem rodar nada."""
        u = self.ultima()
        h = self.historico()
        calculo = nota.calcular(u) if u else {"nota": None, "descontos": [], "sem_leitura": []}
        espaco = (((u or {}).get("coletores") or {}).get("espaco") or {}).get("itens") or []
        volumes = [v["volume"] for v in espaco]
        return {"ultima": u, "nota": calculo["nota"], "descontos": calculo["descontos"],
                "sem_leitura": calculo["sem_leitura"], "resumo": resumo.resumo_do_dia(u, h, self._agora()),
                "tendencia": tendencia.resumo(h, volumes, calculo["nota"] or 0, self._agora()),
                "em_andamento": self.em_andamento}

    # ------------------------------------------------------------ análise
    def analisar(self, progresso=None) -> dict | None:
        """Roda todos os coletores. Devolve None se já há uma análise em curso."""
        if not self._trava.acquire(blocking=False):
            return None
        try:
            tabela = dict(self._coletores) if self._coletores is not None else \
                dict((PRIMEIRO,) + DEMAIS)
            resultados = {}

            def rodar(nome):
                resultados[nome] = _seguro(nome, tabela[nome])
                if progresso:
                    try:
                        progresso(nome, len(resultados), len(tabela))
                    except Exception:
                        pass
            nomes = list(tabela)
            if PRIMEIRO[0] in tabela:
                rodar(PRIMEIRO[0])
                nomes.remove(PRIMEIRO[0])
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(rodar, nomes))
            ultima = {"coletado_em": self._agora().isoformat(timespec="seconds"),
                      "coletores": {n: resultados[n] for n in tabela}}
            self._gravar(ultima)
            return ultima
        finally:
            self._trava.release()

    def _gravar(self, ultima: dict):
        tmp = self.arquivo_ultima + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(ultima, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.arquivo_ultima)
        calculo = nota.calcular(ultima)
        coletores = ultima["coletores"]
        livre = {v["volume"]: v["livre_bytes"] for v in ((coletores.get("espaco") or {}).get("itens") or [])}
        erros = sum(e.get("quantidade", 0) for e in ((coletores.get("eventos") or {}).get("itens") or []))
        linha = {"em": ultima["coletado_em"], "nota": calculo["nota"], "disco_livre_bytes": livre,
                 "erros": erros}
        linhas = self.historico(LIMITE_HISTORICO - 1) + [linha]
        tmp = self.arquivo_historico + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for l in linhas:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")
        os.replace(tmp, self.arquivo_historico)

    # ------------------------------------------------------------ rotina diária
    def precisa_rotina_diaria(self) -> bool:
        u = self.ultima()
        if not u:
            return True
        try:
            desde = datetime.datetime.fromisoformat(u["coletado_em"])
        except (KeyError, ValueError):
            return True
        return (self._agora() - desde).total_seconds() >= INTERVALO_DIARIO_H * 3600
