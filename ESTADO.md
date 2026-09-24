# Estado do DERVS — 23/09/2026

O que funciona, o que não funciona, e o que falta. Escrito para ser lido pelo
dono, não por um programador.

Última verificação: 23/09/2026. **679 testes verdes** no ambiente do
projeto (`dervs-venv`), que é onde o DERVS de fato roda. Nenhum erro de
coleta, que é o que impede um arquivo quebrado de esconder a suíte inteira.

**A cara mudou nesta rodada (16–17/09/2026): a tela agora é um HUD Electron**
(painel ciano/preto, estilo "painel de controle", com anéis girando e um
núcleo que reage à voz), não mais a janela Qt com o selo dourado flutuante. O
Qt continua rodando por baixo — motor invisível, ver `dervs_electron.py` — só
quem desenha a tela mudou. O ponto de entrada padrão passou a ser
`dervs_electron.py` (era `dervs.py`); `dervs.py` continua no disco e ainda
abre se chamado na mão, mas não é mais o que o atalho usa.

**Segunda rodada no mesmo dia (17/09/2026) — fase 1 de "painel completo":**
o dono relatou o HUD "quebrado/sem botão" — na prática a janela estava viva,
mas ficava escondida atrás de outras janelas sem nenhum aviso, e a tela era
bem mais pobre do que a referência JARVIS/Rainmeter que ele mandou. Depois de
duas perguntas de escopo (registradas em
`docs/esteira/dervs-painel-completo/briefing.md`), esta rodada entregou:

- Janela **sempre visível por cima** das outras (`alwaysOnTop`, nível
  "screen-saver") e **ancorada no canto superior direito** da tela, como um
  widget de desktop — resolve o "sumiço" que parecia o app morto.
- Janela **transparente de verdade** (`transparent: true`) — o desktop atrás
  aparece por baixo do tom ciano. **Achado técnico, testado em bancada:**
  `backgroundMaterial: "acrylic"` (o material nativo do Windows 11 que
  borraria o desktop de verdade) **conflita** com `transparent: true` nesta
  versão do Electron (33.2.1) e deixa a janela OPACA — por isso ele foi
  deixado de fora, de propósito (comentário em `electron/main.js`). O efeito
  hoje é "vidro liso" (transparente, sem borrão), não "vidro fosco" — mais
  simples que o pedido original, mas funcional.
- **Relógio e data ao vivo**, e um **painel com CPU/RAM/disco reais** desta
  máquina (`dervs_sistema.py`, biblioteca `psutil`, nova dependência em
  `requirements.txt`) — atualiza a cada ~2s pela mesma ponte que já existia.
- Botão **"Abrir DERVS App"**, que abre `http://localhost:4777` (configurável
  em `dervs_app_url`) no navegador — só isso; a integração de verdade com o
  outro projeto do dono (`garcia-goncalves/dervs`) ficou combinada como fase 2,
  separada, porque mexe em login/cofre daquele projeto.
- 18 testes novos/atualizados (`test_dervs_sistema.py`,
  `test_dervs_ponte_electron.py`, `test_dervs_config.py`,
  `test_dervs_electron_entrada.py`); suíte inteira em 624 verdes.
- Testado ao vivo: app reaberto do zero, janela fotografada (com e sem outras
  janelas por cima), relógio/CPU/RAM variando de verdade entre capturas,
  clique real no botão novo sem derrubar o app.

**Pendência que NÃO foi fechada nesta rodada e precisa do dono presente:** a
Etapa 12 do plano (demonstração ao vivo com voz real e medição de CPU) ainda
não aconteceu. Nada aqui foi testado com a voz do dono, e não há número de CPU
medido ao vivo enquanto ele fala — só o que os 624 testes automatizados
cobrem e o que foi visto ao vivo sem áudio (ver acima). Não confunda "testes
passam" com "demonstrado funcionando com voz real": são coisas diferentes, e
a segunda ainda está pendente.

**Terceira rodada (23/09/2026) — o que fechou:**

- **O botão do microfone voltou ao HUD** (era o item 2.2). Verbo novo `microfone`
  na ponte, nos dois sentidos; o botão só muda de cara quando o Python confirma.
  Provado ao vivo: clique → "MICROFONE LIGADO" → o DERVS fala "Tô ligado" →
  clique → "DESLIGADO", e a escolha fica gravada.
