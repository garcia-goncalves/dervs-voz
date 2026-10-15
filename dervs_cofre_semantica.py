#!/usr/bin/env python3
"""DERVS — busca por SIGNIFICADO no cofre ("dentista" acha "consulta odontológica").

OPCIONAL e local. Depende de `fastembed` (modelo ONNX que roda na CPU) e `numpy`, que NÃO estão
em `requirements.txt` (ver `requirements-semantica.txt`). Sem o pacote, sem o modelo ou sem rede
na primeira vez, o cofre funciona exatamente como antes: nada aqui levanta erro para quem chama.

Como funciona: cada nota vira um vetor de 384 números (float32, guardado em
`vetores.sqlite` na pasta do índice, fora do cofre — ver `dervs_cofre.pasta_indice_padrao`); a pergunta vira outro vetor; as notas mais parecidas (produto
escalar, numpy, força bruta) se juntam ao resultado da busca por palavras (FTS5) pela fusão RRF.

Privacidade: tudo roda no computador. A única coisa que sai é o download do modelo (~240 MB) na
primeira vez, e só se o dono ligou `cofre_semantica`. A marca "privado" acompanha cada vetor;
quem decide o que sai do PC continua sendo `Cofre.contexto_para_nuvem` e a fala por voz.
"""
import importlib.util
import os
import sqlite3
import threading
import time
from pathlib import Path

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIM = 384
LIMIAR = 0.30               # semelhança mínima (cosseno) para uma nota contar como "parecida"
MAX_CHARS_NOTA = 1500       # o modelo só lê ~128 palavras; mais que isso é custo sem ganho
K_RRF = 60                  # constante clássica da fusão por posição (reciprocal rank fusion)
LOTE = 16


def pacote_instalado() -> bool:
    try:
        return all(importlib.util.find_spec(m) is not None for m in ("fastembed", "numpy"))
    except (ImportError, ValueError):
        return False


def pasta_modelos() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / "DERVS" / "modelos") if base else (Path.home() / ".dervs" / "modelos")


class EmbedderFastembed:
    """Carrega o modelo só quando precisa (preguiçoso) e o solta quando ocioso."""

    def __init__(self, modelo=MODELO, pasta=None, baixar=False):
        self.modelo = modelo
        self.pasta = Path(pasta) if pasta else pasta_modelos()
        self.baixar = bool(baixar)          # só quem ligou a opção deixa o download acontecer
        self._m = None
        self._trava = threading.Lock()
        self.ultimo_uso = 0.0
        self.erro = ""

    def _em_cache(self) -> bool:
        try:
            return any(self.pasta.glob("models--*/snapshots/*/*.onnx"))
        except OSError:
            return False

    def pronto(self) -> bool:
        """Barato e honesto: pacote instalado E (modelo na memória, ou em disco, ou download liberado)."""
        return pacote_instalado() and (self._m is not None or self._em_cache() or self.baixar)

    def carregado(self) -> bool:
        return self._m is not None

    def _carregar(self):
        with self._trava:
            if self._m is None:
                from fastembed import TextEmbedding
                self.pasta.mkdir(parents=True, exist_ok=True)
                self._m = TextEmbedding(self.modelo, cache_dir=str(self.pasta),
                                        local_files_only=not self.baixar and self._em_cache())
        return self._m

    def aquecer(self) -> bool:
        try:
            self._carregar()
            return True
        except Exception as erro:               # sem rede, disco cheio, pacote quebrado: degrada
            self.erro = type(erro).__name__
            return False

    def embutir(self, textos):
        import numpy as np
        m = self._carregar()
        self.ultimo_uso = time.monotonic()
        v = np.array(list(m.embed(list(textos))), dtype=np.float32)
        norma = np.linalg.norm(v, axis=1, keepdims=True)
        norma[norma == 0] = 1.0
        return v / norma

    def liberar(self):
        with self._trava:
            self._m = None


class IndiceVetorial:
    """`vetores.sqlite`: um vetor (BLOB float32) por nota, com o mesmo mtime+tamanho do índice de texto."""

    def __init__(self, db: Path):
        self.db = Path(db)

    def _con(self):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db, timeout=10)
        con.execute("CREATE TABLE IF NOT EXISTS vetores(caminho TEXT PRIMARY KEY, mtime INTEGER, "
                    "tamanho INTEGER, privado INTEGER, modelo TEXT, dim INTEGER, vec BLOB)")
        return con

    def estado(self, modelo) -> dict:
        """{caminho: (mtime, tamanho)} dos vetores válidos para este modelo."""
        con = self._con()
        try:
            return {c: (m, t) for c, m, t in con.execute(
                "SELECT caminho,mtime,tamanho FROM vetores WHERE modelo=?", (modelo,))}
        finally:
            con.close()

    def estado_todos(self) -> list:
        """Todos os caminhos com vetor, de qualquer modelo (para esquecer os de nota apagada)."""
        con = self._con()
        try:
            return [c for (c,) in con.execute("SELECT caminho FROM vetores")]
        finally:
            con.close()

    def gravar(self, linhas, modelo):
        """linhas: [(caminho, mtime, tamanho, privado, vetor_np)]"""
        con = self._con()
        try:
            con.executemany(
                "INSERT OR REPLACE INTO vetores VALUES(?,?,?,?,?,?,?)",
                [(c, m, t, int(p), modelo, int(v.shape[0]), v.astype("float32").tobytes())
                 for c, m, t, p, v in linhas])
            con.commit()
        finally:
            con.close()

    def apagar(self, caminhos):
        if not caminhos:
            return
        con = self._con()
        try:
            con.executemany("DELETE FROM vetores WHERE caminho=?", [(c,) for c in caminhos])
            con.commit()
        finally:
            con.close()

    def carregar(self, modelo):
        """(caminhos, matriz[N, dim]) de tudo; vazio se não há nada."""
        import numpy as np
        con = self._con()
        try:
            linhas = con.execute("SELECT caminho, dim, vec FROM vetores WHERE modelo=?", (modelo,)).fetchall()
        finally:
            con.close()
        if not linhas:
            return [], None
        dim = linhas[0][1]
        linhas = [l for l in linhas if l[1] == dim and len(l[2]) == dim * 4]
        matriz = np.frombuffer(b"".join(l[2] for l in linhas), dtype=np.float32).reshape(len(linhas), dim)
        return [l[0] for l in linhas], matriz


def fundir_rrf(*rankings, k=K_RRF) -> list:
    """Fusão por posição: cada lista é uma sequência de chaves, da melhor para a pior. Devolve as
    chaves ordenadas pela soma de 1/(k+posição); empate fica com quem apareceu primeiro."""
    pontos, ordem = {}, {}
    for r in rankings:
        for pos, chave in enumerate(r, start=1):
            pontos[chave] = pontos.get(chave, 0.0) + 1.0 / (k + pos)
            ordem.setdefault(chave, len(ordem))
    return sorted(pontos, key=lambda c: (-pontos[c], ordem[c]))
