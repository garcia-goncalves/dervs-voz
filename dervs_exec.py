#!/usr/bin/env python3
"""DERVS — o executor.

Roda UM comando já aprovado e devolve a PROVA: o código de saída e o que
apareceu. É o que fecha o loop com evidência, em vez de dizer "feito".

Três jeitos de rodar, escolhidos pelo tipo de comando:
  - app de tela (firefox, konsole...) → abre solto e volta na hora.
  - terminal visível → abre um konsole onde o comando roda à vista (para
    ferramenta longa/interativa, tipo captura de Wi-Fi).
  - captura (padrão) → roda e recolhe a saída para mostrar no bloco.

O caminho de captura usa shell (PowerShell no Windows) de propósito: os comandos
que o cérebro monta usam cano (|), redirecionamento (>) e coringas, e todos eles
já passaram pela confirmação do dono e pela rede de segurança. O caminho de app
de tela é o oposto: roda SEM shell, com lista de argumentos, porque abrir uma
janela não precisa de shell — e com shell o cmd.exe emendaria o que viesse
depois de um & ou &&.
"""
import os
import re
import shlex
import subprocess
import sys

HOME = os.path.expanduser("~")
_WINDOWS = sys.platform == "win32"

# Programas de janela: abre e volta, não tem "saída" para capturar.
# Mantém os binários de Linux (repositório irmão, Parrot/KDE) e acrescenta os
# do Windows — os dois convivem, o sistema em uso é que decide qual casa.
_APPS_TELA = [
    r"^\s*firefox\b", r"^\s*chromium\b", r"^\s*google-chrome\b", r"^\s*brave\b",
    r"^\s*konsole\b", r"^\s*xterm\b", r"^\s*code\b", r"^\s*codium\b",
    r"^\s*dolphin\b", r"^\s*nautilus\b", r"^\s*xdg-open\b", r"^\s*gedit\b",
    r"^\s*kate\b", r"^\s*libreoffice\b", r"^\s*wireshark\b", r"^\s*burpsuite\b",
    # Windows
    r"^\s*chrome(\.exe)?\b", r"^\s*msedge(\.exe)?\b", r"^\s*firefox\.exe\b",
    r"^\s*explorer(\.exe)?\b", r"^\s*notepad(\.exe)?\b", r"^\s*calc(\.exe)?\b",
    r"^\s*wt(\.exe)?\b", r"^\s*code\.exe\b",
]

LIMITE_SAIDA = 4000  # não despeja log gigante no bloco/contexto


# Encadeamento: se a linha emenda outro comando, ela NÃO é "só abrir um app".
# "notepad && net user invasor 123 /add" começa com notepad e termina criando
# usuário — o atalho de app de tela (que rodava no cmd.exe, e o cmd.exe honra
# & e &&) executaria os dois.
_ENCADEIA = re.compile(r"[&|;^`]")


def eh_app_de_tela(comando: str) -> bool:
    c = comando.strip()
    if _ENCADEIA.search(c):
        return False
    return any(re.search(p, c, re.IGNORECASE) for p in _APPS_TELA)


def _argumentos(comando: str) -> list:
    """Quebra a linha em lista de argumentos, para rodar SEM shell.

    No Windows a quebra preserva a contrabarra dos caminhos (posix=False) e as
    aspas de cada pedaço são tiradas na mão, porque quem monta a linha final
    para o Windows é o próprio subprocess.
    """
    partes = shlex.split(comando, posix=not _WINDOWS)
    if _WINDOWS:
        partes = [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in partes]
    return partes


def _cortar(texto: str) -> str:
    """Guarda o fim da saída (onde costuma estar o resultado/erro) se for grande."""
    if len(texto) <= LIMITE_SAIDA:
        return texto
    return "…(saída cortada)…\n" + texto[-LIMITE_SAIDA:]


def rodar(comando: str, timeout: int = 60, terminal: bool = False, cwd: str = None,
          manter_aberto: bool = False) -> dict:
    """Executa o comando e devolve {codigo, saida, tipo}.

    tipo: 'app' (abriu janela), 'terminal' (abriu konsole à vista),
          'captura' (rodou e trouxe a saída), 'timeout' ou 'erro'.

    manter_aberto: só para quando o CHAMADOR pede um terminal de verdade
    (ferramenta longa/interativa, saída para ler com calma). Aí a janela fica
    aberta depois que o comando acaba (-NoExit no Windows, 'read' no Linux).
    Fora disso a janela fecha sozinha: antes ela ficava aberta sempre que o
    comando "tocava alvo" — inclusive nos falsos positivos —, e sobrava na
    sessão do dono um PowerShell interativo com o ambiente do DERVS.
    """
    comando = (comando or "").strip()
    cwd = cwd or HOME
    if not comando:
        return {"codigo": 1, "saida": "comando vazio", "tipo": "erro"}

    # 1) App de tela: abre solto, sem prender a interface.
    #    SEM shell=True: abrir uma janela não precisa de shell, e com shell o
    #    cmd.exe interpretaria &, && e | — emendando comando na carona do app.
    if eh_app_de_tela(comando) and not terminal:
        try:
            subprocess.Popen(_argumentos(comando), cwd=cwd,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return {"codigo": 0, "saida": "aplicativo aberto", "tipo": "app"}
        except Exception as e:
            return {"codigo": 1, "saida": f"não consegui abrir: {e}", "tipo": "erro"}

    # 2) Terminal visível: para ferramenta longa/interativa. O dono vê rolando.
    if terminal:
        try:
            if _WINDOWS:
                # No Linux abríamos um konsole com 'read' segurando a janela.
                # No Windows o equivalente é abrir o PowerShell numa CONSOLE
                # NOVA (senão o processo herda a janela do DERVS e não some
                # nada visível). O -NoExit (janela fica aberta no fim) só entra
                # quando o chamador pediu — ver o docstring.
                ps = ["powershell"] + (["-NoExit"] if manter_aberto else []) + \
                     ["-Command", comando]
                subprocess.Popen(ps, cwd=cwd,
                                 creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                # konsole abre e roda o comando; 'read' segura a janela aberta
                # no fim — de novo, só quando o chamador pediu.
                segura = "; echo; read -p 'Enter para fechar…'" if manter_aberto else ""
                konsole = ["konsole", "-e", "bash", "-c", f"{comando}{segura}"]
                subprocess.Popen(konsole, cwd=cwd, start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"codigo": 0, "saida": "rodando num terminal à parte (veja a janela)",
                    "tipo": "terminal"}
        except Exception as e:
            return {"codigo": 1, "saida": f"não consegui abrir o terminal: {e}", "tipo": "erro"}

    # 3) Captura: roda e recolhe a saída.
    try:
        if _WINDOWS:
            # shell=True no Windows chama cmd.exe, não bash — e os comandos
            # que chegam aqui vêm em sintaxe PowerShell (é o que dervs_brain
            # instrui o cérebro a montar e o que dervs_safety reconhece:
            # Get-ChildItem, Remove-Item, |, cmdlets...). cmd.exe não entende
            # nada disso. Por isso rodamos explicitamente via powershell.exe,
            # passando o comando inteiro para -Command: é a própria
            # PowerShell que interpreta pipe, aspas e redirecionamento.
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando]
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True,
                                 text=True, timeout=timeout)
        else:
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
