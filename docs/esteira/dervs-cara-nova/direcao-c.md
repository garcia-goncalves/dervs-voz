# Direção C — Diretor de arte (painel adversarial, fase 3)

## Sensação, em uma frase

Abrir o DERVS deve parecer virar a capa de um vinil que ninguém mais faz: um cartaz de
show gráfico, saturado e um pouco barulhento — não uma tela "de tecnologia", uma peça de
impressão.

## Paleta

Fundo quase preto com temperatura violeta, não cinza-tecnologia:

- `#12041C` — fundo base (violeta-carvão)
- `#1D0A2B` — fundo secundário / painel (camadas de profundidade sem gradiente suave)
- `#7B2FF7` — roxo elétrico (cor de marca, usada em áreas grandes e na onda)
- `#FF2E9A` — rosa-choque (contraste de ação, estado "ouvindo")
- `#C6FF3D` — verde-limão (contraste de destaque, estado "falando"/alerta, nunca em área grande)
- `#FFF6FA` — branco quente (texto principal sobre fundo escuro)
- `#B9A8C9` — lilás apagado (texto secundário, status, timestamps)

Regra de uso: **nunca as três cores fortes (roxo, rosa, limão) juntas na mesma
composição em peso igual** — uma domina, uma pontua, a terceira aparece só na onda ou em
um único acento por tela. Isso evita o efeito "arco-íris neon" que é o clichê que a
direção quer evitar.

Contraste conferido: `#FFF6FA` sobre `#12041C` passa de 15:1; `#B9A8C9` sobre `#12041C`
fica em ~7,3:1 — ambos folgados acima do 4.5:1 exigido. `#C6FF3D` sobre `#12041C` é usado
só para elementos gráficos e ícones grandes, nunca para texto corrido, porque texto limão
sobre fundo escuro cansa a vista em uso o dia inteiro (e este é um app que fica aberto o
dia inteiro — critério do Analista).

## Escala tipográfica

Duas famílias, ambas Google Fonts leves e com bom suporte no Electron/Chromium:

- **Display / título — Space Grotesk, peso 700 (Bold).** Geométrica, larga, com
  personalidade de cartaz sem ser serifada nem "corporativa". Usada em tamanho grande e
  fora do eixo (ver espaçamento): 40px para o nome "DERVS" no estado ocioso, 22px para
  rótulos de estado ("ouvindo", "pensando", "falando").
- **Corpo / status técnico — IBM Plex Mono, pesos 400 e 500.** Monoespaçada dá o
  contraponto técnico-impresso (como legenda de ficha técnica num encarte de disco) para
  texto de transcrição ao vivo, timestamps e mensagens de erro. 15px para texto corrido,
  13px para metadados.

Sem uma terceira família — a régua da casa é poucas fontes, grandes, jogadas com
ousadia de posição, não muitas fontes pequenas.

## Espaçamento e forma

- **Raio de borda: 2px, quase reto.** Cartaz e capa de disco não têm cantos macios;
  suavizar a borda aqui destrói a referência. As únicas curvas da tela inteira são a
  onda e o círculo do estado ("ouvindo"/"falando").
- **Sombra: dura, deslocada, sem blur** — `4px 4px 0 #7B2FF7` (ou a cor de acento da
  vez) em vez de `box-shadow` difuso. É a sombra de impressão registrada errado de
  propósito (efeito "risografia"/serigrafia), não o glow suave que todo app "futurista"
  usa — é o ponto onde esta direção se afasta de propósito do clichê citado no briefing.
- **Densidade: alta em poucos elementos, não muitos elementos pequenos.** Composição
  assimétrica: o texto de estado fica ancorado num canto (ex. inferior-esquerdo), a onda
  ocupa uma faixa diagonal dominante da janela, e há bastante área de fundo "vazia" —
  vazio aqui é parte da composição de cartaz, não espaço desperdiçado.
- **Grade quebrada, não centralizada.** Nada fica no centro geométrico da janela; os
  elementos se apoiam nas bordas e cantos, como um cartaz de show onde o título nunca
  está morto no meio.

## Como a onda se desenha

A onda não é uma senoide fina e simétrica cruzando o centro da tela — é uma **faixa
grossa, diagonal, tipo pincelada serigráfica**, atravessando a janela de um canto ao
outro (por exemplo, inferior-esquerdo a superior-direito), desenhada em Canvas 2D como um
caminho fechado (não uma linha): a amplitude que chega pela ponte controla a **espessura**
da faixa e o deslocamento vertical de cada segmento, não só a altura de picos.

- **Cor:** gradiente de três paradas duras (não suavizadas) — roxo `#7B2FF7` na base da
  faixa, rosa `#FF2E9A` no meio, limão `#C6FF3D` na ponta — como uma capa de vinil
  impressa em risografia com registro levemente deslocado entre camadas (cada cor com um
  offset de 2–3px em relação à seguinte, fixo, não animado).
- **Repouso (ninguém fala):** a faixa "respira" devagar — espessura oscila num intervalo
  pequeno e previsível, para não parecer travada nem parecer estar "escutando" algo que
  não está acontecendo.
- **Ouvindo o dono:** a faixa ganha espessura e serrilhado nas bordas proporcional ao
  `rms()` que chega da ponte — quanto mais alto o volume, mais a borda da faixa vira dente
  de serra em vez de lisa. É o único estado em que a cor pende mais para o rosa-choque.
- **DERVS falando:** mesma faixa, mesma física, mas a cor pende para o verde-limão como
  cor dominante — dá ao dono uma leitura instantânea, sem ler texto, de "sou eu falando"
  vs. "é ele falando".
- **Sem partículas, sem FFT multibanda, sem 3D** — uma forma só, um valor de amplitude
  só, exatamente como o corte do spec pede; a "loucura" visual mora na cor e na
  composição de cartaz, não em efeito de partícula.

## Referência honesta

Três fontes, ditas sem rodeio:

1. **Capas de vinil e cartazes de show de música eletrônica francesa dos anos 2000**
   (Justice, Daft Punk/Ed Banger) — a ideia de cor saturada e forma gráfica geométrica
   como identidade, sem precisar de foto nem de textura realista.
2. **Impressão risográfica/serigráfica** (o "registro deslocado" de camadas de cor) como
   fonte da sombra dura e do offset de cor na onda — é uma estética que existe há décadas
   fora da tela e que quase nenhum app "futurista" usa, porque todo mundo lê "futurista"
   como "glow azul-neon".
3. **A estética gráfica de "Hotline Miami"** (jogo) como referência de como cor saturada
   + tipografia grande + raio de borda reto conseguem parecer "muito loucas" sem depender
   de efeito 3D pesado — relevante porque esta máquina não tem placa de vídeo dedicada.
