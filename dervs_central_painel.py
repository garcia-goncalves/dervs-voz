#!/usr/bin/env python3
"""DERVS — a Central do PC no painel (onda D): a cola entre os coletores
(`dervs_central/`), o motor de aprovação (onda C) e a tela.

Quem manda aqui é o CLIQUE do dono. Este módulo:
  - analisa a máquina sob demanda e uma vez por dia com o PC ocioso (só lê);
  - transforma a leitura dos temporários em PROPOSTAS e as entrega ao
    `Motor.analisar`, que monta o relatório item a item;
  - repassa à tela o relatório junto com o CARTÃO (a senha de uso do clique);
  - quando o clique volta, chama `Motor.aprovar(origem="clique")` e o executor
    — que manda para a QUARENTENA, nunca apaga — e devolve o resultado;
  - responde "DERVS, como está meu PC?" em voz, só com leitura.

O Claude nunca passa por aqui com poder: a voz e o Claude só recebem o
RESUMO. Aprovar, executar e desfazer só existem nos métodos chamados pela
ponte do painel (verbos `central_*` vindos do Electron).
"""
import datetime
import re
import threading
import unicodedata

import dervs_executor_seguro as executor
from dervs_central import central as central_mod
from dervs_central import explicacoes, limpeza, nota

LIMITE_ITENS_TELA = 10
_PERGUNTAS_DE_SAUDE = re.compile(
    r"^(?:dervs )?(?:"
    r"(?:como (?:esta|anda|vai)|qual (?:e )?(?:a )?(?:saude|situacao|estado)) "
    r"(?:de |do |da )?(?:o |a )?(?:meu |minha )?(?:pc|computador|maquina|notebook)"
    r"|(?:diagnostico|saude|checkup|check-up) (?:do|da|de) (?:meu |minha )?(?:pc|computador|maquina|notebook)"
    r"|diagnostico do dia)[?.! ]*$")


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    t = re.sub(r"[^\w\s?!.\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def eh_pergunta_de_saude(texto: str) -> bool:
    """"DERVS, como está meu PC?" e variações próximas. Conservadora: o que
    não casar segue o caminho de sempre (Claude, atalhos, planejador)."""
    return bool(_PERGUNTAS_DE_SAUDE.match(_norm(texto)))


def _data_curta(iso) -> str:
    """'2026-09-29T16:15:03' -> '29/09/2026 16:15' (o formato do dono)."""
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(iso or "")[:16]


def _top(itens, n=LIMITE_ITENS_TELA):
    return list(itens or [])[:n]


def visao_para_tela(visao: dict) -> dict:
    """Corta a visão completa no que a tela mostra. Fica bem abaixo do limite de
    uma linha da ponte (64 KiB) e não leva comando nem caminho de programa."""
    u = visao.get("ultima") or {}
    col = u.get("coletores") or {}

    def itens(nome):
        c = col.get(nome) or {}
        return (c.get("itens") or []) if c.get("ok") else []

    tend = visao.get("tendencia") or {}
    return {
        "coletado_em": u.get("coletado_em", ""),
        "nota": visao.get("nota"),
        "descontos": [dict(d, explicacao=explicacoes.explicar(d["codigo"]))
                      for d in visao.get("descontos") or []],
        "resumo": visao.get("resumo") or [],
        "sem_leitura": visao.get("sem_leitura") or [],
        "precisa_admin": sorted(n for n, c in col.items() if c.get("precisa_admin")),
        "em_andamento": bool(visao.get("em_andamento")),
        "tendencia": {"enche_em_dias": tend.get("enche_em_dias") or {}, "erros": tend.get("erros"),
                      "nota_ha_7_dias": tend.get("nota_ha_7_dias")},
        "discos": [{k: d.get(k) for k in ("volume", "pct_livre", "livre_bytes", "total_bytes", "saude")}
                   for d in itens("espaco")],
        "eventos": [{"fonte": e["fonte"], "id": e["id"], "quantidade": e["quantidade"],
                     "explicacao": explicacoes.explicar_evento(e["fonte"], e["id"])}
                    for e in _top(itens("eventos"), 8)],
        "atualizacoes_pendentes": len(itens("atualizacoes")),
        "programas_desatualizados": [{k: p.get(k) for k in ("nome", "versao_instalada", "versao_nova")}
                                     for p in _top(itens("winget"))],
        "inicializacao": {"total": len(itens("inicializacao")),
                          "ativos": [i["nome"] for i in _top(
                              [i for i in itens("inicializacao") if i.get("ativo")], 15)]},
        "processos": [{k: p.get(k) for k in ("nome", "cpu_pct", "memoria_bytes", "assinatura")}
                      for p in _top(itens("processos"), 5)],
        "temporarios": [{k: t.get(k) for k in ("nome", "tamanho_bytes", "antigos_bytes")}
                        for t in itens("temporarios")],
        "so_informativos": limpeza.informativos(u),
        "repositorios": [{"nome": r.get("nome"), "ahead": r.get("ahead"), "sujo": r.get("sujo")}
                         for r in _top(itens("repositorios"))],
    }


def relatorio_para_tela(relatorio: dict) -> dict:
    """O relatório do motor, sem os campos internos (impressão digital, número do arquivo)."""
    campos = ("id", "acao", "alvo", "onde", "tipo", "tamanho_bytes", "data", "o_que_e", "o_que_muda",
              "como_desfazer", "risco", "por_que_seguro", "reversivel")
    return {"id": relatorio["id"], "criado_em": relatorio["criado_em"],
            "total_bytes": relatorio["total_bytes"],
            "itens": [{k: i.get(k) for k in campos} for i in relatorio["itens"]],
            "recusados": [{"alvo": r["alvo"], "motivo": r["motivo"]} for r in relatorio["recusados"]]}


class CentralDoPc:
    def __init__(self, ponte, motor_fabrica, *, falar=None, perguntar_claude=None,
                 agora=datetime.datetime.now, pasta_central=None):
        """`motor_fabrica()` devolve o Motor de aprovação (criado só na primeira
        vez). `falar(texto)` é seguro de qualquer thread. `perguntar_claude(texto)`
        devolve True se a pergunta foi aceita."""
        self._ponte = ponte
        self._motor_fabrica = motor_fabrica
        self._falar = falar or (lambda texto: None)
        self._perguntar_claude = perguntar_claude or (lambda texto: False)
        self._agora = agora
        self._pasta_central = pasta_central
        self._central = None
        self._trava = threading.Lock()

    @property
    def central(self):
        with self._trava:
            if self._central is None:
                pasta = self._pasta_central or self._motor_fabrica().pasta
                self._central = central_mod.Central(pasta, agora=self._agora)
            return self._central

    def _thread(self, alvo, *args) -> threading.Thread:
        t = threading.Thread(target=self._seguro, args=(alvo, *args), daemon=True)
        t.start()
        return t

    def _seguro(self, alvo, *args):
        try:
            alvo(*args)
        except Exception as erro:  # a tela nunca fica esperando em silêncio
            self._ponte.enviar_central_resultado(
                {"ok": False, "motivo": f"algo falhou por dentro ({type(erro).__name__})", "itens": []})

    # ------------------------------------------------------------ o que a tela pede
    def tratar(self, verbo: str, dados: dict):
        """Ponto único dos verbos `central_*` (já validados pela ponte)."""
        if verbo == "central_pedir":
            self.enviar_visao()
        elif verbo == "central_analisar":
            self.analisar_agora()
        elif verbo == "central_propor_limpeza":
            self._thread(self._propor_limpeza)
        elif verbo == "central_aprovar":
            self._thread(self._aprovar, dados["relatorio_id"], dados["ids"], dados["cartao"],
                         dados.get("dupla") or [])
        elif verbo == "central_desfazer":
            self._thread(self._desfazer, dados["desfazer_id"])
        elif verbo == "central_explicar":
            self._explicar(dados["codigo"])

    def quarentena_ativa(self, limite: int = 15) -> list:
        """O que o executor já mandou para a quarentena e ainda não foi desfeito,
        lido do registro encadeado (o mais recente primeiro)."""
        try:
            linhas = self._motor_fabrica().log.ler()
        except Exception:
            return []
        desfeitos = {(l.get("dados") or {}).get("desfazer_id") for l in linhas if l.get("evento") == "desfez"}
        itens = []
        for l in reversed(linhas):
            d = l.get("dados") or {}
            if l.get("evento") == "executou" and d.get("desfazer_id") and d["desfazer_id"] not in desfeitos:
                itens.append({"desfazer_id": d["desfazer_id"], "alvo": d.get("alvo", ""),
                              "tamanho_bytes": d.get("tamanho_bytes") or 0,
                              "quando": _data_curta(l.get("quando"))})
            if len(itens) >= limite:
                break
        return itens

    def enviar_visao(self):
        self._ponte.enviar_central({**visao_para_tela(self.central.visao()),
                                    "quarentena": self.quarentena_ativa()})

    def analisar_agora(self):
        """Devolve a thread da análise, ou None se já havia uma em curso."""
        if self.central.em_andamento:
            self.enviar_visao()
            return None
        return self._thread(self._analisar)

    def _analisar(self):
        self._ponte.enviar_central({**visao_para_tela(self.central.visao()),
                                    "quarentena": self.quarentena_ativa(), "em_andamento": True})
        self.central.analisar(progresso=lambda nome, feitos, total:
                              self._ponte.enviar_central_progresso(nome, feitos, total))
        self.enviar_visao()

    # ------------------------------------------------------------ limpeza
    def _propor_limpeza(self):
        motor = self._motor_fabrica()
        propostas = limpeza.propostas(self.central.ultima())
        if not propostas:
            self._ponte.enviar_central_resultado(
                {"ok": True, "motivo": "Não achei sobra segura para limpar agora. Analise de novo "
                                       "se faz tempo.", "itens": []})
            return
        relatorio = motor.analisar(propostas, origem="central")
        cartao = motor.abrir_cartao(relatorio["id"]) if relatorio["itens"] else None
        self._ponte.enviar_central_relatorio(relatorio_para_tela(relatorio), cartao)

    def _aprovar(self, relatorio_id, ids, cartao, dupla):
        motor = self._motor_fabrica()
        aprovado = motor.aprovar(relatorio_id, ids, origem="clique", cartao=cartao,
                                 dupla_confirmacao=dupla)
        if not aprovado.get("ok"):
            self._ponte.enviar_central_resultado(
                {"ok": False, "motivo": aprovado.get("motivo", "aprovação recusada"), "itens": []})
            return
        registro = aprovado["registro"]
        saida, liberados = [], 0
        for item_id in registro["ids"]:
            r = executor.executar(motor, registro["id"], registro["token"], item_id, "clique")
            saida.append({"id": item_id, "ok": bool(r.get("ok")), "motivo": r.get("motivo", ""),
                          "desfazer_id": r.get("desfazer_id")})
            if r.get("ok"):
                liberados += int(r.get("tamanho_bytes") or 0)
        feitos = sum(1 for s in saida if s["ok"])
        self._ponte.enviar_central_resultado({
            "ok": feitos == len(saida),
            "motivo": f"{feitos} de {len(saida)} item(ns) foram para a quarentena. Dá para desfazer.",
            "itens": saida, "liberados_bytes": liberados})

    def _desfazer(self, desfazer_id):
        r = executor.desfazer(self._motor_fabrica(), desfazer_id, "clique")
        self._ponte.enviar_central_resultado({"ok": bool(r.get("ok")), "motivo": r.get("motivo", ""),
                                              "itens": [], "desfeito": desfazer_id if r.get("ok") else None})

    # ------------------------------------------------------------ explicar melhor (Claude)
    def _explicar(self, codigo: str):
        """Manda UM item ao Claude, com caminhos de pastas protegidas mascarados."""
        u = self.central.ultima() or {}
        alvo = next((d for d in nota.calcular(u)["descontos"] if d["codigo"] == codigo), None)
        if alvo is None:
            return
        contexto = central_mod.mascarar_para_envio({"desconto": alvo, "coletado_em": u.get("coletado_em")})
        pergunta = ("Explique em português simples, para quem não é técnico, este problema que o painel "
                    f"encontrou no meu PC e diga se preciso fazer algo (só leia, não mude nada): {contexto}")
        if not self._perguntar_claude(pergunta):
            self._ponte.enviar_central_resultado(
                {"ok": False, "motivo": "O Claude ainda está respondendo outra coisa. Tente de novo.",
                 "itens": []})

    # ------------------------------------------------------------ voz
    def diagnostico_por_voz(self) -> threading.Thread:
        """"DERVS, como está meu PC?": fala o resumo da última análise; se ela é
        velha (mais de 24 h) ou não existe, avisa e analisa antes. Só leitura."""
        def _fazer():
            if self.central.precisa_rotina_diaria():
                self._falar("Vou analisar seu computador, leva um minuto.")
                if self.central.analisar() is None:
                    self._falar("Já estou analisando, um instante.")
                    return
            self._falar(" ".join(self.central.visao()["resumo"]))
            self.enviar_visao()
        return self._thread(_fazer)

    # ------------------------------------------------------------ rotina diária
    def iniciar_rotina_diaria(self, parar: threading.Event, atraso_inicial: float = 120.0,
                              intervalo: float = 1800.0, medir_cpu=None) -> threading.Thread:
        """Uma vez por dia, com o PC ocioso: só analisa e avisa (nada de limpeza)."""
        def _cpu():
            try:
                import psutil
                return psutil.cpu_percent(interval=1.0)
            except Exception:
                return 100.0
        medir = medir_cpu or _cpu

        def _laco():
            parar.wait(atraso_inicial)
            while not parar.is_set():
                try:
                    if (self.central.precisa_rotina_diaria() and not self.central.em_andamento
                            and medir() < central_mod.OCIOSO_ATE_CPU_PCT):
                        self._analisar()
                        v = self.central.visao()
                        self._ponte.enviar_acao("dervs", f"Análise diária do PC: nota {v['nota']} de 100.")
                except Exception:
                    pass
                parar.wait(intervalo)
        t = threading.Thread(target=_laco, daemon=True)
        t.start()
        return t
