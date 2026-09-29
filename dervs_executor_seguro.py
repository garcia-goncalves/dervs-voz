#!/usr/bin/env python3
"""DERVS — o ÚNICO caminho que executa mudança aprovada (onda C).

Nada aqui roda sem um registro de aprovação emitido pelo motor
(`dervs_aprovacao.Motor`) a partir de um clique do dono. Antes de tocar em
qualquer coisa, TUDO é conferido de novo, agora — e qualquer dúvida é recusa,
com o motivo em português e uma linha no registro de ações:

  - origem que não seja "clique" (voz, Claude, API);
  - sem registro, registro que não confere, vencido (15 min), já usado, ou
    item fora do que foi aprovado;
  - o caminho de hoje leva a outro lugar, passa por junção/atalho, ou tem
    junção/atalho ou pasta protegida dentro;
  - o caminho é protegido (vale a lista de AGORA, não a da análise);
  - a impressão digital mudou (o arquivo mudou, ou é OUTRO arquivo idêntico).

**A mudança é feita segurando o item.** A revisão de segurança de 29/09/2026
provou que conferir pelo CAMINHO e depois mover pelo CAMINHO deixa uma janela:
entre as duas coisas, a pasta de uma "isca" podia virar uma junção para uma
pasta protegida, e o arquivo protegido ia para a quarentena. Agora o item é
ABERTO (CreateFileW, sem seguir junção, sem deixar ninguém apagá-lo ou
renomeá-lo enquanto está aberto), e só então se confere, NO QUE ESTÁ ABERTO,
o número do arquivo no disco e o caminho final que o Windows dá para ele. A
mudança de lugar é feita nesse mesmo item aberto
(SetFileInformationByHandle). Trocar o caminho depois disso não muda o que
está sendo movido — e, enquanto o item está aberto, o Windows nem deixa
renomear a pasta de cima.

Apagar = QUARENTENA, nunca exclusão direta: o item é MOVIDO (no mesmo disco)
para `%LOCALAPPDATA%\\dervs\\quarentena\\<id>\\conteudo\\`, com um
`manifesto.json`. Antes de mover, grava "vai_executar" no registro — se não
conseguir gravar, NÃO move. Depois de mover, confere número e conteúdo de
novo; se não bate, devolve na hora. `desfazer(id)` só confia no manifesto se
ele bater com o que o executor anotou (na memória desta sessão ou, depois de
reiniciar, na linha "executou" do registro), e devolve também segurando o
item: se o lugar de volta virou junção para pasta protegida, desfaz a volta.

A Lixeira do Windows ainda NÃO está ligada: `SHFileOperation` com
"sem perguntar" apaga de vez, em silêncio, quando a Lixeira não aceita o item
(grande demais, disco sem Lixeira) — exatamente o que o dono proibiu. A ação
`lixeira` passa por todas as travas e para em "não implementado nesta versão".

Ações que não são arquivo (desinstalar, serviço, registro, firewall,
instalar, atualizar...) exigem a MESMA aprovação e, nesta versão, também param
em "não implementado" depois de passar por todas as travas — a onda D liga o
que couber.
"""
import ctypes
import json
import os
import re
import secrets
import time
from ctypes import wintypes

import dervs_aprovacao as ap
import dervs_caminhos_protegidos as cp

_ID_DESFAZER = re.compile(r"^\d{8}-[0-9a-f]{12}$")
_NAO_IMPLEMENTADO = ("não implementado nesta versão — a trava aprovou, mas o DERVS ainda "
                     "não sabe fazer esta ação com segurança")
_SEM_REGISTRO = "não consegui gravar no registro de ações — por segurança, nada foi feito"


# ------------------------------------------------------------ o item seguro na mão

class _Info(ctypes.Structure):
    _fields_ = [("atributos", wintypes.DWORD), ("criado", wintypes.FILETIME),
                ("acesso", wintypes.FILETIME), ("escrita", wintypes.FILETIME),
                ("volume", wintypes.DWORD), ("tamanho_alto", wintypes.DWORD),
                ("tamanho_baixo", wintypes.DWORD), ("ligacoes", wintypes.DWORD),
                ("indice_alto", wintypes.DWORD), ("indice_baixo", wintypes.DWORD)]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Info)]
