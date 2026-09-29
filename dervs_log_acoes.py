#!/usr/bin/env python3
"""DERVS — registro de ações sensíveis (onda C da central do PC).

O que é: um arquivo `%LOCALAPPDATA%\\dervs\\acoes.jsonl` onde cada linha conta
UMA coisa que o motor de aprovação fez — analisou, propôs, aprovou, recusou
(com o motivo), executou, desfez. É o que o dono abre na aba "Registro" do
painel (critério 7 do briefing).

Duas promessas, e é por elas que este arquivo existe em vez de um `print`:

1. **Adulteração fica visível.** O arquivo só cresce (abre em modo de
   acréscimo), e cada linha guarda o hash da linha anterior e o seu próprio.
   Mudar, apagar ou trocar de ordem qualquer linha do meio quebra a corrente,
   e `verificar_cadeia()` diz em que linha. Limite honesto: apagar as ÚLTIMAS
   linhas não quebra corrente nenhuma — isso só se pega comparando com uma
   cópia de fora.
2. **Segredo nunca entra.** Tudo passa por `redigir` antes de ir para o disco:
   chaves (sk-..., ghp_..., AKIA...), tokens, senha dentro de endereço, valor
   de variável de ambiente (`X=...`, `$env:X=...`), campo cujo nome parece
   segredo (senha, token, api_key...) e qualquer valor que esteja numa
   variável de ambiente de nome secreto deste processo.

Cada linha tem um teto de tamanho: um texto gigante vira resumo cortado, para
o arquivo não virar depósito de saída de comando.
"""
import hashlib
import json
import os
import re
import threading
import time

EVENTOS = ("analisou", "propos", "aprovou", "recusou", "executou", "desfez")
LIMITE_LINHA = 8192
_LIMITE_TEXTO = 600
_INICIO = "0" * 64
_TROCA = "[SEGREDO REMOVIDO]"

# Valores que são segredo pela CARA, venham onde vierem.
_PADROES_SEGREDO = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"),
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}"),
]
# Senha dentro de endereço: https://usuario:senha@servidor
_URL_COM_SENHA = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^\s/:@]+:[^\s/@]+@")
# Nome que denuncia segredo, em português e inglês.
_NOME_SECRETO = (r"(?:senha|password|passwd|pwd|pass|token|secret|segredo|chave|"
                 r"api[_\-]?key|apikey|auth|credential|private[_\-]?key|key)")
_CHAVE_SECRETA = re.compile(r"(?i)^[\w.\-]*" + _NOME_SECRETO + r"[\w.\-]*$")
# `nome=valor` / `nome: valor` com nome secreto, em linha de comando ou URL.
_PAR_SECRETO = re.compile(
    r"(?i)(\b[\w.\-]*" + _NOME_SECRETO + r"[\w.\-]*\s*[=:]\s*)(['\"]?)(?!\[SEGREDO)[^\s'\"&;,]+\2")
# Linha de .env e atribuição de ambiente: X=valor, set X=valor, export X=valor.
_ATRIBUICAO_ENV = re.compile(
    r"(?m)^(\s*(?:export\s+|set\s+)?[A-Z_][A-Z0-9_]*\s*=\s*)(.+)$")
_ENV_POWERSHELL = re.compile(r"(?i)(\$env:[A-Za-z_]\w*\s*=\s*)(['\"]?)(?!\[SEGREDO)[^'\"\s;]+\2")

# Campos do próprio motor que carregam hash público, não segredo.
_CAMPOS_PUBLICOS = {"impressao", "impressoes", "desfazer_id", "hash", "anterior"}


def _valores_secretos_do_ambiente():
    return [v for k, v in os.environ.items()
            if len(v or "") >= 8 and _CHAVE_SECRETA.match(k)]


def _redigir_texto(texto: str) -> str:
    for valor in _valores_secretos_do_ambiente():
        texto = texto.replace(valor, _TROCA)
    texto = _URL_COM_SENHA.sub(lambda m: m.group(1) + _TROCA + "@", texto)
    for padrao in _PADROES_SEGREDO:
        texto = padrao.sub(_TROCA, texto)
    texto = _ENV_POWERSHELL.sub(lambda m: m.group(1) + _TROCA, texto)
    texto = _PAR_SECRETO.sub(lambda m: m.group(1) + _TROCA, texto)
    # Valor de variável: só fica o que for número puro (porta, contagem) —
    # assim `PORTA=8080` continua legível e `OPENAI_API_KEY=...` não.
    texto = _ATRIBUICAO_ENV.sub(
        lambda m: m.group(0) if re.fullmatch(r"\s*\d+\s*", m.group(2))
        else m.group(1) + _TROCA, texto)
    return texto


