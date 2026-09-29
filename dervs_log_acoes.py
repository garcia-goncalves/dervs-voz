#!/usr/bin/env python3
"""DERVS — registro de ações sensíveis (onda C da central do PC).

O que é: um arquivo `%LOCALAPPDATA%\\dervs\\acoes.jsonl` onde cada linha conta
UMA coisa que o motor de aprovação fez — analisou, propôs, aprovou, recusou
(com o motivo), vai executar, executou, desfez, e alertas do próprio registro.
É o que o dono abre na aba "Registro" do painel (critério 7 do briefing).

Duas promessas, e é por elas que este arquivo existe em vez de um `print`:

1. **Mexida fica visível — até onde dá.** O arquivo só cresce (abre em modo
   de acréscimo), e cada linha guarda o hash da linha anterior e o seu próprio.
   Mudar, apagar ou trocar de ordem uma linha do meio quebra a corrente, e
   `verificar_cadeia()` diz em que linha. Dito com todas as letras: isso pega
   erro acidental e mexida desajeitada, NÃO sabotagem de quem recalcula todos
   os hashes (o método é público). Contra isso há uma segunda camada, só
   enquanto o DERVS está aberto: ele lembra o último (número, hash) que
   escreveu e, se na escrita seguinte o arquivo não termina onde ele deixou,
   grava um "alerta". Apagar as ÚLTIMAS linhas com o DERVS fechado continua
   invisível — isso só se pega com uma cópia de fora.
2. **Segredo nunca entra.** Tudo é cortado no tamanho e depois passa por
   `redigir` antes de ir para o disco: chaves (sk-..., sk_live_..., AIza...,
   ghp_..., AKIA..., blocos PEM), tokens, senha dentro de endereço, valor de
   variável de ambiente (`X=...`, `$env:X=...`), campo cujo nome parece
   segredo (senha, token, api_key...) e qualquer valor que esteja numa
   variável de ambiente de nome secreto deste processo.

Uma cauda estragada (queda de energia no meio de uma linha) não derruba o
registro: a próxima escrita pula o pedaço ilegível, grava um "alerta" e segue.
"""
import hashlib
import json
import os
import re
import threading
import time

EVENTOS = ("analisou", "propos", "aprovou", "recusou", "vai_executar", "executou",
           "desfez", "alerta")
LIMITE_LINHA = 8192
_LIMITE_TEXTO = 600
_LIMITE_REDIGIR = 4000
_INICIO = "0" * 64
_TROCA = "[SEGREDO REMOVIDO]"

# Valores que são segredo pela CARA, venham onde vierem.
_PADROES_SEGREDO = [
    re.compile(r"-----BEGIN [^\n-]*-----[\s\S]*?(?:-----END [^\n-]*-----|$)"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"),
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}"),
]
# Senha dentro de endereço: https://usuario:senha@servidor
_URL_COM_SENHA = re.compile(r"(?i)(?<![a-z0-9+.\-])([a-z][a-z0-9+.\-]*+://)[^\s/:@]+:[^\s/@]+@")
# Nome que denuncia segredo, em português e inglês.
_NOME_SECRETO = re.compile(r"(?i)senha|password|passwd|pwd|pass|token|secret|segredo|chave|"
                           r"api[_\-]?key|apikey|auth|credential|private[_\-]?key|key")
# `nome=valor` / `nome: valor`. O NOME é testado à parte, numa função: o
# padrão antigo embutia a lista de nomes entre dois `[\w.\-]*` e levava 21 s
# para 3000 caracteres (revisão de 29/09/2026).
# Só começa no INÍCIO de um nome (sem nada de nome antes) e sem voltar atrás:
# assim cada caractere é olhado uma vez.
_NOME_E_SINAL = re.compile(r"(?<![\w.\-])([\w.\-]++)(\s*[=:]\s*)")
_VALOR = re.compile(r"(['\"]?)(?!\[SEGREDO)[^\s'\"&;,]+\1")
# Linha de .env e atribuição de ambiente: X=valor, set X=valor, export X=valor.
_ATRIBUICAO_ENV = re.compile(
    r"(?m)^(\s*(?:export\s+|set\s+)?[A-Z_][A-Z0-9_]*\s*=\s*)(.+)$")
_ENV_POWERSHELL = re.compile(r"(?i)(\$env:[A-Za-z_]\w*\s*=\s*)(['\"]?)(?!\[SEGREDO)[^'\"\s;]+\2")

# Campos do próprio motor que carregam hash ou identificador público, não segredo.
_CAMPOS_PUBLICOS = {"impressao", "impressoes", "desfazer_id", "hash", "anterior"}


def _nome_secreto(nome: str) -> bool:
    return bool(_NOME_SECRETO.search(nome))


def _valores_secretos_do_ambiente():
    return [v for k, v in os.environ.items() if len(v or "") >= 8 and _nome_secreto(k)]


