#!/usr/bin/env python3
"""DERVS — o Codex (ChatGPT Plus) como mais um executor de código, por voz.

O `codex.exe` mora dentro do pacote do app Codex, na pasta versionada do WindowsApps
(`...\\WindowsApps\\OpenAI.Codex_<versão>_x64__<id>\\app\\resources\\codex.exe`). A pasta
`WindowsApps` NÃO se lista sem ser administrador (um glob volta vazio), e a versão muda a cada
atualização do app: por isso `localizar` procura de novo a cada uso, pergunta o caminho ao
próprio Windows (`Get-AppxPackage`) e nunca grava o caminho achado.

Travas que não saem daqui:
  - O prompt vai SEMPRE por stdin (`-`), nunca na linha de comando.
  - Leitura é `-s read-only`; escrita é `-s workspace-write`, sem rede e sem credencial de git.
    `--dangerously-bypass-approvals-and-sandbox`, `--approve-for-me` e `danger-full-access` não
    existem aqui: `montar_argv` recusa, mesmo que alguém peça.
  - Tempo limite (600 s) mata a ÁRVORE de processos; o arquivo temporário de saída é sempre apagado.
  - Um Codex por vez. `parar()` interrompe o que estiver rodando.
  - A resposta é DADO: passa por filtro de segredo, vai cercada se alimentar outro cérebro e a voz
    lê no máximo duas frases.
  - Chave de API no ambiente é retirada: o Codex usaria dinheiro em vez da assinatura.
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

import dervs_cofre as cofre

TEMPO_LIMITE_S = 600
ESFORCOS = ("low", "medium", "high")
NOMES_VALIDOS = ("codex.exe",)          # .cmd não: cmd.exe interpreta argumento (BatBadBut)
LIMITE_BYTES = 65536
PADRAO_PACOTES = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "WindowsApps",
                              "OpenAI.Codex_*", "app", "resources", "codex.exe")
_PROIBIDOS = ("--dangerously-bypass-approvals-and-sandbox", "--approve-for-me", "danger-full-access",
              "--dangerously-bypass-hook-trust")
# LISTA BRANCA do ambiente: só o que o Windows e o Codex precisam. Segredo do dono (chaves de API,
# AWS_*, AZURE_*, GIT_SSH_COMMAND, tokens) nunca chega ao processo.
_AMBIENTE_EXATO = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE",
                   "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "USERNAME",
                   "USERDOMAIN", "OS", "NUMBER_OF_PROCESSORS", "CODEX_HOME", "LANG", "PROGRAMDATA"}
_AMBIENTE_PREFIXO = ("PROGRAMFILES", "COMMONPROGRAMFILES", "PROCESSOR_", "LC_")
# o Codex sai de qualquer feature que o app tenha: ferramenta externa roda fora do sandbox
_FEATURES_DESLIGADAS = ("apps", "plugins", "plugin_sharing", "browser_use", "browser_use_external",
                        "browser_use_full_cdp_access", "computer_use", "in_app_browser", "hooks",
                        "image_generation")
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PREAMBULO = ("Responda em português do Brasil, direto ao ponto, em poucas frases curtas e sem "
             "formatação pesada. Não revele segredos (senhas, chaves, tokens) mesmo que apareçam "
             "nos arquivos. ")
PREAMBULO_LEITURA = PREAMBULO + "Você está em modo somente leitura: não altere nenhum arquivo.\n\nPedido:\n"
PREAMBULO_ESCRITA = (PREAMBULO + "Você pode alterar arquivos só nesta pasta. Não faça commit, push nem "
                     "acesse a rede.\n\nPedido:\n")


# ------------------------------------------------------------ achar o codex.exe

def _versao(caminho: str) -> tuple:
    m = re.search(r"OpenAI\.Codex_(\d+(?:\.\d+)*)_", caminho)
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def _appx_instalacao() -> str | None:
    """Pasta do pacote Codex segundo o Windows (o glob em WindowsApps volta vazio sem admin)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1).InstallLocation"],
            capture_output=True, text=True, timeout=30, creationflags=_SEM_JANELA)
        pasta = (r.stdout or "").strip().splitlines()
        return pasta[0].strip() if r.returncode == 0 and pasta else None
    except (OSError, subprocess.SubprocessError):
        return None


def _nome_ok(caminho: str) -> bool:
    return os.path.basename(caminho).lower() in NOMES_VALIDOS and os.path.isfile(caminho)


