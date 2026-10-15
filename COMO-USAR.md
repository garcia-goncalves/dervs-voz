# DERVS — como usar, no seu Windows

Escrito para quem não mexe em terminal. Nenhum comando aqui precisa ser
decorado; todos podem ser copiados inteiros.

---

## Como abrir o DERVS

**Dois cliques no ícone `DERVS`** — ele está na sua Área de Trabalho e também no
menu Iniciar (aperte a tecla Windows e comece a digitar "DERVS").

O ícone é o mesmo desenho ciano/preto do HUD que aparece dentro do app.

Não abre janela preta de terminal junto: o atalho usa o `pythonw`, que é a
versão do Python que roda sem console.

**Se o atalho sumir** (acontece se a pasta do projeto for movida), ele é refeito
rodando uma vez:

```
dervs-venv\Scripts\python.exe scripts\instalar_atalho.py
```

O que aparece quando dá certo:

```
ícone: ...\dervs-voz\dervs.ico
atalho: ...\Desktop\DERVS.lnk
atalho: ...\Start Menu\Programs\DERVS.lnk
```

Se disser `não achei ... pythonw.exe`, o ambiente do projeto não está montado —
esse é caso de pedir ajuda, não de insistir.

---

## Se o DERVS sumiu da bandeja, travou ou ficou estranho

Na Área de Trabalho e no menu Iniciar existem três botões ao lado do `DERVS`
(dois cliques, sem terminal):

| Botão | O que faz |
|---|---|
| `DERVS - Reiniciar` | Fecha tudo (voz, HUD) e abre de novo. **Comece por este.** |
| `DERVS - Parar` | Fecha por completo e não reabre. |
| `DERVS - Resetar` | Fecha, **guarda uma cópia** de `config.json` ao lado (`config.json.bak-DATA`), volta a configuração ao padrão e reabre. Não apaga modelos de voz nem histórico de gasto. |

Os botões ficam prontos rodando uma vez `dervs-venv\Scripts\python.exe scripts\instalar_atalho.py`.
Também funcionam pelo terminal: `dervs-venv\Scripts\python.exe scripts\dervs_controle.py status|ligar|parar|reiniciar|resetar`.
Para desfazer um reset, copie o `config.json.bak-...` de volta para `%APPDATA%\dervs\config.json`.
O ícone da bandeja pode estar escondido na seta `^` ao lado do relógio; o `Ctrl+Alt+D` também abre o painel.

## Como FECHAR o DERVS

Clique com o **botão direito** no ícone do DERVS na bandeja (o cantinho ao lado
do relógio, na barra de tarefas — talvez seja preciso clicar na setinha `^` para
ver os ícones escondidos) e escolha **Sair do DERVS**.

Até 02/09/2026 **não havia como fechar**, de propósito: a ideia era ele ficar
sempre disponível. Na prática isso deu errado — veja a seção abaixo.

## Cliquei no ícone e "abriu outro DERVS"

Não abre mais. **Clicar no ícone com o DERVS já aberto agora TRAZ o que está
aberto de volta para a frente**, em vez de subir mais um.

Antes de 02/09/2026, cada clique abria um DERVS novo e o antigo continuava vivo,
invisível, disputando o seu microfone — e, sem "Sair", não havia como fechar
nenhum. Depois de alguns cliques a máquina ficava com vários empilhados e o app
parecia "bugado" ou "sumido". Era exatamente isso.

## A janela sumiu da tela

Desde 16/09/2026 o DERVS não é mais o selo dourado pequeno — é uma janela HUD
(painel ciano/preto, com anéis girando e um núcleo que reage à sua voz).

Se ela sumir:

1. **Dê dois cliques no ícone DERVS de novo**, ou clique no ícone da bandeja.
   Ele traz a janela de volta para a frente.
2. **Botão direito no ícone da bandeja → "Abrir DERVS".**

Fechar pelo X (ou Alt+F4) não encerra o DERVS — só esconde a janela, igual antes.
Para fechar de verdade, é sempre **"Sair do DERVS"** no menu da bandeja.

## Transcrever um áudio seu (reunião, WhatsApp, entrevista)

**Dois cliques em `DERVS - Transcrever audio`**, na Área de Trabalho. Abre o
seletor de arquivos, você escolhe o áudio, e ele:

1. manda para a transcrição precisa (a mesma da conversa ao vivo);
2. salva um arquivo `.txt` **na mesma pasta e com o mesmo nome** do áudio;
3. abre o texto no Bloco de Notas sozinho.

Aceita mp3, m4a (iPhone e gravador do Windows), ogg (WhatsApp), wav, flac, e
até vídeo (mp4, webm) — ele tira só o som.

**Áudio longo não é problema.** Reunião de duas horas passa muito do limite de
envio. Antes de reclamar, o áudio é compactado (fica cerca de 10 vezes menor sem
perder a fala) e, se ainda assim for grande, é enviado em pedaços de 20 minutos
que se sobrepõem — a emenda descarta a repetição, para não perder nem duplicar a
palavra dita bem na hora do corte. Numa reunião de teste cortada em 6 pedaços, o
texto saiu **idêntico** ao da transcrição sem cortes.

Enquanto trabalha, a janela mostra o andamento:

```
compactando o áudio (mono, 16 kHz) para caber no envio...
  84.3 MB -> 8.1 MB
áudio de 112 min: enviando em 6 pedaços
  pedaço 1/6 (0–20 min)
```

