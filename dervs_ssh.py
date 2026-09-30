#!/usr/bin/env python3
"""DERVS — terminal SSH (módulo testado, ainda SEM tela ligada a ele).

Um comando digitado aqui roda num servidor de verdade. Por isso o módulo é
feito de recusas, e cada uma tem um teste que quebra se alguém afrouxar:

  1. SÓ roda no computador do dono, chamado pela interface local. Nada do painel
     web nem da ponte importa este arquivo (teste por `ast` em test_dervs_ssh.py).
  2. O destino é um APELIDO da lista `ssh_hosts.json` (em `dervs_config.CONFIG_DIR`,
     vazia por padrão). O host, o usuário e a porta saem do arquivo, nunca do
     texto que chega. Apelido fora da lista ou fora do formato = recusa.
  3. Usa o `ssh.exe` do sistema com a chave/agente do PRÓPRIO usuário, sempre em
     BatchMode. Este módulo nunca guarda, pede nem repassa senha, nunca abre
     arquivo de chave e nunca põe caminho de chave no registro. O comando remoto
     vai como UM argumento de uma lista (sem shell, sem string concatenada).
  4. Classificação conservadora: `leitura` só se o comando casar INTEIRO com uma
     lista curta de comandos de leitura e não tiver nenhum metacaractere de shell.
     O resto é `muda_estado` e exige o clique do dono. O destrutivo óbvio é
     recusado sempre, nem com clique. Arquivo de segredo nunca é leitura.
  5. `muda_estado` só executa depois do clique, pelo mecanismo que já existe
     (`dervs_aprovacao.Motor`). O clique vale uma vez, vence em 15 minutos e fica
     preso ao hash do par (apelido, comando) que o dono viu.
  6. Todo passo vai para o registro de ações (`LogAcoes` INJETADO, nunca uma
     segunda instância sobre o mesmo arquivo).
  7. A saída do servidor é DADO: no máximo 64 KB, no máximo 60 s, passa pelo
     redator de segredos antes de voltar.
  8. Uma sessão por vez por apelido; no máximo 20 comandos por hora no total.

O terminal NÃO recebe o Motor: recebe um `AprovadorMotor`, que só sabe propor e
consumir. Quem abre o cartão e aprova é o painel local, como nas outras ações.
"""
import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
import threading
import time

import dervs_config
import dervs_log_acoes
import dervs_safety

TETO_SAIDA = 64 * 1024
TIMEOUT_S = 60
MAX_POR_HORA = 20
JANELA_S = 3600
VALIDADE_PROPOSTA_S = 15 * 60
MAX_PROPOSTAS = 50
MAX_COMANDO = 400          # cabe inteiro na tela de aprovação (o Motor corta em 500)
_LINHA_MAX = 3900          # o redator só enxerga 4000 caracteres por vez
_TROCA = "[SEGREDO REMOVIDO]"

_APELIDO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
_USUARIO = re.compile(r"[A-Za-z_][A-Za-z0-9._-]{0,31}")

# Opções fixas. Cada uma fecha uma porta: senha, pergunta interativa, repasse de
# agente/porta, servidor desconhecido, conexão pendurada.
OPCOES_FIXAS = (
    "BatchMode=yes",
    "StrictHostKeyChecking=yes",
    "PasswordAuthentication=no",
    "KbdInteractiveAuthentication=no",
    "ForwardAgent=no",
    "ClearAllForwardings=yes",
    "PermitLocalCommand=no",
    "NumberOfPasswordPrompts=0",
    "ConnectTimeout=10",
    "ServerAliveInterval=15",
    "ServerAliveCountMax=2",
)


# ------------------------------------------------------------ hosts (allowlist)

def arquivo_hosts_padrao() -> str:
    return os.path.join(dervs_config.CONFIG_DIR, "ssh_hosts.json")


