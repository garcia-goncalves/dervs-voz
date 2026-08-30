#!/usr/bin/env python3
"""Grimoire — configuração editável pelo dono, sem tocar no código.

Um único arquivo JSON em ~/.config/grimoire/config.json. O app lê ao ligar e
completa com valores-padrão tudo que faltar — então o arquivo pode ter só o que
você quer mudar, e o Grimoire nunca quebra por causa de config torta (config
ilegível cai no padrão em silêncio, não derruba a voz).

Cada chave está documentada no PADRAO abaixo; é ele que vira o arquivo de
exemplo em `garantir_arquivo()`.
"""
import os
import json

CONFIG_DIR = os.path.expanduser("~/.config/grimoire")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# Valores de fábrica. Editar o config.json sobrescreve só o que você mudar.
PADRAO = {
    # Segundos que o Grimoire segue ouvindo depois de te atender, SEM você
    # repetir "Grimoire". Passado isso ele "dorme" e só acorda no nome de novo.
    # Suba para conversar mais tempo à vontade; desça para ele dormir mais rápido.
    "janela_desperto_seg": 20,

    # Atalhos locais para perguntas triviais (que horas são, que dia é hoje,
    # abrir um app): respondem NA HORA, sem esperar o cérebro (~2,7 s a menos).
    # Ponha false para tudo passar pelo cérebro.
    "atalhos_ligados": True,

    # Voz do Piper. Uma de: "jeff", "cadu", "faber".
    "voz": "jeff",
}


def _validar(conf: dict) -> dict:
    """Conserta valores fora do razoável sem quebrar — a config é do dono, mas
    um número absurdo não pode deixar o Grimoire inutilizável."""
    try:
        j = int(conf["janela_desperto_seg"])
        conf["janela_desperto_seg"] = min(max(j, 3), 3600)  # entre 3 s e 1 h
    except (TypeError, ValueError):
        conf["janela_desperto_seg"] = PADRAO["janela_desperto_seg"]
    conf["atalhos_ligados"] = bool(conf.get("atalhos_ligados", True))
    if conf.get("voz") not in ("jeff", "cadu", "faber"):
        conf["voz"] = PADRAO["voz"]
    return conf


def carregar() -> dict:
    """Lê o config.json e devolve o dict completo (padrão + o que o dono mudou).
    Nunca levanta exceção: config faltando ou torta cai no padrão."""
    conf = dict(PADRAO)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            do_disco = json.load(f)
        if isinstance(do_disco, dict):
            conf.update({k: v for k, v in do_disco.items() if k in PADRAO})
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return _validar(conf)


def garantir_arquivo() -> str | None:
    """Cria o config.json com os valores-padrão se ele ainda não existe, para o
    dono ter um arquivo pronto para editar. Devolve o caminho, ou None se não
    deu para criar (nunca quebra o Grimoire por isso)."""
    if os.path.exists(CONFIG_PATH):
        return CONFIG_PATH
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(PADRAO, f, ensure_ascii=False, indent=2)
        return CONFIG_PATH
    except OSError:
        return None


if __name__ == "__main__":
    caminho = garantir_arquivo()
    print(f"config em: {caminho}")
    print(json.dumps(carregar(), ensure_ascii=False, indent=2))
