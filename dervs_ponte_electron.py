#!/usr/bin/env python3
"""DERVS — a ponte com a cara nova: o Electron, subido como processo filho.

O Python continua dono de tudo (microfone, cérebro, trilhos de risco); o
Electron só desenha. A conversa entre os dois é a mais simples que resolve:
uma mensagem por linha, JSON UTF-8, terminada em quebra de linha — o mesmo
espírito de protocolo dos daemons (`dervs_stt_daemon.py`, cabeçalho) e das três
escutas do `QProcess` do STT (`dervs.py`, saída/erro/morte): sem as três,
volta o "DERVS surdo e calado".

Electron fala com o Python pelo `stdout` do filho — essa direção funciona
sem problema. Python fala com o Electron por um SOQUETE TCP local (só
`127.0.0.1`, porta escolhida pelo sistema, passada ao Electron como
argumento de linha de comando), **não** pelo `stdin` do filho.

Por quê: um app Electron (sem console, como todo app gráfico do Windows)
recebe um "fim de stdin" FALSO quase na hora, mesmo com o processo pai
vivo e escrevendo — é uma limitação do Chromium/Electron no Windows, não
um jeito errado de escrever. Confirmado em bancada em 17/09/2026: um
Electron mínimo, sem nenhuma linha do DERVS, reproduz o mesmo "fim falso"
ao ler `stdin` herdado de um `subprocess.Popen` do Python; rodando o
MESMO binário como Node puro (`ELECTRON_RUN_AS_NODE=1`, que tem console)
o problema some. Depois do "fim falso", o `stdin` também para de entregar
dado novo — não dá para só ignorar o evento e seguir lendo. Daí o soquete:
mesmo padrão (`127.0.0.1`, nunca a rede) já comprovado em
`dervs_instancia.py` para a trava de instância única.

O `stderr` do filho é lido aqui e reescrito no `sys.stderr` deste processo,
com o prefixo `electron:` — falha nunca é engolida.

Verbos Python → Electron (só estes):
  estado  {"valor", "texto", "apoio"} — só quando o estado muda.
  volume  {"valor"}                   — 0.0 a 1.0, estrangulado (ver abaixo).
  fala    {"papel", "texto"}          — uma linha nova de conversa.
  plano   {"passos", "nivel", "pergunta", "cartao_id"} — lista vazia limpa
            o cartão. Cada passo em `passos` traz `rotulo`/`nivel` (contrato
            original); um cartão de PASSO ÚNICO (risco de um passo
            destrutivo dentro do plano, não o plano inteiro) também traz,
            por extensão do protocolo: `comando` (texto do comando),
            `precisa_autorizacao` (bool — toca rede de fora ou lê arquivo
            de segredo), `texto_autorizacao` (a frase certa para a caixa) e
            `dupla_confirmacao` (bool — exige dois "confirmar" seguidos).
            `cartao_id` é extensão do protocolo (correção de concorrência):
            identifica de forma única o cartão que espera resposta — sem
            ele, duas mensagens de resposta em trânsito não dá para saber a
            qual cartão cada uma se refere (ver `_confirmar_do_electron` em
            `dervs_electron.py`). Ausente/`None` para cartões que não
            esperam resposta (ex.: a lista vazia que limpa a tela).
            Consumidor que só lê `rotulo`/`nivel` continua funcionando sem
            mudar nada.
  mostrar {}                          — traz o painel (a janela única) para frente.
  microfone {"ligado"}                — extensão do protocolo: a escuta está
            aberta (true) ou fechada (false). Guarda só o último valor até o
            `pronto`, como `estado` — o botão do HUD nasce já no lado certo.
  sistema {"cpu", "ram", "disco_livre_gb", "disco_total_gb"} — extensão do
            protocolo (fase 1 da esteira `dervs-painel-completo`): leitura
            real da máquina, mandada a cada ~2s por `dervs_sistema.py`. Ausente
            (nunca mandado) enquanto `psutil` não estiver instalado — o painel
            de sistema do HUD some em silêncio, nada mais quebra.
  diario  {"ouvidas", "acordou"}      — extensão do protocolo (quarta rodada):
            o resumo de HOJE do diário do porteiro (inteiros), mandado a cada
            ~30 s por `dervs_diario.py`. Só metadados — nunca texto. Não guarda
            o último valor: a próxima leitura chega sozinha. O cartão do HUD
            só aparece depois da primeira.
  gasto   {"total", "tts", "stt", "cerebro"} — extensão do protocolo (painel
            grande, 28/09/2026): gasto ESTIMADO de hoje em dólar, lido de
            `gasto.jsonl` por `dervs_painel.py`. Só depois do `pronto`; valor
            igual ao último não é reenviado.
  cofre   {"notas", "pasta"} — extensão do protocolo (segundo cérebro, 05/10/2026): quantas
            notas o cofre tem e onde ele mora (a pasta fica só no processo principal, para o
            botão "abrir"; o renderer só vê a contagem). Só depois do `pronto`; igual ao último
            não é reenviado.
  codex   {"estado", "texto"} — extensão do protocolo (Codex, 06/10/2026): a linha de estado do
            Codex no painel ("Codex: pronto (ChatGPT)" ou o motivo de não estar). `estado` é um de
            chatgpt | chave_api | nao_logado | desligado | falhou. Só depois do `pronto`; igual ao
            último não é reenviado.
  agenda  {"itens": [{"quando", "quando_txt", "texto"}]} — lembretes pendentes
            reais (`dervs_lembretes.Agenda`). Lista vazia é mensagem válida.
  diario_entradas {"entradas": [{"hora", "acordou", "palavras", "duracao_s"}]}
            — últimas frases que o porteiro ouviu hoje; só metadados, nunca texto.
  voz     {"motor": "nuvem" | "local"} — qual voz está valendo (cai no local
            quando a nuvem falha).
  acao    {"papel", "texto"}          — uma ação do DERVS (resultado, erro ou
            passo que ele anunciou) para a lista "últimas ações" do painel.
  sistema também pode trazer `rede_baixa_kbs` e `rede_sobe_kbs` (KB/s, opcionais).
  reuniao {"restante_s"}              — extensão do protocolo (quarta rodada):
            segundos que faltam do modo reunião (inteiro), ou `null` quando
            não há reunião (terminou ou foi cancelada). Mandado a cada segundo
            enquanto a reunião durar; o temporizador mora no Python (`Motor`).
  claude_delta {"texto"}              — onda B (Claude Code no painel): um pedaço
            da resposta, em streaming. Texto do Claude é DADO hostil: a tela só
            usa `textContent`.
  claude_ferramenta {"nome", "resumo"} — o Claude usou uma ferramenta (linha de
            progresso na conversa).
  claude_pedido {"id", "ferramenta", "resumo", "entrada_cortada", "nivel",
            "expira_s", "escondidos", "rede"} — o Claude pede permissão. O `id`
            vale UMA resposta; `escondidos` é quantos caracteres NÃO couberam na
            tela (a tela avisa); `rede` marca o que sai deste PC.
  central {…}                        — onda D (Central do PC): a visão da última
            análise (nota 0–100, descontos, resumo, discos, eventos...), já
            cortada para a tela (`dervs_central_painel.visao_para_tela`).
  central_progresso {"coletor", "feitos", "total"} — andamento da análise.
  central_relatorio {"relatorio", "cartao"} — proposta de limpeza montada pelo
            motor de aprovação, com o CARTÃO (a senha do clique). Só vai para a
            tela; nunca para o Claude.
  central_resultado {"ok", "motivo", "itens", …} — o que a aprovação, a limpeza
            ou o desfazer fez (ou recusou, com o motivo).
  integracao {"parte", …}            — a tela Integração (cérebro, painel web, terminal SSH):
            `parte` = cerebros | web | fila | avisos | ssh | ssh_cartao | ssh_resultado |
            ssh_cancelado | mensagem. Tudo texto de terceiro: a tela só usa `textContent`.
  permissoes {"parte", …}            — a tela "O que o DERVS pode fazer": `parte` = estado | mensagem.
  vozes {"lista"?, "estado"?, "gravando"?, "resultado"?} — perfis de voz da conversa natural:
            lista [{nome, papel, ativo}], estado {motor_ativo, locutor_ativo, perfis_ativos,
            locutor_aviso}, gravando 0..1 (progresso da gravação), resultado {ok, erro?}.
  claude_fim {"ok", "custo", "erro"}  — o turno acabou. `custo` é o equivalente
            em dólar da assinatura (medida, não cobrança).

Verbos Electron → Python (o mínimo que o comportamento de hoje já faz):
  pronto  — a janela carregou. Antes disso, `estado` e `volume` ficam
            guardados (só o último de cada) e são despachados quando ele
            chega — o mesmo padrão do `READY` dos daemons.
  sair    — "Sair do DERVS" da bandeja.
  microfone {"ligar": bool}           — botão liga/desliga do HUD. Só o
            booleano de verdade vale (mesma checagem estrita de `autorizado`):
            string, número ou null viram linha ignorada no stderr.
  modo_escuta {"modo": "desligado"|"atalho"|"voz"} — seletor de modos do
            painel (Onda A). Só um dos três textos vale; qualquer outro valor
            vira linha ignorada no stderr.
  reuniao {"ligar": bool}             — botão "Reunião 1h": `true` fecha o
            microfone por 1 hora e reabre sozinho; `false` cancela e reabre
            na hora. Booleano estrito, como `microfone`.
  plano   {"resposta": "confirmar" | "cancelar", "autorizado": bool,
            "cartao_id"} — botão do cartão de plano. `autorizado` é
            extensão do protocolo: reflete a caixa "Tenho autorização"
            marcada ou não quando o cartão em tela é um passo com
            `precisa_autorizacao`; qualquer valor que não seja o booleano
            `True` vira `False` (checagem estrita — string "false" ou
            outro valor truthy do JSON não destrava nada). `cartao_id` é
            extensão do protocolo: ecoa o id do cartão a que esta resposta
            se refere — quem decide se ainda vale é `dervs_electron.py`.
  claude_perguntar {"texto"}          — onda B: pergunta digitada na caixa do
            painel. 1 a 8000 caracteres; fora disso, ignorada.
  claude_parar                        — botão Parar.
  claude_resposta {"id", "permitir", "cartao_id"} — resposta ao `claude_pedido`.
            `permitir` só vale se for o booleano de verdade (mesma checagem
            estrita de `autorizado`); `id` é texto não vazio. Quem decide se o
            id ainda vale é `dervs_claude_code.py` (cada id vale uma vez).
  claude_nova_conversa                — botão Nova conversa.
  central_pedir · central_analisar · central_propor_limpeza — sem campos.
  central_aprovar {"relatorio_id", "ids", "cartao", "dupla"} — o CLIQUE do dono:
            só a lista explícita de itens marcados; `dupla` lista os de risco alto.
  central_desfazer {"desfazer_id"}    — devolve um item da quarentena.
  central_explicar {"codigo"}         — manda UM item da nota ao Claude.
  integracao_pedir                    — a tela abriu: manda o estado de todos os blocos.
  integracao_cerebro {"nome"}         — escolhe o cérebro (claude_code | hermes).
  integracao_dispensar {"id"}         — dispensa um pedido da fila do painel web.
  integracao_conserto {"aviso_id"}    — "Pedir conserto" de UM aviso (id local, não o do alerta).
  integracao_ssh_rodar {"apelido", "comando"} — terminal SSH: leitura roda, o resto vira cartão.
  integracao_ssh_confirmar {"proposta_id", "segunda": true} — a segunda confirmação do cartão.
  integracao_ssh_cancelar {"proposta_id"} — desiste do cartão.
  permissoes_pedir                    — a tela abriu: manda o estado das permissões.
  permissoes_definir {"categoria", "nivel"} — muda o nível de UMA categoria.
  permissoes_teto {"valor"}           — muda o teto diário de gasto (US$ 0,01 a 1000).
  vozes_pedir                         — a tela abriu: manda a lista de perfis e o estado.
  vozes_gravar {"nome", "papel"}      — grava ~30 s do microfone e cadastra o perfil.
  vozes_ativar {"nome", "ativo"}      — liga/desliga um perfil.
  vozes_apagar {"nome"}               — apaga o perfil (a pasta inteira).

Regras duras (valem para os dois lados da ponte, e este arquivo cumpre a
parte do Python):
  - linha que não é JSON válido, verbo desconhecido ou campo faltando é
    ignorada e vira uma linha no stderr — nunca derruba o processo;
  - linha maior que 64 KiB é descartada (mesmo espírito do `_LIMITE_LINHA`
    de `dervs_instancia.py`); texto de conversa é cortado a 4000 caracteres;
  - `volume` é estrangulado a no máximo 20 mensagens por segundo (50 ms),
    arredondado em 2 casas, e valor repetido não é reenviado — a `Escuta`
    produz ~33 quadros por segundo (`dervs_listen.py`), e sem estrangular a
    régua de CPU é queimada só com JSON;
  - a escrita é thread-safe: quem manda mensagem são a thread da tela, a
    thread do Qt vinda da `Escuta` e a thread de fala do `dervs_tts` — três
    donos do mesmo `stdin`;
  - o filho sobe com `CREATE_NO_WINDOW` no Windows — sem isso volta a "janela
    preta" já corrigida.
"""
import hmac
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time

