"""Sobras que podem ir para a quarentena: arquivos com mais de 7 dias em pastas
de temporários. Só mede e lista — quem propõe e move é o motor de aprovação."""
import ctypes
import os
import time

from dervs_central.base import resultado

IDADE_MINIMA_DIAS = 7
LIMITE_ENTRADAS = 100_000
LIMITE_CANDIDATOS = 50
PRAZO_POR_PASTA_S = 20  # pasta enorme vira "medida em parte", nunca trava a análise


class _InfoLixeira(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("bytes", ctypes.c_int64), ("itens", ctypes.c_int64)]


def ler_lixeira() -> tuple:
    """(itens, bytes) da Lixeira de todas as unidades, pela API do Windows."""
    info = _InfoLixeira(ctypes.sizeof(_InfoLixeira))
    if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) != 0:
        raise OSError("a Lixeira não respondeu")
    return int(info.itens), int(info.bytes)


def _pastas_padrao(ambiente=None) -> list:
    env = ambiente if ambiente is not None else os.environ
    local = env.get("LOCALAPPDATA", "")
    windir = env.get("SystemRoot", r"C:\Windows")
    return [("Temporários do usuário", env.get("TEMP", "")),
            ("Temporários do Windows", os.path.join(windir, "Temp")),
            ("Miniaturas", os.path.join(local, "Microsoft", "Windows", "Explorer") if local else ""),
            ("Instalação antiga do Windows", os.path.join(os.path.splitdrive(windir)[0] + os.sep, "Windows.old"))]


def _travado(caminho: str) -> bool:
    try:
        with open(caminho, "rb"):
            return False
    except OSError:
        return True


def _varrer(pasta: str, so_miniaturas: bool, corte: float, agora: float):
    total = velhos_bytes = arquivos = entradas = 0
    candidatos, truncado = [], False
    limite_tempo = time.monotonic() + PRAZO_POR_PASTA_S
    pilha = [pasta]
    while pilha and not truncado:
        atual = pilha.pop()
        try:
            with os.scandir(atual) as it:
                for e in it:
                    entradas += 1
                    if entradas > LIMITE_ENTRADAS or (entradas % 500 == 0 and time.monotonic() > limite_tempo):
                        truncado = True
                        break
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            if not so_miniaturas:
                                pilha.append(e.path)
                            continue
                        if so_miniaturas and not e.name.casefold().startswith("thumbcache_"):
                            continue
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    total += st.st_size
                    arquivos += 1
                    if st.st_mtime < corte:
                        velhos_bytes += st.st_size
                        candidatos.append({"caminho": e.path, "tamanho_bytes": st.st_size,
                                           "idade_dias": int((agora - st.st_mtime) // 86400)})
        except OSError:
            continue
    candidatos.sort(key=lambda c: -c["tamanho_bytes"])
    # "em uso agora" só se confere nos finalistas: abrir 20 mil arquivos custa minutos.
    livres = [c for c in candidatos[:LIMITE_CANDIDATOS * 2] if not _travado(c["caminho"])]
    return total, velhos_bytes, arquivos, livres[:LIMITE_CANDIDATOS], truncado


def coletar(rodar=None, pastas=None, agora=None, ambiente=None, ler_lixeira_fn=None) -> dict:
    agora = agora if agora is not None else time.time()
    corte = agora - IDADE_MINIMA_DIAS * 86400
    itens, candidatos = [], []
    for nome, pasta in (pastas if pastas is not None else _pastas_padrao(ambiente)):
        if not pasta or not os.path.isdir(pasta):
            continue
        total, velhos, n, cand, trunc = _varrer(pasta, nome == "Miniaturas", corte, agora)
        itens.append({"nome": nome, "pasta": pasta, "tamanho_bytes": total, "arquivos": n,
                      "antigos_bytes": velhos, "truncado": trunc, "legivel": n > 0 or total == 0})
        candidatos.extend(dict(c, grupo=nome) for c in cand)
    try:
        n, tamanho = (ler_lixeira_fn or ler_lixeira)()
        itens.append({"nome": "Lixeira", "pasta": "", "tamanho_bytes": tamanho, "arquivos": n,
                      "antigos_bytes": 0, "truncado": False, "legivel": True})
    except (OSError, AttributeError):
        pass
    candidatos.sort(key=lambda c: -c["tamanho_bytes"])
    return resultado(itens, candidatos=candidatos[:LIMITE_CANDIDATOS])
