# DESIGN — dervs-cara-nova

## direcao_visual_escolhida

**Decisão final, substituindo a escolha original: "HUD/JARVIS", cor única ciano.** O painel
adversarial original (Direções A, B, C) foi julgado e C venceu na fase 3, como registrado
abaixo em "histórico do painel". Mas o dono só consegue avaliar cor/forma de verdade vendo
animado, não lendo descrição — por isso, depois do painel, ele viu as três direções rodando
ao vivo no navegador (prévias publicadas como Artifact) e nenhuma bateu com o que ele tinha
em mente. Ele pediu, em sequência: (1) uma forma redonda com ondas ao redor, "tipo a voz do
ChatGPT" — prototipado como Direção D (orbe com anéis); (2) recusou D e pediu explicitamente
"JARVIS" e "ultra futurista" — prototipado como Direção E (HUD holográfico: núcleo brilhante,
anéis segmentados girando, ticks radiais tipo dial, tipografia de painel de nave, leitura de
dados ao lado); (3) aprovou o rumo de E e pediu **uma cor só**, deixando a escolha da cor a
critério de quem está construindo.

**Cor escolhida: ciano elétrico (`#00E5FF`).** É a cor mais associada à referência que o
próprio dono nomeou (o HUD azul-ciano holográfico de JARVIS/Homem de Ferro) — usar outra cor
aqui seria contrariar a referência que ele deu, não uma escolha livre. O núcleo central usa
branco (`#FFFFFF`) só no centro do brilho, como ponto mais quente de qualquer luz — isso não
conta como segunda cor de marca, é o mesmo tipo de recurso que uma lâmpada tem no próprio
brilho. Vermelho (`#FF3B3B`) fica reservado só para o estado de erro/aviso, por ser uma cor
semântica (perigo/atenção), não uma cor de identidade — continua valendo a regra de nunca
misturar cor semântica com cor de marca na mesma composição.

**Histórico do painel original (Direções A, B, C — fase 3, mantido por rastreabilidade):**
C ("cartaz de vinil") venceu o painel adversarial por ser a mais alinhada com "surreal, muito
louco" nas palavras do dono; A ("instrumento de precisão", osciloscópio verde-limão) e B
("organismo", blob quente inspirado em *Her*) ficaram registradas como referências para um
eventual "modo alternativo" no futuro. Nenhuma das três sobreviveu ao teste real de o dono
ver e reagir ao vivo — o que confirma a razão de existir o gate de escolha visual com o
dono, e não só o julgamento interno do painel.

## tokens

Substituem por completo os tokens de `direcao-c.md` (histórico, não descartado do disco).
Fonte da verdade agora: a Direção E, com paleta reduzida a uma cor de marca.

**Cor**
| Token | Hex | Uso |
|---|---|---|
| `--bg` | `#050810` | fundo base — quase preto, temperatura azul-marinho |
| `--painel` | `#0A1220` | camada elevada (painel, cartão de aviso) |
| `--acento` | `#00E5FF` | única cor de marca — núcleo, anéis, texto de estado, ticks |
| `--acento-fraco` | `#0A6E82` | mesma cor, escurecida — bordas finas, ticks curtos, estado ocioso |
| `--nucleo-quente` | `#FFFFFF` | ponto mais brilhante do núcleo — não é cor de marca, é brilho |
| `--texto-primario` | `#D9F6FF` | texto principal (branco levemente azulado, não branco puro) |
| `--texto-secundario` | `#5C8A99` | rótulo técnico, timestamp, leitura de dados |
| `--erro` | `#FF3B3B` | só para falha real — cor semântica, nunca decorativa |

Regra dura: **uma cor de marca só.** Nada de segunda cor de acento "para variar" — a
identidade do HUD vem da forma (anéis, ticks, núcleo) e do movimento (rotação, brilho), não
de paleta multicolor. Contraste: `--texto-primario` sobre `--bg` passa de 14:1; `--acento`
sobre `--bg` passa de 9:1 — ambos folgados acima do 4.5:1 exigido.

**Tipografia**
- Display/título e rótulo de estado: **Orbitron**, peso 700 — 22-40px, sempre em caixa alta
  com leve tracking (`letter-spacing: .08-.12em`) — é a família que carrega a referência de
  painel de nave/ficção científica, e caixa alta aqui reforça "sistema", não "app de
  consumo".
- Corpo/status técnico/transcrição/leitura de dados: **Share Tech Mono**, peso 400 — 12-15px
  para texto corrido, 9-10px para leituras pequenas (ex. "AMP 0.42") ao lado do núcleo.
- As duas via Google Fonts, empacotadas localmente no Electron (o app precisa abrir sem
  internet).

**Espaçamento e forma**
- Fundo com grade sutil (linhas de 1px a `rgba(0,229,255,.025)`, espaçadas 26px) — textura de
  painel técnico, quase imperceptível, nunca competindo com o núcleo.
- Cantos técnicos: marcas em L nos 4 cantos da janela (`border` de 2px em `--acento`, 22px de
  comprimento) — referência de HUD/mira, substitui qualquer moldura decorativa.
- Sem sombra dura nem glow difuso de UI — o único "brilho" da tela é o `shadowBlur` do núcleo
  central, que cresce com o volume. É o oposto da Direção C (sombra dura) e da B (glow
  espalhado): aqui o brilho é um efeito físico do núcleo, não um recurso gráfico da moldura.
- Raio de borda: reto (0-2px) em toda a interface — círculos existem só como forma do núcleo,
  dos anéis e dos ticks, nunca como cantos arredondados de cartão/botão.

## telas

