#!/usr/bin/env python3
"""DERVS — configuração editável pelo dono, sem tocar no código.

Um único arquivo JSON em ~/.config/dervs/config.json. O app lê ao ligar e
completa com valores-padrão tudo que faltar — então o arquivo pode ter só o que
você quer mudar, e o DERVS nunca quebra por causa de config torta (config
ilegível cai no padrão em silêncio, não derruba a voz).

Cada chave está documentada no PADRAO abaixo; é ele que vira o arquivo de
exemplo em `garantir_arquivo()`.
"""
import os
import sys
import json


def _resolver_config_dir() -> str:
    """No Windows a config mora em %APPDATA%\\dervs (padrão do sistema para
    dado de app, sobrevive a reinstalação da conta); em Linux continua
    ~/.config/dervs. DERVS_MODELOS não afeta isto — é só para os modelos."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")
        return os.path.join(base, "dervs")
    return os.path.expanduser("~/.config/dervs")


CONFIG_DIR = _resolver_config_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# Valores de fábrica. Editar o config.json sobrescreve só o que você mudar.
PADRAO = {
    # Segundos que o DERVS segue ouvindo depois de te atender, SEM você
    # repetir "DERVS". Passado isso ele "dorme" e só acorda no nome de novo.
    # Suba para conversar mais tempo à vontade; desça para ele dormir mais rápido.
    "janela_desperto_seg": 20,

    # Atalhos locais para perguntas triviais (que horas são, que dia é hoje,
    # abrir um app): respondem NA HORA, sem esperar o cérebro (~2,7 s a menos).
    # Ponha false para tudo passar pelo cérebro.
    "atalhos_ligados": True,

    # Ouvido (transcrição PRECISA, do pedido — não confundir com o porteiro,
    # que é local e de graça): "openai" (precisa de chave e internet) ou
    # "local" (Whisper no processador, grátis e offline, ~4,7s). "openai" cai
    # no local sozinho se falhar.
    "stt": "openai",
    # gpt-transcribe (lançado 28/07/2026, US$ 0,0045/min) é ao mesmo tempo mais
    # preciso e mais barato que o gpt-4o-transcribe (US$ 0,006/min), e a própria
    # OpenAI passou a recomendá-lo à frente dele e do whisper-1. Custa ~US$ 1/mês
    # a mais que o gpt-4o-mini-transcribe (US$ 0,003/min) no volume previsto —
    # e o dono pediu precisão em letra maiúscula. Preços consultados em
    # 01/09/2026 em developers.openai.com/api/docs/pricing.
    "stt_openai_modelo": "gpt-transcribe",

    # O PORTEIRO: quem decide, NA MÁQUINA, se a fala foi com o DERVS. É ele que
    # permite deixar ligado o dia inteiro sem mandar o áudio do dia inteiro para
    # a nuvem. "local" = Whisper pequeno com aviso de vocabulário (medido: 14/14
    # em 0,49s). "porcupine" = detector dedicado, ainda não implementado — exige
    # conta gratuita no picovoice.ai. Ver dervs_porteiro.py.
    "porteiro": "local",
    "porteiro_modelo": "tiny",

    # Cérebro: "openai" (gpt-4.1-nano — ultrarrápido e barato, precisa de chave
    # em ~/voice/.env e internet) ou "claude" (CLI local, grátis na assinatura).
    # Se "openai" mas sem chave/internet, cai no Claude sozinho.
    "cerebro": "openai",
    # Modelo da OpenAI para o cérebro. "gpt-4.1-nano" é o mais barato; suba para
    # "gpt-4o-mini" se quiser um pouco mais de esperteza (custa ~50% mais).
    "cerebro_openai_modelo": "gpt-4.1-nano",

    # Motor de voz: "kokoro" (humana, offline, grátis — PADRÃO), "piper"
    # (sintética, instantânea, reserva) ou "xtts" (a mais humana, mas lenta).
    "motor": "kokoro",

    # Voz do Kokoro (quando motor="kokoro"): "pm_santa" (masculina grave,
    # feiticeiro), "pm_alex" (masculina) ou "pf_dora" (feminina).
    "voz_kokoro": "pm_santa",

    # Velocidade da fala do Kokoro. 1.0 = natural; 1.2 = mais ágil, ainda
    # claro (testado na máquina do dono, sem custo extra de tempo). Aceita de
    # 0.5 (bem devagar) a 2.0 (bem rápido).
    "voz_velocidade": 1.2,

    # Voz do Piper (quando motor="piper"): "jeff", "cadu" ou "faber".
    "voz": "jeff",

    # --- Navegador autônomo (o DERVS clica/digita sozinho no seu Chrome) ---
    # Liga o recurso. Com true, o cérebro pode propor um passo do tipo
    # "navegador" quando você pede algo DENTRO de uma página ("entra no Gmail e
    # me diz os não lidos"). ATENÇÃO: enquanto ele trabalha, seu Chrome do dia a
    # dia precisa estar FECHADO (o perfil só abre num lugar por vez).
    "navegador_ligado": True,
    # Quantos passos (cliques/digitações) ele pode dar sozinho antes de parar
    # para você conferir. Suba para tarefas mais longas; desça para segurar a rédea.
    "navegador_max_passos": 15,
    # Pasta do perfil do Chrome (onde ficam seus logins) e o nome do perfil.
    # Só mude se você usa outro navegador/perfil.
    "navegador_perfil_chrome": "~/.config/google-chrome",
    "navegador_perfil_nome": "Default",
    # Modelo que decide cada clique. Vazio = usa o mesmo do cérebro (o mais
    # barato). Suba só se a navegação exigir mais esperteza.
    "navegador_modelo": "",
}


def _validar(conf: dict) -> dict:
    """Conserta valores fora do razoável sem quebrar — a config é do dono, mas
    um número absurdo não pode deixar o DERVS inutilizável."""
    try:
        j = int(conf["janela_desperto_seg"])
        conf["janela_desperto_seg"] = min(max(j, 3), 3600)  # entre 3 s e 1 h
    except (TypeError, ValueError):
        conf["janela_desperto_seg"] = PADRAO["janela_desperto_seg"]
    conf["atalhos_ligados"] = bool(conf.get("atalhos_ligados", True))
    if conf.get("stt") not in ("openai", "local"):
        conf["stt"] = PADRAO["stt"]
    if not isinstance(conf.get("stt_openai_modelo"), str) or not conf["stt_openai_modelo"]:
        conf["stt_openai_modelo"] = PADRAO["stt_openai_modelo"]
    if conf.get("porteiro") not in ("local", "porcupine"):
        conf["porteiro"] = PADRAO["porteiro"]
    if not isinstance(conf.get("porteiro_modelo"), str) or not conf["porteiro_modelo"]:
        conf["porteiro_modelo"] = PADRAO["porteiro_modelo"]
    if conf.get("cerebro") not in ("openai", "claude"):
        conf["cerebro"] = PADRAO["cerebro"]
    if not isinstance(conf.get("cerebro_openai_modelo"), str) or not conf["cerebro_openai_modelo"]:
        conf["cerebro_openai_modelo"] = PADRAO["cerebro_openai_modelo"]
    if conf.get("motor") not in ("kokoro", "piper", "xtts"):
        conf["motor"] = PADRAO["motor"]
    if conf.get("voz_kokoro") not in ("pm_santa", "pm_alex", "pf_dora"):
        conf["voz_kokoro"] = PADRAO["voz_kokoro"]
    try:
        v = float(conf["voz_velocidade"])
        if not (0.5 <= v <= 2.0):
            raise ValueError
        conf["voz_velocidade"] = v
    except (TypeError, ValueError, KeyError):
        conf["voz_velocidade"] = PADRAO["voz_velocidade"]
    if conf.get("voz") not in ("jeff", "cadu", "faber"):
        conf["voz"] = PADRAO["voz"]
    conf["navegador_ligado"] = bool(conf.get("navegador_ligado", True))
    try:
        n = int(conf["navegador_max_passos"])
        conf["navegador_max_passos"] = min(max(n, 1), 60)  # entre 1 e 60 passos
    except (TypeError, ValueError, KeyError):
        conf["navegador_max_passos"] = PADRAO["navegador_max_passos"]
    if not isinstance(conf.get("navegador_perfil_chrome"), str) or not conf["navegador_perfil_chrome"]:
        conf["navegador_perfil_chrome"] = PADRAO["navegador_perfil_chrome"]
    if not isinstance(conf.get("navegador_perfil_nome"), str) or not conf["navegador_perfil_nome"]:
        conf["navegador_perfil_nome"] = PADRAO["navegador_perfil_nome"]
    if not isinstance(conf.get("navegador_modelo"), str):
        conf["navegador_modelo"] = PADRAO["navegador_modelo"]
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
    deu para criar (nunca quebra o DERVS por isso)."""
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
