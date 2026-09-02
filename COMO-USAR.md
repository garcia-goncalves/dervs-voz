# DERVS — como usar, no seu Windows

Escrito para quem não mexe em terminal. Nenhum comando aqui precisa ser
decorado; todos podem ser copiados inteiros.

---

## Como abrir o DERVS

**Dois cliques no ícone `DERVS`** — ele está na sua Área de Trabalho e também no
menu Iniciar (aperte a tecla Windows e comece a digitar "DERVS").

O ícone é o losango dourado com o ponto aceso, o mesmo selo que aparece dentro
do app.

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

O botão **🎙️ Ei DERVS** / **🔴 Ouvindo**, no alto da janela, é o interruptor do
microfone.

- **🔴 Ouvindo** (dourado aceso): o microfone está aberto. Diga "DERVS" e ele
  atende. Só isso — o que você fala **não sai do seu computador** enquanto ele
  não ouvir o nome.
- **🎙️ Microfone desligado**: nada é ouvido, nem aqui dentro.

**Ele lembra da sua escolha.** Se você desligar e fechar o app, na próxima vez
ele abre desligado, e a barra de status diz *"escuta desligada — clique no botão
para ligar"*. Assim o silêncio é escolha sua, não defeito.

Se preferir que ele sempre abra ouvindo, mude `escuta_ao_abrir` para `true` no
arquivo de configuração (`%APPDATA%\dervs\config.json`).

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

## Ligar e desligar o microfone

Dentro da janela do DERVS há um botão no alto, que diz em qual estado está:

| O botão diz | Significa |
|---|---|
| **🔴 Ouvindo** | O microfone está aberto. Ele só responde se ouvir seu nome. |
| **🎙️ Microfone desligado** | O microfone está fechado. Ele não ouve nada, nem localmente. |

Clicar alterna entre os dois. O estado fica escrito com todas as letras de
propósito: quem deixa um microfone aberto o dia inteiro precisa conseguir olhar
para a tela e saber, na hora, se ele está aberto.

Ao abrir, o DERVS já nasce ouvindo.

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

## Quanto custa por mês

A voz e o porteiro são **de graça** — rodam na sua máquina, offline. O que é
cobrado é só a transcrição do pedido e o cérebro que entende.

Estimativa para uso pesado, cerca de 300 pedidos por dia:

| Item | Onde roda | Custo por mês |
|---|---|---|
| Perceber a fala | seu PC | US$ 0 |
| O porteiro (ouvir o nome) | seu PC | US$ 0 |
| Transcrever o pedido | nuvem | ~US$ 3,40 |
| O cérebro | nuvem | ~US$ 2,00 |
| A voz falando | seu PC | US$ 0 |
| **Total** | | **~US$ 5 a 6** |

Para comparar: sem o porteiro, deixando ligado 8 horas por dia, só a
transcrição daria **~US$ 43 por mês**.

Preços consultados em 01/09/2026 na página oficial da OpenAI. O modelo usado
para transcrever é o `gpt-transcribe`, lançado em julho de 2026 — é ao mesmo
tempo mais preciso e mais barato que o anterior.

---

## O que ainda falta para funcionar 100%

**Falta a chave da OpenAI nesta máquina.** É o que permite a transcrição
precisa e o cérebro. Sem ela o DERVS ainda abre, ouve e reconhece seu nome
(isso é local), mas para transcrever ele cai no modo offline, que é bem mais
lento nesta máquina — que não tem placa de vídeo dedicada.

A chave é um segredo: **não me mande por aqui.** O caminho certo é você mesmo
criar o arquivo. Para descobrir o caminho exato, é este comando:

```
python -c "import dervs_config as c; print(c.caminhos_do_segredo()[0])"
```

Crie um arquivo de texto nesse caminho com uma única linha:

```
OPENAI_API_KEY=sua-chave-aqui
```

Se preferir, me avise e eu te guio passo a passo — inclusive onde pegar a
chave, se você não tiver uma.

---

## Se der errado

| O que acontece | O que fazer |
|---|---|
| Ele não acorda quando chamo | Fale um pouco mais alto e mais perto. Se continuar, me avise: existe um detector mais preciso que dá para ligar (Porcupine), que exige uma conta gratuita de 5 minutos. |
| Ele acorda sozinho, sem eu chamar | Me avise. É o mesmo caminho do item acima. |
| Ele não fala nada | O motor de voz precisa dos modelos em `%LOCALAPPDATA%\dervs\modelos`. Se a pasta sumiu, me avise que eu baixo de novo. |
| A janela não abre | Me avise, e diga se apareceu alguma mensagem na tela. |
| Ele pede confirmação demais | Me avise. A rede de segurança prefere perguntar a mais que a menos, mas se estiver incomodando dá para afinar. |
| "não achei a biblioteca sounddevice" | Faltou instalar. Me avise que eu instalo. |