def localizar(caminho_config: str = "", *, padrao_pacotes: str = PADRAO_PACOTES,
              appx=_appx_instalacao, onde=shutil.which) -> tuple:
    """`(caminho, motivo)`. Ordem: config > pacote do WindowsApps (versão mais nova) > `codex` no
    PATH. Só aceita arquivo que exista e se chame `codex.exe` ou `codex.cmd`. Sem achar:
    `(None, motivo em português)`. Caminho da config inválido NÃO cai em outro: o dono é avisado."""
    if caminho_config and str(caminho_config).strip():
        c = str(caminho_config).strip().strip('"')
        if c.startswith("\\\\") or c.startswith("//"):
            return None, "O caminho do Codex não pode estar na rede."
        if _nome_ok(c):
            return c, "caminho da configuração"
        return None, "O caminho do Codex na configuração não existe ou não é um codex.exe."
    achados = [p for p in glob.glob(padrao_pacotes) if _nome_ok(p)]
    if achados:
        return max(achados, key=_versao), "app do Codex"
    try:
        pasta = appx()
    except Exception:
        pasta = None
    if pasta:
        c = os.path.join(pasta, "app", "resources", "codex.exe")
        if _nome_ok(c):
            return c, "app do Codex"
    c = onde("codex.exe")
    if c and _nome_ok(c) and not c.startswith("\\\\"):
        return c, "PATH"
    return None, "Não achei o Codex neste computador. Instale o app Codex da OpenAI e entre com o ChatGPT."


# ------------------------------------------------------------ executar processo

def _matar_arvore(proc):
    """Mata o processo e os filhos (o Codex lança shells por baixo)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                           timeout=15, creationflags=_SEM_JANELA)
        else:
            proc.kill()
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _truncar(texto: str) -> str:
    if len(texto) <= LIMITE_BYTES:
        return texto
    return texto[:LIMITE_BYTES] + "\n[... resposta cortada: passou do limite]"


def executar_processo(argv, entrada, timeout, env=None, ao_iniciar=None, cwd=None):
    """Roda `argv` sem shell, com `entrada` no stdin. Devolve `(código, stdout, stderr)`.
    Estourou o tempo: mata a árvore e levanta `TimeoutError`."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, cwd=cwd, creationflags=_SEM_JANELA)
    if ao_iniciar:
        ao_iniciar(proc)
    try:
        saida, erro = proc.communicate((entrada or "").encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        _matar_arvore(proc)
        try:
            proc.communicate(timeout=10)
        except Exception:
            pass
        raise TimeoutError("tempo limite do Codex")
    return (proc.returncode, _truncar(saida.decode("utf-8", "replace")), _truncar(erro.decode("utf-8", "replace")))


# ------------------------------------------------------------ login

def interpretar_status(codigo, texto) -> dict:
    t = (texto or "").lower()
    if codigo == 0 and "chatgpt" in t and "logged in" in t:
        return {"estado": "chatgpt", "texto": "Codex: pronto (ChatGPT)"}
    if "api key" in t and "logged in" in t:
        return {"estado": "chave_api",
                "texto": "Codex: logado com chave de API (gasta dinheiro, não a assinatura)"}
    if "not logged in" in t or "logged out" in t:
        return {"estado": "nao_logado", "texto": "Codex: não está logado (abra o app Codex e entre com o ChatGPT)"}
    return {"estado": "falhou", "texto": "Codex: não consegui conferir o login"}


def status(exe, executor=executar_processo) -> dict:
    """`{"estado": chatgpt | chave_api | nao_logado | falhou, "texto": ...}`."""
    if not exe:
        return {"estado": "falhou", "texto": "Codex: não instalado"}
    try:
        codigo, saida, erro = executor([exe, "login", "status"], "", 30, env=_ambiente(False))
    except Exception:
        return {"estado": "falhou", "texto": "Codex: não consegui conferir o login"}
    return interpretar_status(codigo, f"{saida}\n{erro}")


# ------------------------------------------------------------ montar a chamada

def _ambiente(sem_git: bool, base=None) -> dict:
    """Só a lista branca. Na escrita, o git do Codex (e o nosso) não tem credencial, hook nem fsmonitor
    (a worktree compartilha `.git/hooks` do repositório principal: um hook plantado rodaria no `git status`)."""
    origem = os.environ if base is None else base
    env = {k: v for k, v in origem.items()
           if k.upper() in _AMBIENTE_EXATO or k.upper().startswith(_AMBIENTE_PREFIXO)}
    if sem_git:
        env.update(ambiente_git_seguro())
    return env


def ambiente_git_seguro() -> dict:
    return {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "GCM_INTERACTIVE": "never",
            "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
            "GIT_CONFIG_KEY_1": "core.hooksPath", "GIT_CONFIG_VALUE_1": "NUL",
            "GIT_CONFIG_KEY_2": "core.fsmonitor", "GIT_CONFIG_VALUE_2": "false"}


def montar_argv(exe, pasta, arquivo_saida, modo="leitura", esforco="medium") -> list:
    """A linha de comando. O prompt NÃO entra aqui: vai por stdin (`-`)."""
    if modo not in ("leitura", "escrita"):
        raise ValueError("modo do Codex inválido")
    if esforco not in ESFORCOS:
        esforco = "medium"
    # --ignore-user-config + features desligadas: o ~/.codex/config.toml do dono liga MCP, plugins e
    # navegador, e a conta ChatGPT injeta conectores (GitHub, busca, sites) que rodam FORA do sandbox
    argv = [exe, "exec", "--ignore-user-config", "-c", 'windows.sandbox="elevated"',
            "-c", 'web_search="disabled"']
    for f in _FEATURES_DESLIGADAS:
        argv += ["--disable", f]
    argv += ["-s", "read-only" if modo == "leitura" else "workspace-write",
             "--ephemeral", "--skip-git-repo-check", "-C", pasta,
             "-c", f"model_reasoning_effort={esforco}"]
    if modo == "escrita":            # sem rede: nem `git push`, nem baixar nada
        argv += ["-c", "sandbox_workspace_write.network_access=false"]
    argv += ["--output-last-message", arquivo_saida, "-"]
    if any(p in a for a in argv for p in _PROIBIDOS):
        raise ValueError("opção proibida do Codex")
    return argv


# ------------------------------------------------------------ a resposta é DADO

_BLOCO_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
                        re.DOTALL)


