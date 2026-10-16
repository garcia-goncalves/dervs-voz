#!/usr/bin/env python3
"""DERVS — configuração editável pelo dono, sem tocar no código.

Um único arquivo JSON em ~/.config/dervs/config.json. O app lê ao ligar e
completa com valores-padrão tudo que faltar — então o arquivo pode ter só o que
você quer mudar, e o DERVS nunca quebra por causa de config torta (config
ilegível cai no padrão em silêncio, não derruba a voz).

Cada chave está documentada no PADRAO abaixo; é ele que vira o arquivo de
exemplo em `garantir_arquivo()`.
"""
import copy
import os
import shutil
import sys
import json
import threading
import time

import dervs_permissoes


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


def caminhos_do_segredo():
    """Onde o arquivo de segredos pode morar, na ordem em que é procurado.

    O primeiro é ao lado da configuração — `%APPDATA%\\dervs` no Windows,
    `~/.config/dervs` no Linux. O segundo é `~/voice/.env`, que é onde o
    projeto irmão do Linux guarda, mantido para quem vier de lá.
    """
    return [os.path.join(CONFIG_DIR, ".env"),
            os.path.expanduser("~/voice/.env")]


def segredo(nome: str):
    """Devolve o valor de um segredo (ambiente primeiro, depois arquivo).

    Estava duplicado em três arquivos, cada um só olhando o caminho do Linux —
    por isso o DERVS não achava a chave no Windows. Agora existe um lugar só.

    NUNCA registre o retorno em log, mensagem de erro ou commit. Quem chama
    recebe o valor e é responsável por não deixá-lo escapar.
    """
    do_ambiente = os.environ.get(nome)
    if do_ambiente:
        return do_ambiente.strip()
    for caminho in caminhos_do_segredo():
        try:
            with open(caminho, encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if linha.startswith(nome + "="):
                        return linha.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return None

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

    # O microfone nasce aberto quando o app abre? Isto guarda a ÚLTIMA escolha
    # do dono no botão "Ei DERVS": desligou e fechou, abre desligado. Sem isto,
    # o botão não é um liga/desliga — é um lembrete que se apaga sozinho.
    # Padrão True porque nascer desligado já deixou o DERVS surdo uma vez
    # (01/09/2026) e o dono achou que ele estava ignorando.
    "escuta_ao_abrir": True,

    # MODO DE ESCUTA que vale ao abrir (briefing dervs-jarvis): "desligado" (microfone
    # fechado — o padrão), "atalho" (só abre enquanto Ctrl+Alt+Espaço está apertado)
    # ou "voz" (escuta o nome "DERVS"). Guarda a última escolha do dono; qualquer
    # valor torto cai em "desligado". Substitui `escuta_ao_abrir` na hora de abrir.
    "modo_escuta": "desligado",
    # Minutos sem uso até o microfone fechar sozinho (1 a 240). Não existe "nunca":
    # microfone esquecido aberto é o risco que esta chave impede.
    "escuta_auto_desligar_min": 10,

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

    # A COLA que vai junto do áudio, para o modelo saber o que esperar ANTES
    # de ouvir. Existe porque em 02/09/2026 o dono disse "não está me
    # entendendo direito". Medido no código: `dervs_transcrever.py` já lia esta
    # chave para mandar como `prompt` à OpenAI — mas ela não existia aqui, e
    # `carregar()` só copia do disco o que existe no PADRÃO. A dica era sempre
    # vazia e o campo NUNCA era enviado: o áudio ia para a nuvem sem uma pista
    # sequer de que é português do Brasil falado com um assistente chamado
    # DERVS. É a mesma cola usada pelo caminho local (dervs_stt_daemon.py):
    # uma fonte só, senão os dois ouvidos do DERVS entendem coisas diferentes.
    #
    # ESTE É O LUGAR de acrescentar os nomes próprios do dono — clientes,
    # empresas, pessoas, termos do ramo dele. Nome próprio que o modelo nunca
    # viu é o que ele mais erra, e a dica é o único jeito de ensiná-lo sem
    # treinar modelo nenhum. Vale tanto na nuvem quanto no local.
    "stt_dica_vocabulario": (
        "Transcrição em português do Brasil, com acentuação e pontuação "
        "corretas. É uma pessoa falando com um assistente de voz chamado "
        "DERVS — escrito sempre assim, em maiúsculas, e nunca 'Dervis', "
        "'Ders', 'Derbs' ou 'the RVS'. Frases típicas: 'DERVS, que horas "
        "são?', 'DERVS, que dia é hoje?', 'abre o Firefox', 'lista os "
        "arquivos', 'abre o ChatGPT', 'manda no WhatsApp', 'roda o nmap no "
        "alvo'. Vocabulário comum: e-mail, WhatsApp, site, aplicativo, "
        "ChatGPT, Claude, Codex, cofre, VPS, Dervs Root, 'pergunta pro Claude "
        "da VPS', 'pede pro Codex analisar o projeto', 'anota que', 'abre o "
        "cofre', navegador, OSINT, subdomínio, domínio, DNS, certificado, "
        "vulnerabilidade, servidor, repositório, GitHub, Docker, Postgres, "
        "planilha, orçamento, cliente, reunião, proposta, contrato, DERVS, "
        "Parrot, Windows. Números como 2026, R$ 1.500,00 e 10%."
    ),

    # O PORTEIRO: quem decide, NA MÁQUINA, se a fala foi com o DERVS. É ele que
    # permite deixar ligado o dia inteiro sem mandar o áudio do dia inteiro para
    # a nuvem. "local" = Whisper pequeno com aviso de vocabulário (medido: 14/14
    # em 0,49s). "porcupine" = detector dedicado, ainda não implementado — exige
    # conta gratuita no picovoice.ai. Ver dervs_porteiro.py.
    # "base" desde 16/10/2026: o "tiny" errou o nome nas 5 falas REAIS do dono (17:54-17:55 de
    # 15/10; só fora medido com voz sintética); o "base" acordou nas chamadas seguintes, ~1 s.
    "porteiro": "local",
    "porteiro_modelo": "base",
    # Guardar, no diário do porteiro (%LOCALAPPDATA%/dervs/porteiro.jsonl), o
    # TEXTO que ele ouviu em cada decisão? Padrão False: o diário só anota hora,
    # se acordou, nº de palavras e duração — o que foi dito na sala (reunião,
    # família) é justamente o que o porteiro existe para não deixar sair. Ligue
    # por uma semana se o DERVS estiver "ignorando" você e for preciso ver o
    # que o porteiro entendeu; depois desligue e apague o arquivo.
    "porteiro_registrar_texto": False,
    # CHAMADA ESTRITA: só acorda se o nome vier no COMEÇO da fala ("DERVS, ...",
    # "Ei DERVS", "OK DERVS"). Falar SOBRE ele ("vou mostrar o dervs pra ele")
    # não liga o agente. Foi pedido do dono: "não pode ativar do nada". Desligue
    # para voltar ao modo antigo, em que o nome valia em qualquer lugar da frase.
    "chamada_estrita": True,

    # Cérebro: "openai" (gpt-4.1-nano — ultrarrápido e barato, precisa de chave
    # em ~/voice/.env e internet) ou "claude" (CLI local, grátis na assinatura).
    # Se "openai" mas sem chave/internet, cai no Claude sozinho.
    "cerebro": "openai",
    # Modelo da OpenAI para o cérebro. É ELE que faz o teste de sanidade da
    # transcrição, decide perguntar em vez de chutar e monta o plano — ou seja,
    # é a peça que o dono sente como "está me entendendo" ou não.
    #
    # Era "gpt-4.1-nano", o mais fraco da família. Trocado por "gpt-4.1-mini" em
    # 02/09/2026, depois de o dono dizer "não está me entendendo direito".
    # MEDIDO em 01/09: o mini responde no MESMO tempo do nano (1,02 s) — a troca
    # não custa lentidão, só dinheiro, e o dono pediu "ultra rápido E preciso".
    # Custa ~4x o nano por chamada; no volume previsto continua da ordem de
    # centavos de dólar por mês. Voltar é trocar esta palavra.
    "cerebro_openai_modelo": "gpt-4.1-mini",

    # --- CONVERSA NATURAL (dervs_conversa.py) ---------------------------------
    # Ordem dos motores de voz direta; o primeiro que funcionar fica, e o DERVS
    # passa ao próximo sozinho ao bater limite, rede, chave ou teto de gasto.
    # Nomes: "gemini_live" (grátis), "cascata" (Groq + cérebro + voz em fluxo),
    # "openai_realtime" (premium, pago).
    "conversa_motores": ["gemini_live", "cascata"],
    "voz_gemini": "Charon",
    "conversa_realtime_modelo": "gpt-realtime-2.1-mini",
    "voz_realtime": "cedar",

    # Motor de voz: "openai" (voz de nuvem, a mais natural e com sotaque
    # brasileiro de verdade; custa centavos por fala e precisa de internet),
    # "kokoro" (humana, offline, grátis — a RESERVA da nuvem), "piper"
    # (sintética, instantânea) ou "xtts" (humana, mas lenta). "gemini" (PADRÃO desde 16/10/2026):
    # a MESMA voz da conversa natural (voz_gemini, Charon), grátis, e sem reserva em outra voz —
    # o dono ouvia "duas vozes" (cedar, Charon e o Kokoro robótico quando a nuvem demorava).
    "motor": "gemini",

    # Voz da nuvem (quando motor="openai"): ash, onyx, echo, sage, verse, ballad
    # (masculinas/neutras) ou coral, nova, shimmer (femininas).
    # "cedar" (masculina, a mais próxima de um JARVIS) e "marin" são as de maior qualidade,
    # recomendadas pela própria OpenAI. Outras masculinas: onyx, ash, echo, fable, verse.
    "voz_openai": "cedar",
    "voz_openai_modelo": "gpt-4o-mini-tts",
    # Aceleração da voz da nuvem SEM mudar o tom (a OpenAI não tem parâmetro de
    # velocidade). 1.0 = como a API entrega; 1.25 = bem mais ágil; vai de 1.0 a 1.6.
    "voz_openai_tempo": 1.25,

    # Quando o DERVS pede o seu OK antes de agir: "grave" (padrão) só pede em coisa
    # destrutiva, que toca servidor/rede, que lê segredo ou que dirige o seu Chrome
    # logado; o resto ele anuncia ("Entendi: vou...") e faz. "sempre" pede em todo plano.
    "confirmar_plano": "grave",

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
    # Só mude se você usa outro navegador/perfil. Vazio = o do sistema (no
    # Windows, %LOCALAPPDATA%/Google/Chrome/User Data; em Linux,
    # ~/.config/google-chrome — ver `dervs_browser._perfil_chrome_padrao`).
    # Antes o padrão era o caminho de Linux, gravado no config.json de quem
    # rodou o DERVS no Windows: o Chrome abria com um perfil VAZIO, sem login.
    "navegador_perfil_chrome": "",
    "navegador_perfil_nome": "Default",
    # Modelo que decide cada clique. Vazio = usa o mesmo do cérebro (o mais
    # barato). Suba só se a navegação exigir mais esperteza.
    "navegador_modelo": "",

    # --- Painel/HUD (fase 1 da esteira dervs-painel-completo) ---
    # Endereço do outro projeto do dono, "DERVS App" (garcia-goncalves/dervs,
    # o painel de segurança/monitoramento dos projetos dele) — o botão "Abrir
    # DERVS App" do HUD abre isto no navegador. Só ABRE a página; nenhuma
    # outra integração (login, comando, cofre) existe nesta fase — ver
    # docs/esteira/dervs-painel-completo/briefing.md, "fora_de_escopo".
    "dervs_app_url": "http://localhost:4777",

    # --- Ponte com o DERVS web (dervs_ponte_web.py) ---
    # Só saída: o VOZ manda seu estado e busca recados do painel. Usa o token de
    # computador pareado de ~/.dervs/agente.json; sem token, não liga (e diz por quê).
    "ponte_web_ligada": True,
    "ponte_web_alvo": "https://dervs.com.br",
    "ponte_web_intervalo_s": 60,

    # --- Claude Code dentro do painel (onda B da central do PC) ---
    # Perfil da sessão do Claude Code: "dono" carrega o ~/.claude inteiro
    # (CLAUDE.md, skills, agentes, MCPs, plugins) + o projeto; "equipe" carrega só
    # o harness do projeto, para as regras valerem iguais em qualquer PC. Independe
    # de "cerebro": o painel usa o Claude Code por texto de qualquer jeito.
    "claude_perfil": "dono",
    # --- autonomia (esteira dervs-autonomia, 02/10/2026) ---
    # O que o DERVS pode fazer sozinho, categoria por categoria: "analisa" (só
    # olha), "pergunta" (cartão no painel) ou "sozinho". Só REDUZ poder: o teto do
    # dervs_safety vale sempre, e "apagar" e "servidor" nunca chegam a "sozinho".
    # Edite pelo painel "O que o DERVS pode fazer"; valor torto volta ao padrão.
    "permissoes": dervs_permissoes.normalizar(None),
    # Teto de gasto por dia (US$) em API paga: voz, transcrição e cérebro OpenAI.
    # O Claude da assinatura não conta. Ao atingir, o DERVS volta para o Claude.
    "teto_gasto_dia_usd": 3.0,
    # Pastas de projeto onde o DERVS pode criar/alterar arquivos SEM perguntar, quando
    # "Criar e alterar arquivos" está em "Faz sozinho". Caminhos completos. Não vale raiz
    # de disco, o perfil, AppData nem pasta que os contenha; fora delas ele sempre pergunta.
    "pastas_de_projeto": [],
    # Cofre de notas (segundo cérebro, `dervs_cofre.py`). Vazio = a pasta DERVS-Cofre na pasta do
    # usuário (fora de Documentos desde 16/10/2026: o Acesso Controlado a Pastas barrava). O conteúdo nunca sai do computador sem o dono pedir; `privado/` jamais.
    "cofre_pasta": "",
    # Notas NÃO privadas que casam com a fala do dono (no máximo 3, 1.500 caracteres) acompanham a
    # pergunta ao cérebro da OpenAI. DESLIGADO por padrão: é texto pessoal indo a um terceiro, então
    # só o dono liga (`true`). `privado/` nunca vai, nem ligado.
    "cofre_no_cerebro": False,
    # Nomes (ou pedaços) de sessões do PuTTY que o DERVS NUNCA usa por voz, além dos projetos que
    # "não se tocam" (veja `dervs_dp.BLOQUEADAS_PADRAO`). Ex.: ["cliente-x"].
    "ssh_sessoes_bloqueadas": [],
    # Codex (ChatGPT Plus, `dervs_codex.py`): mais um executor de código por voz. Caminho vazio = o
    # DERVS procura o codex.exe do app a cada uso (a pasta do WindowsApps muda a cada atualização).
    # Esforço: low | medium | high (vai em `-c model_reasoning_effort=`).
    "codex_ligado": True,
    "codex_caminho": "",
    "codex_esforco": "medium",
    # Reserva: pedido de ANÁLISE feito com o Claude ocupado vai ao Codex (só leitura, com aviso
    # falado). Pedido de mexer em código nunca é desviado. `false` = o DERVS só diz que está ocupado.
    "codex_reserva": True,
    # Busca por SIGNIFICADO no cofre ("dentista" acha "consulta odontológica"). DESLIGADA por padrão:
    # liga um modelo local (~240 MB de download na 1ª vez, ~600 MB de RAM enquanto em uso) e exige
    # `pip install -r requirements-semantica.txt`. Tudo roda no PC; nada de nota sai por causa dela.
    "cofre_semantica": False,
    # Trava de perfil de voz (`dervs_locutor.py`): só a voz de um perfil ATIVO segue para o motor
    # de conversa. `locutor_limiar` é a similaridade mínima (0 a 1, cosseno) para aceitar a voz;
    # calibrado com o ERes2Net em 15/10/2026. `locutor_ligado=false` desliga a trava.
    "locutor_limiar": 0.5,
    "locutor_ligado": True,

    # Árbitro de vez (`dervs_turno.py`): decide quando você TERMINOU de falar, em vez de cortar na
    # primeira pausa. Silêncio >= turno_silencio_min_ms faz o modelo Smart Turn avaliar a frase; se a
    # chance de "acabou" for >= turno_prob_fim, é a vez dele; senão espera mais, até turno_espera_max_s.
    "turno_prob_fim": 0.5,
    "turno_espera_max_s": 3.0,
    "turno_silencio_min_ms": 300,

    # Conversa natural (`dervs_conversa_natural.py`): depois de acordar, a voz direta (motor da
    # lista `conversa_motores`) atende em vez do caminho antigo (transcrever, cérebro, voz). Sem
    # chave de nenhum motor, ou se a conversa cair, o DERVS volta sozinho ao caminho antigo.
    "conversa_natural": True,
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
    # só True/False valem; qualquer outra coisa (texto, número) cai no padrão,
    # senão um "false" entre aspas ligaria a escuta por ser string não-vazia.
    if not isinstance(conf.get("escuta_ao_abrir"), bool):
        conf["escuta_ao_abrir"] = PADRAO["escuta_ao_abrir"]
    from dervs_modos_escuta import normalizar_minutos, normalizar_modo
    conf["modo_escuta"] = normalizar_modo(conf.get("modo_escuta"))
    conf["escuta_auto_desligar_min"] = normalizar_minutos(conf.get("escuta_auto_desligar_min"))
    if conf.get("stt") not in ("openai", "local"):
        conf["stt"] = PADRAO["stt"]
    if not isinstance(conf.get("stt_openai_modelo"), str) or not conf["stt_openai_modelo"]:
        conf["stt_openai_modelo"] = PADRAO["stt_openai_modelo"]
    # Dica só de espaço em branco é pior que dica nenhuma: vira um campo
    # `prompt` vazio na requisição, e o modelo perde a pista em vez de ganhar.
    if not isinstance(conf.get("stt_dica_vocabulario"), str) \
            or not conf["stt_dica_vocabulario"].strip():
        conf["stt_dica_vocabulario"] = PADRAO["stt_dica_vocabulario"]
    # Só "local" está implementado. Quando o Porcupine existir de verdade, ele
    # entra nesta lista — enquanto não existir, aceitá-lo aqui seria dizer ao
    # dono que ligou uma coisa que não liga.
    if conf.get("porteiro") not in ("local",):
        conf["porteiro"] = PADRAO["porteiro"]
    if not isinstance(conf.get("porteiro_registrar_texto"), bool):
        conf["porteiro_registrar_texto"] = PADRAO["porteiro_registrar_texto"]
    if not isinstance(conf.get("chamada_estrita"), bool):
        conf["chamada_estrita"] = PADRAO["chamada_estrita"]
    if not isinstance(conf.get("porteiro_modelo"), str) or not conf["porteiro_modelo"]:
        conf["porteiro_modelo"] = PADRAO["porteiro_modelo"]
    if conf.get("cerebro") not in ("openai", "claude"):
        conf["cerebro"] = PADRAO["cerebro"]
    if not isinstance(conf.get("cerebro_openai_modelo"), str) or not conf["cerebro_openai_modelo"]:
        conf["cerebro_openai_modelo"] = PADRAO["cerebro_openai_modelo"]
    # --- conversa natural ---
    motores = conf.get("conversa_motores")
    if not isinstance(motores, list):
        motores = []
    motores = [m for i, m in enumerate(motores)
               if m in ("gemini_live", "cascata", "openai_realtime") and m not in motores[:i]]
    conf["conversa_motores"] = motores or list(PADRAO["conversa_motores"])
    if not isinstance(conf.get("voz_gemini"), str) or not conf["voz_gemini"].isalpha()             or len(conf["voz_gemini"]) > 30:
        conf["voz_gemini"] = PADRAO["voz_gemini"]
    if not isinstance(conf.get("conversa_realtime_modelo"), str)             or not conf["conversa_realtime_modelo"]:
        conf["conversa_realtime_modelo"] = PADRAO["conversa_realtime_modelo"]
    if conf.get("voz_realtime") not in ("alloy", "ash", "ballad", "coral", "echo", "sage",
                                        "shimmer", "verse", "marin", "cedar"):
        conf["voz_realtime"] = PADRAO["voz_realtime"]
    if conf.get("motor") not in ("gemini", "openai", "kokoro", "piper", "xtts"):
        conf["motor"] = PADRAO["motor"]
    if conf.get("voz_openai") not in ("alloy", "ash", "ballad", "coral", "echo", "fable",
                                      "nova", "onyx", "sage", "shimmer", "verse", "marin", "cedar"):
        conf["voz_openai"] = PADRAO["voz_openai"]
    if not isinstance(conf.get("voz_openai_modelo"), str) or not conf["voz_openai_modelo"]:
        conf["voz_openai_modelo"] = PADRAO["voz_openai_modelo"]
    if conf.get("confirmar_plano") not in ("grave", "sempre"):
        conf["confirmar_plano"] = PADRAO["confirmar_plano"]
    tempo = conf.get("voz_openai_tempo")
    if isinstance(tempo, bool) or not isinstance(tempo, (int, float)) or not 1.0 <= tempo <= 1.6:
        conf["voz_openai_tempo"] = PADRAO["voz_openai_tempo"]
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
    if not isinstance(conf.get("navegador_perfil_chrome"), str):
        conf["navegador_perfil_chrome"] = PADRAO["navegador_perfil_chrome"]
    # Cura o config.json antigo: o padrão de Linux gravado no Windows não existe
    # aqui e seria obedecido no lugar do perfil de verdade do Chrome.
    if sys.platform == "win32" and conf["navegador_perfil_chrome"].replace(
            "\\", "/").rstrip("/") == "~/.config/google-chrome":
        conf["navegador_perfil_chrome"] = ""
    if not isinstance(conf.get("navegador_perfil_nome"), str) or not conf["navegador_perfil_nome"]:
        conf["navegador_perfil_nome"] = PADRAO["navegador_perfil_nome"]
    if not isinstance(conf.get("navegador_modelo"), str):
        conf["navegador_modelo"] = PADRAO["navegador_modelo"]
    url = conf.get("dervs_app_url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        # nunca deixa passar algo que `shell.openExternal` (main.js) possa
        # tratar como caminho de arquivo local ou outro protocolo — o botão
        # só serve para abrir uma página web.
        conf["dervs_app_url"] = PADRAO["dervs_app_url"]
    if not isinstance(conf.get("ponte_web_ligada"), bool):
        conf["ponte_web_ligada"] = PADRAO["ponte_web_ligada"]
    if not isinstance(conf.get("ponte_web_alvo"), str) or not conf["ponte_web_alvo"].startswith(
            ("http://", "https://")):
        conf["ponte_web_alvo"] = PADRAO["ponte_web_alvo"]
    iv = conf.get("ponte_web_intervalo_s")
    if isinstance(iv, bool) or not isinstance(iv, (int, float)) or not 10 <= iv <= 3600:
        conf["ponte_web_intervalo_s"] = PADRAO["ponte_web_intervalo_s"]
    if conf.get("claude_perfil") not in ("dono", "equipe"):
        conf["claude_perfil"] = PADRAO["claude_perfil"]
    conf["permissoes"] = dervs_permissoes.normalizar(conf.get("permissoes"))
    if not isinstance(conf.get("cofre_pasta"), str) or len(conf["cofre_pasta"]) > 300 or (
            conf["cofre_pasta"] and not dervs_permissoes.raiz_valida(conf["cofre_pasta"])):
        conf["cofre_pasta"] = PADRAO["cofre_pasta"]      # raiz de disco, perfil, AppData, UNC: volta ao padrão
    bloq = conf.get("ssh_sessoes_bloqueadas")
    conf["ssh_sessoes_bloqueadas"] = [b.strip()[:60] for b in bloq if isinstance(b, str) and b.strip()][:40] \
        if isinstance(bloq, list) else []
    if not isinstance(conf.get("cofre_no_cerebro"), bool):
        conf["cofre_no_cerebro"] = PADRAO["cofre_no_cerebro"]
    if not isinstance(conf.get("codex_ligado"), bool):
        conf["codex_ligado"] = PADRAO["codex_ligado"]
    if not isinstance(conf.get("codex_caminho"), str) or len(conf["codex_caminho"]) > 300:
        conf["codex_caminho"] = PADRAO["codex_caminho"]
    if conf.get("codex_esforco") not in ("low", "medium", "high"):
        conf["codex_esforco"] = PADRAO["codex_esforco"]
    if not isinstance(conf.get("codex_reserva"), bool):
        conf["codex_reserva"] = PADRAO["codex_reserva"]
    if not isinstance(conf.get("cofre_semantica"), bool):
        conf["cofre_semantica"] = PADRAO["cofre_semantica"]
    if not isinstance(conf.get("locutor_ligado"), bool):
        conf["locutor_ligado"] = PADRAO["locutor_ligado"]
    lim = conf.get("locutor_limiar")
    if isinstance(lim, bool) or not isinstance(lim, (int, float)) or not 0.0 <= lim <= 1.0:
        conf["locutor_limiar"] = PADRAO["locutor_limiar"]
    else:
        conf["locutor_limiar"] = float(lim)
    pastas = conf.get("pastas_de_projeto")
    if not isinstance(pastas, list):
        pastas = []
    conf["pastas_de_projeto"] = [x for x in pastas[:20] if dervs_permissoes.raiz_valida(x)]
    teto = conf.get("teto_gasto_dia_usd")
    if isinstance(teto, bool) or not isinstance(teto, (int, float)) or not 0.01 <= teto <= 1000:
        conf["teto_gasto_dia_usd"] = PADRAO["teto_gasto_dia_usd"]
    for chave, minimo, maximo in (("turno_prob_fim", 0.0, 1.0), ("turno_espera_max_s", 0.5, 10.0),
                                  ("turno_silencio_min_ms", 100, 2000)):
        v = conf.get(chave)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not minimo <= v <= maximo:
            conf[chave] = PADRAO[chave]
    # cada um é válido sozinho, mas a espera máxima tem de passar do silêncio mínimo (+300 ms, o passo
    # da reavaliação); senão o árbitro fecha a vez sem consultar o modelo. Incoerente: volta os dois.
    if conf["turno_espera_max_s"] <= conf["turno_silencio_min_ms"] / 1000 + 0.3:
        conf["turno_espera_max_s"] = PADRAO["turno_espera_max_s"]
        conf["turno_silencio_min_ms"] = PADRAO["turno_silencio_min_ms"]
    # --- conversa natural: liga/desliga ---
    if not isinstance(conf.get("conversa_natural"), bool):
        conf["conversa_natural"] = PADRAO["conversa_natural"]
    return conf


# Trava do processo inteiro: o painel, a ponte e a voz gravam chaves de threads diferentes, e
# ler-mudar-gravar sem ela perdia a chave de quem chegasse segundo ao disco.
_TRAVA = threading.RLock()
_AVISOU_CORROMPIDO = False
_CACHE = {"chave": None, "conf": None}      # carregar() só relê o disco se o arquivo mudou


def _assinatura():
    """(caminho, mtime, tamanho) do config.json; mtime/tamanho None se ele não existe."""
    try:
        st = os.stat(CONFIG_PATH)
        return (CONFIG_PATH, st.st_mtime_ns, st.st_size)
    except OSError:
        return (CONFIG_PATH, None, None)


def _ler_disco():
    """(dict do disco ou None, corrompido). Arquivo ausente não é corrompido; JSON torto,
    vazio ou que não é objeto é."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            do_disco = json.load(f)
    except FileNotFoundError:
        return None, False
    except (json.JSONDecodeError, OSError, ValueError):
        return None, True
    if not isinstance(do_disco, dict):
        return None, True
    return do_disco, False


def _avisar_corrompido():
    global _AVISOU_CORROMPIDO
    if not _AVISOU_CORROMPIDO:
        _AVISOU_CORROMPIDO = True
        sys.stderr.write("dervs: o config.json está ilegível; uso os valores padrão e, ao gravar uma "
                         "escolha, guardo antes uma cópia dele (config.json.corrompido-<data>).\n")


def carregar() -> dict:
    """Lê o config.json e devolve o dict completo (padrão + o que o dono mudou).
    Nunca levanta exceção: config faltando ou torta cai no padrão (e a torta avisa, uma vez).
    O resultado é cacheado enquanto o arquivo não muda; cada chamada recebe uma cópia."""
    with _TRAVA:
        chave = _assinatura()
        if _CACHE["chave"] == chave and _CACHE["conf"] is not None:
            return copy.deepcopy(_CACHE["conf"])
        conf = dict(PADRAO)
        do_disco, corrompido = _ler_disco()
        if corrompido:
            _avisar_corrompido()
        elif do_disco is not None:
            conf.update({k: v for k, v in do_disco.items() if k in PADRAO})
        conf = _validar(conf)
        _CACHE["chave"], _CACHE["conf"] = chave, copy.deepcopy(conf)
        return conf


def _guardar_copia_do_corrompido() -> bool:
    """Copia o config.json ilegível para config.json.corrompido-<data>. False se não deu."""
    destino = "%s.corrompido-%s" % (CONFIG_PATH, time.strftime("%Y%m%d-%H%M%S"))
    n = 1
    while os.path.exists(destino):               # duas quedas no mesmo segundo: não sobrescreve
        n += 1
        destino = "%s.corrompido-%s-%d" % (CONFIG_PATH, time.strftime("%Y%m%d-%H%M%S"), n)
    try:
        shutil.copy2(CONFIG_PATH, destino)
        return True
    except OSError:
        return False


def gravar(chave: str, valor) -> bool:
    """Grava UMA chave no config.json, preservando o resto do arquivo.

    Serve para o app guardar escolha feita na tela (o botão da escuta), sem
    obrigar o dono a editar arquivo nenhum. Lê o que está no disco, muda só a
    chave pedida e regrava — assim uma opção que o dono editou na mão não é
    apagada por um clique de botão. Tudo sob a trava do processo.

    Arquivo ilegível: guarda antes uma cópia (config.json.corrompido-<data>) e só então grava a
    chave sobre os valores-padrão; se a cópia falhar, recusa — nada é apagado em silêncio.

    Devolve False e segue em silêncio se não deu para gravar: disco cheio ou
    pasta somindo não pode derrubar o DERVS por causa de um botão.
    """
    if chave not in PADRAO:
        return False
    with _TRAVA:
        try:
            do_disco, corrompido = _ler_disco()
            if corrompido:
                _avisar_corrompido()
                if not _guardar_copia_do_corrompido():
                    return False
                do_disco = dict(PADRAO)
            elif do_disco is None:
                do_disco = {}
            do_disco[chave] = valor
            os.makedirs(CONFIG_DIR, exist_ok=True)
            # Escreve ao lado e troca de nome no fim. Abrir o próprio config.json em
            # "w" o ESVAZIA antes de haver conteúdo novo: morrer nesse instante
            # (queda de energia, processo morto) deixava o arquivo truncado, e aí
            # `carregar()` engolia o erro e voltava TUDO ao padrão — a voz, a
            # velocidade e o que o dono editou na mão sumiam calados. `os.replace`
            # é atômico: ou está o arquivo velho inteiro, ou o novo inteiro.
            temporario = CONFIG_PATH + ".tmp"
            try:
                with open(temporario, "w", encoding="utf-8") as f:
                    json.dump(do_disco, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporario, CONFIG_PATH)
            except (OSError, ValueError, TypeError):
                try:
                    os.remove(temporario)
                except OSError:
                    pass
                raise
            _CACHE["chave"] = None               # o arquivo mudou: a próxima leitura revalida
            return True
        except (OSError, ValueError, TypeError):
            return False


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
