# Briefing — DERVS no Windows, em tempo real

## pedido_original

> Comece e faça tudo pra funcionar perfeitamente o DERVS no meu Windows. Quero ele bem
> inteligente, rápido e assertivo. Dê o melhor de si. Ative todos os seus agentes
> necessários para ter maior produtividade. Quero o DERVS o mais "tempo real" possível
> (alta performance. Mas tbm quero que seja econômico. Não quero gastar rios de
> dinheiro)... Quero tbm que tenha o "liga/desliga" para quando ele tiver "ligado" ele
> ouça tudo o que tiver rolando no meu ambiente. Mas só será ativado quando eu falar o
> nome dele "DERVS" ou "OK DERVS" algo assim. Quero a forma mais precisa pra ele
> acordar/despertar/me entender. E isso é você que escolhe o melhor pra mim. Quero suas
> melhores ideias. Pode começar por onde achar melhor. Em ordem e bem organizado. Quero
> tbm que tenha a parte de TRANSCREVER O QUE EU FALO. COM PRECISÃO. Quero que o DERVS
> tenha uma voz o mais humana possível (e fale rápido. Não quero que fale mole igual um
> robô/IA) BORA!

## entendimento

Fazer o DERVS rodar no Windows 11 do dono, ligado o dia inteiro ouvindo o ambiente, mas
só acordando quando ouvir o nome dele — e fazendo isso **sem mandar o áudio do dia
inteiro para a nuvem**, que é como funciona hoje e é o que tornaria a conta cara e a
escuta indiscreta. Depois de acordado, transcrever o pedido com precisão, responder
rápido e falar de volta com voz humana e ritmo de gente, não de robô. A meta de tempo é
o dono parar de falar e o DERVS começar a responder em torno de 2 segundos.

## usuario_alvo

O dono do repositório, no computador dele, usando o DERVS como assistente de voz durante
o trabalho. **Não é desenvolvedor** e não opera terminal: tudo tem de subir por atalho,
ícone ou comando único que outra pessoa executa por ele. A lente DX não se aplica ao uso;
aplica-se só à manutenção futura do próprio repositório.

## criterio_de_aceitacao

Cada item é verificável por comando, por teste ou por escuta direta.

1. `dervs-venv\Scripts\python.exe -m pytest -q` roda **116 de 116 testes verdes** na
   máquina Windows do dono (hoje: 112 verdes, 4 vermelhos).
2. `python -c "import dervs_atalhos as a; print(a.tentar('abre o chrome'))"` devolve um
   plano com um comando que **existe no Windows** (não `google-chrome`).
3. Existe um teste automatizado que prova que **nenhum áudio sai da máquina antes da
   palavra de acordar**: o portão de despertar é avaliado sobre transcrição **local**, e
   a função que chama a nuvem só é acionada depois que o portão abre. Provado com dublê
   (mock) que falha o teste se a ordem inverter.
4. Medição gravada em `docs/esteira/windows-tempo-real/verificacao.md`, feita nesta
   máquina, com número real (não estimativa) para: (a) tempo do portão local de
   despertar, (b) tempo da transcrição na nuvem, (c) tempo do cérebro, (d) tempo até o
   primeiro som da voz. A soma dos quatro é o "tempo até responder".
5. O dono fala "DERVS" e "OK DERVS" ao microfone e o programa acorda; fala 10 frases
   comuns sem o nome e o programa **não** acorda nenhuma vez.
6. Existe um liga/desliga visível: um clique (ou um atalho de teclado) põe o DERVS em
   escuta contínua e outro clique o cala. O estado é visível na tela sem abrir menu.
7. A voz sai pelos alto-falantes no Windows sem `aplay`/`paplay`/`pw-play`, e o dono
   escolhe entre pelo menos 3 amostras de voz geradas nesta máquina, com velocidade
   ajustável por configuração.
8. `python -c "import dervs_config as c; print(c.CONFIG_PATH)"` aponta para uma pasta do
   Windows (`%APPDATA%`), não para `~/.config`.
