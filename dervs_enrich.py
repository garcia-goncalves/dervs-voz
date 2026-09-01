#!/usr/bin/env python3
"""DERVS — enriquecimento de lead (OSINT de domínio).

Recebe um DOMÍNIO ("cliente.com.br") e devolve o que se descobre dele em fonte
PÚBLICA: subdomínios, e-mails, tecnologias, buckets de nuvem, achados. Serve para
qualificar um lead antes de falar com ele — e, na visão defensiva do DERVS,
para mostrar onde a superfície do próprio cliente está exposta.

Motor: o `bbot` (já instalado nesta máquina), o orquestrador de recon. Este
módulo chama o CLI dele e agrega os eventos JSON num resumo estruturado.

DUAS VELOCIDADES, e a diferença é de LEI, não de gosto:
  - PASSIVO (padrão): só fonte pública (DNS, certificados, bases de OSINT). NÃO
    conecta no alvo. Pode rodar livre — não toca a máquina de ninguém.
  - ATIVO: conecta no alvo (resolve, bate em porta/web). SÓ com autorização por
    escrito do dono do lead. Quem libera isso é a carta de confirmação da tela
    (o passo vira toca_alvo=true), nunca este módulo sozinho.

Contexto: a saída bruta do bbot é enorme. Este módulo GUARDA o bruto num arquivo
e devolve só um RESUMO curto (contagens + alguns exemplos) — é o que a voz fala e
o que não estoura o contexto do DERVS.

Contrato: rodar_para_app(dominio, ativo) devolve {"codigo","saida","tipo"}, o
mesmo formato de dervs_exec.rodar, para a tela e o cérebro tratarem igual.
"""
import os
import re
import json
import shutil
import tempfile

BBOT = (shutil.which("bbot")
        or os.path.expanduser("~/.local/bin/bbot")
        or "bbot")

# Domínio válido (evita rodar recon em lixo de transcrição de voz).
_DOMINIO_RE = re.compile(
    r"^(?=.{4,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$", re.IGNORECASE)

# Os tipos de evento que viram campo do lead.
_TIPOS_INTERESSE = ("DNS_NAME", "EMAIL_ADDRESS", "TECHNOLOGY", "STORAGE_BUCKET",
                    "FINDING", "VULNERABILITY", "URL", "OPEN_TCP_PORT")


def dominio_valido(dominio: str) -> bool:
    return bool(_DOMINIO_RE.match((dominio or "").strip().rstrip(".")))


def _texto_do_dado(dado) -> str:
    """O campo 'data' de um evento bbot pode ser string OU objeto. Puxa o texto
    mais útil de qualquer um dos dois, sem quebrar. Devolve "" quando não há nada
    aproveitável (evento sem 'data', ou campo nulo) — o chamador descarta."""
    if dado is None:
        return ""
    if isinstance(dado, str):
        return dado
    if isinstance(dado, dict):
        # campos DESCRITIVOS primeiro; 'host'/'url' por último (são os mais
        # genéricos — para TECHNOLOGY queremos o nome, não o host onde apareceu).
        for chave in ("technology", "description", "name", "bucket_name",
                      "email", "url", "host"):
            v = dado.get(chave)
            if isinstance(v, str) and v:
                return v
        return json.dumps(dado, ensure_ascii=False)[:200]
    return str(dado)


def agregar_eventos(linhas) -> dict:
    """Recebe linhas NDJSON do bbot e devolve o lead estruturado.

    Função pura (entra texto, sai dict) para dar para testar sem rodar recon.
    Deduplica e ordena, para o resumo ficar estável."""
    lead = {"subdominios": set(), "emails": set(), "tecnologias": set(),
            "buckets": set(), "urls": set(), "portas": set(),
            "achados": [], "vulnerabilidades": []}
    for linha in linhas:
        linha = (linha or "").strip()
        if not linha or not linha.startswith("{"):
            continue
        try:
            ev = json.loads(linha)
        except Exception:
            continue
        tipo = ev.get("type")
        if tipo not in _TIPOS_INTERESSE:
            continue
        txt = _texto_do_dado(ev.get("data")).strip()
        # descarta vazio e o literal "None"/"null" (evento sem dado aproveitável)
        if not txt or txt.lower() in ("none", "null"):
            continue
        if tipo == "DNS_NAME":
            lead["subdominios"].add(txt.lower())
        elif tipo == "EMAIL_ADDRESS":
            lead["emails"].add(txt.lower())
        elif tipo == "TECHNOLOGY":
            lead["tecnologias"].add(txt)
        elif tipo == "STORAGE_BUCKET":
            lead["buckets"].add(txt)
        elif tipo == "URL":
            lead["urls"].add(txt)
        elif tipo == "OPEN_TCP_PORT":
            lead["portas"].add(txt)
        elif tipo == "FINDING":
            lead["achados"].append(txt)
        elif tipo == "VULNERABILITY":
            sev = ""
            if isinstance(ev.get("data"), dict):
                sev = ev["data"].get("severity", "")
            lead["vulnerabilidades"].append((sev, txt))
    # conjuntos → listas ordenadas (resumo estável)
    for k in ("subdominios", "emails", "tecnologias", "buckets", "urls", "portas"):
        lead[k] = sorted(lead[k])
    return lead


