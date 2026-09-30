#!/usr/bin/env python3
"""DERVS — supervisão do medidor dos projetos (o `agente.enviar` do DERVS web).

O medidor roda neste PC pela tarefa agendada "DERVS - reportar" e é ele que prova
ao painel que a máquina está viva (o painel só acredita em medição real). Quem
mede é ELE; este módulo só confere que existe exatamente UM e, se caiu, pede ao
Windows para rodar a tarefa que já existe. Três regras:

  - nunca cria tarefa nem processo próprio (seria um segundo medidor);
  - nunca mata processo: dois medidores são avisados, não resolvidos à força;
  - religa no máximo uma vez a cada 10 minutos (medidor que morre ao nascer não
    vira laço apertado).
"""
import re
import subprocess
import time

NOME_DA_TAREFA = "DERVS - reportar"
ESPERA_ENTRE_RELIGADAS_S = 600
_PS = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' -and "
       "$_.CommandLine -match 'agente[\\\\/]enviar|-m\\s+agente\\.enviar' } | "
       "ForEach-Object { $_.ProcessId }")


def _executar_padrao(args, timeout=20):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=flags)
    return p.returncode, p.stdout.decode("utf-8", "replace")


class VigiaAgente:
    def __init__(self, executar=None, relogio=time.monotonic):
        self._executar = executar or _executar_padrao
        self._relogio = relogio
        self._ultima_religada = None

    def _processos(self) -> int:
        _, saida = self._executar(["powershell.exe", "-NoProfile", "-Command", _PS])
        return len(re.findall(r"^\d+\s*$", saida, re.M))

    def _estado_da_tarefa(self):
        """None se a tarefa não existe; senão o texto do status."""
        rc, saida = self._executar(["schtasks.exe", "/Query", "/TN", NOME_DA_TAREFA,
                                    "/FO", "CSV", "/V"])
        if rc != 0:
            return None
        return saida

    def verificar(self) -> dict:
        try:
            n = self._processos()
            if n == 1:
                return {"processos": 1, "acao": "nada"}
            if n > 1:
                return {"processos": n, "acao": "duplicado"}
            estado = self._estado_da_tarefa()
            if estado is None:
                return {"processos": 0, "acao": "sem_tarefa"}
            if "running" in estado.lower() or "em execu" in estado.lower():
                return {"processos": 0, "acao": "nada"}   # o Windows está subindo o medidor
            agora = self._relogio()
            if self._ultima_religada is not None and \
                    agora - self._ultima_religada < ESPERA_ENTRE_RELIGADAS_S:
                return {"processos": 0, "acao": "espera"}
            rc, _ = self._executar(["schtasks.exe", "/Run", "/TN", NOME_DA_TAREFA])
            self._ultima_religada = agora
            return {"processos": 0, "acao": "religou" if rc == 0 else "falhou"}
        except Exception:
            return {"processos": -1, "acao": "indisponivel"}


def iniciar_loop(parar, ao_resultado=None, intervalo_s: float = 120, vigia=None):
    """Thread daemon que confere a cada `intervalo_s` até `parar` (threading.Event)
    ser acionado. `ao_resultado(dict)` só é chamado quando a ação é diferente de
    "nada" — para o app avisar uma vez, não a cada volta."""
    import threading
    vigia = vigia or VigiaAgente()

    def laco():
        while not parar.is_set():
            r = vigia.verificar()
            if ao_resultado is not None and r["acao"] not in ("nada", "espera"):
                try:
                    ao_resultado(r)
                except Exception:
                    pass
            parar.wait(intervalo_s)

    t = threading.Thread(target=laco, name="vigia-agente", daemon=True)
    t.start()
    return t