**Quanto custa:** cerca de **US$ 0,27 por hora** de gravação (US$ 0,0045 o
minuto). Uma reunião de duas horas sai por menos de US$ 0,60.

**O que fazer se der errado:**

| Aparece | O que é | Saída |
|---|---|---|
| `a chave da OpenAI não está nesta máquina` | falta a chave | ver a seção da chave |
| `o ffmpeg não está instalado` | falta o programa que compacta | `winget install Gyan.FFmpeg` |
| `não achei o arquivo` | caminho errado ou arquivo movido | escolher de novo |

---

## Ligar e desligar a escuta

**Três modos de escuta (04/10/2026).** No painel, ao lado do chip MICROFONE, há
um seletor com três botões:

| Modo | O que o microfone faz |
|---|---|
| **Desligado** (padrão ao abrir) | Fechado. Nada é ouvido. |
| **Atalho** | Fechado; abre só **enquanto você segura `Ctrl+Alt+Espaço`** (os Ctrl e Alt da **esquerda**; o AltGr não vale). Ao soltar, fecha em ~1,6 s (o tempo de terminar a frase; se ainda estiver transcrevendo, espera, até 20 s). Como você apertou de propósito, o pedido vai direto, sem precisar dizer "DERVS". |
| **Chamar por voz** | Aberto, acorda quando ouvir "DERVS" no começo da fala. **Fecha sozinho depois de 10 minutos sem uso** (chave `escuta_auto_desligar_min`, de 1 a 240). |