def resumir(lead: dict, dominio: str, ativo: bool) -> str:
    """Monta o resumo curto que a voz fala — contagens e alguns exemplos, nunca
    a lista inteira (isso o dono lê no arquivo/na tela)."""
    modo = "ativo" if ativo else "passivo"
    partes = [f"Enriquecimento {modo} de {dominio}:"]
    def linha(rotulo, itens, n=5):
        if itens:
            amostra = ", ".join(itens[:n])
            mais = f" (+{len(itens) - n})" if len(itens) > n else ""
            partes.append(f"- {rotulo}: {len(itens)} — {amostra}{mais}")
    linha("subdomínios", lead["subdominios"])
    linha("e-mails", lead["emails"])
    linha("tecnologias", lead["tecnologias"])
    linha("buckets de nuvem", lead["buckets"])
    if lead["achados"]:
        partes.append(f"- achados: {len(lead['achados'])} — {lead['achados'][0][:120]}")
    if lead["vulnerabilidades"]:
        vs = lead["vulnerabilidades"]
        partes.append(f"- VULNERABILIDADES: {len(vs)} — {vs[0][1][:120]}")
    if len(partes) == 1:
        partes.append("- nada de público encontrado (ou o alvo não expõe quase nada).")
    return "\n".join(partes)


def _comando(dominio: str, outdir: str, ativo: bool) -> list:
    """Monta a linha de comando do bbot. Passivo por padrão (-rf passive trava
    tudo em módulos que não tocam o alvo); ativo abre os módulos safe de contato."""
    flags = ["subdomain-enum", "email-enum", "cloud-enum"]
    cmd = [BBOT, "-t", dominio, "-f"] + flags
    if not ativo:
        cmd += ["-rf", "passive"]   # SÓ passivo: não conecta no alvo
    else:
        cmd += ["-rf", "safe"]      # ativo, mas só o que não é intrusivo/loud
    cmd += ["--json", "--no-color", "-y", "-o", outdir, "-n", "dervs_lead"]
    return cmd


def enriquecer(dominio: str, ativo: bool = False, timeout: int = 240) -> dict:
    """Roda o bbot no domínio e devolve {codigo, saida, tipo, lead, bruto}.

    'saida' é o resumo curto (fala). 'bruto' é o caminho do NDJSON completo
    (para quem quiser o detalhe). Nunca levanta: erro vira resultado."""
    import subprocess
    dominio = (dominio or "").strip().rstrip(".").lower()
    if not dominio_valido(dominio):
        return {"codigo": 1, "tipo": "erro",
                "saida": f"'{dominio}' não parece um domínio válido — confirme o "
                         f"endereço (ex.: empresa.com.br)."}
    outdir = tempfile.mkdtemp(prefix="grim-lead-")
    try:
        proc = subprocess.run(_comando(dominio, outdir, ativo),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"codigo": 1, "tipo": "erro",
                "saida": f"o recon de {dominio} passou de {timeout}s e foi "
                         f"interrompido. Domínio grande pede mais tempo."}
    except Exception as e:
        return {"codigo": 1, "tipo": "erro",
                "saida": f"não consegui rodar o recon: {e}"}

    # eventos vêm no stdout (--json) e também no arquivo output.ndjson
    linhas = (proc.stdout or "").splitlines()
    arq = os.path.join(outdir, "output.ndjson")
    if not linhas and os.path.exists(arq):
        try:
            linhas = open(arq, encoding="utf-8").read().splitlines()
        except OSError:
            pass
    lead = agregar_eventos(linhas)
    return {"codigo": 0, "tipo": "enriquecimento",
            "saida": resumir(lead, dominio, ativo),
            "lead": lead, "bruto": arq if os.path.exists(arq) else ""}


# Python isolado, caso um dia o bbot só exista numa venv própria. Hoje o CLI
# está no PATH, então rodar_para_app chama enriquecer direto (mesmo processo).
def rodar_para_app(dominio: str, ativo: bool = False) -> dict:
    """Ponto de entrada do app. Devolve {codigo,saida,tipo} enxuto (a tela e o
    cérebro não precisam do 'lead'/'bruto', que ficariam pesados no contexto)."""
    r = enriquecer(dominio, ativo=ativo)
    return {"codigo": r["codigo"], "saida": r["saida"], "tipo": r["tipo"]}


if __name__ == "__main__":
    import sys
    argv = sys.argv[1:]
    ativo = "--ativo" in argv
    argv = [a for a in argv if a != "--ativo"]
    dom = argv[0] if argv else "example.com"
    print(json.dumps(rodar_para_app(dom, ativo), ensure_ascii=False, indent=2))