from dervs_modos_escuta import MODOS as MODOS_DE_ESCUTA

WINDOWS = sys.platform == "win32"

_LIMITE_LINHA = 64 * 1024      # 64 KiB — linha maior que isso é descartada
_PRAZO_ESCRITA = 2.0           # s — write no soquete do Electron que não lê
_PRAZO_TOKEN = 2.0             # s — para a primeira linha (o segredo) chegar
VARIAVEL_DA_FICHA = "DERVS_PONTE_TOKEN"   # o mesmo nome em electron/main.js
_LIMITE_TEXTO = 4000           # texto livre é cortado antes de ser enviado
_LIMITE_PLANO = 60000          # caracteres — teto abaixo de _LIMITE_LINHA,
                                # para sobrar folga para o resto do JSON
_LIMITE_LISTA = 50             # itens de agenda/diário mandados ao painel
_LIMITE_ITEM = 200             # texto de um item de agenda (título hostil)
_LIMITE_PERGUNTA = 8000        # caracteres da caixa de texto do Claude Code
_LIMITE_ERRO_CLAUDE = 300      # mensagem de erro de um turno do Claude
_LIMITE_RESUMO_PEDIDO = 500    # o comando/caminho do pedido de permissão aparece inteiro até aqui
_LIMITE_ENTRADA_PEDIDO = 1000  # o resto dos parâmetros (o corte é avisado em `escondidos`)
_VERBOS_CENTRAL = ("central_pedir", "central_analisar", "central_propor_limpeza",
                   "central_aprovar", "central_desfazer", "central_explicar")