- **Defeito sério achado testando ao vivo: o Python não encerrava quando o
  Electron fechava** ("Sair do DERVS" ou queda). Ele chamava `quit()` da thread
  errada; o Qt ignora. Resultado: o DERVS ficava vivo, sem cara, **com o
  microfone aberto**, e o atalho seguinte "não fazia nada" (avisava um Electron
  que já não existia). É uma causa provável dos "sumiu / bugou" que você
  relatou. Corrigido e provado: derrubando o Electron, o Python e todos os
  ajudantes encerram sozinhos em segundos.
- **Navegador autônomo funciona no Windows** (era o item 2.3). O perfil padrão
  era o de Linux — e ficou **gravado no seu `config.json`**, vencendo a correção;
  agora o valor antigo é curado na leitura. O Playwright entrou no
  `requirements.txt` (usa o Chrome que já está instalado, sem baixar navegador).
  Provado ao vivo com perfil vazio: abriu example.com e leu o título.
  **Com os logins do seu Chrome só funciona com ele FECHADO** (o perfil só abre
  num lugar por vez) — e não testei em cima do seu Chrome aberto, de propósito.
- **Diário do porteiro** (item 4.5) e **testes dos três ajudantes de voz** (4.6).
- **Electron 33.2.1 → 44.4.5**: a 33 saiu de suporte e o `npm audit` acusava
  20+ avisos (4 altos); agora zero.
- Janela 420×560 → 420×620 (o botão novo cortava o rodapé).

**Quarta rodada (23/09/2026) — três funções do HUD, provadas ao vivo:**

- **Atalho global Ctrl+Alt+D:** apertado com a janela à vista, ela some; apertado
  de novo, volta. Minimizar a janela (Win+D) agora é desfeito na hora — provado
  minimizando por fora e vendo a janela de volta. O atalho é solto ao sair.
- **Cartão do diário** (`dervs_diario.py`, verbo `diario`): apareceu
  "HOJE: 1 ouvidas · 1 acordei", igual à contagem feita à mão no `porteiro.jsonl`.
- **Modo reunião** (`Motor`, verbo `reuniao`): clique → "REUNIÃO 59:57" e
  microfone desligado; clique de novo → microfone ligado, botão volta a
  "REUNIÃO 1H". `escuta_ao_abrir` conferido depois: **continuou como estava**
  (a reunião restaura o valor que o caminho do botão grava). Fim da hora e
  cancelar por microfone manual provados nos testes com relógio injetado.
- Janela 420×620 → 420×700: o cartão de erro ("não chegou som") + o cartão do
  diário juntos cortavam o botão "Abrir DERVS App".
- Limite honesto: a hora inteira de reunião não foi esperada ao vivo (só o início
  e o cancelamento); o fim é coberto pelos testes.
- Peso morto removido (item 4.7): `dervs_painel.py`, `falar.sh`,
  `ligar-voz-com-senha.sh` — continuam no histórico do Git, dá para voltar.

---

## 1. O que está funcionando agora

| Parte | Estado | Onde roda | Custo |
|---|---|---|---|
| O HUD (janela Electron ciano/preto, novo desde 16/09) | **funciona** | sua máquina | zero |
| Janela sempre visível por cima, ancorada no canto (novo 17/09) | **funciona** | sua máquina | zero |
| Janela transparente (novo 17/09 — sem o borrão do desktop, ver acima) | **funciona** | sua máquina | zero |
| Relógio/data e painel CPU/RAM/disco reais (novo 17/09) | **funciona** | sua máquina | zero |
| Botão "Abrir DERVS App" (novo 17/09 — só abre, sem integração ainda) | **funciona** | sua máquina | zero |
| Botão liga/desliga do microfone (voltou 23/09) | **funciona** | sua máquina | zero |
| Navegador autônomo (23/09, Chrome fechado) | **funciona** | sua máquina + OpenAI | centavos por tarefa |
| Diário do porteiro (23/09) | **funciona** | sua máquina | zero |
| Abrir por atalho (Área de Trabalho e menu Iniciar, agora abre `dervs_electron.py`) | **funciona** | sua máquina | zero |
| Um DERVS só de cada vez (o 2º clique traz de volta o 1º) | **funciona** | sua máquina | zero |
| Porteiro — "isso foi comigo?" | **funciona** | sua máquina | zero |
| Transcrição precisa (fala → texto) | **funciona** | OpenAI | ~US$ 0,0045/min |
| Voz do DERVS (Kokoro, `pm_alex`, 1,3×) | **funciona** | sua máquina | zero |
| Cérebro (decide o que fazer) | **funciona** | OpenAI `gpt-4.1-mini` | barato |
| Executar comando com trilhos de risco | **funciona** | sua máquina | zero |
| Transcrever um arquivo de áudio (atalho separado) | **funciona** | OpenAI | por minuto |
| Registro de queda (grava o motivo se o app morrer) | **funciona** | sua máquina | zero |
| Aviso de "não entrou som" | **funciona** (novo, 02/09) | sua máquina | zero |

