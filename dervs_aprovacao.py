#!/usr/bin/env python3
"""DERVS — motor de aprovação (onda C da central do PC).

A exigência do dono, palavra por palavra: "Não pode apagar nada sem antes
analisar tudo profundamente e me dizer o que é cada coisa que quer apagar.
Sempre com minha aprovação." Este arquivo é o "analisar" e o "sempre com
minha aprovação". Quem de fato mexe no disco é `dervs_executor_seguro.py`, e
ele só mexe com um registro emitido AQUI.

O ciclo:
  1. `analisar(itens)` — o Claude ou um coletor propõe; o motor confere cada
     item no disco (caminho real, tipo, tamanho, data, impressão digital) e
     monta o RELATÓRIO item a item, com o texto leigo de "o que é", "por que é
     seguro", "o que muda" e "como desfazer". Item protegido, sem explicação ou
     de ação desconhecida é recusado já na criação, com o motivo.
  2. `abrir_cartao(relatorio)` — a senha de uso da tela: vai só para o painel,
     nunca para o Claude. Quem não viu o cartão não consegue aprovar.
  3. `aprovar(relatorio, ids, origem, cartao)` — só vale `origem="clique"`
     (voz, Claude, API: recusado), só com a lista EXPLÍCITA de itens que o dono
     marcou (não existe "aprovar tudo"), risco alto só com dupla confirmação,
     e no máximo 3 itens de pasta pessoal por vez. O registro vence em 15
     minutos, cada item vale uma vez só, e fica amarrado ao relatório e à
     impressão digital de cada item.
  4. `consumir_aprovacao(...)` — usado pelo executor: confere e queima o item
     de uma vez, sob trava.

Os registros de aprovação moram SÓ na memória deste processo, de propósito:
um arquivo em disco poderia ser forjado por quem escreve em disco. O relatório
também é gravado em `%LOCALAPPDATA%\\dervs\\relatorios\\<id>.json`, mas só para a
tela e para auditoria — o motor nunca o lê de volta como autoridade.

Tudo que acontece vai para o registro encadeado (`dervs_log_acoes.py`).
"""
import copy
import hashlib
import json
import os
import secrets
import threading
import time

import dervs_caminhos_protegidos as cp
from dervs_log_acoes import LogAcoes

VALIDADE_S = 15 * 60
LIMITE_PESSOAIS_POR_VEZ = 3
LIMITE_ITENS = 500
LIMITE_TEXTO = 2000
LIMITE_ENTRADAS_PASTA = 5000
_HASH_INTEIRO_ATE = 4 * 1024 * 1024
_AMOSTRA = 64 * 1024

ACOES_DE_ARQUIVO = ("quarentena", "lixeira")
ACOES_DE_SISTEMA = ("desinstalar", "desativar_inicializacao", "atualizar", "instalar",
                    "alterar_servico", "alterar_registro", "alterar_firewall", "alterar_config")
RISCOS = ("baixo", "medio", "alto")

_O_QUE_MUDA_SISTEMA = {
    "desinstalar": "Remove o programa do computador.",
    "desativar_inicializacao": "O programa deixa de abrir sozinho quando o Windows liga.",
    "atualizar": "Troca o programa pela versão mais nova.",
    "instalar": "Instala um programa novo no computador.",
    "alterar_servico": "Muda como um serviço do Windows funciona (ligado, desligado, automático).",
    "alterar_registro": "Muda uma configuração interna do Windows (o registro).",
    "alterar_firewall": "Muda uma regra do firewall — o que pode entrar e sair pela rede.",
    "alterar_config": "Muda uma configuração do sistema.",
}

