"""Diagnóstico do dia: função pura, no máximo 4 frases, as 3 piores primeiro.

É o que a voz fala em "DERVS, como está meu PC?" e o painel mostra. Só leitura
(critério 6 do briefing): nada aqui aciona limpeza ou conserto.
"""
import datetime

from dervs_central import nota as nota_mod
from dervs_central import tendencia

LIMITE_FRASES = 4
ALERTA_DIAS_DISCO = 60


def resumo_do_dia(ultima: dict, historico: list | None = None,
                  agora: datetime.datetime | None = None) -> list:
    if not ultima or not ultima.get("coletores"):
        return ["Ainda não analisei seu PC. Peça para analisar agora."]
    calculo = nota_mod.calcular(ultima)
    piores = sorted(calculo["descontos"], key=lambda d: -d["pontos"])[:3]
    frases = [d["frase"] for d in piores]
    volumes = [v["volume"] for v in ((ultima["coletores"].get("espaco") or {}).get("itens") or [])]
    t = tendencia.resumo(historico or [], volumes, calculo["nota"], agora)
    for volume, dias in t["enche_em_dias"].items():
        if dias is not None and dias <= ALERTA_DIAS_DISCO and len(frases) < LIMITE_FRASES:
            frases.append(f"No ritmo atual, o disco {volume} enche em cerca de {round(dias)} dias.")
            break
    if not frases and calculo["sem_leitura"]:
        frases.append("Não consegui ler as informações do computador direito, então não dá para dizer "
                      "que está tudo em ordem.")
    elif not frases:
        frases.append(f"Seu PC está em ordem, nota {calculo['nota']} de 100.")
    elif len(frases) < LIMITE_FRASES:
        frases.append(f"Nota de saúde: {calculo['nota']} de 100.")
    if calculo["sem_leitura"] and len(frases) < LIMITE_FRASES and not frases[0].startswith("Não consegui"):
        frases.append("Algumas leituras falharam, então a nota pode estar incompleta.")
    return frases[:LIMITE_FRASES]