def redigir(valor, _profundidade=0):
    """Devolve uma cópia de `valor` sem segredo nenhum. Dicionário, lista e
    texto são percorridos; campo de nome secreto perde o valor inteiro."""
    if _profundidade > 8:
        return "[FUNDO DEMAIS]"
    if isinstance(valor, dict):
        saida = {}
        for k, v in valor.items():
            chave = str(k)
            if chave not in _CAMPOS_PUBLICOS and _CHAVE_SECRETA.match(chave):
                saida[chave] = _TROCA
            else:
                saida[chave] = redigir(v, _profundidade + 1)
        return saida
    if isinstance(valor, (list, tuple)):
        return [redigir(v, _profundidade + 1) for v in valor]
    if isinstance(valor, str):
        return _redigir_texto(valor)
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    return _redigir_texto(str(valor))


def _encurtar(valor, limite):
    if isinstance(valor, dict):
        return {k: _encurtar(v, limite) for k, v in list(valor.items())[:50]}
    if isinstance(valor, list):
        return [_encurtar(v, limite) for v in valor[:50]]
    if isinstance(valor, str) and len(valor) > limite:
        return valor[:limite] + f"… [cortado, {len(valor)} caracteres]"
    return valor


def hash_da_linha(linha: dict) -> str:
    corpo = {k: v for k, v in linha.items() if k != "hash"}
    texto = json.dumps(corpo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def arquivo_padrao() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    return os.path.join(base, "dervs", "acoes.jsonl")


class LogAcoes:
    def __init__(self, arquivo: str | None = None, relogio=time.time):
        self.arquivo = arquivo or arquivo_padrao()
        self._relogio = relogio
        self._trava = threading.Lock()

    def _ultima(self):
        """(seq, hash) da última linha, lendo só o fim do arquivo."""
        try:
            with open(self.arquivo, "rb") as f:
                f.seek(0, os.SEEK_END)
                tamanho = f.tell()
                f.seek(max(0, tamanho - 4 * LIMITE_LINHA))
                linhas = [l for l in f.read().splitlines() if l.strip()]
        except FileNotFoundError:
            return 0, _INICIO
        if not linhas:
            return 0, _INICIO
        ultima = json.loads(linhas[-1].decode("utf-8"))
        return int(ultima["seq"]), ultima["hash"]

    def registrar(self, evento: str, dados: dict | None = None) -> dict:
        if evento not in EVENTOS:
            raise ValueError(f"evento desconhecido: {evento!r}")
        limpo = redigir(dict(dados or {}))
        with self._trava:
            os.makedirs(os.path.dirname(self.arquivo), exist_ok=True)
            seq, anterior = self._ultima()
            quando = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._relogio()))
            for limite in (_LIMITE_TEXTO, 120, 0):
                corpo = _encurtar(limpo, limite) if limite else {
                    "cortado": True,
                    "resumo": json.dumps(limpo, ensure_ascii=False)[:1000]}
                linha = {"seq": seq + 1, "quando": quando, "evento": evento,
                         "dados": corpo, "anterior": anterior}
                linha["hash"] = hash_da_linha(linha)
                texto = json.dumps(linha, ensure_ascii=False, sort_keys=True)
                if len(texto.encode("utf-8")) <= LIMITE_LINHA:
                    break
            with open(self.arquivo, "a", encoding="utf-8", newline="\n") as f:
                f.write(texto + "\n")
        return linha

    def verificar_cadeia(self) -> tuple[bool, str]:
        """(True, "") se nenhuma linha foi mexida; senão (False, onde quebrou)."""
        anterior, seq = _INICIO, 0
        try:
            f = open(self.arquivo, encoding="utf-8")
        except FileNotFoundError:
            return True, ""
        with f:
            for numero, texto in enumerate(f, start=1):
                if not texto.strip():
                    return False, f"linha {numero} vazia no meio do registro"
                try:
                    linha = json.loads(texto)
                except ValueError:
                    return False, f"linha {numero} ilegível"
                if not isinstance(linha, dict):
                    return False, f"linha {numero} ilegível"
                if linha.get("seq") != seq + 1:
                    return False, f"linha {numero} fora de ordem (falta ou sobra linha)"
                if linha.get("anterior") != anterior:
                    return False, f"linha {numero} não continua a anterior"
                if linha.get("hash") != hash_da_linha(linha):
                    return False, f"linha {numero} foi alterada"
                anterior, seq = linha["hash"], linha["seq"]
        return True, ""