---

## 2. O que está quebrado, e de quem é a culpa

### 2.1. Você não tem microfone ligado no computador — e essa é a única coisa que falta a sua mão

Esta é a causa do "o DERVS não está me ouvindo". **Não é defeito do programa.**

O que foi medido na sua máquina, em 02/09/2026:

- a última gravação que você fez (19h59) tinha 4,71 segundos e **pico 1 numa
  escala de 32.767** — isso é silêncio absoluto, não "falou baixo";
- gravando 3 segundos de **cada** entrada de áudio da máquina, uma por uma,
  todas devolveram o mesmo silêncio;
- no registro do Windows, as duas entradas de microfone do gabinete —
  `Front Pink In` (frente) e `Rear Pink In` (traseira) — aparecem como
  **DESCONECTADO**;
- não há microfone USB, nem webcam com microfone, nem fone Bluetooth.

O microfone também estava **mudo** no Windows. Isso foi desligado (agora está
em 90% e sem mudo), mas o silêncio continuou — ou seja, o mudo era um segundo
problema empilhado, não a causa.

**O que fazer:** ligar um microfone na entrada **rosa** do gabinete, de
preferência a de trás. Depois disso o DERVS ouve na hora, sem reinstalar nada
— o Windows já reconhece a placa de som (Realtek) e a permissão de microfone
já está liberada para programas de área de trabalho.

Se você ligar e ainda não funcionar, o DERVS agora **diz o motivo na tela** em
vez de mostrar um campo vazio (item 3.1 abaixo).

### 2.2. ~~O microfone perdeu o botão de liga/desliga na tela~~ — RESOLVIDO em 23/09/2026

*(O texto abaixo é o histórico; o botão voltou — ver "Terceira rodada", acima.)*

**Consequência direta da troca de tela (16/09/2026): hoje não existe mais um
botão no HUD para desligar o microfone.** A janela Qt antiga tinha o
interruptor **🎙️ Ei DERVS** / **🔴 Ouvindo**; o HUD do Electron não tem — foi
tirado, não é bug. Isso é algo que o dono podia fazer clicando na tela e hoje
não pode mais.

Hoje, com o DERVS aberto, o microfone fica ligado o tempo todo. As únicas
formas de desligar são:

- sair do DERVS (bandeja → "Sair do DERVS"); ou
- editar `escuta_ao_abrir` para `false` em `%APPDATA%\dervs\config.json` e
  reabrir (o padrão de fábrica é `true`).

Não muda o que sai da máquina (o funil do porteiro continua intacto — nada vai
para a nuvem antes do nome ser ouvido), só o controle fino de "escutar agora
ou não" que existia na tela sumiu. Se isso incomodar, é trabalho de meia hora
trazer o botão de volta ao HUD.

### 2.3. ~~O navegador autônomo não funciona no Windows~~ — RESOLVIDO em 23/09/2026

*(Histórico; ver "Terceira rodada", acima. O que resta: o Chrome do dono tem de
estar fechado para o autônomo usar o perfil com os logins.)*