_k32.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
                                           wintypes.DWORD]
_k32.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                            wintypes.DWORD]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_INVALIDO = wintypes.HANDLE(-1).value


class _Alca:
    """O item aberto: DELETE (para poder mover) + ler atributos, sem seguir
    junção e SEM partilhar DELETE — ninguém apaga nem renomeia enquanto está
    aberto."""

    def __init__(self, caminho: str):
        acesso = 0x00010000 | 0x0080 | 0x00100000        # DELETE | READ_ATTRIBUTES | SYNCHRONIZE
        partilha = 0x1 | 0x2                              # ler e escrever, NÃO apagar
        flags = 0x02000000 | 0x00200000                   # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        self.h = _k32.CreateFileW(caminho, acesso, partilha, None, 3, flags, None)
        if self.h in (None, _INVALIDO):
            raise ctypes.WinError(ctypes.get_last_error())

    def identidade(self) -> tuple[int, int]:
        info = _Info()
        if not _k32.GetFileInformationByHandle(self.h, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (info.indice_alto << 32) | info.indice_baixo, info.atributos

    def caminho_final(self) -> str:
        buf = ctypes.create_unicode_buffer(32768)
        if not _k32.GetFinalPathNameByHandleW(self.h, buf, 32768, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return buf.value[4:] if buf.value.startswith("\\\\?\\") else buf.value

    def renomear(self, destino: str):
        """FILE_RENAME_INFO: ReplaceIfExists=0 (nunca sobrescreve), sem pasta
        raiz, tamanho do nome em bytes, nome."""
        nome = ctypes.create_unicode_buffer(destino)
        tamanho = len(destino) * 2
        buf = ctypes.create_string_buffer(max(24, 20 + tamanho + 2))
        ctypes.memmove(ctypes.addressof(buf) + 16, ctypes.byref(wintypes.DWORD(tamanho)), 4)
        ctypes.memmove(ctypes.addressof(buf) + 20, nome, tamanho + 2)
        if not _k32.SetFileInformationByHandle(self.h, 3, buf, len(buf)):
            raise ctypes.WinError(ctypes.get_last_error())

    def fechar(self):
        if self.h not in (None, _INVALIDO):
            _k32.CloseHandle(self.h)
            self.h = None


def _igual(a: str, b: str) -> bool:
    return os.path.normcase(a) == os.path.normcase(b)


def _mover_segurando(de: str, para: str, ino: int, antes, depois) -> str:
    """Move `de` para `para` segurando o item. `antes(final)` e `depois(final)`
    devolvem "" ou um motivo; se `depois` reclamar, o item volta. Devolve ""
    se moveu, senão o motivo (e nada mudou)."""
    try:
        alca = _Alca(de)
    except OSError as erro:
        return f"não deu para segurar o item (em uso ou sem permissão: {erro.winerror})"
    try:
        numero, atributos = alca.identidade()
        if atributos & 0x400:
            return "o item virou uma junção ou atalho simbólico"
        if numero != ino:
            return "o item no disco não é o mesmo que foi analisado (foi trocado por outro)"
        final = alca.caminho_final()
        if not _igual(final, de):
            return "o caminho agora leva a outro lugar (junção ou atalho trocado depois da análise)"
        motivo = antes(final)
        if motivo:
            return motivo
        alca.renomear(para)
        final = alca.caminho_final()
        motivo = "" if _igual(final, para) else "o item foi parar num lugar inesperado"
        motivo = motivo or depois(final)
        if motivo:
            try:
                alca.renomear(de)
            except OSError:
                motivo += " — e NÃO deu para devolver: veja a quarentena"
            return motivo
        return ""
    except OSError as erro:
        return f"o Windows recusou a mudança ({erro.winerror}) — nada foi alterado"
    finally:
        alca.fechar()


# ------------------------------------------------------------ quarentena

def _pasta_quarentena(motor) -> str:
    return os.path.join(motor.pasta, "quarentena")


def _gravar_manifesto(pasta: str, manifesto: dict):
    temporario = os.path.join(pasta, "manifesto.json.novo")
    with open(temporario, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)
    os.replace(temporario, os.path.join(pasta, "manifesto.json"))


def _conferir_arquivo(motor, item: dict, impressao_aprovada: str):
    """(motivo, info) — motivo "" se pode seguir."""
    alvo, real_analisado = item["alvo"], item["caminho_real"]
    lexico = cp._lexico(alvo)
    real = cp.normalizar(alvo)
    if lexico is None or real is None:
        return "caminho inválido ou disfarçado", None
    if cp.link_no_caminho(lexico) or cp.link_no_caminho(real):
        return "o caminho passa por uma junção ou atalho simbólico — o destino pode ter sido trocado", None
    if not _igual(real, real_analisado):
        return "o caminho agora leva a outro lugar (junção ou atalho trocado depois da análise)", None
    if not os.path.lexists(real):
        return "o item não existe mais", None
    eh_pasta = os.path.isdir(real)
    if eh_pasta:
        problema = cp.problema_dentro(real, ap.LIMITE_ENTRADAS_PASTA)
        if problema:
            return problema, None
    protegido, motivo = motor.checar_protegido(alvo, em_massa=eh_pasta and motor.pessoal(real))
    if protegido:
        return f"caminho protegido: {motivo}", None
    try:
        info = ap.conteudo_de(real)
    except ap.Recusado as erro:
        return str(erro), None
    if ap.impressao_de(real, info["digest"]) != impressao_aprovada or info["ino"] != item.get("identidade"):
        return "o item mudou depois da análise (a impressão digital não bate) — analise de novo", None
    return "", info


def _quarentenar(motor, item: dict, info: dict, registro: dict) -> dict:
    real = item["caminho_real"]
    base = _pasta_quarentena(motor)
    os.makedirs(base, exist_ok=True)
    if os.path.splitdrive(real)[0].casefold() != os.path.splitdrive(os.path.realpath(base))[0].casefold():
        return motor.recusar("executar", "o item está em outro disco — nesta versão a quarentena "
                                         "só recebe itens do mesmo disco dela",
                             item_id=item["id"], alvo=real)
    desfazer_id = time.strftime("%Y%m%d", time.localtime(motor.relogio())) + "-" + secrets.token_hex(6)
    pasta = os.path.join(base, desfazer_id)
    destino = os.path.join(pasta, "conteudo", os.path.basename(real))
    manifesto = {
        "id": desfazer_id, "origem": real, "nome": os.path.basename(real), "tipo": info["tipo"],
        "tamanho_bytes": info["tamanho"], "conteudo": info["digest"], "ino": info["ino"],
        "impressao": item["impressao"], "relatorio_id": registro["relatorio_id"],
        "registro_id": registro["id"], "item_id": item["id"], "acao": item["acao"],
        "quando": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(motor.relogio())),
        "estado": "movendo",
    }

    def antes(final):
        protegido, motivo = motor.checar_protegido(final, em_massa=info["tipo"] == "pasta"
                                                   and motor.pessoal(final))
        if protegido:
            return f"caminho protegido: {motivo}"
        try:
            motor.log.registrar("vai_executar", {"registro_id": registro["id"],
                                                 "item_id": item["id"], "alvo": final,
                                                 "destino": destino, "desfazer_id": desfazer_id})
        except Exception:
            return _SEM_REGISTRO
        os.makedirs(os.path.join(pasta, "conteudo"))
        _gravar_manifesto(pasta, manifesto)
        return ""

    motivo = _mover_segurando(real, destino, info["ino"], antes, lambda final: "")
    if motivo:
        if os.path.isdir(pasta):
            manifesto["estado"] = "nao_movido"
            _gravar_manifesto(pasta, manifesto)
        return motor.recusar("executar", motivo, item_id=item["id"], alvo=real)
    # Conferência depois de mover: mesmo número, mesmo conteúdo.
    try:
        depois = ap.conteudo_de(destino)
    except (ap.Recusado, OSError):
        depois = None
    if depois is None or depois["digest"] != info["digest"] or depois["ino"] != info["ino"]:
        devolveu = _mover_segurando(destino, real, info["ino"], lambda f: "", lambda f: "") == ""
        manifesto["estado"] = "devolvido" if devolveu else "em_quarentena"
        _gravar_manifesto(pasta, manifesto)
        return motor.recusar("executar", "o item mudou durante a execução — "
                             + ("foi devolvido para onde estava" if devolveu else
                                "ficou na quarentena"), item_id=item["id"], alvo=real)
    manifesto["estado"] = "em_quarentena"
    _gravar_manifesto(pasta, manifesto)
    with motor._trava:
        motor._quarentenas[desfazer_id] = {"alvo": real, "destino": destino,
                                           "conteudo": info["digest"], "ino": info["ino"]}
    try:
        motor.log.registrar("executou", {"registro_id": registro["id"], "item_id": item["id"],
                                         "acao": item["acao"], "alvo": real, "destino": destino,
                                         "desfazer_id": desfazer_id, "conteudo": info["digest"],
                                         "ino": info["ino"], "tamanho_bytes": info["tamanho"]})
    except Exception:
        pass  # o "vai_executar" já está gravado; o desfazer desta sessão usa a memória
    return {"ok": True, "motivo": "movido para a quarentena — dá para desfazer",
            "desfazer_id": desfazer_id}


def executar(motor, registro_id, token, item_id, origem) -> dict:
    """Executa UM item aprovado. Devolve {"ok", "motivo", "desfazer_id"?}."""
    if type(motor) is not ap.Motor:  # subclasse poderia trocar a conferência
        return {"ok": False, "motivo": "motor de aprovação inválido — nada foi feito"}
    if not isinstance(origem, str) or origem != "clique":
        return motor.recusar("executar", "só um clique seu no painel executa — voz, pedido do "
                                         "Claude ou de outro programa não valem",
                             item_id=str(item_id)[:40], origem=str(origem)[:40])
    consumo = motor.consumir_aprovacao(registro_id, token, item_id)
    if not consumo["ok"]:
        return motor.recusar("executar", consumo["motivo"], registro_id=str(registro_id)[:40],
                             item_id=str(item_id)[:40])
    item, registro = consumo["item"], consumo["registro"]
    aprovada = registro["impressoes"][item_id]
    try:
        if item["acao"] in ap.ACOES_DE_ARQUIVO:
            motivo, info = _conferir_arquivo(motor, item, aprovada)
            if motivo:
                return motor.recusar("executar", motivo, item_id=item_id, alvo=item["caminho_real"])
            if item["acao"] == "quarentena":
                return _quarentenar(motor, item, info, registro)
            return motor.recusar("executar", _NAO_IMPLEMENTADO, item_id=item_id, acao=item["acao"])
        if ap.impressao_de_sistema(item["acao"], item["alvo"], item.get("versao", "")) != aprovada:
            return motor.recusar("executar", "a ação mudou depois da análise", item_id=item_id)
        return motor.recusar("executar", _NAO_IMPLEMENTADO, item_id=item_id, acao=item["acao"],
                             alvo=item["alvo"])
    except Exception as erro:  # na dúvida, para
        return motor.recusar("executar", f"erro inesperado ({type(erro).__name__}) — parei sem "
                                         f"concluir", item_id=item_id)


def _anotado(motor, desfazer_id: str) -> dict | None:
    """O que o executor anotou ao mover: na memória desta sessão ou, depois
    de reiniciar, na linha "executou" do registro. O manifesto sozinho não
    vale — é um arquivo que qualquer um que escreva no disco pode trocar."""
    with motor._trava:
        if desfazer_id in motor._quarentenas:
            return dict(motor._quarentenas[desfazer_id])
    for linha in reversed(motor.log.ler()):
        dados = linha.get("dados") or {}
        if linha.get("evento") == "executou" and dados.get("desfazer_id") == desfazer_id:
            if all(isinstance(dados.get(k), str) for k in ("alvo", "destino", "conteudo")) \
                    and isinstance(dados.get("ino"), int):
                return {k: dados[k] for k in ("alvo", "destino", "conteudo", "ino")}
            return None
    return None


def desfazer(motor, desfazer_id, origem) -> dict:
    """Devolve um item da quarentena para onde estava. Nunca sobrescreve."""
    if type(motor) is not ap.Motor:
        return {"ok": False, "motivo": "motor de aprovação inválido — nada foi feito"}

    def recusa(motivo):
        return motor.recusar("desfazer", motivo, desfazer_id=str(desfazer_id)[:40])

    if not isinstance(origem, str) or origem != "clique":
        return recusa("desfazer também só vale com um clique seu no painel")
    if not isinstance(desfazer_id, str) or not _ID_DESFAZER.match(desfazer_id):
        return recusa("identificador de quarentena inválido")
    with motor._trava:
        pasta = os.path.join(_pasta_quarentena(motor), desfazer_id)
        try:
            with open(os.path.join(pasta, "manifesto.json"), encoding="utf-8") as f:
                manifesto = json.load(f)
        except (OSError, ValueError):
            return recusa("não achei o registro dessa quarentena")
        if not isinstance(manifesto, dict) or manifesto.get("estado") != "em_quarentena":
            return recusa("este item não está mais na quarentena (já foi desfeito ou devolvido)")
        destino, nome = manifesto.get("origem"), manifesto.get("nome")
        if (not isinstance(nome, str) or not isinstance(destino, str) or nome in ("", ".", "..")
                or re.search(r"[\\/:]", nome) or os.path.basename(destino) != nome):
            return recusa("o manifesto da quarentena está inconsistente — não mexo")
        guardado = os.path.join(pasta, "conteudo", nome)
        anotado = _anotado(motor, desfazer_id)
        if (anotado is None or not _igual(anotado["alvo"], destino)
                or not _igual(anotado["destino"], guardado)
                or anotado["conteudo"] != manifesto.get("conteudo")):
            return recusa("o manifesto da quarentena não bate com o que o DERVS anotou ao mover "
                          "— não devolvo")
        if not os.path.lexists(guardado) or cp.link_no_caminho(guardado):
            return recusa("o conteúdo da quarentena sumiu ou virou atalho")
        if cp.normalizar(destino) is None or os.path.lexists(destino):
            return recusa("já existe algo no lugar original — nunca sobrescrevo")
        pai = os.path.dirname(destino)
        if not os.path.isdir(pai) or cp.link_no_caminho(pai):
            return recusa("a pasta original não existe mais ou virou atalho")
        protegido, motivo = motor.checar_protegido(destino)
        if protegido:
            return recusa(f"o lugar original agora é protegido: {motivo}")
        try:
            digest = ap.conteudo_de(guardado)["digest"]
        except (ap.Recusado, OSError):
            digest = None
        if digest != anotado["conteudo"]:
            return recusa("o conteúdo na quarentena foi mexido — não devolvo algo diferente do que saiu")

        def depois(final):
            protegido, motivo = motor.checar_protegido(final)
            return f"o lugar de volta virou área protegida ({motivo})" if protegido else ""

        motivo = _mover_segurando(guardado, destino, anotado["ino"], lambda final: "", depois)
        if motivo:
            return recusa(motivo)
        manifesto["estado"] = "desfeito"
        _gravar_manifesto(pasta, manifesto)
        motor._quarentenas.pop(desfazer_id, None)
    try:
        motor.log.registrar("desfez", {"desfazer_id": desfazer_id, "alvo": destino})
    except Exception:
        pass
    return {"ok": True, "motivo": "o item voltou para onde estava"}