_EXTENSOES = [
    ((".tmp", ".temp"), "arquivo temporário — sobra que um programa cria enquanto trabalha "
                        "e costuma esquecer de apagar"),
    ((".crdownload", ".part", ".partial"), "download que não terminou"),
    ((".log",), "registro de atividade de um programa (um diário técnico)"),
    ((".dmp", ".mdmp", ".hdmp"), "cópia da memória gravada quando um programa travou "
                                 "(serve para diagnóstico)"),
    ((".old", ".bak", ".backup"), "cópia de segurança antiga de um arquivo"),
    ((".msi", ".msp", ".msix"), "instalador de programa"),
    ((".exe",), "programa (um arquivo que executa)"),
    ((".dll", ".sys"), "peça de programa ou do Windows (biblioteca que outro programa usa)"),
    ((".zip", ".7z", ".rar", ".tar", ".gz"), "arquivo compactado (vários arquivos num só)"),
    ((".iso", ".img"), "imagem de disco (cópia de um CD/DVD ou de um instalador grande)"),
    ((".cab",), "pacote de instalação do Windows"),
    ((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".txt", ".rtf"),
     "documento"),
    ((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".webp"), "imagem ou foto"),
    ((".mp4", ".mkv", ".avi", ".mov", ".wmv"), "vídeo"),
    ((".mp3", ".wav", ".m4a", ".flac", ".ogg"), "áudio"),
]


class Recusado(Exception):
    """Item que não pode entrar no relatório; a mensagem é o motivo."""


# ------------------------------------------------------------ impressão digital

