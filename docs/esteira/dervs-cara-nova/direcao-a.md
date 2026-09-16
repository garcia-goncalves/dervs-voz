# Direção A — Diretor de arte (agente 1 de 3, cego aos outros dois)

## Sensação, em uma frase

Instrumento de precisão que escuta em silêncio — não uma tela que grita "eu sou o futuro",
mas uma que se comporta como se já fosse óbvio que é.

## Ângulo escolhido

Sobriedade radical: futurismo pela ausência, não pelo excesso. A tela do DERVS não decora
nada — ela é quase vazia, quase preta, quase sem cor, e o único elemento que se move é a
onda. Tudo o resto existe para não competir com ela. É o oposto do "escuro com detalhes em
neon": aqui não há gradiente decorativo, não há brilho difuso cobrindo painel inteiro, não
há textura de fundo. Há espaço negro, uma linha fininha de texto monoespaçado, e a onda.

A referência mental é o painel de um instrumento de laboratório caro, não o painel de nave
espacial de filme — o tipo de tela que um equipamento médico ou um osciloscópio de precisão
mostra: dado real, sem enfeite, e por isso mesmo com uma beleza que não precisa se explicar.

## Paleta de cor

Quase monocromática — a cor entra em doses homeopáticas, nunca em bloco:

| Token | Hex | Uso |
|---|---|---|
| `--bg` | `#0A0B0C` | fundo da janela inteira — quase preto, não preto puro (evita banding em telas integradas) |
| `--surface` | `#121316` | painel/bandeja, quando precisa se destacar 1 grau do fundo |
| `--linha` | `#26282C` | divisores, bordas finas — quase invisível de propósito |
| `--texto-primario` | `#E4E6EA` | texto principal, nunca branco puro |
| `--texto-secundario` | `#6E7480` | rótulo, estado, texto de apoio |
| `--sinal` | `#D8FF3E` | única cor viva do sistema — verde-limão elétrico, cor de instrumento de laboratório/osciloscópio, não de cyberpunk |
| `--sinal-fraco` | `#7A8A2A` | o mesmo tom, dessaturado, para a onda em repouso/silêncio |
| `--erro` | `#FF5C5C` | só para falha real (microfone morto, processo caiu) |

Regra dura desta direção: **nenhuma cor além dessas oito**. Nada de azul, nada de roxo,
nada de gradiente multicolor. A onda é a única coisa viva na tela — se tudo brilhasse,
nada brilharia.

## Escala tipográfica

Monoespaçada em tudo — é o elemento que mais carrega "instrumento", não "aplicativo de
consumo":

- **Família:** `"JetBrains Mono"` (Google Fonts, licença SIL Open Font, roda bem
  empacotada localmente no Electron sem depender de rede) — com `ui-monospace`,
  `"Cascadia Code"`, `monospace` como fallback do sistema.
- **Pesos:** só dois — 400 (texto) e 500 (ênfase). Nunca bold 700: nesta direção,
  ênfase é dada por espaço e por cor, não por peso.
- **Tamanhos**, em escala curta e discreta (a tela não tem hierarquia de "H1, H2, H3" —
  é quase tudo o mesmo tamanho, porque quase tudo tem a mesma importância baixa):
  - 11px / `--texto-secundario` — rótulos de estado ("ouvindo", "processando", "em silêncio")
  - 13px / `--texto-primario` — texto de conversa (o que o DERVS transcreveu/respondeu)
  - 20px / `--texto-primario`, tracking levemente aberto (+0.02em) — o único momento de
    destaque tipográfico: o nome "DERVS" ou o relógio, quando aparecem
- Todo texto em caixa baixa, exceto siglas — maiúscula constante é o primeiro instinto de
  quem quer parecer "tech" e é exatamente o clichê que esta direção evita.

## Espaçamento e forma

- **Raio de borda:** 2px, quase reto. Cantos vivos comunicam instrumento; cantos muito
  arredondados comunicam brinquedo. Não é zero porque zero fica agressivo numa janela
  flutuante pequena.
- **Sombra:** nenhuma sombra de elevação (`box-shadow` com blur) — em vez disso, um único
  contorno de 1px em `--linha`. Elevação por sombra é linguagem de app de consumo
  (Material/iOS); aqui a hierarquia é feita por espaço em branco, não por profundidade
  falsa.
- **Densidade:** muito baixa. Padding generoso (24–32px nas bordas da janela, 16px entre
  blocos). A janela de conversa mostra poucas linhas por vez, com bastante fundo negro ao
  redor — o vazio é o luxo desta direção, não falta de conteúdo.
- **Grade:** um único eixo vertical centralizado; nada de colunas, cards ou grid de
  múltiplas células. A tela inteira é uma coluna estreita (~360–420px), o que também
  resolve "sobreviver em 360px" de graça: ela já nasce nesse comprimento.

## A onda de voz

- **Forma:** uma única linha fina — 1.5px de espessura em repouso — atravessando
  horizontalmente o terço inferior da janela. Não é um bloco de barras (equalizador) nem
  um círculo pulsante: é um traço, como o de um osciloscópio real, desenhado em Canvas 2D
  com `requestAnimationFrame` a partir do valor de amplitude que chega da ponte Python
  (`rms()` de `dervs_listen.py`, por `Escuta.run`) — nunca captura própria de áudio no
  Electron.
- **Cor:** `--sinal-fraco` em repouso (quase invisível, uma sugestão de linha reta);
  `--sinal` quando há amplitude, com a intensidade da cor (não o brilho/glow) variando
  com o volume — é uma alteração de saturação/opacidade, não um `box-shadow` de neon.
- **Comportamento:** a linha se deforma em picos finos e precisos proporcionais ao RMS de
  cada quadro — sem suavização exagerada, sem física de mola "orgânica". O movimento deve
  parecer leitura de instrumento, não organismo respirando. Quando o DERVS fala (TTS), a
  mesma linha se anima com a amplitude do `.wav` sincronizada à reprodução (ver C9 do
  spec) — sem trocar de cor entre "eu falo" e "ele fala": a diferença fica só no rótulo de
  estado (11px, texto) acima da linha, nunca na cor da onda. Um rótulo de estado textual
  minúsculo (`ouvindo` / `falando` / `em silêncio`) acompanha a linha, sempre em
  `--texto-secundario`.
- **Em silêncio absoluto:** a linha não some — fica reta e fraca. Uma tela "futurista" que
  apaga tudo quando não há som pareceria quebrada; aqui, linha reta e viva é o estado de
  repouso do instrumento, não ausência de interface.

## Referência honesta

A ideia não nasceu do nada: vem do painel de controle de equipamento de laboratório e
osciloscópio digital (o traço fino verde-limão sobre fundo preto é literalmente a estética
de um osciloscópio Tektronix ou de um monitor de sinais vitais simplificado), cruzado com a
tipografia monoespaçada e o vazio generoso de terminais modernos como o próprio Warp/iTerm
em tema escuro extremo — e com o princípio geral de "menos elementos, mais silêncio visual"
que aparece em interfaces de ficção científica que optam por realismo técnico em vez de
espetáculo (o tipo de HUD que parece que alguém de verdade projetou para ler um dado, não
para impressionar visitante). Não é nenhum produto específico copiado; é a combinação
desses três hábitos visuais aplicada a um app de um usuário só, numa máquina sem placa de
vídeo — onde "bonito" pode significar "quase nada na tela, e o nada é intencional".
