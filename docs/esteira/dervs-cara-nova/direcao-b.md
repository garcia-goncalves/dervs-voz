# Direção B — Organismo

## Sensação, em uma frase

Falar com uma criatura quente que respira ao seu lado — não operar um painel de controle.

## Paleta

Fundo quase preto, mas puxado para marrom-vinho, nunca azul-frio — é isso que separa
"futurista orgânico" de "futurista de nave espacial":

| Papel | Cor | Hex |
|---|---|---|
| Fundo base | preto-vinho | `#1A0F12` |
| Fundo elevado (painel, cartão) | marrom-carvão | `#2A1518` |
| Texto principal | marfim quente | `#F5E9DE` |
| Texto secundário | marfim opaco | `#C9AFA0` |
| Acento primário — a onda em repouso | coral vivo | `#FF6B5B` |
| Acento secundário — pico de volume | âmbar | `#FFB648` |
| Acento terciário — a "respiração" de fundo | magenta suave | `#E85D9E` |
| Estado de escuta ativa | rosa-coral translúcido | `#FF8B7A` a 40% de opacidade |
| Borda/traço fino | marrom-rosa | `#4A2B2E` |

Regra da paleta: nunca mais de duas cores de acento acesas ao mesmo tempo na tela — coral
e âmbar se revezam com o volume (baixo = coral, alto = âmbar), o magenta mora só no glow
de fundo, pulsando devagar mesmo em silêncio, como um sinal vital. Contraste do texto
principal sobre o fundo base: `#F5E9DE` em `#1A0F12` passa de 14:1 — sobra folga para
qualquer estado.

## Tipografia

- **Display / nome do DERVS e estado** ("Ouvindo...", "Pensando..."): **Fraunces**
  (Google Fonts), peso 400–500, itálico opcional no estado de "pensando" — é uma serifa
  com curvas orgânicas, quase caligráfica em pesos baixos, o oposto de uma mono técnica.
  Tamanho 28–36px.
- **Corpo / texto de conversa**: **Literata** (Google Fonts) ou, na ausência dela,
  `Georgia, "Iowan Old Style", serif` como fallback de sistema — uma serifa de leitura
  confortável, 16–18px, para não cansar em texto longo de transcrição.
  Peso 400 para fala do dono, 500 para fala do DERVS (leve diferenciação de peso, não de
  cor, para não competir com a paleta).
- **Rótulos pequenos** (hora, bandeja, tooltip): `system-ui` mesmo, 12–13px — não vale a
  pena carregar uma terceira fonte para texto que ninguém para para ler.

Nada de mono/geométrica sem-serifa como face principal: é o clichê visual de "tech", e a
direção aqui é o oposto disso.

## Espaçamento e forma

- **Raio de borda generoso e assimétrico**: 24–32px nos cantos, nunca retângulo reto —
  os cartões e a janela principal têm cara de "gota" ou "célula", não de janela de app.
  Onde o Electron permitir (`BrowserWindow` sem moldura + `border-radius` no `body`), a
  própria janela é arredondada.
- **Sombra**: sem sombra dura de UI corporativa. Em vez disso, glow suave e colorido —
  `box-shadow: 0 0 60px -10px rgba(255,107,91,0.35)` ao redor da janela e do avatar/onda,
  como se a interface tivesse uma auréola de calor. Intensidade do glow cresce e diminui
  em ciclo lento (4–6s) mesmo sem áudio, para dar sensação de "algo vivo, respirando".
- **Densidade**: baixa. Muito espaço negativo em volta do elemento central (a onda). Um
  único foco visual por tela — nunca dois elementos competindo por atenção. Texto de
  conversa em bolhas largas, bem espaçadas verticalmente (16–20px de gap), sem grade
  rígida.
- **Bordas de separação**: nunca linha reta de 1px cinza. Onde precisar separar áreas,
  usa gradiente radial suave (`#4A2B2E` esmaecendo para transparente) em vez de régua.

## A onda de voz

Não é um espectro técnico de barras nem um osciloscópio de linha reta — é uma **massa
fluida e translúcida**, como uma gota de líquido colorido vista de cima, ou uma medusa
pulsando:

- **Forma base**: um blob (metaball simples, 2D, feito com alguns círculos sobrepostos
  com `filter: blur()` + `contrast()` para fundir as bordas — o efeito "metaball" clássico
  em Canvas 2D, leve o suficiente para gráfico integrado) posicionado no centro da janela,
  ocupando ~120–180px de diâmetro em repouso.
- **Cor**: gradiente radial coral (`#FF6B5B`) no centro para magenta (`#E85D9E`) na borda,
  com opacidade entre 50% e 80% — nunca sólido, sempre com sensação de algo translúcido e
  quente por trás.
- **Repouso (sem áudio)**: pulsa devagar e por conta própria, como respiração — período de
  ~3,5s, variação de raio pequena (±6%), simulando estar viva mesmo em silêncio. Nunca
  fica estática.
- **Reação ao volume** (`rms()` que chega pela ponte): o raio do blob cresce
  proporcionalmente ao nível — silêncio = quase repouso, pico = até ~1,6x o tamanho base —
  e a cor desliza de coral para âmbar conforme o volume sobe, sem transição abrupta
  (interpolação linear de cor quadro a quadro). O contorno também fica ligeiramente mais
  irregular/"esquentado" (mais ruído na posição dos círculos do metaball) quanto mais alto
  o som, como se a criatura reagisse com mais agitação.
- **Diferenciação dono vs. DERVS falando**: quando é a voz do dono (entrada de
  microfone), o blob pulsa em coral/âmbar como descrito; quando é o DERVS falando
  (playback do TTS), o blob pulsa com o mesmo motor de amplitude mas girando a paleta
  para o eixo magenta/rosa — mesma criatura, "timbre" de cor diferente, para o dono
  distinguir num relance quem está com a palavra sem precisar ler nada.
- **Estado ocioso prolongado** (nem escutando nem falando por minutos): a respiração de
  repouso desacelera ainda mais (período de ~6s) e o glow ao redor da janela também
  esmaece — sinal sutil de "estou aqui, mas de boa".

## Referência honesta

A ideia veio de dois lugares concretos, não de moodboard genérico:

1. **As texturas de "vida digital" do filme *Her* (2013)** — a interface do OS1 nunca usa
   frio/mecânico; ela é quente, com luz âmbar/coral e formas que parecem respirar, e é
   citada há anos como o contraponto ao clichê "IA = azul neon". É a referência mais direta
   para "futurista sem ser frio".
2. **Metaballs / "blob" de interface**, o mesmo truque visual usado em widgets de
   assistente de voz mais recentes que abandonaram a barra de onda tradicional em favor de
   uma forma orgânica única que "engorda e afina" com o áudio — tecnicamente é o mesmo
   efeito de fusão de círculos com blur que se vê em fundos de site "líquidos" (bem
   documentado em tutoriais de Canvas 2D / SVG filter `feGaussianBlur` + `feColorMatrix`
   para o efeito metaball), reaproveitado aqui como o próprio "rosto" do DERVS em vez de
   decoração de fundo.

Essa combinação — paleta quente de *Her* + blob de metaball reagindo a `rms()` — é o que
torna a direção genuinamente diferente de "onda técnica em neon azul": em vez de mostrar
um gráfico de áudio, ela mostra uma presença viva reagindo à voz.
