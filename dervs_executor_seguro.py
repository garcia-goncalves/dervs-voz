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
  - a impressão digital mudou (o arquivo mudou depois da análise).

Apagar = QUARENTENA, nunca exclusão direta: o item é MOVIDO (renomeado, no
mesmo disco) para `%LOCALAPPDATA%\\dervs\\quarentena\\<id>\\conteudo\\`, com um
`manifesto.json` que permite `desfazer(id)`. Depois de mover, o conteúdo é
conferido de novo; se não bate com o aprovado, volta na hora.

A Lixeira do Windows ainda NÃO está ligada: `SHFileOperation` com
"sem perguntar" apaga de vez, em silêncio, quando a Lixeira não aceita o item
(grande demais, disco sem Lixeira) — exatamente o que o dono proibiu. A ação
`lixeira` passa por todas as travas e para em "não implementado nesta versão".

Ações que não são arquivo (desinstalar, serviço, registro, firewall,
instalar, atualizar...) exigem a MESMA aprovação e, nesta versão, também param
em "não implementado" depois de passar por todas as travas — a onda D liga o
que couber.
"""
import json
import os
import re
import secrets
import time

import dervs_aprovacao as ap
import dervs_caminhos_protegidos as cp

_ID_DESFAZER = re.compile(r"^\d{8}-[0-9a-f]{12}$")
_NAO_IMPLEMENTADO = ("não implementado nesta versão — a trava aprovou, mas o DERVS ainda "
                     "não sabe fazer esta ação com segurança")


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
    if os.path.normcase(real) != os.path.normcase(real_analisado):
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
    if ap.impressao_de(real, info["digest"]) != impressao_aprovada:
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
    os.makedirs(os.path.join(pasta, "conteudo"))
    destino = os.path.join(pasta, "conteudo", os.path.basename(real))
    manifesto = {
        "id": desfazer_id, "origem": real, "nome": os.path.basename(real), "tipo": info["tipo"],
        "tamanho_bytes": info["tamanho"], "conteudo": info["digest"], "impressao": item["impressao"],
        "relatorio_id": registro["relatorio_id"], "registro_id": registro["id"],
        "item_id": item["id"], "acao": item["acao"],
        "quando": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(motor.relogio())),
        "estado": "movendo",
    }
    _gravar_manifesto(pasta, manifesto)
    try:
        os.rename(real, destino)
    except OSError as erro:
        manifesto["estado"] = "nao_movido"
        _gravar_manifesto(pasta, manifesto)
        return motor.recusar("executar", f"não deu para mover o item (em uso ou sem permissão: "
                                         f"{type(erro).__name__}) — nada foi alterado",
                             item_id=item["id"], alvo=real)
    try:
        depois = ap.conteudo_de(destino)["digest"]
    except (ap.Recusado, OSError):
        depois = None
    if depois != info["digest"]:
        # Mudou entre a conferência e a mudança: devolve para onde estava.
        try:
            os.rename(destino, real)
            manifesto["estado"] = "devolvido"
        except OSError:
            manifesto["estado"] = "em_quarentena"
        _gravar_manifesto(pasta, manifesto)
        return motor.recusar("executar", "o item mudou durante a execução — foi devolvido "
                                         "para onde estava", item_id=item["id"], alvo=real)
    manifesto["estado"] = "em_quarentena"
    _gravar_manifesto(pasta, manifesto)
    motor.log.registrar("executou", {"registro_id": registro["id"], "item_id": item["id"],
                                     "acao": item["acao"], "alvo": real, "destino": destino,
                                     "desfazer_id": desfazer_id, "tamanho_bytes": info["tamanho"]})
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


def desfazer(motor, desfazer_id, origem) -> dict:
    """Devolve um item da quarentena para onde estava. Nunca sobrescreve."""
    if type(motor) is not ap.Motor:  # subclasse poderia trocar a conferência
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
        if digest != manifesto.get("conteudo"):
            return recusa("o conteúdo na quarentena foi mexido — não devolvo algo diferente do que saiu")
        try:
            os.rename(guardado, destino)
        except OSError as erro:
            return recusa(f"não deu para devolver ({type(erro).__name__})")
        manifesto["estado"] = "desfeito"
        _gravar_manifesto(pasta, manifesto)
    motor.log.registrar("desfez", {"desfazer_id": desfazer_id, "alvo": destino})
    return {"ok": True, "motivo": "o item voltou para onde estava"}