9. Um comando destrutivo típico do Windows (ex.: `Remove-Item -Recurse -Force C:\`,
   `format`, `del /f /s /q`) é classificado como **destrutivo** por `dervs_safety`, com
   teste que prova.
10. Um documento em português explica ao dono, sem jargão, como ligar, desligar, trocar
    a voz e quanto custa por mês.

## fora_de_escopo

- **Portar o `dervs_enrich.py` (OSINT com `bbot`)** — a ferramenta `bbot` não roda em
  Windows sem WSL. O módulo fica no repositório, desligado, com mensagem clara.
- **Portar o `dervs_painel.py`** — é programa solto e legado, não é importado por
  ninguém no projeto. Fica como está, marcado como legado.
- **Navegador autônomo (`dervs_browser.py`)** — depende de Playwright e do perfil do
  Chrome; o caminho do perfil será corrigido para Windows, mas validar o agente de
  navegação ponta a ponta é trabalho próprio, de outra rodada.
- **Serviço que sobe sozinho no boot** — na primeira rodada o DERVS sobe por atalho. A
  Tarefa Agendada entra depois que o comportamento estiver estável.
- **Streaming de áudio dentro da mesma frase** — o projeto já testou e descartou por
  engasgar sem placa de vídeo dedicada; esta máquina também não tem uma.
- **Trocar o provedor do cérebro** — segue OpenAI com reserva no Claude, como hoje.

## riscos

1. **Escuta contínua é dado sensível.** O DERVS ligado ouve reunião, ligação e conversa
   de família. Mitigação, que é o coração desta rodada: o áudio só sai da máquina depois
   da palavra de acordar; antes disso tudo é processado localmente e descartado. Precisa
   de teste automatizado provando a ordem (critério 3).
2. **A rede de segurança de comandos está escrita para Linux.** `dervs_safety.py`
   reconhece `rm -rf`, `mkfs`, `dd` — e não reconhece `Remove-Item -Recurse -Force`,
   `format`, `diskpart`, `del /f /s /q`. Enquanto não for portada, um comando destrutivo
   do Windows pode ser classificado como leve e rodar com confirmação fraca. **É o item
   de maior risco desta rodada** e por isso vira portão de risco na fase 6.
3. **O prompt do cérebro manda o LLM usar binários do Linux.** Rodando no Windows, ele
   sugeriria `konsole` e `firefox`. Corrigir o prompt faz parte da rodada.
4. **Custo de nuvem depende da inversão do portão dar certo.** Se o portão local falhar e
   o programa cair no comportamento antigo, a conta vai de poucos dólares por mês para
   dezenas. Precisa de trava explícita, não só de boa intenção.
5. Sem dado de paciente. Sem pagamento. Sem migration. Sem produção. Sem deploy.

## plano_de_voo

**Modo: enxuto.** O domínio já está mapeado — dois relatórios de leitura completa do
código foram feitos nesta sessão e cobrem entrada de áudio, saída de voz, cérebro,
execução, segurança, atalhos e tudo que é específico de Linux. A fase 2 (Descoberta) não
precisa redescobrir nada; vira **um** despacho com as perguntas que sobraram, que são de
pesquisa externa (preço e precisão de transcrição, opções de detector de palavra-chave).

**Fase 3 (Design) fica desligada.** Não há tela nova: a interface PyQt já existe e o que
muda é comportamento, não estética. O liga/desliga entra na janela que já existe.

| Fase | Liga? | Papéis | Modelo | Despachos |
|---|---|---|---|---|
| 1 Interrogador | sim | eu mesmo, já feito | opus | 0 |
| 2 Descoberta | sim, enxuta | 1 pesquisador (preço/precisão de STT e detector de palavra-chave) | sonnet | 1 |
| 3 Design | **não** | — | — | 0 |
| 4 Plano | sim | neguin-planner | opus | 1 |
| 5 Execução | sim | neguin-executor em worktrees isoladas, por trilha independente | sonnet | 4 |
| 6 Revisão | sim | python-reviewer, security-reviewer (portão de risco: rede de segurança), verificador técnico | opus (security) + sonnet | 3 |
| 7 Cronista | sim | doc, memória, CI, PR, handoff | sonnet | 1 |

**Número de despachos previsto: 10.** Mais os 2 já gastos na leitura do código = 12 no
total desta rodada.

**As quatro trilhas da fase 5**, escolhidas por não se cruzarem nos mesmos arquivos:

- **A — Áudio no Windows:** captura e reprodução via `sounddevice` no lugar de
  `arecord`/`pw-play`; caminhos `/tmp` viram pasta temporária do Windows; caminhos de
  ambiente Python `bin/python` viram `Scripts\python.exe`; configuração vai para
  `%APPDATA%`. Arquivos: `dervs_listen.py`, `dervs_tts.py`, `dervs_config.py`,
  `calibrar_microfone.py`, os três daemons de voz.
- **B — O portão de despertar (o item central):** inverter a ordem para que a palavra de
  acordar seja decidida **localmente**, antes de qualquer chamada à nuvem; memória
  circular de áudio para não perder o começo da frase; aceitar "DERVS", "OK DERVS", "EI
  DERVS" com limiar mais frouxo na forma de duas palavras, que é mais difícil de
  acontecer por acaso. Arquivos: `dervs_listen.py`, `dervs_stt_daemon.py`, `dervs.py`.
- **C — Windows por dentro:** atalhos de aplicativo, comandos de execução, rede de
  segurança e o prompt do cérebro, todos passados para o vocabulário do Windows.
  Arquivos: `dervs_atalhos.py`, `dervs_exec.py`, `dervs_safety.py`, `dervs_brain.py`.
- **D — Liga/desliga e voz:** botão de estado visível, atalho de teclado global,
  velocidade de fala configurável, três amostras de voz geradas para o dono escolher.
  Arquivos: `dervs.py`, `dervs_tts.py`.

A trilha B depende da A (precisa do áudio entrando por `sounddevice`); C e D são
independentes das outras duas e rodam em paralelo desde o início.
