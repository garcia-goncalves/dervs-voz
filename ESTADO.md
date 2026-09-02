# Estado do DERVS — 02/09/2026

O que funciona, o que não funciona, e o que falta. Escrito para ser lido pelo
dono, não por um programador.

Última verificação: 02/09/2026, noite. **543 testes verdes** no ambiente do
projeto (`dervs-venv`), que é onde o DERVS de fato roda. No Python do sistema,
496 verdes e 16 pulados — a diferença são os testes que precisam da biblioteca
da janela (PyQt6), que só existe no ambiente do projeto. Nenhum erro de coleta
nos dois, que é o que impede um arquivo quebrado de esconder a suíte inteira.

---

## 1. O que está funcionando agora

| Parte | Estado | Onde roda | Custo |
|---|---|---|---|
| A janela e o selo flutuante | **funciona** | sua máquina | zero |
| Abrir por atalho (Área de Trabalho e menu Iniciar) | **funciona** | sua máquina | zero |
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

### 2.2. O navegador autônomo não funciona no Windows

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

### 4.5. Telemetria do porteiro

Quando o porteiro decide "não era comigo", o texto que ele ouviu é jogado fora
e o arquivo apagado. Consequência: se uma frase sua for ignorada por engano,
**não há como provar onde ela sumiu**. Vale guardar um resumo (sem o áudio) para
poder investigar.

### 4.6. Três ajudantes sem teste próprio

`dervs_kokoro_daemon.py`, `dervs_piper_daemon.py` e `dervs_tts_daemon.py` não
têm teste dedicado. Eles são exercitados de raspão pelos testes da voz, mas uma
quebra dentro deles não seria pega.

### 4.7. Peso morto que sobrou da versão de Linux

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
dervs-venv\Scripts\python.exe scripts\instalar_atalho.py
```

Fica de fora, e precisa ser baixado à parte: o modelo da voz (`kokoro-model/`,
~350 MB) e a chave da OpenAI (que mora em `%APPDATA%\dervs\.env` e **nunca** vai
para o repositório).