_VERBOS_INTEGRACAO = ("integracao_pedir", "integracao_cerebro", "integracao_dispensar",
                      "integracao_conserto", "integracao_ssh_rodar", "integracao_ssh_confirmar",
                      "integracao_ssh_cancelar")
_VERBOS_PERMISSOES = ("permissoes_pedir", "permissoes_definir", "permissoes_teto")
_VERBOS_VOZES = ("vozes_pedir", "vozes_gravar", "vozes_ativar", "vozes_apagar")
_PAPEIS_VOZ = ("dono", "convidado")
_LIMITE_NOME_VOZ = 40
_CATEGORIAS_PERMISSAO = ("ler", "abrir", "instalar", "alterar_projeto", "apagar",
                         "internet", "servidor", "gastar_api")
_NIVEIS_PERMISSAO = ("analisa", "pergunta", "sozinho")
_LIMITE_COMANDO_SSH = 400      # o mesmo teto do terminal (cabe inteiro no cartão)
_LIMITE_SAIDA_SSH = 16000      # caracteres da saída do servidor que vão para a tela
_ID_DO_PEDIDO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_ID_LOCAL = re.compile(r"[A-Za-z0-9]{1,40}")
_APELIDO_SSH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
_LIMITE_TEXTO_CENTRAL = 600    # cada texto de item da Central (nomes de arquivo, explicações)
_ESTRANGULA_SEG = 0.05         # 50 ms = no máximo 20 mensagens de volume/s

_EXECUTAVEL_PADRAO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "electron", "node_modules", "electron", "dist", "electron.exe")


def _cortar(texto: str) -> str:
    """Texto livre nunca atravessa a ponte sem limite — é conteúdo hostil
    por definição (transcrição, resposta do cérebro, saída de comando)."""
    return (texto or "")[:_LIMITE_TEXTO]


