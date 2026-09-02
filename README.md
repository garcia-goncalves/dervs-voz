# DERVS — companheiro de voz (Windows)

> **Origem:** este projeto é o irmão Windows do
> [`thi-garcia/grimoire-voz`](https://github.com/thi-garcia/grimoire-voz), que roda
> no Parrot OS (Linux). O original continua onde está.
>
> **Para quem só quer usar:** leia **[COMO-USAR.md](COMO-USAR.md)**, escrito sem
> jargão. Este README é para quem vai mexer no código.

Selo flutuante na bandeja. Você fala → transcreve → o cérebro entende e propõe um
plano → você confirma → ele executa (abre apps, sites, roda comandos). Fala de
volta com voz humana.

Detalhe completo em **[DERVS-EXECUTAR.md](DERVS-EXECUTAR.md)**.

## A espinha (2026-09-01)

O desenho é um **funil**: cada estágio custa mais que o anterior e só roda se o
anterior deixar passar. É isso que permite deixar ligado o dia inteiro.

| # | Estágio | Onde | Custo |
|---|---|---|---|
| 1 | Fim de fala (`Endpointer`, energia + histerese) | local | zero |
| 2 | **Porteiro** — "foi comigo?" (`dervs_porteiro.py`, Whisper `tiny` com aviso de vocabulário) | **local** | **zero** |
| 3 | Transcrição precisa — OpenAI `gpt-transcribe`. Reserva: Whisper local | nuvem | US$ 0,0045/min |
| 4 | Cérebro — OpenAI `gpt-4.1-nano`. Reserva: Claude CLI | nuvem | barato |
| 5 | Voz — Kokoro, velocidade 1,2. Reserva: Piper | local | zero |

**Nada sai da máquina antes do estágio 2 abrir**, e isso é travado por teste
(`test_dervs_porteiro.py::test_porteiro_nao_manda_audio_para_a_nuvem`). A
gravação de cada frase é apagada depois de usada, inclusive a que o porteiro
recusa (`test_dervs_privacidade.py`).

Custo estimado de uso pesado (~300 interações/dia): **~US$ 5–6/mês**. Sem o
funil, ligado 8 h/dia, só a transcrição daria ~US$ 43/mês.

O porteiro é peça trocável (`criar_porteiro`). Hoje só existe o local; o encaixe
para o Picovoice Porcupine está documentado em `dervs_porteiro.py`.

## Rodar e gerenciar

No Windows, do diretório do projeto:

```
dervs-venv\Scripts\python.exe dervs.py                      # abre o DERVS
dervs-venv\Scripts\python.exe dervs_transcrever.py [audio]  # audio -> texto
dervs-venv\Scripts\python.exe scripts\instalar_atalho.py    # icone + atalhos
dervs-venv\Scripts\python.exe -m pytest -q                  # testes (416 verdes)
dervs-venv\Scripts\python.exe amostras_de_voz.py            # amostras das 3 vozes
```

O dono não usa terminal: para ele existem os atalhos **DERVS** e
**DERVS - Transcrever audio** na Área de Trabalho e no menu Iniciar, criados por
`scripts/instalar_atalho.py` (que também desenha o `dervs.ico` a partir do selo
da janela). O atalho do app usa `pythonw.exe` para não abrir console junto; o da
transcrição usa `python.exe` de propósito, porque ali o console **é** a interface
que mostra o andamento.

Ainda **não** há serviço que suba sozinho no boot — está fora do escopo desta
rodada, de propósito, até o comportamento estabilizar.

No Linux (repositório irmão) o serviço continua sendo `systemctl --user`.

## Configuração

No Windows fica em `%APPDATA%\dervs\config.json`; no Linux, em
`~/.config/dervs/config.json`. Criado sozinho no 1º boot. Para descobrir o
caminho: `python -c "import dervs_config as c; print(c.CONFIG_PATH)"`.

Chaves: `stt`, `stt_openai_modelo`, `porteiro`, `porteiro_modelo`, `cerebro`,
`cerebro_openai_modelo`, `motor`, `voz_kokoro`, `voz`, `voz_velocidade`,
`janela_desperto_seg`, `atalhos_ligados`, `escuta_ao_abrir`, e as do navegador. Valor inválido cai
no padrão em vez de derrubar o app (`_validar`). Mudou → reinicie.

## Segredo

`OPENAI_API_KEY` é procurado por `dervs_config.segredo()`, nesta ordem:
variável de ambiente → arquivo de segredos ao lado da configuração → o caminho
antigo da máquina irmã. Nunca é registrado em log nem commitado.

Ver o caminho certo:
`python -c "import dervs_config as c; print(c.caminhos_do_segredo()[0])"`.

## O que fica fora do git

Ambientes Python (`*-venv/`, `dervs-venv/`), modelos, o arquivo de segredos,
`.wav`, `.log`, `amostras_voz/` e `.claude/worktrees/`. Ver `.gitignore`.

## O estado da portabilidade (01/09/2026)

**Feito:** captura e reprodução de áudio por `sounddevice` (sem `arecord`,
`pw-play` nem `pw-record`); porteiro local invertendo a ordem nuvem/portão;
atalhos, execução, rede de segurança e prompt do cérebro com vocabulário do
Windows; configuração e segredo nos caminhos do Windows; colar por
`keybd_event` no lugar do `ydotool`; gravações apagadas depois de usadas.
**284 testes passam, zero falham** (antes: 112 passavam e 4 falhavam).

## O que mudou em 02/09/2026, com a chave da OpenAI instalada

Medição ponta a ponta fechada: **3,94 s** do fim da fala até o DERVS começar a
responder. Números por estágio em `docs/esteira/windows-tempo-real/verificacao.md`.

Quatro defeitos achados **por medir**, todos corrigidos e travados por teste:

| Defeito | Efeito |
|---|---|
| `response_format: json_object` no cérebro | JSON quebrado em 3 de 20 chamadas; caía no cérebro reserva à toa. Agora `json_schema` com `strict` |
| Motores de voz procurados em `~/voice` | `Voz.disponivel()` era **False**: o DERVS estava mudo no Windows |
| Cérebro sem relógio | inventava a hora fora do alcance dos atalhos locais ("quanto falta pro Natal") |
| Escuta religada sozinha ao abrir | o botão liga/desliga não era liga/desliga; agora `escuta_ao_abrir` lembra |

Novidades: `dervs_transcrever.py` (arquivo de áudio → texto, com corte e emenda
para reunião longa), ícone e atalhos, e `dervs_config.gravar()` para o app
guardar escolha feita na tela.

**359 testes passam, zero falham.**

## O "o DERVS sumiu / bugou" — investigado em 02/09/2026

Relato do dono, sem mais detalhe. **Os 331 testes passavam e o app subia sem
erro.** O defeito estava fora do alcance de todos eles. Achado medindo o app de
verdade, pelo caminho do atalho:

| Defeito | Como foi confirmado | Efeito para o dono |
|---|---|---|
| **Sem trava de instância única** | abrir pelo atalho 2× → de 2 processos para 4 | cada clique no ícone subia MAIS um DERVS; os antigos ficavam vivos e invisíveis, disputando o microfone, empilhados no mesmo pixel |
| **Bandeja sem "Sair"** | lído no código, era intencional | somado ao de cima: nenhum jeito de fechar sem o Gerenciador de Tarefas, que o dono não usa. O app piorava a cada uso, para sempre |
| **Morte do daemon de STT não era escutada** | `finished`/`errorOccurred`/`stderr`: zero ocorrências no arquivo | daemon morto = `_stt_pronto` False para sempre = o botão Gravar deixava de fazer **qualquer** coisa, em silêncio. DERVS surdo e calado |
| **`atualizar()` mentia** | sonda com o daemon quebrado de propósito: o status voltava a "pronto" em 3 s | o timer de 500 ms reescrevia "pronto" por cima de tudo — inclusive com o ouvido morto |
| **Selo arrastável para fora da tela** | `mouseMoveEvent` sem limite de `availableGeometry` | arrastar até a borda sumia com o selo, sem volta |

**Conserto**, com prova pelo caminho de produção:

- `dervs_instancia.py` (novo, 9 testes): UM DERVS só. Quem abre primeiro reserva
  uma porta em `127.0.0.1` e anota porta + senha sorteada em
  `%APPDATA%\dervs\instancia.json`; quem abrir depois manda `MOSTRAR <senha>`,
  o primeiro pula na frente, e o segundo encerra. Medido: 3 cliques no atalho =
  1 DERVS.
- `finished`, `errorOccurred` e `readyReadStandardError` ligados no daemon de
  STT, com 2 tentativas de religar e vigia de 90 s. Medido com o daemon
  quebrado de propósito: a tela passa a dizer "não estou conseguindo ouvir — o
  motor de voz não sobe", e o recado **fica** (motivo real no tooltip). Com o
  daemon inteiro, chega em "pronto" em menos de 2 s, sem alarme falso.
- Bandeja com **"Sair do DERVS"** e **"Trazer o selo de volta"**; arrasto do
  selo limitado à tela.

**A revisão pegou dois bloqueantes no próprio conserto**, ambos reproduzidos e
corrigidos: (1) `QTimer.singleShot` chamado da thread do socket nunca dispara —
o segundo clique encerrava o processo novo e a janela **não** aparecia, pior que
o defeito original; agora a travessia é por sinal do Qt (`Ponte`), medido em
2,01 s. (2) procurar `OK` solto na resposta deixava qualquer servidor local que
responda `HTTP/1.1 200 OK` numa porta reciclada impedir o DERVS de abrir para
sempre; agora a resposta tem de ser exatamente `DERVS-OK`, e o registro só vale
se o processo dono ainda estiver vivo. Mais: uma queda avisava duas vezes e
gastava as duas tentativas de uma só; o vigia de 90 s não era rearmado; o selo
não ia mais para um segundo monitor; a gravação pendente era descartada calada;
e falha de reserva por motivo de máquina agora deixa o app abrir SEM trava, em
vez de recusar-se a abrir.

**Medido e descartado:** processo órfão. Matando só o DERVS principal, os
filhos (`dervs_stt_daemon` 130 MB, `dervs_kokoro_daemon` 395 MB) morrem junto —
0 órfãos.

## "Fechando sozinho, e não está me entendendo" — 02/09/2026, tarde

**O fechamento sozinho NÃO foi reproduzido.** 6 apertos reais de mouse no botão
Voz e 8 no do microfone, no app aberto pelo atalho, processo vivo no fim dos
dois. Sonda em processo: 3 rodadas sem morrer. Em vez de adivinhar em cima de
código que funciona, o app passou a **registrar a própria morte**
(`dervs_registro.py`): `sys.excepthook`, `threading.excepthook` e `faulthandler`
gravam em `%APPDATA%\dervs\ultimo_erro.txt`, e a abertura seguinte mostra o
motivo na tela. Até aqui o app morria sem deixar uma linha — `pythonw` não tem
terminal.

Para "não está me entendendo" e "a transcrição não está boa", cinco defeitos
confirmados no código:

| Defeito | Onde | Efeito |
|---|---|---|
| **A margem de áudio sumia da 2ª frase em diante** | `dervs_listen.py`, `_entregar` | `self.pre` era esvaziado no início da fala e nunca reposto: toda frase depois da primeira começava no 1º quadro acima do limiar e **perdia a primeira sílaba**. Agora a cauda da frase vira a margem da próxima — travado por teste |
| **O cérebro achava que estava no Linux** | `dervs_brain.SISTEMA` | dizia em texto fixo "roda na máquina Linux (Parrot)" enquanto o bloco de comandos logo abaixo era de Windows 11. Agora o SO vem do mesmo `sys.platform` |
| **Ordem contraditória no mesmo prompt** | `dervs_brain.SISTEMA` | "SEMPRE espere o OK" e, 6 linhas depois, "aja sem pedir licença" |
| **Porteiro com `beam_size=1` e sem VAD** | `dervs_porteiro.py` | quando ele erra, a frase é **descartada em silêncio**. Agora `beam_size=3` + `vad_filter` |
| **Cérebro no modelo mais fraco da família** | `dervs_config.py` | `gpt-4.1-nano` para `gpt-4.1-mini` |

Margem subiu de 300 ms para 600 ms (`pre_roll=20`) e `min_fala_ms` caiu de 300
para 200 — um "sim"/"ok" rápido de confirmação batia perto do piso e sumia.

**Medido depois da troca do modelo**, mesmas 3 perguntas: nano 3,07/1,21/1,50 s
contra mini **2,04**/1,51/1,42 s. Mais preciso e **não ficou mais lento**.

> **Armadilha:** mudar o `PADRAO` de `dervs_config.py` **não muda nada** numa
> instalação que já existe — `garantir_arquivo()` grava o dicionário inteiro no
> `config.json`, e `carregar()` só completa o que falta. A troca do modelo só
> valeu depois de `cfg.gravar()` na máquina do dono. Vale para toda chave nova.

**Falta:**

| Peça | Situação |
|---|---|
| Chave da OpenAI nesta máquina | **bloqueia** a transcrição precisa e o cérebro. Depende do dono |
| Medir o tempo de resposta ponta a ponta | depende da chave |
| Reconhecer a voz do dono no ruído real dele | o porteiro foi medido com voz sintetizada |
| Serviço que sobe sozinho no boot | fora de escopo desta rodada, de propósito |
| `dervs_enrich.py` (OSINT com `bbot`) | `bbot` não roda em Windows. Fica desligado |
| `dervs_painel.py` | legado, ninguém importa. Fica como está |
| `falar.sh`, `ligar-voz-com-senha.sh` | scripts do Linux, ainda não traduzidos |
| Navegador autônomo ponta a ponta | caminho do perfil do Chrome corrigido, mas não validado |

## "Sumiu definitivamente" — 02/09/2026, noite. O registro de queda pagou.

O dono voltou dizendo que o DERVS **não aparecia mais**. Desta vez não houve
adivinhação: o `dervs_registro.py` instalado de tarde tinha gravado a morte, em
`%APPDATA%\dervs\ultimo_erro.txt.duro`, com o rastro exato.

```
Windows fatal exception: code 0xc0000374     <- corrupção de memória
  sounddevice.py:1168 in close
  dervs.py:313 in fechar
  dervs.py:429 in run
```

**Causa raiz:** duas threads fechavam o MESMO stream do PortAudio no mesmo
instante — a thread da tela, ao parar a escuta (`Escuta.parar()`), e a própria
thread de captura, no `finally` do laço `run()`. O guarda
`if self._stream is not None` não protegia nada: as duas passavam por ele antes
de qualquer uma zerar o atributo, e não havia trava nenhuma. Liberar duas vezes
a mesma memória — ou ler a já liberada, o outro lado da mesma corrida — faz o
Windows matar o processo NA HORA, sem traceback nem mensagem.

É por isso que os 14 apertos manuais da tarde **não reproduziram**: é corrida,
e depende de o `fechar()` cair dentro da janela de tempo em que o outro lado
está dentro do PortAudio. Era exatamente o "fecha sozinho quando aperto VOZ".

| Defeito | Onde | Efeito para o dono |
|---|---|---|
| **Duas threads fechando o mesmo microfone** | `dervs.py`, `Microfone.fechar` | o app **morre na hora**, sem deixar rastro na tela. Corrigido com duas travas: `fechar()` TOMA a fonte para si (troca atômica por None — só uma thread sai com ela na mão), `abort()`, espera o `ler()` em voo sair, e só então `close()` |
| **A dica de vocabulário era lida e nunca existia** | `dervs_config.PADRAO` | `dervs_transcrever.py` lia `stt_dica_vocabulario` para mandar como `prompt` à OpenAI, mas a chave não existia em lugar nenhum. O áudio ia para a nuvem **sem uma pista sequer** de que é português do Brasil falado com um assistente chamado DERVS |
| **`kill()` num objeto que não tem `kill()`** | `dervs.py`, fechamento do app | `GravacaoManual` é uma `QThread`; `kill()` é de `QProcess`. Fechar com uma gravação em andamento levantava `AttributeError` na PRIMEIRA linha do bloco e abortava **todo o resto**: escuta, voz, espera das threads e motor de transcrição ficavam de pé, órfãos |
| **Dois locks diferentes sobre o mesmo dado** | `dervs_tts.py`, `desligar` | os três daemons saíam sob `self._lock`, enquanto a thread da fala mexe neles sob `_lock_piper`/`_lock_kokoro`. Fechar no meio de uma fala matava o daemon com a thread ainda escrevendo nele — e o `except` genérico engolia |
| **A escuta nascia desligada** | `config.json` da máquina | o valor foi gravado **às 15:22, o minuto do crash**: o app anotou "ouvido desligado" enquanto morria. Não foi escolha do dono. Restaurado para `True` |

**Provado com o PortAudio de verdade**, não só com dublê: 60 rodadas de
abrir / ler-em-duas-threads / fechar-em-três-mãos. No código anterior o processo
morre na **mesma linha** do crash do dono; com a correção, sobrevive às 60.

**Prova A/B da dica**, 5 frases faladas, mesmo áudio transcrito duas vezes:

| | o nome "DERVS" | palavras não ensinadas |
|---|---|---|
| Sem dica | **0 de 5** — virava "Dervs", "Derves" | 84% |
| Com dica | **5 de 5** | 86% (ruído, não ganho) |

A leitura honesta: a dica acerta **o que está escrita nela, e só isso**. Por
isso o próximo passo de maior valor é o dono passar 20–30 nomes próprios dele
— clientes, empresas, pessoas, termos do ramo — para entrarem em
`stt_dica_vocabulario`. Nome próprio que o modelo nunca viu é o que ele mais
erra, e a dica é o único jeito de ensiná-lo sem treinar modelo nenhum.

**Órfãos:** medido que matar o app sem fechamento limpo deixa 3 processos
filhos vivos. Eles saem sozinhos por EOF do `stdin` em ~19 s — mas nesse
intervalo seguram o microfone, e um DERVS aberto aí parece "não funcionar".
Com o fechamento corrigido, saem na hora.

> **Precisão da armadilha do `PADRAO`** (a seção acima dizia menos do que
> devia): chave **nova**, que ainda não existe no `config.json`, chega sozinha
> — `carregar()` faz `dict(PADRAO)` e completa o que falta; foi assim que a
> dica de vocabulário alcançou a máquina do dono sem reescrever nada. Chave que
> **já existe** no arquivo com valor antigo é que não muda: aí é `cfg.gravar()`.

> **Cada passo do fechamento é independente** agora, e o que falha é dito no
> `stderr` em vez de engolido. Foi o `except Exception: pass` de bloco inteiro
> que manteve o `kill()` escondido. O próximo defeito nessa lista custa um
> passo, não o fechamento todo.

Detalhe e medições: `docs/esteira/windows-tempo-real/`.

## "Não está me ouvindo, e tem uma janela preta" — 02/09/2026, noite

Dois sintomas, duas causas raiz **diferentes**, e uma delas não é do software.

### 1. A surdez — e por que ela não era da transcrição

O `dervs_rec.wav` da última tentativa do dono (19h59) ainda estava no disco.
Medido, amostra por amostra:

```
duracao: 4.71 s
pico:    1  (max possivel 32767)  ->  0.0% da escala
rms:     0.5                      -> -96.7 dBFS
```

Isso é **silêncio digital puro**. O dono falou, e nada entrou. Passando esse
mesmo arquivo pelo daemon de verdade, ele responde certo e rápido:

```
READY
PORTEIRO {"acordou": false, "texto": ""}
RESULT ""
```

A transcrição nunca esteve quebrada: ela recebeu silêncio e devolveu vazio,
que é a resposta correta. O defeito estava **antes**, na entrada.

Gravando 3 s de cada entrada de áudio da máquina, uma por uma, todas as que
abrem devolvem pico 1. Não é o DERVS escolhendo o dispositivo errado. O
registro do Windows fecha o caso:

| Entrada | Estado |
|---|---|
| `Microfone` (Realtek) | ATIVO — mas alimentado por um conector vazio |
| `Front Pink In` | **DESCONECTADO** |
| `Rear Pink In` | **DESCONECTADO** |
| USB / webcam / Bluetooth | não existem nesta máquina |

**Causa raiz 1: não há microfone fisicamente ligado ao computador.** As duas
entradas rosa do gabinete estão vazias, e não há nenhuma outra fonte de áudio.
Isso precisa da mão do dono — nenhuma linha de código resolve.

O microfone também estava **mudo** no Windows (volume 72%, mudo=Sim). Foi
desmutado; o pico continuou 1, o que confirma que o mudo era um segundo
problema empilhado, não a causa. O DERVS **não** mexe no mudo do sistema —
`SetMute`, `amixer` e afins não aparecem em lugar nenhum do código.

**Causa raiz 2, essa sim do DERVS: ele ficou calado sobre isso.** Gravou 4,71 s
de silêncio, mandou para a OpenAI, pagou a chamada, recebeu `""` e mostrou um
campo vazio. O dono concluiu, com toda a razão, que "a transcrição não
funciona". Silêncio não é falha de transcrição — é falha de ENTRADA, e tem de
ser dita com todas as letras.

Corrigido em `dervs_listen.py` (`pico`, `esta_mudo`, `motivo_do_silencio`) e
`dervs.py` (`GravacaoManual.mudo`, `_gravacao_fechada`). Agora uma gravação sem
som **não vai para a nuvem** — economiza dinheiro — e a tela diz, em português:

> não entrou som: o microfone está mudo no Windows ou desconectado da entrada rosa

ou, quando o sistema não enxerga entrada nenhuma:

> não entrou som: nenhum microfone foi encontrado neste computador

O limiar é pico ≤ 30 numa escala de 32.767, folgado de propósito: um microfone
ligado num quarto silencioso já entrega chiado na casa das centenas, então uma
fala fraca de verdade nunca é confundida com cabo solto.

### 2. A janela preta

O rastro estava nos processos, não no código-fonte:

```
conhost.exe 22744  <- pai 19008  dervs_stt_daemon.py     (o ouvido)
conhost.exe 41280  <- pai  3528  dervs_kokoro_daemon.py  (a voz)
```

`conhost.exe` é o programa que **desenha** a janela de terminal do Windows.
Os dois ajudantes eram abertos com `python.exe` — a versão do Python que vem
**com** terminal — e sem nenhuma bandeira mandando escondê-lo. O Windows fez
exatamente o que foi pedido.

O atalho do app já usava `pythonw` desde sempre (por isso o próprio DERVS não
abria janela); o que ninguém tinha notado é que **os filhos dele** não usavam.

Corrigido em `dervs_processos.py`, com duas camadas de propósito:

| Camada | O que faz | Por que as duas |
|---|---|---|
| `python_sem_console()` | troca `python.exe` por `pythonw.exe` ao lado | resolve na raiz |
| `sem_janela()` | acrescenta `CREATE_NO_WINDOW` ao `subprocess` | cobre o dia em que alguém apontar `DERVS_PY` para um `python.exe` na mão |

Se o `pythonw.exe` não estiver ao lado, o caminho original é mantido sem
reclamar: janela preta incomoda, caminho quebrado deixaria o DERVS sem voz e
sem ouvido.

**Provado depois de reiniciar o app** — todos os ajudantes em `pythonw.exe`, e:

```
NENHUMA janela de terminal pendurada no DERVS
```

Nenhum processo `WindowsTerminal` sobrou na máquina.

