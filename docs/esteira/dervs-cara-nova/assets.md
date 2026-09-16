# ASSETS — dervs-cara-nova

**Revisado após decisão final do dono: direção "HUD/JARVIS", cor única ciano
(`design.md`, `direcao-visual_escolhida`).** A versão original deste
documento especificava ícones na linguagem da Direção C ("cartaz de vinil",
três cores, faixa diagonal) — o dono viu essa direção animada ao vivo,
recusou, e pediu explicitamente uma identidade "tipo JARVIS", só depois
convergindo para os anéis/núcleo da Direção E com uma cor só. Os ícones
abaixo substituem os da versão anterior por completo, na mesma ordem de
trabalho do papel (gerar por código primeiro, nada de foto).

## confirmação — não falta nenhuma foto real

Continua valendo sem alteração: o DERVS é um aplicativo de desktop de um
usuário só, sem página de marketing, sem pessoa nem lugar para retratar.
`midia-livre` não se aplica. Sem uso de API paga de geração de imagem
(decisão fechada com o dono em 05/08/2026) — tudo abaixo é forma geométrica
simples (círculo, anel, tick), resolvida em SVG sem IA.

---

## 1. Ícone do app / favicon da janela (substitui `dervs.ico`)

**O que é hoje:** `scripts/instalar_atalho.py:37-76` desenha `dervs.ico` a
partir do selo Qt (`dervs._selo(px)`). Como o selo flutuante sai de escopo
nesta rodada (`spec.md`, corte #1) mas `dervs.py`/`dervs._selo` ficam no
disco (corte #8), o ícone precisa de uma fonte visual nova, na linguagem do
HUD. **Nota para a fase 5:** a estrutura de empacotamento de `gerar_icone()`
pode continuar igual; só troca o que `_png_de(px)` desenha.

**Formato:** SVG mestre, `viewBox="0 0 256 256"`, quadrado, fundo sólido
(o Windows recorta a máscara do ícone sozinho).

**Composição:** núcleo brilhante cercado por um anel segmentado — a mesma
dupla "núcleo + anel" da tela do app, em miniatura estática (um só anel,
não três, porque em 256px um anel já lê bem; três é o que a tela ao vivo
faz com animação, que um ícone parado não tem).

```svg
<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <rect width="256" height="256" fill="#050810"/>

  <!-- anel externo, segmentado (8 arcos com espaço entre eles) -->
  <g stroke="#00E5FF" stroke-width="10" fill="none" stroke-linecap="round">
    <path d="M 128 40 A 88 88 0 0 1 206 90"/>
    <path d="M 216 128 A 88 88 0 0 1 190 196"/>
    <path d="M 128 216 A 88 88 0 0 1 50 190"/>
    <path d="M 40 128 A 88 88 0 0 1 66 60"/>
  </g>

  <!-- ticks curtos ao redor, tipo dial -->
  <g stroke="#0A6E82" stroke-width="4">
    <path d="M 128 18 L 128 30"/>
    <path d="M 238 128 L 226 128"/>
    <path d="M 128 238 L 128 226"/>
    <path d="M 18 128 L 30 128"/>
  </g>

  <!-- nucleo -->
  <circle cx="128" cy="128" r="34" fill="#00E5FF"/>
  <circle cx="128" cy="128" r="16" fill="#FFFFFF"/>
</svg>
```

Leitura da geometria: anel de raio 88 desenhado em 4 arcos (não um círculo
fechado) para ler como "segmentado/técnico", não como argola sólida; 4 ticks
curtos nos eixos cardeais reforçam a leitura de dial/instrumento; o núcleo é
um círculo cheio em `--acento` com um centro branco (`--nucleo-quente`),
reproduzindo o gradiente radial da tela viva como duas cores sólidas
concêntricas (um ícone estático não precisa do gradiente completo).

**Sombra/glow opcional:** se o ícone "sumir" em fundos escuros da barra de
tarefas por falta de contraste de borda, adicionar um `<circle>` extra atrás
do núcleo, raio 44, `fill="#00E5FF" opacity="0.25"` — simula o `shadowBlur`
da tela viva sem precisar de filtro SVG (mais barato de renderizar em
tamanho de ícone). Testar com o ícone real antes de decidir se é necessário.

**Tamanhos a exportar** (mesma lista que `instalar_atalho.py:34` já usa):
16, 20, 24, 32, 40, 48, 64, 96, 128, 256.

**Favicon da janela Electron:** PNG de 32×32 gerado do mesmo SVG — não
precisa de arquivo separado.

---

## 2. Ícone da bandeja do sistema (16×16 / 32×32)

**Por que simplificar:** em 16-32px, 4 arcos + 4 ticks + 2 círculos
concêntricos viram um borrão. A ordem de trabalho do papel manda simplificar
de propósito, não encolher a arte grande.

**Versão simplificada — um anel fechado (não segmentado) e o núcleo, sem
ticks:**

```svg
<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
  <rect width="32" height="32" fill="#050810"/>
  <circle cx="16" cy="16" r="11" fill="none" stroke="#00E5FF" stroke-width="2.5"/>
  <circle cx="16" cy="16" r="4" fill="#00E5FF"/>
</svg>
```

Um anel fechado lê como forma sólida em tamanho pequeno; o núcleo perde o
centro branco (dois tons já é demais em 16px) e vira um único ponto cheio
em `--acento`. Sem ticks, sem segmentação — a essa escala eles só sujam o
desenho.

**Tamanhos:** 16×16 e 32×32, exportados a partir deste segundo SVG. Caminho
sugerido para a fase 5: `electron/assets/bandeja-16.png`,
`electron/assets/bandeja-32.png`.

**Estado único:** os três itens do menu ("Abrir DERVS", "Recolher janela",
"Sair do DERVS", decisão C8 do `spec.md`) não mudam com o estado da escuta —
um ícone só resolve, sem variantes por estado.

---

## 3. Ícone de estado de erro/aviso (tela 4)

Contexto no `design.md`: cartão com fundo `--painel` (`#0A1220`), borda 2px
em `--erro` (`#FF3B3B`) — a única exceção à cor única, porque erro é estado
semântico.

**Formato:** SVG inline, `viewBox="0 0 48 48"` — embutir direto no
HTML/CSS da tela de erro, permitindo `currentColor` se a fase 5 preferir.

```svg
<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
  <circle cx="24" cy="24" r="20" fill="none" stroke="#FF3B3B" stroke-width="2.5"
          stroke-dasharray="6 4"/>
  <rect x="22" y="14" width="4" height="16" fill="#FF3B3B"/>
  <rect x="22" y="33" width="4" height="4" fill="#FF3B3B"/>
</svg>
```

Leitura: um anel tracejado (não sólido, não triângulo) — continua a
linguagem de "dial" do resto da identidade, agora em vermelho para marcar
alerta, com uma exclamação retangular (barra + ponto) dentro. Nada de
triângulo de alerta genérico: o círculo tracejado é o mesmo vocabulário
visual do núcleo/anel do app, só que parado e vermelho — reforça que é o
mesmo sistema avisando, não um ícone de terceiro importado.

---

## 4. Textura ou padrão de fundo

**Decisão: grade sutil, já especificada em `design.md` (não uma textura
nova).** A Direção E already define um fundo com linhas finas
(`rgba(0,229,255,.025)`, 26px de espaçamento) — é a única "textura" da
interface, extremamente discreta (opacidade de 2,5%) e alinhada ao
vocabulário de painel técnico. Nenhuma textura adicional (grão, halftone,
scanline animada) entra nesta rodada: a régua de custo do `spec.md` (C10 —
não consumir mais CPU que o selo atual) vale ainda mais aqui, porque o
próprio núcleo já anima com `shadowBlur` a cada quadro; empilhar mais uma
camada animada é o tipo de custo que a régua existe para barrar.

---

## resumo para a fase 5

| Asset | Formato | Tamanhos | Arquivo sugerido |
|---|---|---|---|
| Ícone do app (substitui `dervs.ico`) | SVG → PNG por tamanho → `.ico` | 16,20,24,32,40,48,64,96,128,256 | mestre `assets/icone-app.svg`; `.ico` continua em `dervs.ico` na raiz |
| Favicon da janela | PNG do mesmo mestre | 32×32 | reusa o PNG de 32px acima |
| Ícone de bandeja | SVG simplificado → PNG | 16×16, 32×32 | `assets/icone-bandeja.svg` → `electron/assets/bandeja-16.png`, `bandeja-32.png` |
| Ícone de erro/aviso | SVG inline (ou arquivo texto) | `viewBox 0 0 48 48`, escalável | inline no componente da tela 4; opcional `assets/icone-erro.svg` |
| Grade de fundo | CSS (linear-gradient repetido) | — | já especificada em `design.md`, sem asset de imagem |

Nenhum destes tem origem externa a creditar — são formas geométricas
descritas por código. O que tem origem externa e precisa de crédito são as
duas fontes tipográficas (agora Orbitron e Share Tech Mono); ver
`assets/CREDITOS.md`, que precisa da mesma atualização de nome de fonte —
ver nota na fase 5.