def _digest_arquivo(caminho: str, st) -> str:
    h = hashlib.sha256(f"arquivo|{st.st_size}|{st.st_mtime_ns}|".encode())
    with open(caminho, "rb") as f:
        if st.st_size <= _HASH_INTEIRO_ATE:
            for bloco in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloco)
        else:
            for pos in (0, st.st_size // 2, st.st_size - _AMOSTRA):
                f.seek(pos)
                h.update(f.read(_AMOSTRA))
    return h.hexdigest()


def conteudo_de(caminho: str) -> dict:
    """Tipo, tamanho, data e resumo (hash) do conteúdo — o que prova que é a
    MESMA coisa que o dono viu. Arquivo: tamanho + data + hash (inteiro até
    4 MB, amostrado acima). Pasta: nome, tipo, tamanho e data de cada item lá
    dentro. Não segue atalho; atalho, dispositivo ou pasta grande demais =
    `Recusado`."""
    st = os.lstat(caminho)
    if cp.eh_link(caminho):
        raise Recusado("é uma junção ou atalho simbólico")
    if os.path.isfile(caminho) and not os.path.isdir(caminho):
        return {"tipo": "arquivo", "tamanho": st.st_size, "mtime_ns": st.st_mtime_ns,
                "digest": _digest_arquivo(caminho, st), "arquivos": 1}
    if not os.path.isdir(caminho):
        raise Recusado("não é arquivo nem pasta comum")
    h = hashlib.sha256(b"pasta|")
    total, arquivos, linhas = 0, 0, []
    for raiz, pastas, nomes in os.walk(caminho, followlinks=False, onerror=_falha_ao_ler):
        pastas.sort()
        for nome in sorted(pastas) + sorted(nomes):
            completo = os.path.join(raiz, nome)
            s = os.lstat(completo)
            if cp.eh_link(completo):
                raise Recusado("tem uma junção ou atalho simbólico dentro")
            eh_pasta = nome in pastas
            linhas.append(f"{os.path.relpath(completo, caminho)}|{'p' if eh_pasta else 'a'}|"
                          f"{0 if eh_pasta else s.st_size}|{0 if eh_pasta else s.st_mtime_ns}")
            if not eh_pasta:
                total += s.st_size
                arquivos += 1
            if len(linhas) > LIMITE_ENTRADAS_PASTA:
                raise Recusado(f"pasta grande demais para analisar item a item "
                               f"(mais de {LIMITE_ENTRADAS_PASTA} itens)")
    for linha in linhas:
        h.update(linha.encode("utf-8") + b"\n")
    return {"tipo": "pasta", "tamanho": total, "mtime_ns": st.st_mtime_ns,
            "digest": h.hexdigest(), "arquivos": arquivos, "subpastas": len(linhas) - arquivos}


def _falha_ao_ler(erro):
    raise Recusado("tem uma parte que não deu para ler")


def impressao_de(caminho_real: str, digest: str) -> str:
    chave = os.path.normcase(caminho_real)
    return hashlib.sha256(f"{chave}|{digest}".encode("utf-8")).hexdigest()


def impressao_de_sistema(acao: str, alvo: str, versao: str) -> str:
    return hashlib.sha256(f"{acao}|{alvo}|{versao}".encode("utf-8")).hexdigest()


def _hash_do_relatorio(itens) -> str:
    texto = json.dumps(itens, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ------------------------------------------------------------ texto leigo

def _o_que_e(caminho_real: str, info: dict, ambiente) -> str:
    partes = []
    if info["tipo"] == "pasta":
        partes.append(f"Pasta com {info['arquivos']} arquivo(s) e {info['subpastas']} subpasta(s).")
    else:
        ext = os.path.splitext(caminho_real)[1].casefold()
        tipo = next((t for exts, t in _EXTENSOES if ext in exts), None)
        partes.append(f"É um {tipo}." if tipo else
                      f"Arquivo do tipo \"{ext or 'sem extensão'}\" — o DERVS não reconhece "
                      f"esse tipo sozinho.")
    pedacos = os.path.normcase(caminho_real).split("\\")
    if "temp" in pedacos or "tmp" in pedacos:
        partes.append("Fica numa pasta de temporários, onde os programas deixam sobras.")
    elif "downloads" in pedacos:
        partes.append("Fica em Downloads: é algo que foi baixado da internet.")
    elif cp.dentro_de_pasta_pessoal(caminho_real, ambiente):
        partes.append("Fica numa pasta pessoal sua — confira com atenção.")
    elif any("cache" in p for p in pedacos):
        partes.append("Fica numa pasta de cache (cópias que um programa guarda para "
                      "abrir mais rápido e refaz sozinho).")
    return " ".join(partes)


def _texto(valor, campo: str, obrigatorio: bool, minimo: int = 10) -> str:
    if valor is None and not obrigatorio:
        return ""
    if not isinstance(valor, str):
        raise Recusado(f"o campo '{campo}' veio num formato que não é texto")
    valor = "".join(c for c in valor if c.isprintable() or c == "\n").strip()
    if obrigatorio and len(valor) < minimo:
        raise Recusado(f"falta explicar {campo.replace('_', ' ')} ({campo})")
    return valor[:LIMITE_TEXTO]


def _risco_max(*riscos) -> str:
    return max(riscos, key=RISCOS.index)


# ------------------------------------------------------------ o motor

class Motor:
    def __init__(self, pasta: str | None = None, *, arquivo_extras: str | None = None,
                 ambiente: dict | None = None, relogio=time.time):
        self.ambiente = ambiente
        local = cp._env(ambiente, "LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
        pasta = pasta or os.path.join(local, "dervs")
        os.makedirs(pasta, exist_ok=True)
        self.pasta = cp.normalizar(os.path.abspath(pasta)) or os.path.abspath(pasta)
        self.arquivo_extras = arquivo_extras or cp.arquivo_extras(ambiente)
        try:
            cp.garantir_arquivo_extras(self.arquivo_extras)
        except OSError:
            pass  # sem o modelo, carregar_extras devolve lista vazia; nada afrouxa
        self.relogio = relogio
        self.log = LogAcoes(os.path.join(self.pasta, "acoes.jsonl"), relogio=relogio)
        self._trava = threading.RLock()
        self._relatorios = {}   # id -> {"dados": relatório, "hash": str}
        self._cartoes = {}      # relatorio_id -> senha do cartão
        self._registros = {}    # registro_id -> registro (com a senha de uso)
        self._aprovados = set()  # (relatorio_id, item_id) já aprovados uma vez

    # --------------------------------------------------- caminhos protegidos
    def checar_protegido(self, caminho, em_massa: bool = False) -> tuple[bool, str]:
        """A lista padrão + a do dono + a própria pasta do DERVS (onde moram
        a quarentena e o registro)."""
        try:
            extras = cp.carregar_extras(self.arquivo_extras)
        except ValueError as erro:
            return True, f"{erro} — nada se apaga até o arquivo ser consertado"
        return cp.esta_protegido(caminho, em_massa=em_massa, extras=extras + [self.pasta],
                                 ambiente=self.ambiente)

    def pessoal(self, caminho_real: str) -> bool:
        return cp.dentro_de_pasta_pessoal(caminho_real, self.ambiente)

    def recusar(self, etapa: str, motivo: str, **dados) -> dict:
        self.log.registrar("recusou", dict(dados, etapa=etapa, motivo=motivo))
        return {"ok": False, "motivo": motivo}

    # --------------------------------------------------- 1. analisar
    def _item_de_arquivo(self, proposta: dict, acao: str) -> dict:
        alvo = proposta.get("alvo")
        real = cp.normalizar(alvo)
        if real is None:
            raise Recusado("caminho inválido ou disfarçado")
        protegido, motivo = self.checar_protegido(alvo)
        if protegido:
            raise Recusado(f"caminho protegido: {motivo}")
        if not os.path.lexists(real):
            raise Recusado("o item não existe")
        info = conteudo_de(real)
        if info["tipo"] == "pasta":
            problema = cp.problema_dentro(real, LIMITE_ENTRADAS_PASTA)
            if problema:
                raise Recusado(problema)
            if self.pessoal(real):
                protegido, motivo = self.checar_protegido(alvo, em_massa=True)
                if protegido:
                    raise Recusado(f"caminho protegido: {motivo}")
        risco = "baixo"
        if info["tipo"] == "pasta" or info["tamanho"] > 1024 ** 3:
            risco = "medio"
        if os.path.splitext(real)[1].casefold() in (".exe", ".dll", ".sys", ".msi"):
            risco = "medio"
        if self.pessoal(real):
            risco = "alto"
        if acao == "quarentena":
            o_que_muda = ("Sai de onde está e vai para a quarentena do DERVS. Nada é destruído; "
                          "o espaço no disco só volta quando a quarentena for esvaziada (outra "
                          "ação, com nova aprovação).")
            como_desfazer = "Clique em Desfazer no Registro: o item volta exatamente para onde estava."
        else:
            o_que_muda = "Vai para a Lixeira do Windows."
            como_desfazer = "Restaurar pela Lixeira do Windows."
        return {
            "alvo": alvo, "caminho_real": real, "onde": os.path.dirname(real),
            "tipo": info["tipo"], "tamanho_bytes": info["tamanho"],
            "data": time.strftime("%d/%m/%Y %H:%M", time.localtime(info["mtime_ns"] / 1e9)),
            "o_que_e": _o_que_e(real, info, self.ambiente), "o_que_muda": o_que_muda,
            "como_desfazer": como_desfazer, "reversivel": True, "risco": risco,
            "impressao": impressao_de(real, info["digest"]),
        }

    def _item_de_sistema(self, proposta: dict, acao: str) -> dict:
        alvo = _texto(proposta.get("alvo"), "alvo", True, minimo=1)[:300]
        versao = _texto(proposta.get("versao"), "versao", False)[:100]
        return {
            "alvo": alvo, "caminho_real": "", "onde": "", "versao": versao,
            "tipo": "programa" if acao in ("desinstalar", "atualizar", "instalar") else "configuração",
            "tamanho_bytes": 0, "data": "", "o_que_e": f"{acao.replace('_', ' ')}: {alvo}",
            "o_que_muda": _O_QUE_MUDA_SISTEMA[acao],
            "como_desfazer": "Nesta versão não há desfazer automático para este tipo de ação.",
            "reversivel": False, "risco": "alto" if acao == "desinstalar" else "medio",
            "impressao": impressao_de_sistema(acao, alvo, versao),
        }

    def _analisar_um(self, proposta) -> dict:
        if not isinstance(proposta, dict):
            raise Recusado("proposta sem formato de item")
        acao = proposta.get("acao")
        if acao not in ACOES_DE_ARQUIVO + ACOES_DE_SISTEMA:
            raise Recusado(f"ação desconhecida ({str(acao)[:40]!r}) — o motor não faz o que não conhece")
        por_que = _texto(proposta.get("por_que_seguro"), "por_que_seguro", True)
        explicacao = _texto(proposta.get("explicacao"), "explicacao", False)
        muda_extra = _texto(proposta.get("o_que_muda"), "o_que_muda", False)
        risco_proposto = proposta.get("risco", "baixo")
        if risco_proposto not in RISCOS:
            risco_proposto = "alto"  # risco ilegível sobe, nunca desce
        if acao in ACOES_DE_ARQUIVO:
            item = self._item_de_arquivo(proposta, acao)
        else:
            item = self._item_de_sistema(proposta, acao)
        item["acao"] = acao
        item["explicacao_claude"] = explicacao
        if explicacao:
            item["o_que_e"] += f" Explicação do Claude: {explicacao}"
        if muda_extra:
            item["o_que_muda"] += f" Segundo o Claude: {muda_extra}"
        item["por_que_seguro"] = por_que
        item["risco"] = _risco_max(item["risco"], risco_proposto)
        return item

    def analisar(self, itens, origem: str = "claude") -> dict:
        """Monta o relatório. Nunca executa nada."""
        relatorio_id = secrets.token_hex(8)
        aceitos, recusados = [], []
        if not isinstance(itens, list) or len(itens) > LIMITE_ITENS:
            recusados.append({"alvo": "", "motivo": f"a proposta tem de ser uma lista de até "
                                                    f"{LIMITE_ITENS} itens"})
            itens = []
        for proposta in itens:
            alvo = str(proposta.get("alvo", ""))[:300] if isinstance(proposta, dict) else ""
            try:
                item = self._analisar_um(proposta)
            except Recusado as erro:
                recusados.append({"alvo": alvo, "motivo": str(erro)})
                continue
            except Exception as erro:  # na dúvida, fora do relatório
                recusados.append({"alvo": alvo,
                                  "motivo": f"não deu para analisar ({type(erro).__name__})"})
                continue
            item["id"] = f"item-{len(aceitos) + 1}"
            aceitos.append(item)
        relatorio = {
            "id": relatorio_id, "origem": str(origem)[:40],
            "criado_em": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(self.relogio())),
            "itens": aceitos, "recusados": recusados,
            "total_bytes": sum(i["tamanho_bytes"] for i in aceitos),
        }
        with self._trava:
            self._relatorios[relatorio_id] = {"dados": copy.deepcopy(relatorio),
                                              "hash": _hash_do_relatorio(aceitos)}
        pasta = os.path.join(self.pasta, "relatorios")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, relatorio_id + ".json"), "w", encoding="utf-8",
                  newline="\n") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        self.log.registrar("analisou", {"relatorio_id": relatorio_id, "origem": relatorio["origem"],
                                        "itens": len(aceitos), "recusados": len(recusados)})
        for item in aceitos:
            self.log.registrar("propos", {
                "relatorio_id": relatorio_id, "item_id": item["id"], "acao": item["acao"],
                "alvo": item["caminho_real"] or item["alvo"], "tamanho_bytes": item["tamanho_bytes"],
                "risco": item["risco"], "impressao": item["impressao"]})
        for r in recusados:
            self.log.registrar("recusou", {"etapa": "analisar", "relatorio_id": relatorio_id,
                                           "alvo": r["alvo"], "motivo": r["motivo"]})
        return copy.deepcopy(relatorio)

    # --------------------------------------------------- 2. cartão da tela
    def abrir_cartao(self, relatorio_id: str) -> str | None:
        """Senha que acompanha o relatório SÓ até o painel. O clique devolve."""
        with self._trava:
            if relatorio_id not in self._relatorios:
                return None
            senha = secrets.token_urlsafe(32)
            self._cartoes[relatorio_id] = senha
            return senha

    # --------------------------------------------------- 3. aprovar
    def aprovar(self, relatorio_id, ids, *, origem, cartao, dupla_confirmacao=None) -> dict:
        def recusa(motivo):
            return self.recusar("aprovar", motivo, relatorio_id=str(relatorio_id)[:40],
                                origem=str(origem)[:40])

        if not isinstance(origem, str) or origem != "clique":
            return recusa("aprovação só vale com um clique seu no painel — voz, pedido do "
                          "Claude ou de outro programa não aprovam")
        with self._trava:
            guardado = self._relatorios.get(relatorio_id) if isinstance(relatorio_id, str) else None
            if guardado is None:
                return recusa("relatório não encontrado — analise de novo")
            senha = self._cartoes.get(relatorio_id)
            if not (isinstance(cartao, str) and senha and secrets.compare_digest(cartao, senha)):
                return recusa("a aprovação não veio do cartão deste relatório no painel")
            if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
                return recusa("marque os itens um a um — não existe 'aprovar tudo' às cegas")
            if len(set(ids)) != len(ids):
                return recusa("a lista de itens aprovados tem repetição")
            itens = {i["id"]: i for i in guardado["dados"]["itens"]}
            fora = [i for i in ids if i not in itens]
            if fora:
                return recusa(f"itens fora do relatório: {', '.join(fora)[:200]}")
            repetidos = [i for i in ids if (relatorio_id, i) in self._aprovados]
            if repetidos:
                return recusa(f"itens já aprovados antes: {', '.join(repetidos)[:200]}")
            dupla = dupla_confirmacao if isinstance(dupla_confirmacao, list) else []
            sem_dupla = [i for i in ids if itens[i]["risco"] == "alto" and i not in dupla]
            if sem_dupla:
                return recusa(f"risco alto pede confirmação dupla: {', '.join(sem_dupla)[:200]}")
            pessoais = [i for i in ids
                        if itens[i]["caminho_real"] and self.pessoal(itens[i]["caminho_real"])]
            if len(pessoais) > LIMITE_PESSOAIS_POR_VEZ:
                return recusa(f"exclusão em massa em pasta pessoal: no máximo "
                              f"{LIMITE_PESSOAIS_POR_VEZ} itens por vez")
            agora = self.relogio()
            registro = {
                "id": secrets.token_hex(8), "token": secrets.token_urlsafe(32),
                "relatorio_id": relatorio_id, "relatorio_hash": guardado["hash"],
                "ids": list(ids), "impressoes": {i: itens[i]["impressao"] for i in ids},
                "quando": agora, "expira_em": agora + VALIDADE_S, "origem": "clique",
                "usados": [],
            }
            self._registros[registro["id"]] = registro
            self._aprovados.update((relatorio_id, i) for i in ids)
            devolver = copy.deepcopy(registro)
        self.log.registrar("aprovou", {"registro_id": devolver["id"], "relatorio_id": relatorio_id,
                                       "ids": list(ids), "origem": "clique",
                                       "impressoes": devolver["impressoes"]})
        return {"ok": True, "registro": devolver}

    # --------------------------------------------------- 4. consumir (executor)
    def consumir_aprovacao(self, registro_id, token, item_id) -> dict:
        """Confere e QUEIMA a aprovação de um item, de uma vez só, sob trava."""
        with self._trava:
            reg = self._registros.get(registro_id) if isinstance(registro_id, str) else None
            if reg is None:
                return {"ok": False, "motivo": "não há aprovação registrada para isto"}
            if not (isinstance(token, str) and secrets.compare_digest(token, reg["token"])):
                return {"ok": False, "motivo": "a aprovação apresentada não confere com a registrada"}
            if self.relogio() > reg["expira_em"]:
                return {"ok": False, "motivo": "a aprovação venceu (vale 15 minutos) — "
                                               "analise e aprove de novo"}
            if not isinstance(item_id, str) or item_id not in reg["ids"]:
                return {"ok": False, "motivo": "este item não está entre os que você aprovou"}
            if item_id in reg["usados"]:
                return {"ok": False, "motivo": "esta aprovação já foi usada — cada clique vale uma vez"}
            guardado = self._relatorios.get(reg["relatorio_id"])
            if guardado is None or _hash_do_relatorio(guardado["dados"]["itens"]) != reg["relatorio_hash"]:
                return {"ok": False, "motivo": "o relatório mudou depois da aprovação"}
            item = next(i for i in guardado["dados"]["itens"] if i["id"] == item_id)
            if item["impressao"] != reg["impressoes"][item_id]:
                return {"ok": False, "motivo": "a impressão digital do item não confere"}
            reg["usados"].append(item_id)
            publico = {k: v for k, v in reg.items() if k != "token"}
            return {"ok": True, "item": copy.deepcopy(item), "registro": copy.deepcopy(publico)}
