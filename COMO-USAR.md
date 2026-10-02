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

**O botão voltou (23/09/2026).** Logo abaixo do nome **DERVS** na tela há um
botão que diz **MICROFONE LIGADO** (ponto cheio, ciano) ou **MICROFONE
DESLIGADO** (ponto vazio, apagado). Um clique liga ou desliga a escuta. O
botão só muda quando o DERVS realmente abriu ou fechou o microfone — ele não
"finge" o estado. A sua última escolha fica guardada: se desligar e fechar o
DERVS, ele abre desligado.

Outras formas, se precisar:

1. **Sair do DERVS** (botão direito no ícone da bandeja → "Sair do DERVS").
   Fechando o app, o microfone fecha junto.
2. **Editar a configuração** — a chave `escuta_ao_abrir` em
   `%APPDATA%\dervs\config.json` (`true` = abre escutando, o padrão).

Enquanto ele não ouvir o seu nome, o que você fala **não sai do seu
computador** de qualquer forma (ver o funil mais abaixo).

---

## O que ele faz, em uma frase

Fica ouvindo a sala. Quando você diz **"DERVS"** (ou "OK DERVS", ou "Ei DERVS"),
ele acorda, entende o pedido, mostra o que vai fazer, espera você aprovar, faz,
e responde falando.

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