A janela do DERVS tem cinco estados visuais, todos usando os mesmos tokens acima —
**tela parada e funcionando em cada estado antes de qualquer animação ser ligada**. O
Redator apontou corretamente uma lacuna na lista original (faltava o intervalo entre o dono
parar de falar e a resposta chegar) — mantida abaixo como estado 2.5 "pensando". O elemento
central mudou de "faixa diagonal" (Direção C) para **núcleo + anéis segmentados girando**
(Direção E/JARVIS), mas a lógica de dados que alimenta cada estado é a mesma decidida no
spec (C4: amplitude calculada no Python, nunca captura de áudio no Electron).

1. **Ocioso (nada acontecendo).** Fundo `--bg` com a grade sutil e os cantos técnicos em
   `--acento`. No centro, o núcleo pulsa devagar e por conta própria (nunca estático) e os
   anéis giram devagar, sempre — "o sistema nunca aparenta estar desligado". Nome "DERVS" em
   Orbitron 700, caixa alta, ancorado no topo da janela. Nenhum texto de transcrição visível.
   Ícone da bandeja com os três itens: "Abrir DERVS", "Recolher janela", "Sair do DERVS".
2. **Ouvindo (o dono está falando).** Rótulo **"ouvindo"** (palavra do Redator, mantida —
   `textos.md`), renderizado em Orbitron 700/22px com `text-transform: uppercase` (a caixa
   alta é só estilo visual do HUD; a palavra continua simples, não a troco de um termo
   técnico) — cor `--acento`, acima do núcleo. Os anéis aceleram a rotação e o núcleo brilha
   mais forte (`shadowBlur` maior), proporcional ao `rms()` recebido da ponte Python — reage
   em velocidade e brilho, não em cor (só existe uma cor). Leitura técnica ao lado do núcleo
   (`AMP 0.xx`) em Share Tech Mono — essa sim pode ser técnica, é leitura de instrumento, não
   texto que o dono precisa entender para usar o app. Texto sendo transcrito aparece ao vivo,
   `--texto-primario`, conforme chega — não espera a frase terminar para mostrar algo.
2.5. **Pensando (entre o dono parar de falar e a resposta chegar).** Rótulo **"pensando"**
   (mesma palavra do Redator), mesma cor `--acento` (não há segunda cor para diferenciar — a
   diferença é a física do movimento). Rotação constante e moderada, sem reagir a amplitude
   (não há áudio novo). Sem texto novo de transcrição; o texto do dono, já transcrito,
   continua visível.
3. **Falando (o DERVS está respondendo).** Rótulo **"falando"** (mesma palavra do Redator).
   Mesmo motor de rotação e brilho do estado "ouvindo", agora reagindo à amplitude do `.wav`
   da resposta
   sincronizado à reprodução (tarefa da fase 4, item C9 do spec) — o dono distingue "eu falo"
   de "ele fala" pelo rótulo de texto e pelo contexto (só um dos dois acontece por vez), não
   por cor, já que a paleta é intencionalmente monocromática. Texto da resposta em
   `--texto-primario`, abaixo do texto do dono (histórico curto, só a última troca).
4. **Erro/aviso** (ex.: "não entrou som", "microfone desligado", daemon caiu). Os anéis
   desaceleram e mudam para `--erro` (vermelho) — única exceção à regra de cor única, porque
   erro é estado semântico, não estético. Cartão de aviso em `--painel`, borda `--erro`.
   Texto do erro em Share Tech Mono, `--texto-primario`, sempre dizendo o que fazer (regra do
   Redator), nunca só um código de erro.

**Em 360px de largura** (janela redimensionada ao mínimo): o núcleo e seus anéis são
desenhados num `<canvas>` quadrado que encolhe proporcionalmente; rótulo e leitura técnica
continuam legíveis porque ficam ancorados nas bordas/cantos da janela, não numa grade de
múltiplas colunas. Nenhum elemento depende de largura mínima maior que isso para fazer
sentido.

## textos

Ver `docs/esteira/dervs-cara-nova/textos.md` (produzido pelo Redator de interface).

## assets

Ver `docs/esteira/dervs-cara-nova/assets.md` e `docs/esteira/dervs-cara-nova/assets/CREDITOS.md`
(produzidos pelo Diretor de mídia).

## estrategia_de_aquisicao

Adaptado ao caso real: **não é um site público** — é um aplicativo de desktop pessoal, de um
usuário só, que já sabe que o DERVS existe e já tem os atalhos instalados (Área de Trabalho e
menu Iniciar, criados por `scripts/instalar_atalho.py`). Não há SEO, meta tag, Open Graph ou
página de marketing a fazer — a lente Estrategista (fase 3) não foi despachada por esse
motivo: nenhum critério dela (title, meta description, `schema.org`, Core Web Vitals) se
aplica a uma janela que não é uma página web pública, e despachar o papel aqui seria gastar
sem mudar nenhuma decisão.

**Como chega:** o mesmo atalho de sempre — nada muda para o dono no "como abrir".

**Por que fica (o equivalente ao "não sair da página"):** a primeira coisa que o dono vê ao
abrir o app depois da atualização precisa já ser a onda reagindo à própria voz — é o momento
que prova, sem precisar de texto explicando nada, que a "cara nova" existe e funciona. Se a
primeira tela mostrada for uma tela ociosa sem reação visível em poucos segundos, a entrega
falha o critério de aceitação do briefing ("o dono consegue ver a onda reagindo à própria voz
numa demonstração ao vivo").

**Próximo passo, sempre único e visível:** em cada estado, há uma única coisa clara para o
dono fazer ou entender (falar, esperar a resposta, ou corrigir um problema apontado em
linguagem direta) — nunca duas chamadas de atenção competindo na mesma tela pequena.