O chip diz o estado real: `DESLIGADO`, `FECHADO · ATALHO`, `ABERTO (ATALHO)` ou
`OUVINDO · FECHA EM 7 MIN`. Para fechar por voz: **"DERVS, pare de ouvir"** (ou "desliga
o microfone"). Na reunião de 1 hora o atalho não abre o microfone. A última escolha fica
na chave `modo_escuta` do `config.json` (`desligado`, `atalho` ou `voz`); valor torto cai
em `desligado`. **Ao abrir o app o microfone nasce sempre fechado:** o modo Atalho volta
como estava, mas quem estava em "Chamar por voz" abre em Desligado e liga de novo com
um clique (regra do briefing: nunca ativar do nada). **Se o DERVS "não acorda", confira o modo antes de tudo:** em
Desligado ou Atalho ele não está ouvindo, de propósito.

**O botão voltou (23/09/2026).** Logo abaixo do nome **DERVS** na tela há um
botão que diz **MICROFONE LIGADO** (ponto cheio, ciano) ou **MICROFONE
DESLIGADO** (ponto vazio, apagado). Um clique liga ou desliga a escuta. O
botão só muda quando o DERVS realmente abriu ou fechou o microfone — ele não
"finge" o estado. A sua última escolha fica guardada: se desligar e fechar o
DERVS, ele abre desligado.

Outras formas, se precisar:

1. **Sair do DERVS** (botão direito no ícone da bandeja → "Sair do DERVS").
   Fechando o app, o microfone fecha junto.
2. **Editar a configuração** — a chave `modo_escuta` em
   `%APPDATA%\dervs\config.json` (`desligado`, o padrão, `atalho` ou `voz`).
   A antiga `escuta_ao_abrir` ainda é gravada, mas **não decide mais** ao abrir.

Enquanto ele não ouvir o seu nome, o que você fala **não sai do seu
computador** de qualquer forma (ver o funil mais abaixo).

---

## O que ele faz, em uma frase

Fica ouvindo a sala. Quando você diz **"DERVS"** (ou "OK DERVS", ou "Ei DERVS"),
ele acorda, entende o pedido, mostra o que vai fazer, espera você aprovar, faz,
e responde falando.

**Só acorda se você o chamar no começo da fala.** "DERVS, que horas são?" e
"Ei DERVS, abre o Chrome" funcionam. Falar *sobre* ele ("vou mostrar o dervs pra
ele") **não** o acorda. Se preferir o jeito antigo, em que o nome valia em qualquer
lugar da frase, ponha `"chamada_estrita": false` no `config.json`.

---

## O ponto mais importante: o que sai da sua máquina, e o que não sai

Isto foi o principal trabalho desta rodada, e vale entender.

```
   você fala
       │
       ▼
  [1] o computador percebe que houve fala          ← na sua máquina, de graça
       │
       ▼
  [2] O PORTEIRO: "isso foi comigo?"               ← NA SUA MÁQUINA, de graça
       │
       ├── não era com ele ──► descarta. FIM.
       │                       nada sai do computador, nada é cobrado
       │
       └── ouviu o nome
                │
                ▼
  [3] transcrição precisa do pedido                ← vai para a nuvem, é cobrado
                │
                ▼
  [4] o cérebro entende e monta o plano            ← vai para a nuvem, é cobrado
                │
                ▼
  [5] ele fala a resposta                          ← na sua máquina, de graça
```

**Enquanto ele não ouvir o seu nome, o áudio nunca sai do seu computador.** Sua
reunião, sua ligação, a conversa da sua casa: tudo isso é processado e
descartado ali mesmo.

Antes desta rodada era o contrário — tudo ia para a nuvem primeiro e só depois
ele conferia se era com ele. Ligado 8 horas por dia, isso custaria cerca de
**US$ 43 por mês** e mandaria o dia inteiro da sua casa para um servidor de
terceiro.

---

## Pedir um lembrete

Você pode pedir para o DERVS te avisar de alguma coisa. Ele guarda no
computador (nada vai para a internet) e, na hora, **fala em voz alta e
escreve na tela**. Diga, por exemplo:

> "DERVS, me lembra em 10 minutos de ligar para o cliente."
> "DERVS, me lembra às 15h30 de tomar o remédio."
> "DERVS, me lembra amanhã às 9 de pagar o boleto."
> "DERVS, daqui a 2 horas me avisa da reunião."

Ele responde na hora, por exemplo: *"Certo, te aviso às 15h30: tomar o remédio."*
Se ele **não entender a hora**, ele não inventa: diz *"Não entendi a hora. Diga
por exemplo: me lembra em 10 minutos de ligar para o cliente."* e você repete.

Outros pedidos:

> "DERVS, quais são meus lembretes?" — ele lê a lista.
> "DERVS, cancela os lembretes." — apaga todos e diz quantos apagou.

Bom saber:

- Só vale até **7 dias** à frente.
- Se você disser só a hora ("às 9") e ela já passou hoje, vale para amanhã.
- Se o DERVS estiver **fechado** na hora, ele avisa quando você abrir de novo
  ("Você tinha um lembrete às 13h: ..."), uma vez só.
- Se ele estiver falando, o aviso espera a fala acabar.
- O que você pede para lembrar é só **falado de volta**: nunca é executado
  como comando.

---

## Ligar e desligar o microfone

Ver a seção **"Ligar e desligar a escuta"**, acima — o botão **MICROFONE
LIGADO / DESLIGADO** fica logo abaixo do nome DERVS, na tela.

Ao abrir (com a configuração padrão), o DERVS já nasce ouvindo.

**Reunião 1h:** na barra de estado do painel, o botão **REUNIÃO 1H** fecha o
microfone por uma hora e o reabre sozinho. Enquanto dura, mostra o tempo que falta
(**REUNIÃO 59:12**). Clique de novo para cancelar e voltar a ouvir na hora. Se você
ligar ou desligar o microfone pelo botão dele durante a reunião, ela é cancelada.
Se fechar o DERVS no meio, ele abre ouvindo da próxima vez.

**Atalho no teclado:** `Ctrl+Alt+D` abre o **painel** (a tela JARVIS, explicada
logo abaixo); apertando de novo, ele some. **A janelinha compacta (widget) deixou
de existir**: agora há uma janela só, e `Ctrl+Alt+D` é o único atalho. O ícone do
DERVS na bandeja do Windows também abre e fecha o painel (menu: Abrir DERVS / Sair
do DERVS).

**Uma linha pequena** perto do rodapé diz **HOJE: N ouvidas · M acordei** — quantas
frases o DERVS ouviu hoje e em quantas ele acordou. Só números; o que foi dito não
aparece.

---

## Como falar com ele

Diga o nome e o pedido **de um fôlego só** — não precisa esperar bipe:

> "DERVS, abre o Chrome."
> "OK DERVS, que horas são?"
> "Ei DERVS, que dia é hoje?"

Depois que ele te atende, ele fica **desperto por 20 segundos**: nesse tempo
você pode continuar falando sem repetir o nome, como faria com uma pessoa.
Passados os 20 segundos sem você falar, ele volta a dormir e é preciso chamar
pelo nome de novo.

Se você disser só "DERVS", ele responde "Oi! Pode falar" e fica esperando.

---

## Conversa natural: falar com ele como com uma pessoa (15/10/2026)

Depois que ele acorda (você disse "DERVS" ou segurou o atalho), a conversa passa para a
voz direta: ele espera você terminar de verdade (pausa para pensar, "éé… hum…" e gagueira
não cortam você), responde em pouco mais de um segundo e você pode falar por cima dele
para mudar o pedido. Pedido fácil (abrir programa, abrir pasta, volume) ele só faz e toca
um sinal curto, sem falar. Pedido com dúvida ele pergunta antes. Coisa grave continua
pedindo o clique. Pedido ao Claude Code, ao Codex, ao cofre ou ao servidor ele confirma
com você antes ("Quer que eu faça isto…?" — responda "sim").

**Grave a sua voz** (tela Vozes do painel, quando ela chegar): com uma voz gravada, ele só
ouve quem está cadastrado e ativo — conversa de outras pessoas por perto não sai do
computador. Sem nenhuma voz gravada ele ouve qualquer um, como antes, e o painel avisa.
Quem for gravado como convidado (por exemplo a sua filha) conversa e faz só coisa fácil.

Para desligar e voltar ao jeito antigo: `"conversa_natural": false` no `config.json`.

## Trocar a voz

Foram geradas 6 amostras para você ouvir, na pasta `amostras_voz` dentro do
projeto. São 3 vozes, cada uma em 2 velocidades:

| Arquivo | Voz | Velocidade |
|---|---|---|
| `pm_santa_1.0x.wav` | masculina grave | normal |
| `pm_santa_1.3x.wav` | masculina grave | rápida |
| `pm_alex_1.0x.wav` | masculina | normal |
| `pm_alex_1.3x.wav` | masculina | rápida |
| `pf_dora_1.0x.wav` | feminina | normal |
| `pf_dora_1.3x.wav` | feminina | rápida |

Dê dois cliques em cada uma para ouvir. Depois de escolher, me diga qual — ou,
se quiser mexer sozinho, o arquivo de configuração fica em:

```
%APPDATA%\dervs\config.json
```

Cole esse caminho na barra do Explorador de Arquivos do Windows e ele abre a
pasta. Dentro do arquivo, duas linhas importam:

- `"voz_kokoro"` — aceita `pm_santa`, `pm_alex` ou `pf_dora`
- `"voz_velocidade"` — de `0.5` a `2.0`. O padrão é **1.2**, que é o ritmo de
  quem está conversando, não o de robô lendo.

Mudou o arquivo? Feche e abra o DERVS para valer.

---

## O painel grande (a tela JARVIS)

**Como abrir:** ele já abre sozinho com o DERVS; depois, `Ctrl+Alt+D` ou um clique
no ícone da bandeja. **Os três botões do canto:** o **traço** minimiza de verdade
(vai para a barra de tarefas), o **quadrado** diminui/restaura o tamanho (ocupa a
tela toda e volta) e o **x** fecha para a bandeja — o DERVS continua vivo; para
sair de vez, use **Sair do DERVS** no menu da bandeja. A alça no canto de baixo à
direita muda o tamanho. Quando o DERVS precisar da sua confirmação num plano, o
painel vem para a frente com um **cartão de confirmação** (Confirmar / Cancelar, e
a caixa "tenho autorização" quando o passo pede). Na barra de estado também ficam
o botão **REUNIÃO 1H** e o **ABRIR DERVS APP** (abre o outro projeto no navegador).

**O que cada parte mostra** (tudo é dado real, atualizado sozinho):

- **Topo:** relógio e data, e a barra de estado — **microfone** (clique nele para
  ligar/desligar), **voz** (NUVEM = a voz humana da OpenAI; LOCAL = a de reserva
  do computador, que entra quando a internet cai), **internet** e o **gasto do dia**.
- **Esquerda, SISTEMA:** CPU, memória, disco e rede, cada um com um gráfico dos
  últimos 60 segundos.
- **Centro:** o reator. Ele gira e brilha conforme você e o DERVS falam, e o arco
  em volta cresce com o volume da voz.
- **Direita, AGENDA:** os lembretes que você pediu (os mesmos de "Pedir um
  lembrete"). Sem lembrete, aparece um texto explicando como pedir.
  **DIÁRIO:** as últimas frases que o DERVS ouviu hoje — só a hora, se ele foi
  chamado e a duração; o que foi dito **nunca** aparece.
- **Embaixo:** o **Claude Code** (a caixa de texto para pedir trabalho ao Claude),
  a **conversa ao vivo** (as últimas falas suas e dele) e as **últimas ações** (o
  que ele rodou, o resultado e os erros).

**O "GASTO HOJE" é uma estimativa.** Cada vez que o DERVS fala com a voz de nuvem,
transcreve o que você disse ou pensa na nuvem, ele anota uma linha no arquivo
`gasto.jsonl` (na pasta `%LOCALAPPDATA%\dervs`, só neste computador; guarda data,
tipo e valor, nunca texto nem chave). O valor sai de uma tabela: voz da nuvem
≈ US$ 0,015 por minuto de áudio falado, transcrição ≈ US$ 0,006 por minuto de áudio
enviado, e o cérebro pelos tokens que a OpenAI informa. **A fatura de verdade é a
da OpenAI** — este número serve para você ver o ritmo do dia, não para conferir
centavos. Ele zera à meia-noite.

**Fica pesado?** Não: com o DERVS parado, o painel fechado ou aberto, o programa
inteiro usa bem menos de um décimo de um núcleo do processador. A animação para
quando o painel está escondido e cai para 10 quadros por segundo quando você está
em outra janela.

---

## Pedir trabalho ao Claude no painel

No canto de baixo à esquerda do painel fica a caixa **CLAUDE CODE**. É o mesmo Claude
do seu terminal (com as suas regras e ferramentas), usando a sua assinatura — não
gasta chave de API.

- **Como usar:** escreva o que quer ("olha o que está ocupando espaço no C:") e
  aperte **Enter** (Shift+Enter pula linha). A resposta vai aparecendo palavra por
  palavra. Ele lê o computador inteiro; para **mudar** qualquer coisa, aparece um
  aviso no meio da tela perguntando se pode. O botão que já vem selecionado é
  **Negar** — de propósito, para um Enter sem querer não liberar nada. Se você não
  responder em 5 minutos, ele conta como "não".
- **Por voz:** "pede pro Claude verificar meu PC", "analisa o uso de memória" ou
  "verifica meu PC". A voz responde só um resumo de duas frases; o texto completo fica
  no painel. Para interromper, diga **"para"**.
- **Parar:** o botão **PARAR** (ou a palavra "para") interrompe. Se ele não obedecer
  em 5 segundos, o DERVS encerra o processo dele à força.
- **Nova conversa:** esquece tudo e começa do zero. Sem apertar, o DERVS lembra da
  conversa mesmo depois de fechar e abrir de novo.
- **O que ele não faz sozinho:** apagar, desinstalar ou mexer em pasta do sistema
  (`C:\Windows`, `Program Files`, `.git`, `.ssh`). Ele só **propõe** e você decide;
  quem decide e executa é a **Central do PC** (a próxima seção): só o seu clique, item
  a item, e nada é apagado — vai para a quarentena.
- **Se ficar sem resposta:** confira se o `claude` está instalado e logado (abra um
  terminal e digite `claude`); o erro aparece em vermelho na própria caixa.

---

## Central do PC: saúde, limpeza e desfazer

No topo do painel, o botão **CENTRAL DO PC** mostra a nota do computador (0 a 100).
Clique nele para abrir a Central.

- **Analisar agora:** lê o computador (discos, erros do Windows na última semana,
  atualizações, proteção contra vírus, firewall, programas que abrem sozinhos,
  programas pesados, projetos ainda não enviados ao GitHub, drivers, energia). Leva de 30
  segundos a 2 minutos. **Só lê: nada é mudado nessa etapa.** Sozinho, o DERVS repete
  essa análise uma vez por dia, quando o computador está parado, e só avisa a nota.
- **A nota:** começa em 100 e desconta por regra, e a tela mostra cada desconto com o
  motivo (disco quase cheio −20, disco com defeito −40, proteção contra vírus desligada
  −30, firewall desligado −20, atualização de segurança atrasada −15, e assim por
  diante). **Explicar melhor** manda só aquele item ao Claude, que explica em palavras
  simples.
- **Por voz:** "DERVS, como está meu PC?" — ele fala até 4 frases: as 3 piores coisas e
  a nota. Se a última análise tem mais de 24 horas, avisa e analisa antes.
- **Limpeza (o que você decide):** **Ver sugestão de limpeza** monta um relatório com
  cada arquivo velho de temporários: o que é, por que é seguro, o que muda e como
  desfazer. Todas as caixas começam **desmarcadas**; você marca uma a uma e clica em
  **Mover os marcados para a quarentena**. Não existe "marcar tudo". Item de risco alto
  pede uma segunda caixa de confirmação. O relatório vale 15 minutos.
- **Nada é apagado.** O item vai para a quarentena do DERVS
  (`%LOCALAPPDATA%\dervs\quarentena`) e aparece em **Na quarentena** com o botão
  **Desfazer**, que devolve o arquivo exatamente para onde estava. Nunca voz, nunca o
  Claude: só o seu clique aprova e executa.
- **Fica de fora, de propósito:** `C:\Windows\Temp`, `Windows.old` e a Lixeira só
  aparecem com o tamanho (use a Limpeza de Disco do Windows), e programas, bibliotecas
  e scripts nunca entram na sugestão.
- **"1 leitura só funciona como administrador":** o detalhe de saúde do disco (SMART)
  precisa de administrador. O resto da nota funciona sem.

## O que o DERVS pode fazer (permissões)

No topo do painel, o botão **O QUE O DERVS PODE FAZER** abre a lista de permissões.
Para cada coisa (ler arquivos, abrir programas, instalar, alterar projetos, apagar,
usar a internet, mexer em servidor, gastar com API paga) você escolhe:

- **Só analisa:** o DERVS olha e explica, mas não age.
- **Pergunta antes:** aparece um cartão e ele espera o seu sim.
- **Faz sozinho:** ele faz sem perguntar e registra na lista "O que fez sozinho"
  (as últimas 10 ações).

Cada item mostra só as opções que fazem sentido para ele. Apagar e mexer em servidor
nunca têm "Faz sozinho". Se uma opção não aparece, é uma trava de segurança.

Ali também fica o **teto de gasto por dia** com API paga (de US$ 0,01 a US$ 1000) e
quanto já foi gasto hoje. As escolhas são salvas na hora e valem na próxima ação.

Estas travas valem sempre e não aparecem na tela: nada em servidor sem o seu sim,
apagar só vai para a quarentena, nunca ignorar permissões.

### O que "Faz sozinho" libera de verdade

"Faz sozinho" não é um cheque em branco: só passa sem cartão o que o DERVS reconhece
por inteiro. Todo o resto continua pedindo o seu sim, mesmo com a opção ligada.

| Categoria | O que passa sem cartão |
|---|---|
| Ler | Ler arquivos e comandos que só olham |
| Criar e alterar arquivos | Escrever arquivo **dentro das suas pastas de projeto** (nunca `.git`, `.ssh`, arquivos que começam com ponto, perfil do PowerShell, pasta Inicializar) |
| Abrir programas | Só os conhecidos: bloco de notas, calculadora, Chrome, Edge, Word, Excel... (nunca `cmd`, `powershell`, scripts) |
| Instalar | `pip`, `npm` ou `winget` com nome de pacote simples (nada de endereço, `-r` ou comando encadeado). Atenção: instalar roda o instalador do pacote |
| Internet | Só **pesquisar**. Abrir uma página qualquer sempre pergunta (uma página pode carregar dado seu na URL) |

As **pastas de projeto** ficam no `config.json` (em `%APPDATA%\dervs`), na chave
`pastas_de_projeto`, com caminho completo. Não vale raiz de disco (`C:\`), a sua pasta
de usuário nem `AppData`. Sem pasta listada, escrever sempre pergunta.

### Pedir para o DERVS desenvolver

Se você falar um pedido claro de construir software ("cria um site para a clínica",
"conserta o bug do login", "implementa a tela de cadastro"), o DERVS manda direto para o
Claude Code, sem você dizer "pede pro Claude". Pedidos rápidos (hora, abrir app, lembrete)
continuam no caminho rápido de sempre. Cada escolha fica em
`%LOCALAPPDATA%\dervs\roteamento.jsonl`, com o motivo (só a frase de quem foi para o
Claude é guardada, cortada em 80 letras).

### Voz e conversa (03/10/2026)

A voz agora é a **cedar** (masculina, estilo JARVIS), um pouco mais rápida (1,25x). Para
mudar, `voz_openai` (cedar, marin, onyx, ash, echo, fable, verse...) e `voz_openai_tempo`
(1,0 a 1,6) no `config.json`; reinicie com o botão `DERVS - Reiniciar`. Assim que você
termina de falar ele diz "Certo." na hora e depois "Entendi: vou ..." com o que vai fazer.
Ele só pede o seu OK em coisa grave (apagar, servidor/rede de terceiros, segredo, e-mail ou
banco pelo navegador). Para voltar a pedir sempre: `"confirmar_plano": "sempre"`.

### Teto de gasto

O teto diário (padrão US$ 3,00) vale para **toda** chamada paga: cérebro, voz na nuvem,
transcrição e navegador autônomo. Ao atingir, o DERVS volta para o Claude e para a voz e a
transcrição locais. "Só analisa" em "Gastar com serviços pagos de IA" desliga as APIs
pagas por completo. O Claude da assinatura não conta no teto.

---

## Se o DERVS cair: o piloto automático

Quando o DERVS fecha sozinho, ele anota o motivo. Na abertura seguinte ele lê esse registro, explica em português o que aconteceu (arquivo, linha e tipo do erro, sem segredos) e guarda uma cópia em `quedas\` na pasta de configuração (as 20 mais recentes).

O que ele faz depende da permissão **Alterar projeto**:

| Permissão | O que o piloto faz |
|---|---|
| analisa | só conta o que houve |
| pergunta | conta e oferece: diga "conserta" |
| sozinho | conta e avisa que vai preparar o conserto |

O conserto nunca mexe no projeto principal: é preparado numa cópia isolada (branch `piloto/...`), com teste novo. Nada é mesclado nem enviado ao GitHub sem você decidir. Nesta versão o piloto só **explica**; preparar o conserto de verdade ainda não está ligado.

## Quanto custa por mês

O porteiro é **de graça** — roda na sua máquina, offline. Desde 28/09/2026 a voz
falando também é da nuvem (soa como gente, com sotaque brasileiro) e passa a ser
cobrada; se a internet cair, ele volta sozinho para a voz local, que é grátis.
O painel grande mostra o **gasto do dia** em dólar (é estimativa).

Estimativa para uso pesado, cerca de 300 pedidos por dia:

| Item | Onde roda | Custo por mês |
|---|---|---|
| Perceber a fala | seu PC | US$ 0 |
| O porteiro (ouvir o nome) | seu PC | US$ 0 |
| Transcrever o pedido | nuvem | ~US$ 3,40 |
| O cérebro | nuvem | ~US$ 2,00 |
| A voz falando | nuvem | ~US$ 4,50 |
| **Total** | | **~US$ 10** |

Para comparar: sem o porteiro, deixando ligado 8 horas por dia, só a
transcrição daria **~US$ 43 por mês**.

Preços consultados em 01/09/2026 na página oficial da OpenAI. O modelo usado
para transcrever é o `gpt-transcribe`, lançado em julho de 2026 — é ao mesmo
tempo mais preciso e mais barato que o anterior.

---

## O que ainda falta para funcionar 100%

*(atualizado em 03/09/2026 — a versão anterior desta seção dizia que faltava a
chave da OpenAI. Ela foi instalada em 02/09 e está funcionando.)*

**1. Ligar um microfone no computador.** É a única coisa que depende da sua
mão, e é o motivo do "o DERVS não está me ouvindo". As duas entradas de
microfone do gabinete — a rosa da frente e a rosa de trás — estão **vazias**, e
não há microfone USB, webcam com microfone nem fone Bluetooth nesta máquina.
Ligue na entrada rosa de trás e ele ouve na hora, sem instalar nada.

**2. Me passar 20 a 30 nomes próprios seus** (clientes, empresas, pessoas,
termos do seu ramo). Está medido: o DERVS só acerta nome que esteja escrito
numa lista dentro do programa — o nome "DERVS" saiu de 0 acertos em 5 para 5 em
5 só por estar lá. Hoje a lista tem palavras genéricas e nenhum nome seu.

**3. Decidir se quer a voz da nuvem.** Fica 0,42 segundo mais lenta e custa
cerca de US$ 4,50 por mês. É dinheiro, então é sua decisão — a voz de hoje
continua funcionando de graça.

**4. O navegador automático não funciona no Windows.** O DERVS sabe pilotar o
Chrome sozinho, mas o ambiente que isso precisa nunca foi montado aqui. Se você
quiser essa parte, me avise.

O inventário completo — o que funciona, o que não funciona e de quem é a culpa
de cada coisa — está no arquivo `ESTADO.md`, na pasta do projeto.

---

## Se der errado

| O que acontece | O que fazer |
|---|---|
| **A tela diz "não entrou som"** | É o aviso mais importante que ele dá: o microfone não está entregando áudio nenhum. Ou não tem microfone ligado na entrada rosa, ou ele está mudo no Windows (clique com o botão direito no ícone de som → Configurações de som → Entrada). |
| **Falo e o texto vem vazio (ou nada aparece)** | Se ele não mostrou nenhum recado, avise. Se mostrou "não entrou som", é a linha de cima. Desde 03/09/2026 ele nunca mais fica calado nesse caso — e também não gasta com a nuvem à toa. |
| Ele não acorda quando chamo | Primeiro veja se não é a linha acima: sem microfone, ele nunca acorda. Se o microfone está bom, fale um pouco mais alto e mais perto. Se continuar, me avise: existe um detector mais preciso que dá para ligar (Porcupine), que exige uma conta gratuita de 5 minutos. |
| Ele acorda sozinho, sem eu chamar | Me avise. É o mesmo caminho do item acima. |
| Ele não fala nada | O motor de voz precisa dos modelos em `%LOCALAPPDATA%\dervs\modelos`. Se a pasta sumiu, me avise que eu baixo de novo. |
| A janela não abre | Me avise, e diga se apareceu alguma mensagem na tela. |
| Falo e **nada acontece** | Olhe o rótulo de estado no alto do HUD. Se disser "não estou conseguindo ouvir", o motor de voz caiu — me avise. Antes de 02/09/2026 ele dizia "pronto" mesmo surdo, e você não tinha como saber. |
| "o ouvido caiu — levantando de novo" | É normal e se resolve sozinho: ele tenta duas vezes. Só me avise se virar "não estou conseguindo ouvir". |
| Parece que tem mais de um DERVS aberto | Não tem mais como acontecer. Se acontecer, me avise — é um defeito novo. |
| Ele pede confirmação demais | Me avise. A rede de segurança prefere perguntar a mais que a menos, mas se estiver incomodando dá para afinar. |
| "não achei a biblioteca sounddevice" | Faltou instalar. Me avise que eu instalo. |

## Pedidos por voz: servidor, projetos, GitHub e ajustes

| Você diz | O que acontece |
|---|---|
| "Como está o disco da VPS?" (também memória, uptime, containers, "status do nginx", "logs do X") | Roda na hora e lê o resultado; a saída inteira fica na tela Integração. |
| "Roda <comando> na VPS" | Leitura roda; o que muda o servidor vira um cartão na tela Integração e só roda se você clicar. |
| "Pergunta pro Claude da VPS …" | Sempre vira cartão, com o texto exato. |
| "Abre o projeto X" | Abre a pasta no VS Code (procura em `source\repos` ou nas pastas de projeto do painel). |
| "No projeto X, pede pro Claude …" | Pede "confirma"; então abre o Claude Code numa cópia isolada, sem poder mandar nada ao GitHub. |
| "Faz commit e push do projeto X" | Diz o que vai e pede "confirma"; sobe num branch novo `dervs/voz-…`, nunca na main, nunca com segredo. |
| "Fala mais rápido" / "troca a voz para onyx" / "ativa o modo sempre confirmar" | Muda só essas configurações. Permissões, teto de gasto e pastas de projeto só pelo painel. |

Servidores vêm das sessões salvas do PuTTY (precisam de endereço **e** usuário) e do arquivo `ssh_hosts.json`. Na primeira vez, conecte uma vez pelo PuTTY para ele guardar a chave do servidor: o DERVS recusa servidor desconhecido.


## O cofre: o segundo cérebro (05/10/2026)

O cofre é uma **pasta de notas no seu computador**, a pasta `DERVS-Cofre` dentro de *Documentos* (dá para trocar: `cofre_pasta` no `config.json`). Cada nota é um arquivo de texto comum (`.md`), então abre no Bloco de Notas, no **Obsidian** (gratuito: "Abrir pasta como cofre") ou no Logseq. Os links `[[assim]]` ligam uma nota a outra e a busca é instantânea. O DERVS cria a pasta sozinho na primeira vez.

**Por voz** (com o microfone aberto, no modo Atalho ou Chamar por voz):

| Você diz | O que acontece |
|---|---|
| "DERVS, anota que preciso renovar o domínio" | grava uma nota em `entrada/` e responde "Anotei." |
| "lembra que o dentista é na terça" · "não esquece que…" | o mesmo (para avisar numa hora marcada, continue usando "me lembra em 10 minutos…") |
| "anota em privado que…" | grava em `privado/`; nunca é lida em voz alta nem sai do computador |
| "o que eu sei sobre o servidor?" · "procura nas minhas notas disco cheio" | acha as 3 melhores notas e lê o título e um pedacinho da primeira |
| "abre o cofre" | abre a pasta no Explorer (o botão **COFRE** do painel faz o mesmo e mostra quantas notas há) |

**O que ele nunca faz:** anotar senha ou chave (ele recusa e avisa); ler em voz alta ou mandar para a internet o que está em `privado/` ou tem a etiqueta `#privado`; escrever fora da pasta do cofre. O diário do dia (`diario/AAAA-MM-DD.md`) guarda só números: quantas frases ouviu, quantas vezes acordou e o gasto. Nunca o que você disse.

Uma nota conta como privada se estiver numa pasta `privado/` (maiúscula não importa), tiver `#privado` no texto ou `privado` em `tags:`/`etiquetas:` no cabeçalho (o jeito do Obsidian). Na dúvida, o DERVS trata como privada. O DERVS também **não entra** em atalho de pasta (junction) para fora do cofre, e não sobrescreve uma nota diária sua: se já existir `diario/AAAA-MM-DD.md` escrita por você, o diário dele vai para `AAAA-MM-DD-dervs.md`.

**O filtro de segredo é uma heurística, não um cofre-forte:** pega chave `sk-…`, `ghp_…`, `AKIA…`, "senha: …", e "a senha do wifi é bananas123" (frase com número), mas uma senha só de letras dita em frase solta pode passar. Não dite senha.

**Um aviso honesto:** o que você dita passa pela transcrição de voz, que (se estiver em `openai`) vai para a OpenAI como qualquer outra fala sua. O cofre protege o que já está guardado, não o que você acabou de dizer. Para algo realmente sigiloso, escreva direto no arquivo.

**Ainda não existe:** sincronizar o cofre com outro computador ou com a VPS, e o cérebro **Claude** (o plano B, quando a OpenAI falha) consultar o cofre.

**Busca por significado (06/10/2026) — OPCIONAL e DESLIGADA até você ligar:** com ela, "o que eu sei sobre o dentista" acha a nota "Consulta odontológica" mesmo sem a palavra "dentista" no texto; ela se junta à busca por palavras, que continua igual. Tudo roda **no seu computador** (modelo `paraphrase-multilingual-MiniLM-L12-v2`, na CPU); nenhuma nota sai por causa dela, e as privadas continuam sem ser lidas em voz alta nem mandadas à OpenAI. **Custo:** ~240 MB de download na primeira vez (única coisa que usa a internet), ~600 MB de RAM enquanto o modelo está carregado (ele é solto depois de 10 minutos sem uso) e ~25 ms por nota na primeira indexação, em segundo plano. **Para ligar:** `dervs-venv\Scripts\python.exe -m pip install -r requirements-semantica.txt`, ponha `"cofre_semantica": true` no `config.json` e reabra o DERVS. Sem o pacote, sem o modelo ou sem internet na primeira vez, o cofre funciona como sempre, sem aviso de erro. A primeira pergunta depois de o modelo ser solto responde só por palavras (o modelo recarrega ao fundo, ~2 s, e a seguinte já usa o significado). Os vetores ficam em `.indice/vetores.sqlite` dentro do cofre.

**O cérebro consulta o cofre sozinho (06/10/2026) — DESLIGADO até você ligar:** com isto ligado, quando você faz uma pergunta e o cérebro é a OpenAI (o padrão), o DERVS procura no cofre as palavras que importam da sua fala e manda junto, **no máximo 3 notas e 1.500 caracteres, nunca as privadas**, marcadas como "dado, não ordem". Assim ele sabe, sem você repetir, que "o servidor novo é o OVH" ou "o dentista é na terça". Falas banais ("abre o chrome", "que horas são") não levam nota nenhuma. **Isso manda trechos das suas notas públicas para a OpenAI.** Por ser texto pessoal indo a um terceiro, **vem desligado**: para ligar, ponha `"cofre_no_cerebro": true` no `config.json` (ou peça ao Claude para fazer isso) e reabra o DERVS. As notas chegam à OpenAI só como *dado* cercado, nunca como ordem. Em subpasta `privado/` de qualquer nível, nada vai.

## O Codex: o ChatGPT Plus como mais um ajudante de código (06/10/2026)

O DERVS passa trabalho de código ao **Codex**, o programa que já vem com o app Codex da OpenAI neste PC, usando a sua assinatura do ChatGPT Plus (nada de chave de API, nada de gasto extra). Ele é **mais um** ajudante, ao lado do Claude Code: só entra quando você cita o nome dele.

**O que dizer**
- "DERVS, pergunta pro Codex como funciona X" / "pede pro Codex analisar Y" / "manda o Codex revisar Z" / "usa o Codex para explicar W": leitura. Ele só lê e responde; **não mexe em arquivo nenhum**.
- "No projeto dervs-voz, pede pro Codex analisar a ponte" (ou "pede pro Codex analisar a ponte no projeto dervs-voz"): lê aquele projeto. Sem dizer o projeto, ele responde sem ler código nenhum.
- "No projeto X, pede pro Codex corrigir/criar/refatorar...": **escrita**. O DERVS repete o pedido e espera você dizer **confirma**. Só então cria uma cópia isolada do projeto (branch `dervs/codex-...`), e o Codex trabalha **só nela**, sem internet e sem acesso ao GitHub. Nada é commitado nem enviado: você vê as mudanças na cópia e decide.
- "Para" interrompe o Codex. Só roda um pedido por vez.

**O que você ouve e vê:** a voz lê no máximo duas frases; o texto completo aparece na conversa do painel. Se a resposta tiver algo parecido com senha ou chave, aquela linha é cortada. O painel mostra o chip **CODEX** ("pronto (ChatGPT)", ou o motivo de não estar: não instalado, não logado, desligado). Se o login for por chave de API, o chip avisa que gasta dinheiro.

**Configuração (`config.json`):** `codex_ligado` (padrão `true`), `codex_caminho` (vazio = o DERVS acha o programa sozinho a cada uso), `codex_esforco` (`low`, `medium` ou `high`; mais alto pensa mais e demora mais).

**O Codex como reserva do Claude (08/10/2026):** se você pede uma *análise de um projeto seu* ("analisa o projeto dervs-voz", "investiga o bug do login no projeto dervs voz") e o Claude ainda está ocupado com o pedido anterior, o DERVS passa esse pedido ao Codex, só para leitura e preso à pasta daquele projeto, e avisa antes: "O Claude está ocupado; passei para o Codex, só para leitura." Pedido sem projeto ("verifica meu PC", "analisa meus documentos") nunca é desviado: o Codex, mesmo só lendo, enxergaria o computador inteiro, e isso iria para a OpenAI sem você ter escolhido. Ele nunca desvia pedido de mexer em código ("conserta…", "cria…"). Nesse caso continua dizendo que está ocupado e lembra que você pode dizer "no projeto tal, pede pro Codex fazer isso". Se você chamou o Claude pelo nome ("pede pro Claude…"), o pedido também não é desviado. Para desligar a reserva, ponha `"codex_reserva": false` no `config.json`. Cada desvio fica anotado em `roteamento.jsonl`.

**Se der errado:** "Não achei o Codex" = instale o app Codex e entre com o ChatGPT. "Não está logado" = abra o app Codex e entre. A pasta do app muda de versão a cada atualização (`...\WindowsApps\OpenAI.Codex_<versão>...`) e o Windows não deixa listá-la sem ser administrador; por isso o DERVS pergunta o caminho ao próprio Windows em vez de gravá-lo.
