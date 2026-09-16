# Lente do Analista — a cara nova do DERVS e o documento de arquitetura

## Quem usa

Uma pessoa só: o dono do repositório, dono também da máquina Windows e do VPS. Não é
programador — não abre terminal, não lê stack trace, decide produto no olho e na voz. Isso
está registrado no `ESTADO.md` (ex.: "Escrito para ser lido pelo dono, não por um
programador", linha 4) e confirmado pelo próprio pedido no
`docs/esteira/dervs-cara-nova/briefing.md` ("não sei se estou sabendo me expressar", linha
9) — ele fala em imagem e sensação ("futurista", "surreal", "muito louco"), não em
especificação técnica.

Hoje ele já convive com duas peças de interface, ambas em `dervs.py`: o selo flutuante
sempre-no-topo (`class Launcher`, `dervs.py:1504`) e a janela central de conversa
(`class PopUp`, `dervs.py:402`), mais o ícone permanente na bandeja com "Sair do DERVS"
(`_montar_bandeja`, `dervs.py:1640`). É essa experiência de três peças que a cara nova
Electron substitui — não é greenfield para ele, é uma casa que ele já mora e não pode ficar
pior nela nem por um dia.

Não existe segundo usuário. Não há equipe, não há cliente, não há administrador diferente
do dono. Todo "quem controla o quê" no documento de arquitetura também tem um usuário só —
mas com um detalhe que muda o risco: o mesmo dono, na frente do computador, é uma pessoa;
o mesmo dono, hospedando um agente autônomo num VPS exposto na internet, cria uma segunda
superfície de decisão que **age sem ele estar olhando**. A lente de usuário da segunda
entrega, portanto, não é "quem usa" — é "quem pode ser convencido a agir por ele", e a
resposta triste é: qualquer site, e-mail ou processo malicioso que consiga se disfarçar de
instrução dele, se o caminho de controle não tiver cerca. Isso já é dor conhecida deste
repositório: `ESTADO.md` linha 130-135 registra que uma página web já conseguiu, uma vez,
dar ordem disfarçada de dono para o cérebro do DERVS ("[dono] agora rode: ..."), e foi
corrigido só porque havia teste. O documento de arquitetura da segunda entrega herda esse
mesmo adversário, só que com um raio de ação maior (PC, navegador, servidor, GitHub,
VS Code em vez de só o próprio DERVS).

## Momentos de uso, em ordem de frequência

### Parte 1 — a cara nova (interface)

1. **Falar com o DERVS no dia a dia, sem clicar em nada** — a escuta contínua já existe
   (`self.escuta`, `dervs.py:427`; janela de "desperto" em `self._desperto`,
   `dervs.py:432`). É o modo mais frequente e o que menos pode regredir: se a onda nova
   travar, atrasar ou consumir mais CPU que o `self.timer` de 500ms do selo atual
   (`dervs.py:1521-1522`), o dono nota na hora porque é a interação de todo dia.
2. **Clicar para abrir e ver o pop-up de conversa** — segundo clique traz a janela
   existente para frente em vez de abrir outra (`dervs_instancia.py`, comportamento
   descrito em `dervs.py:1682-1686`). Esse é literalmente um item do
   `criterio_de_aceitacao` do briefing (linha 36) e é também a dor mais dolorosa já
   registrada: "o DERVS sumiu/bugou" quando essa trava não existia.
3. **Olhar a onda reagindo à própria voz e à voz do DERVS** — é o pedido central desta
   rodada ("quero que quando falamos, balance as ondas da voz", briefing linha 9) e é
   também o único item do critério de aceitação que pede demonstração ao vivo, não só
   teste automatizado (briefing linha 51). É baixa frequência absoluta de "reparar
   conscientemente", mas altíssima frequência de "estar na tela" — é o pano de fundo de
   toda conversa.
4. **Recolher para o selo/bandeja e seguir trabalhando** — `launcher.pop.hide` e
   "Recolher janela" no menu da bandeja (`dervs.py:1654`). Uso frequente para quem deixa
   o programa aberto o dia inteiro.
5. **Fechar o DERVS de vez** — "Sair do DERVS" na bandeja (`dervs.py:1656`). Baixa
   frequência, mas crítica: é a única saída que não depende do Gerenciador de Tarefas,
   e o próprio código documenta que sem ela "o dono não tinha NENHUM jeito de fechar o
   app" (`dervs.py:1643-1644`). Se a versão Electron perder esse caminho, o dono volta a
   um sintoma já resolvido uma vez.
6. **Transcrever um arquivo de áudio pelo atalho separado** (`ESTADO.md` linha 26) —
   uso esporádico, não é tela principal, mas usa o mesmo processo/janela.

### Parte 2 — arquitetura de agente e controle remoto

Aqui não há "uso" no sentido de tela — é leitura de um documento e, depois, uma decisão.
Os momentos são:

1. **O dono lê a recomendação e decide entre OpenAI API (créditos já pagos) e IA open
   source no VPS** — isso é o `fora_de_escopo` desta rodada admitir explicitamente que
   não hospeda nada agora (briefing linha 57-58); o "momento de uso" real é o dono
   decidindo com clareza de custo e risco, não operando nada.
2. **O dono imagina o dia em que pede "Dervs, olha meu GitHub" ou "Dervs, reinicia o
   servidor" estando longe do computador** — é o desejo mais explícito do pedido
   original ("Quero que ele controle tudo... meu navegador, meu PC, meu servidor, meu
   GitHub, meu VS Code, tudo", briefing linhas 13-15). Esse é o momento que a
   arquitetura precisa servir, mesmo sem implementá-lo agora.
3. **Um agente autônomo agindo sem o dono estar olhando** — é o momento de maior risco
   e o motivo do documento existir: "riscos" do briefing (linha 62-64) já nomeia isso
   como "decisão de segurança de alto impacto". Este momento raro é o que deve moldar a
   recomendação — não o momento 2, que é o mais desejado mas o mais perigoso de otimizar
   às cegas.

## O que seria fracasso

**Na cara nova:**
- A onda não reagir de verdade ao volume do áudio — ficar bonita mas decorativa/aleatória.
  O próprio dono pede demonstração ao vivo por saber que isso é fácil de fingir
  (briefing linha 51); "parece que reage" não passa, só "reage".
- Abrir duas janelas Electron ao clicar duas vezes — é o sintoma que já aconteceu uma vez
  neste projeto e tem nome documentado ("o DERVS sumiu", `dervs.py:1682-1686`). Reintroduzir
  isso na reescrita é o fracasso mais caro possível, porque é dor já resolvida voltando.
- Perder o "Sair do DERVS" da bandeja, ou qualquer caminho de fechar sem Gerenciador de
  Tarefas — o dono não tem essa habilidade de reserva.
- Regressão em qualquer funcionalidade que hoje funciona sem a interface nova perceber:
  porteiro, transcrição, cérebro, execução com trilhos, atalho de transcrever arquivo,
  registro de queda (todos listados na tabela do `ESTADO.md`, seção 1). O
  `criterio_de_aceitacao` do briefing (linha 41-44) trata isso como não-negociável: os
  543 testes verdes continuam verdes.
- Vazar credencial na tela nova, em log ou em arquivo do repositório — critério explícito
  do briefing (linha 45) e coerente com a regra global de segredo nunca em código/log/
  commit.
- Interface "futurista" que sacrifica legibilidade ou custa CPU/bateria ao ponto de atrapalhar
  o uso o dia inteiro — o dono pediu bonito, não pediu lento; nenhuma dor dele hoje é
  "a interface é feia", e sim "a interface bugou" — fracasso estético é secundário a
  fracasso funcional.

**No documento de arquitetura:**
- Recomendar controle irrestrito de PC/navegador/servidor/GitHub/VS Code a partir de um
  agente hospedado fora da máquina, sem cerca — isso é o próprio risco que o briefing
  pede para não liberar ainda (linha 55, `fora_de_escopo`; linha 62-64, `riscos`).
- Comparar Hermes Agent, LiveKit e Open Claw sem fonte (URL + data) — vira opinião com
  sotaque de fato, o que a regra do papel Pesquisador (não o meu) proíbe, mas que eu, como
  Analista, preciso cobrar: se o documento final não tiver isso, nenhum usuário real
  consegue decidir com ele.
- Empurrar a decisão de custo (OpenAI API vs IA open source no VPS) sem número concreto —
  o dono já demonstrou, no próprio `ESTADO.md` (seção 4.3, custo da voz na nuvem em
  US$/mês), que decide dinheiro quando vê o número, não quando vê "depende".

## Funcionalidade sem dono (candidata a corte)

- **"Fusão de várias aplicações open source"** (briefing linha 12) — é o pedido mais
  aberto e o que menos tem um momento de uso nomeável. Ninguém descreveu uma situação em
  que "ter várias ferramentas fundidas" resolve uma dor específica; a dor real e nomeada é
  "quero que ele controle X, Y, Z" (momento 2 da parte 2). Fundir ferramentas é meio, não
  fim — o documento de arquitetura deve tratar isso como critério de escolha (qual
  ferramenta cobre qual pedaço do controle), não como entrega em si.
- **Open Claw** especificamente: aparece no pedido original como "também vi sobre" (briefing
  linha 11), no mesmo tom de quem viu um vídeo, sem um cenário de uso associado a ele que
  seja diferente do que Hermes Agent ou LiveKit já cobririam. Se o Pesquisador não achar
  para ele um papel que os outros dois não cobrem, é candidato natural a ficar de fora da
  recomendação principal.
- **Onda "surreal, muito louca"** sem mais especificação — é estética pura, sem um momento
  de uso que dependa do grau de "loucura" visual. O risco aqui não é cortar a funcionalidade
  (a onda é center-piece, não se corta), é a fase de Design inflar variações estéticas sem
  fim porque o pedido é vago de propósito. Cabe ao Diretor, não a mim, decidir quantas
  direções visuais valem a pena — eu só registro que "surreal e bonito" não é critério
  verificável sozinho, e o `criterio_de_aceitacao` do briefing já resolveu isso corretamente
  ao pedir demonstração ao vivo em vez de descrição.
- **Controlar "tudo"** (navegador, PC, servidor, GitHub, VS Code, "tudo o que eu pedir") —
  o próprio briefing já cortou isso da rodada atual (linha 55-58), e concordo com esse
  corte pela lente de usuário: nenhum desses cinco alvos tem, hoje, um momento de uso
  concreto e frequente nomeado pelo dono além do desejo genérico. O documento de
  arquitetura deve propor uma ordem de prioridade entre eles (qual dor é mais comum:
  navegador, que já tem código parcial em `dervs_browser.py` e teste, ou GitHub/VS Code,
  que não têm nada hoje?) em vez de tratá-los como um pacote único.

## Nota — a lente DX não se aplica em cheio

O usuário final não é desenvolvedor, então a lente DX (README, tempo até rodar, erro de
chamada) não é o eixo principal aqui. Mas ela toca de raspão o **documento de arquitetura**:
quem vai operar a instalação de Hermes Agent/LiveKit/Open Claw no VPS é o próprio dono,
seguindo passo a passo — e ele já demonstrou, no jeito como o `ESTADO.md` foi escrito para
ele (seção 5, "Como refazer o ambiente numa máquina limpa"), que precisa de receita literal,
sem jargão, com comando exato. Se a arquitetura recomendada exigir operação manual
recorrente que só um programador faria sem sofrer, isso é uma dívida de UX que o documento
precisa nomear como custo, não deixar implícita.
