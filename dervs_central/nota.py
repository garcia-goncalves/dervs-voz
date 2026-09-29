"""Nota de saúde 0–100: começa em 100 e desconta por regra, com peso e motivo.

Determinística e sem modelo — a tela mostra a nota E os descontos, e o dono
pode conferir cada um. Coletor que falhou não desconta (não sabemos), mas
aparece em `sem_leitura` para a tela avisar que a nota está incompleta.

`ultima` é o dicionário que `dervs_central.central.analisar` grava:
`{"coletores": {"espaco": {...}, "saude": {...}, ...}}`.
"""

CRITICOS = ("critical", "crítico", "critico")
# Sem leitura de saúde não é doença: USB, adaptador e driver sem suporte devolvem "Unknown".
SAUDE_SEM_PROBLEMA = ("Healthy", "Desconhecida", "Unknown", "")
DIAS_SEGURANCA = 14
LIMITE_LIVRE_PCT = 10


def _coletor(ultima: dict, nome: str) -> dict:
    return (ultima.get("coletores") or {}).get(nome) or {}


def _itens(ultima: dict, nome: str) -> list:
    c = _coletor(ultima, nome)
    return (c.get("itens") or []) if c.get("ok") else []


def _desconto(codigo: str, pontos: int, motivo: str, frase: str) -> dict:
    return {"codigo": codigo, "pontos": pontos, "motivo": motivo, "frase": frase}


def descontos(ultima: dict) -> list:
    d = []
    cheios = [v for v in _itens(ultima, "espaco") if v.get("pct_livre", 100) < LIMITE_LIVRE_PCT]
    if cheios:
        v = min(cheios, key=lambda x: x["pct_livre"])
        d.append(_desconto("disco_cheio", 20, f"disco {v['volume']} com menos de {LIMITE_LIVRE_PCT}% livre",
                           f"O disco {v['volume']} está quase cheio: só {v['pct_livre']:.0f}% livre."))
    doentes = [x for x in _itens(ultima, "saude") if x.get("saude") not in SAUDE_SEM_PROBLEMA]
    doentes += [v for v in _itens(ultima, "espaco") if v.get("saude") not in SAUDE_SEM_PROBLEMA]
    if doentes:
        nome = doentes[0].get("nome") or doentes[0].get("volume") or "um disco"
        d.append(_desconto("disco_doente", 40, f"disco com saúde diferente de Healthy ({nome})",
                           f"O disco {nome} reportou problema de saúde: faça backup agora."))
    defender = _coletor(ultima, "defender")
    if defender.get("ok") and not defender.get("antivirus_de_terceiros"):
        s = (defender.get("itens") or [{}])[0]
        if s and (not s.get("antivirus") or not s.get("tempo_real")):
            d.append(_desconto("defender_desligado", 30, "Defender ou proteção em tempo real desligados",
                               "A proteção contra vírus do Windows está desligada."))
    desligados = [p["perfil"] for p in _itens(ultima, "firewall") if not p.get("ligado")]
    if desligados:
        d.append(_desconto("firewall_desligado", 20, f"firewall desligado em {', '.join(desligados)}",
                           "O firewall (a barreira contra acesso pela rede) está desligado."))
    atrasadas = [u for u in _itens(ultima, "atualizacoes")
                 if u.get("seguranca") and (u.get("dias_pendente") or 0) > DIAS_SEGURANCA]
    if atrasadas:
        d.append(_desconto("seguranca_pendente", 15,
                           f"atualização de segurança pendente há mais de {DIAS_SEGURANCA} dias",
                           f"Há {len(atrasadas)} atualização(ões) de segurança do Windows esperando "
                           f"há mais de {DIAS_SEGURANCA} dias."))
    if _coletor(ultima, "atualizacoes").get("reinicio_pendente"):
        d.append(_desconto("reinicio_pendente", 5, "reinício pendente",
                           "O Windows está esperando um reinício para terminar de atualizar."))
    fontes = [e for e in _itens(ultima, "eventos")
              if str(e.get("nivel", "")).casefold() in CRITICOS and e.get("quantidade", 0) >= 2]
    if fontes:
        d.append(_desconto("erro_critico", min(20, 10 * len(fontes)),
                           f"erro crítico repetido em {len(fontes)} fonte(s) na semana",
                           f"O Windows registrou erros críticos repetidos nesta semana "
                           f"({fontes[0]['fonte']}, {fontes[0]['quantidade']} vezes)."))
    drivers = _itens(ultima, "drivers")
    if drivers:
        d.append(_desconto("driver_com_erro", 10, f"{len(drivers)} dispositivo(s) com driver em erro",
                           f"Há {len(drivers)} dispositivo(s) com defeito no Gerenciador de Dispositivos."))
    sem_push = [r for r in _itens(ultima, "repositorios") if r.get("ahead", 0) > 0]
    if sem_push:
        d.append(_desconto("commit_sem_push", min(10, 5 * len(sem_push)),
                           f"{len(sem_push)} repositório(s) com commit sem push",
                           f"{len(sem_push)} projeto(s) têm trabalho salvo só neste computador, sem cópia no GitHub."))
    return d


def calcular(ultima: dict) -> dict:
    ultima = ultima or {}
    lista = descontos(ultima)
    nota = max(0, 100 - sum(x["pontos"] for x in lista))
    sem_leitura = sorted(n for n, c in (ultima.get("coletores") or {}).items() if not c.get("ok"))
    return {"nota": nota, "descontos": lista, "sem_leitura": sem_leitura}
