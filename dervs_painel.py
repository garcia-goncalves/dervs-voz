#!/usr/bin/env python3
"""DERVS — os dados do painel grande (JARVIS): agenda, diário, gasto e voz.

Um laço só (thread daemon) lê tudo do disco a cada poucos segundos e manda pela
ponte. A ponte não reenvia valor igual ao anterior (`_enviar_se_mudou`), então
com o DERVS parado quase nada atravessa o soquete.

Regra de ouro do projeto: painel é decoração — qualquer erro aqui é engolido, a
thread nunca levanta.
"""
import datetime
import threading

import dervs_diario
import dervs_gasto
import dervs_lembretes

INTERVALO_PADRAO_SEG = 5.0


def montar_agenda(agenda) -> list:
    """Lembretes pendentes reais, já com a hora dita em português."""
    agora = agenda.agora()
    return [{"quando": i["quando"].isoformat(timespec="seconds"),
             "quando_txt": dervs_lembretes.descrever(i["quando"], agora),
             "texto": i["texto"]} for i in agenda.listar()]


def motor_de_voz(voz) -> str:
    """'nuvem' só se a voz de nuvem está valendo AGORA (chave, internet e sem
    descanso por falha); senão 'local'."""
    try:
        return "nuvem" if (voz is not None and voz.motor == "openai"
                           and voz._openai_disponivel()) else "local"
    except Exception:
        return "local"


def um_passo(ponte, agenda, voz, caminho_diario: str) -> None:
    """Uma rodada de leituras + envios. Separado do laço para testar sem thread."""
    ponte.enviar_gasto(dervs_gasto.total_do_dia())
    ponte.enviar_voz(motor_de_voz(voz))
    ponte.enviar_agenda(montar_agenda(agenda))
    ponte.enviar_diario_entradas(
        dervs_diario.entradas_recentes(caminho_diario, datetime.date.today()))


def iniciar_loop_painel(ponte, parar_evento: threading.Event, agenda=None, voz=None,
                        caminho_diario: str | None = None,
                        intervalo: float = INTERVALO_PADRAO_SEG) -> threading.Thread:
    if agenda is None:
        agenda = dervs_lembretes.Agenda()      # instância própria: só LÊ o arquivo
    if caminho_diario is None:
        from dervs_porteiro import caminho_do_diario
        caminho_diario = caminho_do_diario()

    def _laco():
        while not parar_evento.is_set():
            try:
                um_passo(ponte, agenda, voz, caminho_diario)
            except Exception:
                pass
            parar_evento.wait(intervalo)
    t = threading.Thread(target=_laco, daemon=True)
    t.start()
    return t
