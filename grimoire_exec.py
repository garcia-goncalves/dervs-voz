#!/usr/bin/env python3
"""Grimoire — o executor.

Roda UM comando já aprovado e devolve a PROVA: o código de saída e o que
apareceu. É o que fecha o loop com evidência, em vez de dizer "feito".

Três jeitos de rodar, escolhidos pelo tipo de comando:
  - app de tela (firefox, konsole...) → abre solto e volta na hora.
  - terminal visível → abre um konsole onde o comando roda à vista (para
    ferramenta longa/interativa, tipo captura de Wi-Fi).
  - captura (padrão) → roda e recolhe a saída para mostrar no bloco.

Roda com shell=True de propósito: os comandos que o cérebro monta usam cano (|),
redirecionamento (>) e coringas. Isso NÃO é uma brecha — todo comando aqui já
passou pela confirmação do dono e pela rede de segurança.
"""
import os
import re
import subprocess

HOME = os.path.expanduser("~")

# Programas de janela: abre e volta, não tem "saída" para capturar.
_APPS_TELA = [
    r"^\s*firefox\b", r"^\s*chromium\b", r"^\s*google-chrome\b", r"^\s*brave\b",
    r"^\s*konsole\b", r"^\s*xterm\b", r"^\s*code\b", r"^\s*codium\b",
    r"^\s*dolphin\b", r"^\s*nautilus\b", r"^\s*xdg-open\b", r"^\s*gedit\b",
    r"^\s*kate\b", r"^\s*libreoffice\b", r"^\s*wireshark\b", r"^\s*burpsuite\b",
]

LIMITE_SAIDA = 4000  # não despeja log gigante no bloco/contexto


def eh_app_de_tela(comando: str) -> bool:
    c = comando.strip()
    return any(re.search(p, c, re.IGNORECASE) for p in _APPS_TELA)


def _cortar(texto: str) -> str:
    """Guarda o fim da saída (onde costuma estar o resultado/erro) se for grande."""
    if len(texto) <= LIMITE_SAIDA:
        return texto
    return "…(saída cortada)…\n" + texto[-LIMITE_SAIDA:]


def rodar(comando: str, timeout: int = 60, terminal: bool = False, cwd: str = None) -> dict:
    """Executa o comando e devolve {codigo, saida, tipo}.

    tipo: 'app' (abriu janela), 'terminal' (abriu konsole à vista),
          'captura' (rodou e trouxe a saída), 'timeout' ou 'erro'.
    """
    comando = (comando or "").strip()
    cwd = cwd or HOME
    if not comando:
        return {"codigo": 1, "saida": "comando vazio", "tipo": "erro"}

    # 1) App de tela: abre solto, sem prender a interface.
    if eh_app_de_tela(comando) and not terminal:
        try:
            subprocess.Popen(comando, shell=True, cwd=cwd,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return {"codigo": 0, "saida": "aplicativo aberto", "tipo": "app"}
        except Exception as e:
            return {"codigo": 1, "saida": f"não consegui abrir: {e}", "tipo": "erro"}

    # 2) Terminal visível: para ferramenta longa/interativa. O dono vê rolando.
    if terminal:
        try:
            # konsole abre e roda o comando; 'read' segura a janela aberta no fim.
            konsole = ["konsole", "-e", "bash", "-c", f"{comando}; echo; read -p 'Enter para fechar…'"]
            subprocess.Popen(konsole, cwd=cwd, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"codigo": 0, "saida": "rodando num terminal à parte (veja a janela)",
                    "tipo": "terminal"}
        except Exception as e:
            return {"codigo": 1, "saida": f"não consegui abrir o terminal: {e}", "tipo": "erro"}

    # 3) Captura: roda e recolhe a saída.
    try:
        proc = subprocess.run(comando, shell=True, cwd=cwd, capture_output=True,
                             text=True, timeout=timeout)
        saida = (proc.stdout or "") + (proc.stderr or "")
        return {"codigo": proc.returncode, "saida": _cortar(saida.strip()), "tipo": "captura"}
    except subprocess.TimeoutExpired:
        return {"codigo": 124,
                "saida": f"passou de {timeout}s e foi interrompido — talvez precise "
                         f"rodar num terminal à parte", "tipo": "timeout"}
    except Exception as e:
        return {"codigo": 1, "saida": f"falhou ao rodar: {e}", "tipo": "erro"}


if __name__ == "__main__":
    import sys
    c = sys.argv[1] if len(sys.argv) > 1 else "echo oi && ls /naoexiste"
    print(rodar(c))