class PonteElectron:
    """Sobe o Electron como filho e fala com ele em linhas de JSON.

    `ao_sair` é chamado quando o filho pede para sair (verbo `sair`) ou
    quando ele morre sozinho (o `stdout` fecha). `ao_plano` é chamado com
    "confirmar" ou "cancelar" quando o cartão de plano responde. `ao_pronto`
    é chamado quando a janela terminou de carregar.
    """

    def __init__(self, ao_sair, ao_plano, ao_pronto, ao_microfone=None,
                 ao_reuniao=None, ao_claude=None, ao_central=None, ao_integracao=None,
                 ao_permissoes=None, ao_modo_escuta=None, ao_vozes=None):
        """`ao_modo_escuta(modo: str)` recebe um dos três modos já validados,
        na thread de leitura (mesma regra do `ao_microfone`).

        `ao_plano` é chamado como `ao_plano(resposta, autorizado, cartao_id)`.
        `ao_microfone(ligar: bool)` roda na thread de leitura da ponte — quem
        o fornece precisa atravessar para a thread da tela antes de mexer em
        widget ou thread do Qt (ver `Motor` em `dervs_electron.py`); vale o
        mesmo para `ao_reuniao(ligar: bool)`.

        `ao_claude(verbo, dados)` recebe os quatro verbos do Claude Code
        (`claude_perguntar`, `claude_parar`, `claude_resposta`,
        `claude_nova_conversa`) já validados, também na thread de leitura. A
        sessão (`dervs_claude_code.SessaoClaudeCode`) é segura entre threads."""
        self._ao_claude = ao_claude
        self._ao_central = ao_central   # verbos `central_*` já validados (onda D)
        self._ao_integracao = ao_integracao   # verbos `integracao_*` já validados (tela Integração)
        self._ao_permissoes = ao_permissoes   # verbos `permissoes_*` já validados
        self._ao_vozes = ao_vozes             # verbos `vozes_*` já validados (perfis de voz)
        self._ao_microfone = ao_microfone
        self._ao_reuniao = ao_reuniao
        self._ao_modo_escuta = ao_modo_escuta
        self._ultimo_microfone_guardado = None
        self._ultimo_modo_guardado = None
        self._ao_sair = ao_sair
        self._ao_plano = ao_plano
        self._ao_pronto = ao_pronto
        self._processo = None
        self._fechado = False
        self._lock = threading.RLock()
        # Serializa só a escrita (linhas não se misturam). Quem escreve NÃO
        # segura `_lock` durante o write: Electron travado não congela o app.
        self._lock_escrita = threading.Lock()
        self._conexao_perdida = False
        self._pronto = False
        self._ultimo_estado_guardado = None
        self._ultimo_volume_guardado = None
        self._ultimo_volume_enviado = None
        self._ultimo_do_painel = {}     # verbo -> última msg enviada (painel grande)
        self._ultimo_envio_volume = 0.0
        self._sair_notificado = False
        self._servidor = None       # soquete que escuta a conexão do Electron
        self._token = None          # segredo da ponte: sem ele ninguém conecta
        self._conexao = None        # soquete aceito, já conversando com o Electron
        self._canal_saida = None    # onde `_escrever` escreve de verdade
                                     # (o objeto do soquete, via makefile) —
                                     # `None` nos testes com dublê, que
                                     # continuam escrevendo em `processo.stdin`

    # ---- subir o filho -----------------------------------------------

    def abrir(self, caminho_app, executavel=None, env_extra=None):
        """Sobe o Electron apontando para `caminho_app` (a pasta com o
        `package.json`/`main.js`). Levanta `FileNotFoundError` se o Electron
        não estiver instalado — nunca sobe um DERVS invisível calado.

        Antes de subir o filho, abre o soquete de escuta (só `127.0.0.1`)
        que vai carregar a direção Python → Electron (ver o cabeçalho do
        arquivo para o porquê de não ser o `stdin`) e passa a porta como
        último argumento de linha de comando.

        `env_extra` (dict opcional) entra por cima do ambiente herdado do
        processo pai — hoje só carrega `DERVS_APP_URL` (ver `dervs_electron.py`),
        a URL do botão "Abrir DERVS App". Variável de ambiente, não argumento
        de linha de comando, de propósito: `main.js` já lê o ÚLTIMO argumento
        como a porta do soquete (comentário em `main.js`, `ligarCanalDoPython`)
        — um argumento a mais quebraria essa convenção."""
        executavel = executavel or _EXECUTAVEL_PADRAO
        if not os.path.isfile(executavel):
            raise FileNotFoundError(
                f"o Electron não está instalado ({executavel}) — rode "
                f"'npm install' dentro da pasta 'electron/' e tente de novo")
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(4)
        # Segredo só desta subida: loopback não basta, qualquer programa da máquina
        # chega em 127.0.0.1 e a primeira conexão ganhava o canal. Vai ao filho por
        # variável de ambiente (argumento de linha de comando aparece na lista de
        # processos); o Electron o manda como primeira linha ao conectar.
        self._token = secrets.token_hex(32)
        porta = servidor.getsockname()[1]
        self._servidor = servidor
        threading.Thread(target=self._aceitar_conexao, daemon=True).start()
        kwargs = {}
        if WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        ambiente = dict(os.environ)
        ambiente.update(env_extra or {})
        ambiente[VARIAVEL_DA_FICHA] = self._token
        kwargs["env"] = ambiente
        processo = subprocess.Popen(
            [executavel, caminho_app, str(porta)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **kwargs)
        self._iniciar(processo)

    def _token_confere(self, conexao) -> bool:
        """A primeira linha da conexão tem de ser o segredo da subida (prazo curto).
        Sem segredo configurado, ninguém entra."""
        if not self._token:
            return False
        esperado = (self._token + "\n").encode("ascii")
        recebido = b""
        fim = time.monotonic() + _PRAZO_TOKEN
        try:
            while not recebido.endswith(b"\n") and len(recebido) < len(esperado):
                restante = fim - time.monotonic()
                if restante <= 0:
                    return False
                conexao.settimeout(restante)
                pedaco = conexao.recv(1)
                if not pedaco:
                    return False
                recebido += pedaco
        except OSError:
            return False
        return hmac.compare_digest(recebido, esperado)

    def _aceitar_conexao(self, prazo: float = 15.0):
        """Espera o Electron conectar no soquete de escuta.

        15 s é folgado de propósito: o Electron só conecta depois de subir o
        runtime do Chromium, que em máquina carregada pode não ser instantâneo.
        Endereço de origem é conferido por segurança em profundidade — o
        soquete já só escuta em `127.0.0.1`, mas nunca custa checar de novo
        quem está do outro lado antes de tratar a conexão como o Electron. E só
        vale quem diz o segredo da subida como primeira linha: as outras
        conexões são fechadas e a espera continua até o prazo."""
        servidor = self._servidor
        fim = time.monotonic() + prazo
        while True:
            restante = fim - time.monotonic()
            if restante <= 0:
                return
            try:
                servidor.settimeout(restante)
                conexao, endereco = servidor.accept()
            except OSError:
                return
            if endereco[0] != "127.0.0.1":
                sys.stderr.write(f"ponte: conexão recusada de {endereco!r} (não é loopback)\n")
                conexao.close()
                continue
            if not self._token_confere(conexao):
                sys.stderr.write("ponte: conexão recusada (segredo da ponte ausente ou errado)\n")
                conexao.close()
                continue
            break
        try:
            servidor.close()        # já tem dono: as demais tentativas nem conectam
        except OSError:
            pass
        # Escrita com prazo: se o Electron travar e parar de ler, o write falha
        # em 2 s em vez de segurar o app para sempre.
        conexao.settimeout(_PRAZO_ESCRITA)
        canal = conexao.makefile("wb")
        with self._lock:
            if self._fechado:
                canal.close()
                conexao.close()
                return
            self._conexao = conexao
            self._canal_saida = canal

    def _iniciar(self, processo):
        """Liga as leituras de `stdout` e `stderr` num processo já subido.

        Separado de `abrir()` de propósito: os testes usam um dublê de
        processo aqui (um objeto com `stdin`/`stdout` de pipe), sem precisar
        do Electron instalado.
        """
        self._processo = processo
        threading.Thread(target=self._ler_saida, daemon=True).start()
        threading.Thread(target=self._ler_erro, daemon=True).start()

    # ---- ler o que volta do Electron ----------------------------------

    def _ler_saida(self):
        """O `stdout` fechar é o filho morrendo — o DERVS não pode ficar sem
        cara em silêncio."""
        processo = self._processo
        try:
            for linha in processo.stdout:
                self._processar_linha(linha)
        except (OSError, ValueError):
            pass
        finally:
            self._chamar_ao_sair()

    def _ler_erro(self):
        processo = self._processo
        try:
            for linha in processo.stderr:
                texto = linha.decode("utf-8", "replace")
                sys.stderr.write("electron: " + texto)
                sys.stderr.flush()
        except (OSError, ValueError):
            pass

    def _processar_linha(self, linha: bytes):
        if len(linha) > _LIMITE_LINHA:
            sys.stderr.write("ponte: linha do Electron maior que 64 KiB, descartada\n")
            return
        try:
            texto = linha.decode("utf-8").strip()
            if not texto:
                return
            dado = json.loads(texto)
            verbo = dado["verbo"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, RecursionError):
            sys.stderr.write(f"ponte: linha inválida vinda do Electron: {linha!r}\n")
            return
        if verbo == "pronto":
            self._despachar_guardado()
        elif verbo == "sair":
            self._chamar_ao_sair()
        elif verbo == "plano":
            resposta = dado.get("resposta")
            if resposta not in ("confirmar", "cancelar"):
                sys.stderr.write(f"ponte: resposta de plano desconhecida: {dado!r}\n")
                return
            # `autorizado` é extensão do protocolo (ver cabeçalho, verbo
            # `plano` Electron → Python): a caixa "Tenho autorização"
            # marcada ou não. Checagem ESTRITA — só o booleano `True` de
            # verdade destrava; `bool("false")` é `True` em Python, então
            # qualquer outro valor truthy do JSON (string, lista não-vazia)
            # não pode passar por essa porta.
            autorizado = dado.get("autorizado") is True
            # `cartao_id` é extensão do protocolo (correção de concorrência,
            # ver cabeçalho): identifica a qual cartão esta resposta se
            # refere. Repassado como veio (string ou número) — quem decide
            # se ainda vale é `dervs_electron.py`.
            cartao_id = dado.get("cartao_id")
            self._chamar(self._ao_plano, resposta, autorizado, cartao_id)
        elif verbo == "microfone":
            ligar = dado.get("ligar")
            if not isinstance(ligar, bool):
                sys.stderr.write(f"ponte: pedido de microfone inválido: {dado!r}\n")
                return
            if self._ao_microfone is not None:
                self._chamar(self._ao_microfone, ligar)
        elif verbo == "modo_escuta":
            modo = dado.get("modo")
            if not isinstance(modo, str) or modo not in MODOS_DE_ESCUTA:
                sys.stderr.write(f"ponte: pedido de modo de escuta inválido: {dado!r}\n")
                return
            if self._ao_modo_escuta is not None:
                self._chamar(self._ao_modo_escuta, modo)
        elif verbo == "reuniao":
            ligar = dado.get("ligar")
            if not isinstance(ligar, bool):
                sys.stderr.write(f"ponte: pedido de reuniao inválido: {dado!r}\n")
                return
            if self._ao_reuniao is not None:
                self._chamar(self._ao_reuniao, ligar)
        elif verbo in ("claude_perguntar", "claude_parar", "claude_resposta",
                       "claude_nova_conversa"):
            self._tratar_claude(verbo, dado)
        elif verbo in _VERBOS_CENTRAL:
            self._tratar_central(verbo, dado)
        elif verbo in _VERBOS_INTEGRACAO:
            self._tratar_integracao(verbo, dado)
        elif verbo in _VERBOS_PERMISSOES:
            self._tratar_permissoes(verbo, dado)
        elif verbo in _VERBOS_VOZES:
            self._tratar_vozes(verbo, dado)
        else:
            sys.stderr.write(f"ponte: verbo desconhecido vindo do Electron: {verbo!r}\n")

    def _tratar_central(self, verbo, dado):
        """Valida os verbos da Central do PC. O clique de aprovar é o mais sensível:
        só o formato exato passa, e o motor confere tudo de novo."""
        def texto(campo, limite=64):
            v = dado.get(campo)
            return v if isinstance(v, str) and 0 < len(v) <= limite else None

        def lista(campo):
            v = dado.get(campo, [])
            ok = isinstance(v, list) and len(v) <= _LIMITE_LISTA and all(
                isinstance(i, str) and 0 < len(i) <= 64 for i in v)
            return v if ok else None
        dados = {}
        if verbo == "central_aprovar":
            dados = {"relatorio_id": texto("relatorio_id"), "cartao": texto("cartao", 200),
                     "ids": lista("ids"), "dupla": lista("dupla")}
            if None in dados.values() or not dados["ids"]:
                sys.stderr.write("ponte: central_aprovar inválido, ignorado\n")
                return
        elif verbo == "central_desfazer":
            dados = {"desfazer_id": texto("desfazer_id")}
            if dados["desfazer_id"] is None:
                sys.stderr.write("ponte: central_desfazer inválido, ignorado\n")
                return
        elif verbo == "central_explicar":
            dados = {"codigo": texto("codigo", 40)}
            if dados["codigo"] is None or not dados["codigo"].replace("_", "").isalnum():
                sys.stderr.write("ponte: central_explicar inválido, ignorado\n")
                return
        if self._ao_central is not None:
            self._chamar(self._ao_central, verbo, dados)

    def _tratar_integracao(self, verbo, dado):
        """Valida os verbos da tela Integração. O formato exato passa; o resto é linha
        ignorada no stderr. O que é sensível (aprovar o SSH) ainda é conferido de novo
        pelo `IntegracaoLocal` e pelo Motor de aprovação."""
        def casa(campo, padrao):
            v = dado.get(campo)
            return v if isinstance(v, str) and padrao.fullmatch(v) else None
        dados = {}
        if verbo == "integracao_cerebro":
            dados = {"nome": casa("nome", re.compile(r"[a-z_]{1,20}"))}
        elif verbo == "integracao_dispensar":
            dados = {"id": casa("id", _ID_DO_PEDIDO)}
        elif verbo == "integracao_conserto":
            dados = {"aviso_id": casa("aviso_id", _ID_LOCAL)}
        elif verbo == "integracao_ssh_rodar":
            comando = dado.get("comando")
            dados = {"apelido": casa("apelido", _APELIDO_SSH),
                     "comando": comando if (isinstance(comando, str) and comando.strip()
                                            and len(comando) <= _LIMITE_COMANDO_SSH) else None}
        elif verbo == "integracao_ssh_confirmar":
            # só o booleano de verdade confirma (mesma checagem estrita de `autorizado`)
            dados = {"proposta_id": casa("proposta_id", _ID_LOCAL),
                     "segunda": True if dado.get("segunda") is True else None}
        elif verbo == "integracao_ssh_cancelar":
            dados = {"proposta_id": casa("proposta_id", _ID_LOCAL)}
        if None in dados.values():
            sys.stderr.write(f"ponte: {verbo} inválido, ignorado\n")
            return
        if self._ao_integracao is not None:
            self._chamar(self._ao_integracao, verbo, dados)

    def _tratar_permissoes(self, verbo, dado):
        """Valida os verbos da tela de permissões: categoria e nível só de listas fixas,
        teto só número na faixa. O `PermissoesLocal` confere a política de novo."""
        dados = {}
        if verbo == "permissoes_definir":
            cat, nivel = dado.get("categoria"), dado.get("nivel")
            dados = {"categoria": cat if cat in _CATEGORIAS_PERMISSAO else None,
                     "nivel": nivel if nivel in _NIVEIS_PERMISSAO else None}
        elif verbo == "permissoes_teto":
            valor = dado.get("valor")
            ok = (isinstance(valor, (int, float)) and not isinstance(valor, bool)
                  and 0.01 <= valor <= 1000)
            dados = {"valor": valor if ok else None}
        if None in dados.values():
            sys.stderr.write(f"ponte: {verbo} inválido, ignorado\n")
            return
        if self._ao_permissoes is not None:
            self._chamar(self._ao_permissoes, verbo, dados)

    def _tratar_vozes(self, verbo, dado):
        """Valida os verbos dos perfis de voz: nome texto curto, papel e `ativo` de listas fixas.
        O `dervs_locutor` confere o nome de novo (caminho dentro da pasta de vozes)."""
        dados = {}
        if verbo != "vozes_pedir":
            nome = dado.get("nome")
            ok = isinstance(nome, str) and 0 < len(nome.strip()) <= _LIMITE_NOME_VOZ
            dados["nome"] = nome.strip() if ok else None
        if verbo == "vozes_gravar":
            dados["papel"] = dado.get("papel") if dado.get("papel") in _PAPEIS_VOZ else None
        elif verbo == "vozes_ativar":
            dados["ativo"] = dado.get("ativo") if isinstance(dado.get("ativo"), bool) else None
        if None in dados.values():
            sys.stderr.write(f"ponte: {verbo} inválido, ignorado\n")
            return
        if self._ao_vozes is not None:
            self._chamar(self._ao_vozes, verbo, dados)

    def _tratar_claude(self, verbo, dado):
        """Valida os verbos do Claude Code ANTES de entregar: tudo aqui vem de
        uma tela que exibe texto hostil, então só o formato exato passa."""
        if verbo == "claude_perguntar":
            texto = dado.get("texto")
            if (not isinstance(texto, str) or not texto.strip()
                    or len(texto) > _LIMITE_PERGUNTA):
                sys.stderr.write("ponte: claude_perguntar inválido (vazio, longo demais "
                                 "ou não é texto), ignorado\n")
                return
            dados = {"texto": texto}
        elif verbo == "claude_resposta":
            id_ = dado.get("id")
            if not isinstance(id_, str) or not id_ or len(id_) > 64 \
                    or not isinstance(dado.get("permitir"), bool):
                sys.stderr.write(f"ponte: claude_resposta inválida: {dado!r}\n")
                return
            cartao_id = dado.get("cartao_id")
            dados = {"id": id_, "permitir": dado["permitir"],
                     "cartao_id": cartao_id if isinstance(cartao_id, str) else None}
        else:
            dados = {}
        if self._ao_claude is not None:
            self._chamar(self._ao_claude, verbo, dados)

    def _chamar(self, callback, *args):
        """Callback do dono explodir não pode derrubar a ponte."""
        try:
            callback(*args)
        except Exception as e:
            sys.stderr.write(f"ponte: callback falhou: {e}\n")

    def _chamar_ao_sair(self):
        """`ao_sair` é o gatilho de encerramento do DERVS — no máximo uma vez
        por instância, mesmo que o verbo `sair` chegue e em seguida o
        `stdout` feche (o mesmo evento de saída, contado duas vezes)."""
        with self._lock:
            if self._sair_notificado:
                return
            self._sair_notificado = True
        self._chamar(self._ao_sair)

    def _despachar_guardado(self):
        with self._lock:
            self._pronto = True
            estado = self._ultimo_estado_guardado
            volume = self._ultimo_volume_guardado
            microfone = self._ultimo_microfone_guardado
            modo = self._ultimo_modo_guardado
        if estado is not None:
            self._escrever(estado)
        if microfone is not None:
            self._escrever(microfone)
        if modo is not None:
            self._escrever(modo)
        if volume is not None:
            self._escrever(volume)
        self._chamar(self._ao_pronto)

    # ---- mandar mensagem para o Electron -------------------------------

    def enviar_estado(self, valor, texto="", apoio=""):
        msg = {"verbo": "estado", "valor": valor, "texto": _cortar(texto),
               "apoio": _cortar(apoio)}
        with self._lock:
            if not self._pronto:
                self._ultimo_estado_guardado = msg
                return
        self._escrever(msg)

    def enviar_microfone(self, ligado):
        msg = {"verbo": "microfone", "ligado": bool(ligado)}
        with self._lock:
            if not self._pronto:
                self._ultimo_microfone_guardado = msg
                return
        self._escrever(msg)

    def enviar_modo_escuta(self, modo, fecha_em_min=None):
        """Modo de escuta atual e, se o microfone está aberto sob desligamento
        automático, em quantos minutos ele fecha (inteiro >= 0; `None` sem prazo)."""
        if modo not in MODOS_DE_ESCUTA:
            return
        if isinstance(fecha_em_min, bool) or not isinstance(fecha_em_min, int) or fecha_em_min < 0:
            fecha_em_min = None
        msg = {"verbo": "modo_escuta", "modo": modo, "fecha_em_min": fecha_em_min}
        with self._lock:
            if not self._pronto:
                self._ultimo_modo_guardado = msg
                return
        self._escrever(msg)

    def enviar_volume(self, x):
        try:
            x = float(x)
        except (TypeError, ValueError):
            return
        x = max(0.0, min(1.0, x))
        valor = round(x, 2)
        msg = {"verbo": "volume", "valor": valor}
        with self._lock:
            if not self._pronto:
                self._ultimo_volume_guardado = msg
                return
            if valor == self._ultimo_volume_enviado:
                return
            agora = time.monotonic()
            if agora - self._ultimo_envio_volume < _ESTRANGULA_SEG:
                return
            self._ultimo_volume_enviado = valor
            self._ultimo_envio_volume = agora
        self._escrever(msg)

    def enviar_fala(self, papel, texto):
        self._escrever({"verbo": "fala", "papel": papel, "texto": _cortar(texto)})

    def enviar_plano(self, passos, nivel, pergunta, cartao_id=None):
        msg = {"verbo": "plano", "passos": list(passos), "nivel": nivel,
               "pergunta": _cortar(pergunta)}
        if cartao_id is not None:
            msg["cartao_id"] = cartao_id
        # Teto de tamanho: sem isto, um plano grande o bastante estoura o
        # `_LIMITE_LINHA` de 64 KiB (linha inteira descartada do lado do
        # Electron, ver `_processar_linha`), reintroduzindo por outra porta
        # o mesmo sintoma "cartão nunca aparece" que a `_cortar` de `pergunta`
        # já resolve para o texto livre. Corta a lista de passos, mantendo
        # os primeiros que couberem — nunca deixa a linha estourar em
        # silêncio sem alternativa nenhuma chegando à tela.
        total_original = len(msg["passos"])
        while msg["passos"] and len(json.dumps(msg, ensure_ascii=False)) > _LIMITE_PLANO:
            msg["passos"].pop()
        if len(msg["passos"]) < total_original:
            sys.stderr.write(
                f"ponte: plano com {total_original} passos estourava "
                f"{_LIMITE_PLANO} caracteres — cortado para "
                f"{len(msg['passos'])} passo(s)\n")
        self._escrever(msg)

    def enviar_mostrar(self):
        self._escrever({"verbo": "mostrar"})

    def enviar_sistema(self, cpu, ram, disco_livre_gb, disco_total_gb,
                       rede_baixa_kbs=None, rede_sobe_kbs=None):
        """CPU/RAM/disco reais desta máquina (ver `dervs_sistema.py`). Só
        manda depois do `pronto` — diferente de `estado`/`volume`, não guarda
        o último valor para reenviar depois: a próxima leitura (a cada ~2s)
        chega sozinha, então não vale a pena guardar um valor que pode já
        estar velho quando a janela finalmente carregar."""
        with self._lock:
            if not self._pronto:
                return
        msg = {
            "verbo": "sistema", "cpu": cpu, "ram": ram,
            "disco_livre_gb": disco_livre_gb, "disco_total_gb": disco_total_gb,
        }
        # Rede (KB/s) é opcional: o widget compacto ignora, o painel grande desenha.
        if rede_baixa_kbs is not None and rede_sobe_kbs is not None:
            msg["rede_baixa_kbs"] = rede_baixa_kbs
            msg["rede_sobe_kbs"] = rede_sobe_kbs
        self._escrever(msg)

    def enviar_diario(self, ouvidas, acordou):
        """Resumo de hoje do diário do porteiro (ver `dervs_diario.py`). Como
        `sistema`, só manda depois do `pronto` e não guarda o último valor."""
        with self._lock:
            if not self._pronto:
                return
        self._escrever({"verbo": "diario", "ouvidas": int(ouvidas),
                        "acordou": int(acordou)})

    # ---- painel grande (JARVIS) -----------------------------------------------
    # Estes verbos só alimentam a janela grande. Como `sistema`/`diario`, só
    # saem depois do `pronto`; e um valor IGUAL ao último enviado não é
    # reenviado (o laço do painel repete a leitura a cada poucos segundos).

    def _enviar_se_mudou(self, msg: dict):
        with self._lock:
            if not self._pronto:
                return
            if self._ultimo_do_painel.get(msg["verbo"]) == msg:
                return
            self._ultimo_do_painel[msg["verbo"]] = msg
        self._escrever(msg)

    def enviar_gasto(self, gasto: dict):
        """Gasto estimado de HOJE em dólar (ver `dervs_gasto.py`)."""
        self._enviar_se_mudou({"verbo": "gasto", **{
            k: round(float(gasto.get(k, 0.0)), 6)
            for k in ("total", "tts", "stt", "cerebro")}})

    def enviar_cofre(self, notas, pasta):
        """Contagem de notas do cofre e a pasta dele (ver `dervs_cofre.py`)."""
        try:
            n = max(0, int(notas))
        except (TypeError, ValueError):
            n = 0
        self._enviar_se_mudou({"verbo": "cofre", "notas": n, "pasta": str(pasta)[:500]})

    def enviar_codex(self, estado, texto):
        """Linha de estado do Codex (ver `dervs_codex.py`)."""
        if estado not in ("chatgpt", "chave_api", "nao_logado", "desligado", "falhou"):
            estado = "falhou"
        self._enviar_se_mudou({"verbo": "codex", "estado": estado, "texto": str(texto)[:120]})

    def enviar_agenda(self, itens):
        """Lembretes pendentes: `[{"quando", "quando_txt", "texto"}]`."""
        limpos = [{"quando": str(i.get("quando", ""))[:32],
                   "quando_txt": str(i.get("quando_txt", ""))[:40],
                   "texto": str(i.get("texto", ""))[:_LIMITE_ITEM]}
                  for i in list(itens)[:_LIMITE_LISTA]]
        self._enviar_se_mudou({"verbo": "agenda", "itens": limpos})

    def enviar_diario_entradas(self, entradas):
        """Últimas frases ouvidas hoje — só metadados (hora, acordou, palavras,
        duração), nunca o texto."""
        limpas = [{"hora": str(e.get("hora", ""))[:8], "acordou": bool(e.get("acordou")),
                   "palavras": int(e.get("palavras") or 0),
                   "duracao_s": float(e.get("duracao_s") or 0.0)}
                  for e in list(entradas)[:_LIMITE_LISTA]]
        self._enviar_se_mudou({"verbo": "diario_entradas", "entradas": limpas})

    def enviar_voz(self, motor):
        """Qual voz está valendo agora: "nuvem" ou "local" (qualquer outro
        valor vira "local")."""
        self._enviar_se_mudou({"verbo": "voz", "motor": "nuvem" if motor == "nuvem" else "local"})

    def enviar_acao(self, papel, texto):
        """Uma ação do DERVS para a lista de "últimas ações" do painel."""
        self._escrever({"verbo": "acao", "papel": str(papel)[:16], "texto": _cortar(texto)})

    # ---- Claude Code (onda B) ---------------------------------------------------
    # Sem guarda antes do `pronto` e sem "só se mudou": cada pedaço de resposta
    # é único, e uma resposta que começa antes da janela carregar não é
    # reencenada depois (a caixa de texto do painel só existe carregada).

    def enviar_claude_delta(self, texto):
        self._escrever({"verbo": "claude_delta", "texto": _cortar(texto)})

    def enviar_claude_ferramenta(self, nome, resumo):
        self._escrever({"verbo": "claude_ferramenta", "nome": str(nome)[:64],
                        "resumo": str(resumo)[:_LIMITE_ITEM]})

    def enviar_claude_pedido(self, pedido: dict):
        """Só os campos do contrato atravessam; o resto do dict fica de fora."""
        self._escrever({
            "verbo": "claude_pedido",
            "id": str(pedido.get("id", ""))[:64],
            "ferramenta": str(pedido.get("ferramenta", ""))[:64],
            "resumo": str(pedido.get("resumo", ""))[:_LIMITE_RESUMO_PEDIDO],
            "entrada_cortada": str(pedido.get("entrada_cortada", ""))[:_LIMITE_ENTRADA_PEDIDO],
            "nivel": str(pedido.get("nivel", "muda_estado"))[:16],
            "expira_s": int(pedido.get("expira_s") or 0),
            "escondidos": max(0, int(pedido.get("escondidos") or 0)),
            "rede": bool(pedido.get("rede"))})

    def enviar_claude_fim(self, ok, custo, erro):
        try:
            custo = round(float(custo or 0.0), 6)
        except (TypeError, ValueError):
            custo = 0.0
        self._escrever({"verbo": "claude_fim", "ok": bool(ok), "custo": custo,
                        "erro": None if erro is None else str(erro)[:_LIMITE_ERRO_CLAUDE]})

    def enviar_claude(self, verbo, dados):
        """Ponto único que a sessão do Claude Code usa (`ao_evento`)."""
        if verbo == "claude_delta":
            self.enviar_claude_delta(dados.get("texto", ""))
        elif verbo == "claude_ferramenta":
            self.enviar_claude_ferramenta(dados.get("nome", ""), dados.get("resumo", ""))
        elif verbo == "claude_pedido":
            self.enviar_claude_pedido(dados)
        elif verbo == "claude_fim":
            self.enviar_claude_fim(dados.get("ok"), dados.get("custo"), dados.get("erro"))

    # ---- Central do PC (onda D) -----------------------------------------------
    # Sem guarda de "só se mudou": cada análise é um evento. Todo texto é cortado
    # (nome de arquivo e de programa são conteúdo hostil) e a linha inteira tem
    # de caber no limite da ponte; se não couber, as listas são esvaziadas.

    def _limpar_central(self, valor, fundo=0):
        if isinstance(valor, str):
            return valor[:_LIMITE_TEXTO_CENTRAL]
        if fundo > 6:
            return None
        if isinstance(valor, dict):
            return {str(k)[:64]: self._limpar_central(v, fundo + 1) for k, v in valor.items()}
        if isinstance(valor, (list, tuple)):
            return [self._limpar_central(v, fundo + 1) for v in list(valor)[:_LIMITE_LISTA]]
        if isinstance(valor, (bool, int, float)) or valor is None:
            return valor
        return str(valor)[:_LIMITE_TEXTO_CENTRAL]

    def _escrever_central(self, msg: dict):
        limpa = self._limpar_central(msg)
        if len(json.dumps(limpa, ensure_ascii=False).encode("utf-8")) > _LIMITE_PLANO:
            limpa = {k: ([] if isinstance(v, list) else v) for k, v in limpa.items()}
        self._escrever(limpa)

    def enviar_central(self, visao: dict):
        self._escrever_central({"verbo": "central", **visao})

    def enviar_central_progresso(self, coletor, feitos, total):
        self._escrever_central({"verbo": "central_progresso", "coletor": str(coletor)[:40],
                                "feitos": int(feitos), "total": int(total)})

    def enviar_central_relatorio(self, relatorio: dict, cartao):
        self._escrever_central({"verbo": "central_relatorio", "relatorio": relatorio,
                                "cartao": cartao if isinstance(cartao, str) else None})

    def enviar_central_resultado(self, resultado: dict):
        self._escrever_central({"verbo": "central_resultado", **resultado})

    # ---- tela Integração ---------------------------------------------------------
    # Mesmo cuidado da Central (texto cortado, lista limitada), mas com teto próprio:
    # a saída de um comando no servidor é o único texto que passa de 600 caracteres.
    def _limpar_integracao(self, valor, chave="", fundo=0):
        if isinstance(valor, str):
            return valor[:_LIMITE_SAIDA_SSH if chave == "saida" else _LIMITE_TEXTO_CENTRAL]
        if fundo > 4:
            return None
        if isinstance(valor, dict):
            return {str(k)[:64]: self._limpar_integracao(v, str(k), fundo + 1) for k, v in valor.items()}
        if isinstance(valor, (list, tuple)):
            return [self._limpar_integracao(v, chave, fundo + 1) for v in list(valor)[:100]]
        if isinstance(valor, (bool, int, float)) or valor is None:
            return valor
        return str(valor)[:_LIMITE_TEXTO_CENTRAL]

    def enviar_integracao(self, parte: str, dados: dict):
        limpa = self._limpar_integracao({"verbo": "integracao", "parte": str(parte)[:30], **(dados or {})})
        if len(json.dumps(limpa, ensure_ascii=False).encode("utf-8")) > _LIMITE_PLANO:
            limpa = {k: ([] if isinstance(v, list) else ("" if k == "saida" else v))
                     for k, v in limpa.items()}
            limpa["truncada"] = True
        self._escrever(limpa)

    def enviar_permissoes(self, dados: dict):
        """Estado ou mensagem da tela de permissões (mesma limpeza da Integração)."""
        self._escrever(self._limpar_integracao({"verbo": "permissoes", **(dados or {})}))

    def enviar_vozes(self, dados: dict):
        """Perfis de voz, estado da conversa natural, progresso ou resultado (ver cabeçalho)."""
        self._escrever(self._limpar_integracao({"verbo": "vozes", **(dados or {})}))

    def enviar_reuniao(self, restante_s):
        """Segundos restantes do modo reunião, ou `None` quando não há."""
        restante = None if restante_s is None else int(restante_s)
        self._escrever({"verbo": "reuniao", "restante_s": restante})

    def _escrever(self, msg: dict):
        linha = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            if self._conexao_perdida:
                return
            # Caminho real: o soquete aceito de `_aceitar_conexao`. Caminho
            # de teste: nenhum soquete foi aberto (ninguém chamou `abrir()`
            # de verdade), então cai no `processo.stdin` do dublê — é assim
            # que a suíte inteira de testes desta ponte continua funcionando
            # sem precisar subir soquete nenhum.
            canal = self._canal_saida
            if canal is None:
                processo = self._processo
                canal = processo.stdin if processo is not None else None
            real = canal is not None and canal is self._canal_saida
        if canal is None:
            return
        falhou = False
        with self._lock_escrita:
            try:
                canal.write(linha)
                canal.flush()
            except (BrokenPipeError, OSError, ValueError) as e:
                sys.stderr.write(f"ponte: falha ao escrever para o Electron: {e}\n")
                falhou = True
        if falhou and real:
            self._perder_conexao(canal)

    def _perder_conexao(self, canal):
        """Escrita falhou ou estourou o prazo: dá o soquete por perdido, sem
        segurar o lock durante o fechamento."""
        with self._lock:
            if self._canal_saida is not canal:
                return
            conexao = self._conexao
            self._canal_saida = None
            self._conexao = None
            self._conexao_perdida = True
        for alvo in (conexao, canal):
            try:
                if alvo is not None:
                    alvo.close()
            except (OSError, ValueError):
                pass

    # ---- encerrar -------------------------------------------------------

    def fechar(self, espera: float = 3.0):
        """Fecha o canal de escrita (soquete ou `stdin` do dublê), o soquete
        de escuta, espera, `terminate()`, espera de novo, `kill()`.
        Seguro chamar duas vezes."""
        with self._lock:
            if self._fechado:
                return
            self._fechado = True
            processo = self._processo
            canal = self._canal_saida
            conexao = self._conexao
            servidor = self._servidor
        # Fecha fora do lock: o flush do canal pode esperar o prazo do soquete
        # e o app não pode ficar congelado por causa disso. Soquete primeiro,
        # para destravar uma escrita em andamento.
        if conexao is not None:
            try:
                conexao.close()
            except OSError:
                pass
        if canal is not None:
            try:
                canal.close()
            except (OSError, ValueError):
                pass
        if servidor is not None:
            try:
                servidor.close()
            except OSError:
                pass
        if canal is None and processo is not None:
            try:
                if processo.stdin is not None:
                    processo.stdin.close()
            except (OSError, ValueError):
                pass
        if processo is None:
            return
        try:
            processo.wait(timeout=espera)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            processo.terminate()
            processo.wait(timeout=espera)
            return
        except (subprocess.TimeoutExpired, OSError):
            pass
        try:
            processo.kill()
        except OSError:
            pass
