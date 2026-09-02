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
    (r"\b(Invoke-WebRequest|iwr|curl|wget)\b.*\|\s*(Invoke-Expression|iex)\b",
     "baixa e executa código da internet às cegas (PowerShell)"),
    (r"\biex\s*\(", "executa código dinamicamente (PowerShell)"),
    (r"\bInvoke-Expression\b", "executa código dinamicamente (PowerShell)"),
    (r"\bRemove-Item\b.+(C:\\\\?Windows|C:\\\\?Program Files|\$env:SystemRoot)",
     "apaga uma pasta de sistema do Windows"),
    (r"\btakeown\s+/f\s+C:\\?\s+/r", "toma posse da raiz do disco C:"),
    (r"\bicacls\s+C:\\?\s+.*\bgrant\b.*\s/t\b", "reescreve permissões da raiz do disco C:"),
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
    (r"\b(curl|wget)\b.+https?://(?!localhost|127\.0\.0\.1)", "acessa um endereço na internet"),
    (r"\b\d{1,3}(\.\d{1,3}){3}\b", "aponta para um endereço de rede (IP)"),
]

# --- comandos claramente inofensivos: podem ficar no trilho reversível ---------
# Só o que está aqui pode ser "reversível". Qualquer coisa fora desta lista e
# fora da lista de destrutivos cai em "muda_estado" — ou seja, no MÍNIMO pede
# uma confirmação. Assim um comando novo/desconhecido nunca roda sozinho.
_SEGUROS = [
    r"\bls\b", r"\bcat\b", r"\bless\b", r"\bhead\b", r"\btail\b", r"\becho\b",
    r"\bpwd\b", r"\bcd\b", r"\bwhoami\b", r"\bid\b", r"\bdate\b", r"\buname\b",
    r"\bwhich\b", r"\btype\b", r"\bps\b", r"\btop\b", r"\bhtop\b", r"\bdf\b",
    r"\bdu\b", r"\bfree\b", r"\bgrep\b", r"\bfind\b", r"\bfile\b", r"\bstat\b",
    r"\bhistory\b", r"\benv\b", r"\bprintenv\b", r"\bwc\b", r"\bsort\b",
    r"\buniq\b", r"\bgit\s+(status|log|diff|branch|show)\b",
    r"\bxdg-open\b", r"\bkonsole\b", r"\bfirefox\b", r"\bchromium\b",
    r"\bcode\b", r"\bnautilus\b", r"\bdolphin\b",
    # Windows (PowerShell/cmd) — só leitura ou abrir app de tela.
    r"\bdir\b", r"\btype\b", r"\bGet-ChildItem\b", r"\bGet-Content\b",
    r"\bGet-Location\b", r"\bGet-Date\b", r"\bGet-Process\b", r"\bTest-Path\b",
    r"\bwhere\b", r"\bwhoami\b", r"\bhostname\b", r"\bsysteminfo\b",
    r"\bipconfig\b", r"\bexplorer\b", r"\bnotepad\b", r"\bcalc\b", r"\bwt\b",
    r"\bchrome\b", r"\bmsedge\b", r"\bcode\b", r"\bstart\b",
]


def _casa(comando: str, padroes) -> bool:
    return any(re.search(p, comando, re.IGNORECASE) for p in padroes)


def classificar_local(comando: str) -> dict:
    """A palavra final da máquina sobre UM comando.

    Devolve:
      piso        — o trilho MÍNIMO que a máquina exige (o Claude pode subir).
      toca_alvo   — True se o comando fala com uma rede/alvo real.
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

    # 2) Toca um alvo de rede? — topo também, e marca para pedir autorização.
    if _casa(comando, _FERRAMENTAS_ALVO):
        toca_alvo = True
        motivos.append("usa ferramenta que toca um alvo de rede")
    for padrao, motivo in _REDE_GENERICA:
        if re.search(padrao, comando, re.IGNORECASE):
            toca_alvo = True
            motivos.append(motivo)
    if toca_alvo:
        piso = _nivel_max(piso, "destrutivo")

    # 3) Não é perigoso nem toca alvo: é reconhecidamente inofensivo?
    #    Se não for da lista de seguros, exige no mínimo uma confirmação.
    if piso == "reversivel" and not toca_alvo:
        if not _casa(comando, _SEGUROS):
            piso = "muda_estado"
            motivos.append("comando não reconhecido como inofensivo — confirmar por garantia")

    return {"piso": piso, "toca_alvo": toca_alvo, "motivos": motivos}


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
        "precisa_autorizacao": local["toca_alvo"],
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