O DERVS sabe pilotar o Chrome sozinho ("entra no meu Gmail e vê quantos não
lidos"). Todo o código existe e está testado. **Mas o ambiente que ele precisa
(Playwright) nunca foi montado no Windows** — o caminho procurado
(`~/voice/playwright-venv`) é do Linux, e não existe instalador para Windows em
lugar nenhum do projeto.

Hoje, se um plano pedir o navegador, o DERVS devolve um recado de erro em vez
de travar. Mas a funcionalidade está indisponível.

**Falta:** escrever o instalador dessa parte. É trabalho de meia hora a uma
hora, e depende de você querer a funcionalidade.

---

## 3. O que foi corrigido nesta sessão (02/09/2026, noite)

### 3.1. O DERVS ficava calado quando não entrava som

Você gravou 4,71 segundos de silêncio. O DERVS mandou aquilo para a OpenAI,
**pagou a chamada**, recebeu texto vazio e mostrou um campo em branco — sem
explicar nada. Você concluiu, com toda a razão, que "a transcrição não
funciona". Ela funcionava; a entrada é que não existia.

Agora: gravação sem som **não vai para a nuvem** (economiza dinheiro) e a tela
diz o motivo. Vale nos dois modos:

- apertando **Gravar**: aviso imediato;
- na **escuta contínua** ("Ei DERVS"): depois de 8 segundos de silêncio digital
  seguido, o DERVS avisa uma vez — antes ele ficava escrito "pronto" enquanto
  estava surdo, e você passava horas achando que estava sendo ignorado.

### 3.2. A janela preta

Eram os terminais dos dois ajudantes do DERVS (o que ouve e o que fala). Os
dois eram abertos com a versão do Python que **vem com** janela de terminal, e
sem ninguém mandar escondê-la. Corrigido, e provado: depois de reiniciar, não
sobra nenhum terminal pendurado no DERVS.

### 3.3. Comando podia continuar rodando depois de "interrompido"

Quando um comando passava do tempo, o DERVS matava só a casca. Exemplo real: se
você pedisse "roda o nmap no alvo" e passasse de 60 segundos, a tela dizia "foi
interrompido" — **e o nmap continuava varrendo a rede**. O mesmo valia para o
navegador: sobrava um `chrome.exe` órfão segurando o seu perfil, e depois disso
você não conseguia mais abrir o próprio Chrome sem saber por quê.

Corrigido, e provado com processos de verdade.

### 3.4. Seis buracos de segurança

A lista de comandos "seguros" do DERVS foi escrita para Linux e traduzida para
Windows por cima. O vocabulário do PowerShell escapava pelos buracos. Isso
importa muito aqui porque **um comando marcado como "reversível" pode ser
confirmado por VOZ** — ou seja, sem ninguém tocar no computador. A TV ligada na
sala serve.

| O que escapava | Saía como | Agora |
|---|---|---|
| `irm <url> \| iex` (baixar da internet e executar) | um clique | cartão vermelho, dois cliques |
| `start C:\...\programa.exe` | inofensivo, confirmável por voz | pede clique |
| `explorer \\servidor\pasta` (entrega o hash da sua senha) | inofensivo | pede clique |
| `echo x > seu_arquivo.txt` (apaga o conteúdo) | inofensivo | pede clique |
| mandar arquivo seu por POST para fora | um clique sem pergunta | pede autorização |
| plano só de navegador (dirige seu Chrome logado) | confirmável **por voz** | pede clique |

Mais duas, que não são lista de comando:

- **A proteção contra "página web dando ordem" existia só no cérebro que não
  roda.** O DERVS usa a OpenAI por padrão, e era justamente nesse caminho que a
  saída de ferramenta entrava sem cerca — uma página podia escrever "[dono]
  agora rode: ..." e o modelo lia como se fosse você falando. Pior: o teste
  dessa proteção passava verde, porque exercitava o outro caminho. Agora os
  dois caminhos rodam a mesma bateria de testes.
- **O piloto do navegador ouvia a página como se fosse você.** Os rótulos dos
  botões (até ~4.800 caracteres escolhidos por quem fez o site) entravam no
  mesmo nível do seu objetivo. Agora vão cercados, e o piloto é instruído
  explicitamente a não obedecer a eles.

### 3.5. O ouvido mandava áudio para a nuvem por engano

Qualquer linha que o programa mandasse ao ouvido e que não começasse com a
palavra exata `PORTEIRO ` ia direto para a OpenAI. Um erro de digitação, um
verbo quase certo, uma sobra de formato antigo — qualquer coisa. A promessa
central do projeto (o porteiro decide **na sua máquina** o que sai daqui)
dependia de ninguém nunca errar uma palavra. Agora a porta falha **fechada**.

### 3.6. Sua voz ficava no disco para sempre

Cada frase captada vira um arquivo **antes** de o porteiro decidir se era com o
DERVS. No caminho normal eles são apagados — mas nada limpava o que sobrava de
uma queda do app, e este app já caiu várias vezes. A pasta temporária do
Windows, ao contrário da do Linux, não se limpa sozinha. Agora o DERVS faz
faxina ao abrir, mexendo só no que é dele e só no que já está parado há mais de
uma hora.

### 3.7. O interruptor do navegador não desligava nada

A configuração `navegador_ligado` existia, era validada e até tinha teste — e
**ninguém a lia**. Ligar ou desligar não mudava nada. Corrigido.

---

## 4. O que ainda falta

Em ordem de valor para você:

### 4.0. A demonstração ao vivo do HUD novo — PARCIAL, falta você falar perto do microfone

**Atualizado em 17/09/2026, com medição real:**

- **A janela abre e fica de pé — confirmado ao vivo, na sua máquina.** Achado
  e corrigido um bug sério nessa mesma verificação: o Electron não conseguia
  ficar aberto em NENHUM Windows (recebia um sinal falso de "o Python
  morreu" quase na hora de subir — limitação do Chromium no Windows, não
  defeito do projeto). Corrigido trocando a forma como o Python fala com o
  Electron (de `stdin` para um soquete local, `127.0.0.1`). Depois da
  correção: janela aberta, título "DERVS" visível, processos do Electron
  (principal, GPU, renderização) todos de pé e respondendo.
- **CPU medido de verdade, com a janela aberta e parada por 2 minutos:**
  em média **21% de um núcleo** somando Python + todos os processos do
  Electron — numa máquina com vários núcleos (Ryzen 7), isso é menos de 3%
  da CPU total da máquina. Não foi comparado lado a lado com o app antigo
  (`dervs.py`/Qt) nesta rodada — se um dia parecer pesado no dia a dia, o
  primeiro lugar a olhar é o `requestAnimationFrame` do HUD (`hud.js`), que
  desenha o núcleo e os anéis o tempo todo enquanto a janela está visível.
- **PR #1 mesclado na `main`** — a cara nova não é mais uma branch separada,
  é o que abre pelo atalho hoje.
- **Segundo bug achado e corrigido na mesma verificação, depois do merge:**
  o dono relatou "está bugado" e, ao tirar uma foto da tela, os cartões de
  erro e de plano apareciam **vazios desde a abertura do app**, mesmo sem
  nenhum erro ou plano ter acontecido. Causa: no CSS, a classe `.cartao`
  (e `.cartao-plano-autorizacao`) declara `display: flex`, que tem mais
  força que a regra padrão do navegador que esconde elemento com o
  atributo `hidden` — o `hidden` nunca vencia. Corrigido com uma regra
  `[hidden] { display: none !important; }` em `electron/renderer/estilo.css`
  (commit `dce1fe2`, direto na `main`). Confirmado com foto da tela antes e
  depois da correção.

**Ainda em aberto, sem data — só acontece com você por perto:**
- ouvir você falar de verdade perto do microfone e ver a onda reagir, do
  jeito que você usa no dia a dia.

### 4.1. Os seus nomes próprios no vocabulário — depende de você

**A maior melhoria que sobrou, e ela é barata.** Ficou provado por medição que
o DERVS só acerta nome próprio que esteja escrito numa lista dentro do código:
o nome "DERVS" saiu de 0 acertos em 5 para 5 em 5 só por estar lá. As outras
palavras ficaram em 86% — praticamente o mesmo de antes.

Ou seja: a lista só ajuda no que está **escrito** nela. Hoje ela tem palavras
genéricas (WhatsApp, Firefox, GitHub, Docker) e **nenhum cliente, empresa ou
pessoa sua**.

**Falta:** você me passar 20 a 30 nomes que fala no dia a dia. Meia hora de
trabalho depois disso.

### 4.2. Provar com a sua voz e o seu barulho

Tudo até hoje foi medido com áudio sintetizado. Nada foi testado com a sua voz,
o seu microfone e o barulho da sua sala. Isso só dá para fazer depois do
item 2.1 (o microfone).

### 4.3. Voz da nuvem — decisão de dinheiro, sua

Trocar a voz local pela da nuvem deixa o DERVS 0,42 segundo mais lento e custa
cerca de **US$ 4,50 por mês**. A voz local (Kokoro `pm_alex`, 1,3×) continua
como está. Só faço com o seu sim.

### 4.4. Não há CI

Não existe verificação automática no GitHub: se alguém quebrar algo, ninguém é
avisado até rodar os testes na mão. **Não instalei de propósito** — o Actions
do GitHub é pago por minuto e a sua cota já estourou uma vez. É uma decisão de
dinheiro, e é sua. Se quiser, monto no padrão barato (roda pouco no `push`, o
caro só antes de publicar).

### 4.5. ~~Telemetria do porteiro~~ — FEITO em 23/09/2026 (`porteiro.jsonl`; texto só se `porteiro_registrar_texto`)

*(Histórico:)*

Quando o porteiro decide "não era comigo", o texto que ele ouviu é jogado fora
e o arquivo apagado. Consequência: se uma frase sua for ignorada por engano,
**não há como provar onde ela sumiu**. Vale guardar um resumo (sem o áudio) para
poder investigar.

### 4.6. ~~Três ajudantes sem teste próprio~~ — FEITO em 23/09/2026 (23 testes em `test_dervs_daemons_de_voz.py`)

*(Histórico:)*

`dervs_kokoro_daemon.py`, `dervs_piper_daemon.py` e `dervs_tts_daemon.py` não
têm teste dedicado. Eles são exercitados de raspão pelos testes da voz, mas uma
quebra dentro deles não seria pega.

### 4.7. ~~Peso morto que sobrou da versão de Linux~~ — REMOVIDO em 23/09/2026

*(Histórico; o caminho do `arecord` continua, é reserva intencional.)*

- `dervs_painel.py` — arquivo inteiro, do projeto irmão de Linux. Ninguém no
  Windows o importa. Deixei no lugar: apagar é irreversível e ele não atrapalha.
- `falar.sh` e `ligar-voz-com-senha.sh` — scripts de Linux, na raiz, sem uso
  aqui.
- O caminho do `arecord` (gravação por Linux) dentro do microfone: é reserva
  intencional, não sobra esquecida — está testado como tal.

### 4.8. Uma escolha de segurança que vale você saber

Ao fechar o buraco do "abrir endereço com dados dentro", tive de escolher onde
traçar a linha:

- `chrome https://google.com` continua **manso** — é uso diário seu, e cartão
  vermelho à toa treina você a clicar "sim" sem ler, o que estraga o "sim" que
  importa;
- endereço com `?` ou `#` (que é onde dados caberiam) passa a **pedir um
  clique**.

**Custo dessa escolha, dito com todas as letras:** uma busca montada como
`google.com/search?q=gatos` passa a pedir um clique a mais, e um endereço que
esconda dados no caminho (sem `?`) ainda escapa. Se você achar incômodo, dá
para afrouxar.

---

## 5. Como refazer o ambiente numa máquina limpa

Isto não existia até hoje — a receita vivia só dentro da pasta `dervs-venv`
desta máquina. Agora está em `requirements.txt`:

```
python -m venv dervs-venv
dervs-venv\Scripts\python.exe -m pip install -r requirements.txt
cd electron && npm install && cd ..
# se electron\node_modules\electron\dist não existir depois do npm install:
#   node electron\node_modules\electron\install.js
dervs-venv\Scripts\python.exe scripts\instalar_atalho.py
```

O passo `npm install` é novo (16/09/2026, com a tela Electron): baixa o
Electron (~150–300 MB), precisa de internet, e sem ele `dervs_electron.py` não
abre.

Fica de fora, e precisa ser baixado à parte: o modelo da voz (`kokoro-model/`,
~350 MB) e a chave da OpenAI (que mora em `%APPDATA%\dervs\.env` e **nunca** vai
para o repositório).