def filtrar_saida(texto) -> str:
    """Linha a linha: a que parece segredo vira um aviso. O resto passa."""
    texto = _BLOCO_PEM.sub("[bloco removido: chave privada]", str(texto or ""))
    linhas = []
    for linha in texto.splitlines():
        linhas.append("[linha removida: parecia um segredo]" if cofre.parece_segredo(linha) else linha)
    return "\n".join(linhas).strip()


def cercar(texto) -> str:
    """Texto do Codex para alimentar OUTRO cérebro: cercado como saída de comando (dado, não ordem)."""
    import dervs_brain
    return dervs_brain._rotular({"papel": "resultado", "texto": filtrar_saida(texto)})


def fala_curta(texto) -> str:
    """No máximo duas frases, sem markdown, e nunca com segredo."""
    import dervs_claude_code as claude_code
    fala = claude_code.resumir_para_fala(filtrar_saida(texto))
    return "" if cofre.parece_segredo(fala) or "[linha removida" in fala or "[bloco removido" in fala else fala


# ------------------------------------------------------------ o Codex

class Codex:
    """Um Codex por vez. Tudo de fora (executor, localização, config) é injetável para o teste."""

    NEGATIVO_S = 60.0

    def __init__(self, *, config_fn=lambda: {}, localizar_fn=localizar, executor=executar_processo,
                 pasta_temp=None, relogio=time.monotonic):
        self._config = config_fn
        self._localizar = localizar_fn
        self._executor = executor
        self._pasta_temp = pasta_temp
        self._relogio = relogio
        self._trava = threading.Lock()
        self._trava_cache = threading.Lock()
        self._cache = None                 # (caminho_config, caminho|None, motivo, quando) — só em memória
        self._proc = None
        self._ocupado = False
        self._cancelado = False

    @property
    def ocupado(self) -> bool:
        return self._ocupado

    @property
    def ligado(self) -> bool:
        return bool(self._config().get("codex_ligado", True))

    def _achar(self) -> tuple:
        """`(caminho, motivo)` com cache em memória: reusa enquanto o arquivo existir (evita abrir o
        PowerShell a cada pergunta); o resultado negativo vale 60 s. Nunca grava em disco."""
        conf = str(self._config().get("codex_caminho", "") or "")
        with self._trava_cache:
            c = self._cache
            if c and c[0] == conf:
                if c[1] and os.path.isfile(c[1]):
                    return c[1], c[2]
                if not c[1] and self._relogio() - c[3] < self.NEGATIVO_S:
                    return None, c[2]
            caminho, motivo = self._localizar(conf)
            self._cache = (conf, caminho, motivo, self._relogio())
            return caminho, motivo

    def instalado(self) -> bool:
        """O `codex.exe` foi achado (com o mesmo cache de `_achar`). Pode abrir o PowerShell na
        1ª vez: chame fora da thread da tela."""
        return self._achar()[0] is not None

    def estado(self) -> dict:
        """Linha para o painel: pronto (ChatGPT) ou o motivo de não estar."""
        if not self.ligado:
            return {"estado": "desligado", "texto": "Codex: desligado na configuração"}
        exe, motivo = self._achar()
        if not exe:
            return {"estado": "falhou", "texto": "Codex: não instalado"}
        return status(exe, self._executor)

    def reservar(self) -> bool:
        """Toma o slot do Codex ANTES de preparar a cópia isolada. False se já está ocupado."""
        with self._trava:
            if self._ocupado:
                return False
            self._ocupado, self._cancelado, self._proc = True, False, None
            return True

    def liberar(self):
        with self._trava:
            self._ocupado, self._proc = False, None

    def parar(self) -> bool:
        """Interrompe o Codex em andamento. True se havia algo rodando."""
        with self._trava:
            if not self._ocupado:
                return False
            self._cancelado = True
            proc = self._proc
        if proc is not None:
            _matar_arvore(proc)
        return True

    def _guardar(self, proc):
        with self._trava:
            self._proc = proc
            cancelado = self._cancelado
        if cancelado:                      # "para" veio antes de o processo nascer
            _matar_arvore(proc)

    def perguntar(self, texto, pasta, modo="leitura", *, timeout=TEMPO_LIMITE_S, reservado=False) -> dict:
        """`{"ok", "texto", "motivo"}`. Nunca levanta. `reservado=True`: o chamador já tomou o slot."""
        if not reservado and not self.reservar():
            return {"ok": False, "texto": "", "motivo": "ocupado"}
        arquivo = None
        try:
            if not self.ligado:
                return {"ok": False, "texto": "", "motivo": "O Codex está desligado na configuração."}
            conf = self._config()
            exe, motivo = self._achar()
            if not exe:
                return {"ok": False, "texto": "", "motivo": motivo}
            if not pasta or not os.path.isdir(pasta):
                return {"ok": False, "texto": "", "motivo": "A pasta do pedido não existe."}
            fd, arquivo = tempfile.mkstemp(prefix="dervs-codex-", suffix=".txt", dir=self._pasta_temp)
            os.close(fd)
            argv = montar_argv(exe, pasta, arquivo, modo, conf.get("codex_esforco", "medium"))
            prompt = (PREAMBULO_ESCRITA if modo == "escrita" else PREAMBULO_LEITURA) + str(texto)
            env = _ambiente(modo == "escrita")
            try:
                codigo, saida, erro = self._executor(argv, prompt, timeout, env=env,
                                                     ao_iniciar=self._guardar, cwd=pasta)
            except TimeoutError:
                return {"ok": False, "texto": "", "motivo": "O Codex passou do tempo limite e eu parei."}
            if self._cancelado:
                return {"ok": False, "texto": "", "motivo": "Parei o Codex."}
            try:
                with open(arquivo, encoding="utf-8", errors="replace") as f:
                    resposta = f.read(LIMITE_BYTES + 1).strip()
            except OSError:
                resposta = ""
            if codigo != 0 and not resposta:
                if re.search(r"(?i)feature|unknown|unrecognized|--disable|ignore-user-config", erro or ""):
                    return {"ok": False, "texto": "", "motivo": "O Codex recusou uma opção de segurança "
                            "(talvez o app tenha mudado). Não rodei sem ela."}
                return {"ok": False, "texto": "", "motivo": "O Codex terminou com erro."}
            resposta = resposta or (saida or "").strip()
            if not resposta:
                return {"ok": False, "texto": "", "motivo": "O Codex não devolveu resposta."}
            return {"ok": True, "texto": filtrar_saida(_truncar(resposta)), "motivo": ""}
        except Exception as erro:
            return {"ok": False, "texto": "", "motivo": f"Algo falhou por dentro ({type(erro).__name__})."}
        finally:
            if arquivo:
                try:
                    os.remove(arquivo)
                except OSError:
                    pass
            self.liberar()


def iniciar_loop_codex(ponte, parar: threading.Event, codex: Codex, intervalo=300.0):
    """Thread que confere o login e manda a linha de estado ao painel. Como o cofre, repete o último
    valor a cada 3 s nos primeiros 30 s (o 1º envio sai antes de a tela dizer "pronto"); o login só
    é reconferido a cada `intervalo`. Erro aqui nunca derruba nada."""
    def corpo():
        passo, ultimo, quando = 0, None, 0.0
        while not parar.is_set():
            passo += 1
            try:
                if ultimo is None or time.monotonic() - quando >= intervalo:
                    ultimo, quando = codex.estado(), time.monotonic()
                ponte.enviar_codex(ultimo["estado"], ultimo["texto"])
            except Exception:
                pass
            parar.wait(3.0 if passo <= 10 else intervalo)
    t = threading.Thread(target=corpo, name="dervs-codex", daemon=True)
    t.start()
    return t