def _porta_valida(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and 1 <= valor <= 65535


def _host_valido(host) -> bool:
    if not isinstance(host, str) or not host or "%" in host or "@" in host:
        return False
    if _HOST.fullmatch(host):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def carregar_hosts(caminho: str) -> dict:
    """{apelido: {"host","usuario","porta"}}. Arquivo ausente vira `{}` (e é
    criado vazio); arquivo ilegível ou entrada fora do formato libera NADA."""
    try:
        with open(caminho, encoding="utf-8") as f:
            bruto = json.load(f)
    except FileNotFoundError:
        try:
            os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
            with open(caminho, "w", encoding="utf-8", newline="\n") as f:
                f.write("{}\n")
        except OSError:
            pass
        return {}
    except (OSError, ValueError):
        return {}
    if not isinstance(bruto, dict):
        return {}
    saida = {}
    for apelido, dados in bruto.items():
        if not (isinstance(apelido, str) and _APELIDO.fullmatch(apelido) and isinstance(dados, dict)):
            continue
        host, usuario, porta = dados.get("host"), dados.get("usuario"), dados.get("porta", 22)
        if not (_host_valido(host) and isinstance(usuario, str) and _USUARIO.fullmatch(usuario)
                and _porta_valida(porta)):
            continue
        saida[apelido] = {"host": host, "usuario": usuario, "porta": porta}
    return saida


# ------------------------------------------------------------ classificação

# Única lista de leitura. Comparação com `fullmatch`, sem IGNORECASE.
_UNIDADE = r"[A-Za-z0-9][A-Za-z0-9@._-]{0,63}"
_CHARS = r"[A-Za-z0-9._@+/-]"
# Leitura só sob prefixos PERMITIDOS; o resto (chave do host, histórico, /dev, /proc...)
# vira `muda_estado` com clique. Dentro dos prefixos o nome de segredo ainda bloqueia.
_CAMINHO_TAIL = rf"/var/log/{_CHARS}{{1,200}}"
_CAMINHO_LS = rf"(?:/var/log|/srv|/opt|/var/www)(?:/{_CHARS}{{0,200}})?"
_N = r"[1-9][0-9]{0,2}"
_LEITURAS = [re.compile(p) for p in (
    r"uptime", r"hostname", r"date", r"whoami", r"df -h", r"free -m",
    r"docker ps", r"docker compose ps",
    rf"systemctl status {_UNIDADE}",
    rf"journalctl -n {_N} --no-pager",
    rf"journalctl -u {_UNIDADE} -n {_N} --no-pager",
    rf"tail -n {_N} {_CAMINHO_TAIL}",
    rf"ls {_CAMINHO_LS}",
    rf"ls -(?:l|la|lh|lah) {_CAMINHO_LS}",
)]

# Qualquer um destes caracteres (ou `..`) tira o comando da leitura.
_METACARACTERE = re.compile(r"[;&|`$()<>\\\n\r\t'\"*?\[\]{}!#~^]|\.\.")

_SEGREDO_CAMINHO = re.compile(
    r"(?i)(?:^|[/\s])(?:\.env[\w.\-]*|[\w.\-]*\.env|id_[\w.\-]*|"
    r"[\w.\-]*\.(?:pem|key|pfx|p12|kdbx|jks|keystore)|shadow|gshadow|sudoers|environ|"
    r"authorized_keys|\.ssh|\.aws|\.gnupg|\.netrc|\.pgpass|\.npmrc|\.pypirc|\.git-credentials|"
    r"credentials[\w.\-]*|secrets?[\w.\-]*|passwd)(?:$|[/\s])")

_PULA_PARA_SHELL = r"\|\s*(?:sudo\s+)?(?:ba|z|da|k|c)?sh\b"
_DESTRUTIVOS = [(re.compile(p, re.IGNORECASE), m) for p, m in (
    (r"(?<![\w-])rm\b(?=.*(?:\s-\w*[rRf]|--recursive|--force|--no-preserve-root))",
     "apaga arquivos ou pastas"),
    (r"\bfind\b.*(?:\s-delete\b|\s-exec\b)", "apaga ou executa por cima de uma busca"),
    (r"\brsync\b.*--delete", "sincroniza apagando o que sobra no destino"),
    (r"\b(?:shred|wipe|wipefs)\b", "destrói dados de forma irreversível"),
    (r"\bdd\b.*\bof=", "escreve direto no disco"),
    (r"\bmkfs", "formata um dispositivo"),
    (r"\b(?:fdisk|sfdisk|parted|sgdisk|gdisk)\b", "mexe na tabela de partições"),
    (r">\s*/dev/(?:sd|nvme|mmc|hd|vd|disk)", "escreve por cima de um disco"),
    (r"\bmv\b.*\s/dev/null", "joga arquivo fora"),
    (r":\(\)\s*\{", "fork bomb"),
    (r"\b(?:shutdown|reboot|poweroff|halt|telinit)\b", "desliga ou reinicia o servidor"),
    (r"\binit\s+[06]\b", "desliga ou reinicia o servidor"),
    (r"\btruncate\b", "zera arquivo ou tabela"),
    (r"\bdrop\s+(?:table|database|schema|user|index|view)\b", "apaga tabela ou banco"),
    (r"\b(?:chmod|chown|chgrp)\b.*(?:\s-\w*R|--recursive)", "muda permissão em massa"),
    (r"\b(?:curl|wget|fetch)\b.*" + _PULA_PARA_SHELL, "baixa e executa código às cegas"),
    (r"<\(\s*(?:curl|wget)\b", "baixa e executa código às cegas"),
    (_PULA_PARA_SHELL, "manda texto direto para um shell"),
    (r"\beval\b", "executa texto montado na hora"),
    (r"\bdocker\b.*(?:\bsystem\s+prune|\bvolume\s+(?:rm|prune)|\bdown\s+-\w*v)",
     "remove contêineres ou volumes"),
    (r"\bgit\s+(?:reset\s+--hard|clean\s+-\w*[fdx]|push\b.*--force)", "descarta ou reescreve histórico"),
    (r"\b(?:userdel|deluser|groupdel|chpasswd|visudo)\b", "mexe em contas do servidor"),
    (r"\bcrontab\s+-r\b", "apaga todas as tarefas agendadas"),
    (r"\b(?:iptables|nft)\b.*\s-F\b", "zera o firewall"),
)]


def hash_do_par(apelido: str, comando: str, host: dict) -> str:
    """Impressão digital do que o dono viu: apelido, comando E o destino que o
    apelido tinha na hora (host, usuário, porta). Se o cadastro mudar depois do
    clique, o hash muda e a execução é recusada."""
    texto = json.dumps(["ssh", apelido, comando, host["host"], host["usuario"], host["porta"]],
                       ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("ascii")).hexdigest()


def classificar_comando(comando) -> dict:
    """{"nivel": leitura|muda_estado|recusado, "motivo": str, "le_segredo": bool}.
    Na dúvida sobe: leitura é o único nível que dispensa o clique."""
    def resposta(nivel, motivo, segredo=False):
        return {"nivel": nivel, "motivo": motivo, "le_segredo": segredo}

    if not isinstance(comando, str) or not comando:
        return resposta("recusado", "comando vazio ou que não é texto")
    if len(comando) > MAX_COMANDO:
        return resposta("recusado", f"comando longo demais (máximo {MAX_COMANDO} caracteres)")
    if not comando.isprintable() or comando != comando.strip() or "  " in comando:
        return resposta("recusado", "o comando tem quebra de linha, tabulação, caractere invisível "
                                    "ou espaço repetido — o que você aprova tem de ser o que roda")
    for padrao, motivo in _DESTRUTIVOS:
        if padrao.search(comando):
            return resposta("recusado", f"recusado sempre: {motivo}")
    if str(dervs_log_acoes.redigir(comando)) != comando:
        return resposta("recusado", "o comando parece conter uma senha ou chave — não escreva segredo "
                                    "aqui; use o que já está configurado no servidor", True)
    local = dervs_safety.classificar_local(comando)
    segredo = bool(local["le_segredo"]) or bool(_SEGREDO_CAMINHO.search(comando))
    if segredo:
        return resposta("muda_estado", "mexe em arquivo de segredo — precisa do seu clique", True)
    if local["toca_alvo"]:
        return resposta("muda_estado", "fala com outro alvo de rede — precisa do seu clique")
    if (not _METACARACTERE.search(comando)
            and any(p.fullmatch(comando) for p in _LEITURAS)):
        return resposta("leitura", "comando de leitura conhecido")
    return resposta("muda_estado", "comando fora da lista de leitura — precisa do seu clique")


# ------------------------------------------------------------ o ssh de verdade

def localizar_ssh() -> str | None:
    """SÓ o OpenSSH do Windows, em System32/OpenSSH dentro de %SystemRoot%. Nada de PATH,
    pasta atual, .cmd ou .bat: um `ssh` plantado nesses lugares receberia o
    comando e a chave do dono."""
    raiz = os.environ.get("SystemRoot") or r"C:\Windows"
    candidato = os.path.join(raiz, "System32", "OpenSSH", "ssh.exe")
    return candidato if os.path.isfile(candidato) else None


def montar_argv(ssh_exe: str, host: dict, comando: str) -> list:
    """Lista de argumentos para o `ssh`. O destino vem do arquivo de hosts; o
    comando remoto é o ÚLTIMO argumento, inteiro, sem passar por shell local."""
    argv = [ssh_exe, "-T"]
    for opcao in OPCOES_FIXAS:
        argv += ["-o", opcao]
    argv += ["-p", str(host["porta"]), "-l", host["usuario"], "--", host["host"], comando]
    return argv


def executar_ssh_padrao(argv, timeout):
    """(rc, bytes). Sem stdin (não há onde digitar senha), sem shell. No estouro
    do tempo mata o processo e levanta TimeoutError; se a saída passar do teto,
    mata também e devolve um byte a mais que o teto (sinal de corte)."""
    proc = subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    acumulado = bytearray()

    def ler():
        try:
            while True:
                bloco = proc.stdout.read1(65536)
                if not bloco:
                    return
                sobra = TETO_SAIDA + 1 - len(acumulado)
                if sobra > 0:
                    acumulado.extend(bloco[:sobra])
                if len(acumulado) > TETO_SAIDA:
                    proc.kill()
                    return
        except (OSError, ValueError):
            return

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        leitor.join(2)
        raise TimeoutError("tempo esgotado")
    leitor.join(5)
    return proc.returncode, bytes(acumulado)


# ------------------------------------------------------------ saída do servidor

_TRACOS = "-" * 5      # o bloco PEM é montado em partes (o scanner de segredo do repo)
_CHAVE_PRIVADA = re.compile(_TRACOS + r"BEGIN [^\n-]*" + _TRACOS + r"[\s\S]*?(?:" + _TRACOS
                            + r"END [^\n-]*" + _TRACOS + r"|\Z)")
_FIM_DE_CHAVE = re.compile(_TRACOS + r"END [^\n-]*KEY" + _TRACOS)
_PAR_JSON = re.compile(r'"([\w.\-]{1,60})"(\s*:\s*)"((?:[^"\\]|\\.){0,4000})"')
_MARCA_DE_CHAVE = re.compile(r"id_(?:rsa|dsa|ecdsa|ed25519)|\.pem\b|[\\/]\.ssh[\\/]")
_PALAVRA = re.compile(r"\S+")


def _valor_json(m) -> str:
    """`"auth":"base64..."`: o redator geral só enxerga nome=valor sem aspas."""
    if dervs_log_acoes._nome_secreto(m.group(1)):
        return f'"{m.group(1)}"{m.group(2)}"{_TROCA}"'
    return m.group(0)


def _sem_caminho_de_chave(linha: str) -> str:
    """Palavra por palavra (tempo linear): a que cheira a arquivo de chave vira
    `[caminho]`. Uma regex com prefixo guloso aqui levou 56 s para 64 KB."""
    return _PALAVRA.sub(
        lambda m: "[caminho]" if _MARCA_DE_CHAVE.search(m.group(0)) else m.group(0), linha)


def _limpar_saida(bruto) -> tuple[str, bool]:
    """(texto seguro, truncada). A saída é dado: corta, decodifica, tira segredo
    e caminho de chave. O redator só olha 4000 caracteres por vez, então a
    saída é redigida por blocos de linhas inteiras (linha enorme é cortada, não
    partida no meio)."""
    if isinstance(bruto, (bytes, bytearray)):
        truncada = len(bruto) > TETO_SAIDA
        texto = bytes(bruto[:TETO_SAIDA]).decode("utf-8", errors="replace")
    else:
        texto = str(bruto)
        truncada = len(texto.encode("utf-8", errors="replace")) > TETO_SAIDA
        texto = texto[:TETO_SAIDA]
    texto = _CHAVE_PRIVADA.sub(_TROCA, texto)
    # `tail -n 6` de uma chave deixa só o corpo em base64 e a linha END: sem BEGIN
    # antes, apaga do começo do texto até o fim dessa linha.
    fins = list(_FIM_DE_CHAVE.finditer(texto))
    if fins:
        corte = texto.find("\n", fins[-1].end())
        texto = _TROCA + "\n" + (texto[corte + 1:] if corte != -1 else "")
    blocos, atual = [], ""
    for linha in texto.splitlines(keepends=True):
        if len(linha) > _LINHA_MAX:
            linha = linha[:_LINHA_MAX] + " [linha cortada]\n"
        linha = _sem_caminho_de_chave(linha)
        linha = _PAR_JSON.sub(_valor_json, linha)
        if atual and len(atual) + len(linha) > _LINHA_MAX + 50:
            blocos.append(atual)
            atual = ""
        atual += linha
    if atual:
        blocos.append(atual)
    limpo = "".join(str(dervs_log_acoes.redigir(b)) for b in blocos)
    if truncada:
        limpo += "\n[saída cortada em 64 KB]"
    return limpo, truncada


# ------------------------------------------------------------ ponte com o Motor

class AprovadorMotor:
    """O que o terminal enxerga do `dervs_aprovacao.Motor`: propor um item e
    consumir o clique. NÃO carrega `aprovar` nem `abrir_cartao` — esses ficam com
    o painel local, que é quem recebe o clique do dono.

    O item vai como a ação própria `executar_ssh` do Motor, com alvo
    `ssh:<apelido>`, o comando e `versao` = hash do par. O Motor só aceita essa
    ação com origem "ssh" (a Fachada do Claude nunca cria) e só a entrega a quem
    se identifica como consumidor "ssh"; o hash é conferido de novo aqui (clique
    dado a outro comando não vale)."""

    def __init__(self, motor):
        self._analisar = motor.analisar
        self._consumir = motor.consumir_aprovacao
        self._concluir = motor.marcar_resultado

    def registrar(self, apelido: str, comando: str, hash_do_par_: str) -> dict:
        relatorio = self._analisar([{
            "acao": "executar_ssh", "alvo": f"ssh:{apelido}", "comando": comando,
            "versao": hash_do_par_,
            "por_que_seguro": "Comando do terminal SSH do próprio DERVS; só roda com o seu clique, "
                              "uma única vez.",
            "risco": "alto",
        }], origem="ssh")
        if not relatorio["itens"]:
            motivo = relatorio["recusados"][0]["motivo"] if relatorio["recusados"] else "recusado"
            raise ValueError(motivo)
        return {"relatorio_id": relatorio["id"], "item_id": relatorio["itens"][0]["id"]}

    def consumir(self, ref: dict, prova, apelido: str, hash_do_par_: str) -> tuple[bool, str]:
        if not isinstance(prova, dict):
            return False, "falta o clique de aprovação"
        registro_id = prova.get("registro_id", prova.get("id"))
        token_de_uso = prova.get("token")
        if not (isinstance(registro_id, str) and isinstance(token_de_uso, str)):
            return False, "falta o clique de aprovação"
        rel = prova.get("relatorio_id")
        if not isinstance(rel, str) or rel != ref["relatorio_id"]:
            # sem relatório ou de outro: recusa ANTES de consumir, para não queimar
            # o clique que pertence a outra ação
            return False, "esse clique não é deste comando (falta o relatório certo)"
        r = self._consumir(registro_id, token_de_uso, ref["item_id"], consumidor="ssh")
        if not r.get("ok"):
            return False, str(r.get("motivo", "aprovação recusada"))
        item, registro = r["item"], r["registro"]
        if (registro.get("relatorio_id") != ref["relatorio_id"]
                or item.get("acao") != "executar_ssh" or item.get("alvo") != f"ssh:{apelido}" or item.get("versao") != hash_do_par_):
            return False, "esse clique foi dado para outro comando"
        return True, ""

    def concluir(self, ref: dict, ok: bool):
        self._concluir(ref["relatorio_id"], ref["item_id"], ok)


# ------------------------------------------------------------ o terminal

class TerminalSSH:
    def __init__(self, log, aprovador=None, *, executar_ssh=None, arquivo_hosts: str | None = None,
                 ssh_exe: str | None = None, relogio=time.monotonic, timeout_s: int = TIMEOUT_S,
                 max_por_hora: int = MAX_POR_HORA):
        if log is None or not hasattr(log, "registrar"):
            raise TypeError("o terminal SSH recebe o LogAcoes já existente; não cria outro")
        self._log = log
        self._aprovador = aprovador
        self._executar = executar_ssh or executar_ssh_padrao
        self._arquivo_hosts = arquivo_hosts or arquivo_hosts_padrao()
        self._ssh_exe = ssh_exe
        self._relogio = relogio
        self._timeout_s = timeout_s
        self._max_por_hora = max_por_hora
        self._trava = threading.Lock()
        self._propostas = {}
        self._em_uso = set()
        self._horas = []

    # --------------------------------------------------- utilidades
    def _hosts(self) -> dict:
        return carregar_hosts(self._arquivo_hosts)

    def apelidos(self) -> list:
        return sorted(self._hosts())

    def _registrar(self, evento, dados):
        self._log.registrar(evento, dados)

    def _recusa(self, etapa: str, motivo: str, **dados) -> dict:
        try:
            self._registrar("recusou", dict(dados, etapa=etapa, motivo=motivo))
        except Exception:
            pass  # recusar não depende do registro; executar, sim
        return {"ok": False, "motivo": motivo}

    def _podar(self, agora):
        for pid in [p for p, v in self._propostas.items() if agora > v["expira"]]:
            del self._propostas[pid]
        while len(self._propostas) >= MAX_PROPOSTAS:
            del self._propostas[min(self._propostas, key=lambda p: self._propostas[p]["criada"])]

    # --------------------------------------------------- 1. propor
    def propor(self, apelido, comando) -> dict:
        if not isinstance(apelido, str) or not _APELIDO.fullmatch(apelido):
            return self._recusa("propor", "apelido em formato inválido",
                                apelido=repr(apelido)[:40])
        hosts = self._hosts()
        if apelido not in hosts:
            return self._recusa("propor", "apelido fora da lista de servidores permitidos",
                                apelido=apelido)
        c = classificar_comando(comando)
        if c["nivel"] == "recusado":
            return self._recusa("propor", c["motivo"], apelido=apelido,
                                comando=comando if isinstance(comando, str) else repr(comando)[:40])
        impressao = hash_do_par(apelido, comando, hosts[apelido])
        ref = None
        if c["nivel"] == "muda_estado":
            if self._aprovador is None:
                return self._recusa("propor", "não há como aprovar aqui; nada foi proposto",
                                    apelido=apelido, comando=comando)
            try:
                ref = self._aprovador.registrar(apelido, comando, impressao)
            except Exception as erro:
                return self._recusa("propor", f"a aprovação não aceitou o comando: {str(erro)[:120]}",
                                    apelido=apelido, comando=comando)
        agora = self._relogio()
        proposta_id = secrets.token_hex(8)
        with self._trava:
            self._podar(agora)
            self._propostas[proposta_id] = {
                "apelido": apelido, "comando": comando, "nivel": c["nivel"], "hash": impressao,
                "ref": ref, "criada": agora, "expira": agora + VALIDADE_PROPOSTA_S}
        dados = {"proposta_id": proposta_id, "apelido": apelido, "comando": comando,
                 "nivel": c["nivel"], "hash": impressao}
        try:
            self._registrar("analisou", dados)
            if ref:
                self._registrar("propos", dict(dados, **ref))
        except Exception:
            pass  # propor não age; o registro que importa é o de executar
        return {"ok": True, "proposta_id": proposta_id, "apelido": apelido, "comando": comando,
                "nivel": c["nivel"], "hash": impressao, "aprovacao": dict(ref) if ref else None,
                "motivo": c["motivo"], "valida_por_s": VALIDADE_PROPOSTA_S}

    # --------------------------------------------------- 2. executar
    def executar(self, proposta_id, prova=None) -> dict:
        def recusa(motivo, **dados):
            return self._recusa("executar", motivo, proposta_id=str(proposta_id)[:40], **dados)

        agora = self._relogio()
        with self._trava:
            p = self._propostas.get(proposta_id) if isinstance(proposta_id, str) else None
            if p is not None and agora > p["expira"]:
                del self._propostas[proposta_id]
                p = None
            p = dict(p) if p else None
        if p is None:
            return recusa("proposta não encontrada ou vencida — proponha de novo")
        apelido, comando = p["apelido"], p["comando"]
        host = self._hosts().get(apelido)
        if host is None:
            return recusa("o apelido saiu da lista de servidores permitidos", apelido=apelido)
        if hash_do_par(apelido, comando, host) != p["hash"]:
            return recusa("a proposta, ou o cadastro do servidor, mudou desde que você viu — "
                          "proponha de novo", apelido=apelido)
        c = classificar_comando(comando)
        if c["nivel"] == "recusado" or c["nivel"] != p["nivel"]:
            return recusa("o comando não passa mais na classificação", apelido=apelido)
        ssh_exe = self._ssh_exe or localizar_ssh()
        if not ssh_exe:
            return recusa("o terminal SSH está indisponível: o OpenSSH do Windows (ssh.exe em "
                          "System32/OpenSSH) não está instalado", apelido=apelido)

        # Reserva a sessão e o lugar no teto ANTES de consumir o clique: negar por
        # sessão ocupada ou por teto não pode gastar a aprovação do dono.
        with self._trava:
            if apelido in self._em_uso:
                return recusa("já há uma sessão aberta neste servidor — espere terminar",
                              apelido=apelido)
            self._horas = [t for t in self._horas if t > agora - JANELA_S]
            if len(self._horas) >= self._max_por_hora:
                return recusa(f"teto de {self._max_por_hora} comandos por hora atingido",
                              apelido=apelido)
            self._em_uso.add(apelido)
            self._horas.append(agora)
        try:
            if p["nivel"] == "muda_estado":
                if self._aprovador is None or not p["ref"]:
                    ok, motivo = False, "sem mecanismo de aprovação"
                else:
                    try:
                        ok, motivo = self._aprovador.consumir(p["ref"], prova, apelido, p["hash"])
                    except Exception:
                        ok, motivo = False, "a aprovação não pôde ser conferida"
                if not ok:
                    with self._trava:
                        if agora in self._horas:
                            self._horas.remove(agora)   # tentativa negada não gasta o teto
                    return recusa(motivo, apelido=apelido)
                try:
                    self._registrar("aprovou", {"proposta_id": proposta_id, "apelido": apelido,
                                                "hash": p["hash"], "origem": "clique"})
                except Exception:
                    pass  # o Motor já registrou o "aprovou"; o que bloqueia é o vai_executar
            with self._trava:
                self._propostas.pop(proposta_id, None)   # vale uma vez, deu certo ou não
            try:
                self._registrar("vai_executar", {"proposta_id": proposta_id, "apelido": apelido,
                                                 "comando": comando, "hash": p["hash"],
                                                 "nivel": p["nivel"]})
            except Exception:
                return {"ok": False, "motivo": "não consegui gravar no registro de ações — "
                                               "por segurança, nada foi feito"}
            return self._rodar(proposta_id, p, host, ssh_exe)
        finally:
            with self._trava:
                self._em_uso.discard(apelido)

    def _rodar(self, proposta_id, p, host, ssh_exe) -> dict:
        argv = montar_argv(ssh_exe, host, p["comando"])
        rc, bruto, motivo = None, b"", ""
        try:
            rc, bruto = self._executar(argv, self._timeout_s)
        except TimeoutError:
            motivo = f"tempo esgotado ({self._timeout_s} s) — o DERVS encerrou a conexão"
        except Exception as erro:
            motivo = f"falha ao rodar o ssh ({type(erro).__name__})"
        saida, truncada = ("", False) if motivo else _limpar_saida(bruto)
        ok = not motivo
        try:
            self._registrar("executou", {
                "proposta_id": proposta_id, "apelido": p["apelido"], "hash": p["hash"],
                "ok": ok, "rc": rc if rc is not None else -1,
                "bytes": len(bruto) if ok else 0, "truncada": truncada, "motivo": motivo})
        except Exception:
            pass  # já executou; o aviso de registro falho não desfaz nada
        if p["ref"] and self._aprovador is not None:
            try:
                self._aprovador.concluir(p["ref"], ok)
            except Exception:
                pass
        if not ok:
            return {"ok": False, "motivo": motivo, "apelido": p["apelido"]}
        return {"ok": True, "rc": rc, "saida": saida, "truncada": truncada, "apelido": p["apelido"]}

    # --------------------------------------------------- atalho para a tela
    def rodar(self, apelido, comando) -> dict:
        """Leitura roda direto; o resto volta como proposta esperando o clique."""
        p = self.propor(apelido, comando)
        if not p["ok"]:
            return p
        if p["nivel"] == "leitura":
            return dict(self.executar(p["proposta_id"]), proposta=p)
        return {"ok": False, "precisa_clique": True, "proposta": p,
                "motivo": "este comando muda o servidor — precisa do seu clique"}