def _redigir_pares(texto: str) -> str:
    """`nome=valor` / `nome: valor`: some o valor quando o NOME é de segredo.
    O nome é testado à parte — o padrão antigo embutia a lista de nomes entre
    dois `[\\w.\\-]*` e levava 21 s para 3000 caracteres (revisão de
    29/09/2026). Um nome inocente não "come" o resto: em
    `https://x?token=abc`, o `https:` é pulado e o `token=` é achado."""
    pedacos, pos = [], 0
    for m in _NOME_E_SINAL.finditer(texto):
        if m.start() < pos or not _nome_secreto(m.group(1)):
            continue
        valor = _VALOR.match(texto, m.end())
        if valor is None:
            continue
        pedacos += [texto[pos:m.end()], _TROCA]
        pos = valor.end()
    pedacos.append(texto[pos:])
    return "".join(pedacos)


def _redigir_texto(texto: str) -> str:
    texto = texto[:_LIMITE_REDIGIR]
    for valor in _valores_secretos_do_ambiente():
        texto = texto.replace(valor, _TROCA)
    texto = _URL_COM_SENHA.sub(lambda m: m.group(1) + _TROCA + "@", texto)
    for padrao in _PADROES_SEGREDO:
        texto = padrao.sub(_TROCA, texto)
    texto = _ENV_POWERSHELL.sub(lambda m: m.group(1) + _TROCA, texto)
    texto = _redigir_pares(texto)
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
            if chave not in _CAMPOS_PUBLICOS and _nome_secreto(chave):
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
    if isinstance(valor, (list, tuple)):
        return [_encurtar(v, limite) for v in list(valor)[:50]]
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


def _linha_valida(bruta: bytes):
    try:
        linha = json.loads(bruta.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if (isinstance(linha, dict) and isinstance(linha.get("seq"), int)
            and isinstance(linha.get("hash"), str)):
        return linha
    return None


class LogAcoes:
    def __init__(self, arquivo: str | None = None, relogio=time.time):
        self.arquivo = arquivo or arquivo_padrao()
        self._relogio = relogio
        self._trava = threading.Lock()
        self._ultimo = None  # (seq, hash) que ESTE processo escreveu por último

    def _ultima(self):
        """(seq, hash, cauda_estragada) da última linha legível, lendo só o fim."""
        try:
            with open(self.arquivo, "rb") as f:
                f.seek(0, os.SEEK_END)
                tamanho = f.tell()
                f.seek(max(0, tamanho - 4 * LIMITE_LINHA))
                linhas = [l for l in f.read().splitlines() if l.strip()]
        except FileNotFoundError:
            return 0, _INICIO, False
        for n, bruta in enumerate(reversed(linhas)):
            linha = _linha_valida(bruta)
            if linha is not None:
                return linha["seq"], linha["hash"], n > 0
        return 0, _INICIO, bool(linhas)

    def _linha(self, seq, anterior, quando, evento, limpo) -> tuple[dict, str]:
        for limite in (_LIMITE_TEXTO, 120, 0):
            corpo = _encurtar(limpo, limite) if limite else {
                "cortado": True, "resumo": json.dumps(limpo, ensure_ascii=False)[:1000]}
            linha = {"seq": seq, "quando": quando, "evento": evento,
                     "dados": corpo, "anterior": anterior}
            linha["hash"] = hash_da_linha(linha)
            texto = json.dumps(linha, ensure_ascii=False, sort_keys=True)
            if len(texto.encode("utf-8")) <= LIMITE_LINHA:
                break
        return linha, texto

    def registrar(self, evento: str, dados: dict | None = None) -> dict:
        """Acrescenta uma linha. Erro de disco SOBE para quem chamou: o
        executor usa isso para não agir sem deixar rastro."""
        if evento not in EVENTOS:
            raise ValueError(f"evento desconhecido: {evento!r}")
        # Corta ANTES de redigir: o redator nunca vê texto gigante.
        limpo = redigir(_encurtar(dict(dados or {}), _LIMITE_TEXTO))
        with self._trava:
            os.makedirs(os.path.dirname(self.arquivo), exist_ok=True)
            seq, anterior, estragada = self._ultima()
            quando = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._relogio()))
            textos = []
            avisos = []
            if estragada:
                avisos.append("o fim do registro estava ilegível (linha cortada ou mexida) — "
                              "o trecho foi pulado")
            if self._ultimo is not None and (seq, anterior) != self._ultimo:
                avisos.append("o registro mudou por fora entre duas escritas do DERVS")
            if avisos:
                seq += 1
                alerta, texto = self._linha(seq, anterior, quando, "alerta",
                                            {"motivo": "; ".join(avisos)})
                textos.append(texto)
                anterior = alerta["hash"]
            linha, texto = self._linha(seq + 1, anterior, quando, evento, limpo)
            textos.append(texto)
            with open(self.arquivo, "a", encoding="utf-8", newline="\n") as f:
                if estragada:
                    f.write("\n")  # a linha cortada não gruda na próxima
                f.write("\n".join(textos) + "\n")
            self._ultimo = (linha["seq"], linha["hash"])
        return linha

    def ler(self) -> list[dict]:
        """As linhas legíveis, para a aba Registro e para o desfazer."""
        saida = []
        try:
            with open(self.arquivo, "rb") as f:
                for bruta in f:
                    linha = _linha_valida(bruta.strip())
                    if linha is not None:
                        saida.append(linha)
        except FileNotFoundError:
            pass
        return saida

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
