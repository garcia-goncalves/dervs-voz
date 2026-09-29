// Processo principal do DERVS-Electron.
//
// Este processo é só casca: janela e bandeja. Todo o cérebro (STT, plano,
// trilhos de risco, execução) continua no processo Python-pai, que sobe este
// Electron como filho (dervs_ponte_electron.py). Electron → Python vai pelo
// stdout (uma linha de JSON por vez). Python → Electron vai por um SOQUETE
// TCP local (só 127.0.0.1, porta recebida como último argumento de linha de
// comando), NÃO pelo stdin.
//
// Por quê: um app Electron (sem console, como todo app gráfico do Windows)
// recebe um "fim de stdin" FALSO quase na hora, mesmo com o processo pai
// vivo e escrevendo — limitação do Chromium/Electron no Windows, confirmada
// em bancada em 17/09/2026 (ver o cabeçalho de dervs_ponte_electron.py para
// o teste que provou isso). Depois desse "fim falso" o stdin também para de
// entregar dado novo — não dá pra só ignorar o evento e seguir lendo.
//
// O contrato completo (os verbos, os campos) está em
// docs/superpowers/plans/dervs-cara-nova.md, seção "Contrato compartilhado".
//
// REGRA DURA: nada além dos verbos do contrato pode ir para o stdout —
// console.log é PROIBIDO neste processo porque sujaria o canal que carrega o
// protocolo. Diagnóstico só com console.error (vai para o stderr, que o
// Python relê e reescreve com prefixo "electron:").

const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, screen, shell, globalShortcut } = require("electron");
const path = require("path");
const net = require("net");
const readline = require("readline");

// URL do outro projeto do dono ("DERVS App", garcia-goncalves/dervs) que o
// botão "Abrir DERVS App" do HUD abre no navegador — nunca navegado DENTRO
// desta janela (CSP do renderer já proíbe isso, ver index.html). Chega por
// variável de ambiente, passada pelo processo Python pai (dervs_electron.py,
// que lê de dervs_config.py) — não por argumento de linha de comando, para
// não colidir com a convenção de "porta é sempre o último argv" (ver
// ligarCanalDoPython, abaixo).
const URL_DERVS_APP_PADRAO = "http://localhost:4777";
function urlDoDervsApp() {
  const v = process.env.DERVS_APP_URL;
  return typeof v === "string" && (v.startsWith("http://") || v.startsWith("https://"))
    ? v : URL_DERVS_APP_PADRAO;
}

const LIMITE_LINHA = 64 * 1024; // mesmo espírito do _LIMITE_LINHA de dervs_instancia.py

let janela = null;       // o widget compacto (420x700)
let painel = null;       // a janela grande (JARVIS), criada na primeira abertura
let bandeja = null;
let widgetEstavaVisivel = true;
let painelAmpliado = false;
let painelAntes = null;  // bounds antes de "ocupar a tela"
let arrastoAlca = null;  // { x, y, largura, altura } no começo do arrasto

// Últimas mensagens do Python, guardadas para a janela grande (criada sob
// demanda) nascer já com tudo preenchido, sem esperar a próxima leitura.
const ultimosPorCanal = new Map();   // canal -> último dado (só canais "de estado")
const CANAIS_DE_ESTADO = new Set([
  "dervs:estado", "dervs:microfone", "dervs:sistema", "dervs:diario", "dervs:reuniao",
  "dervs:agenda", "dervs:diario-entradas", "dervs:gasto", "dervs:voz"]);
const historicoFalas = [];           // últimas falas da conversa
const historicoAcoes = [];           // últimas ações
const MAX_HISTORICO = 30;

function janelaViva(j) {
  return j && !j.isDestroyed() && !j.webContents.isDestroyed();
}

// Manda o mesmo evento ao widget e ao painel grande (se existir).
function difundir(canal, dado) {
  if (CANAIS_DE_ESTADO.has(canal)) ultimosPorCanal.set(canal, dado);
  if (canal === "dervs:fala") {
    historicoFalas.push(dado);
    if (historicoFalas.length > MAX_HISTORICO) historicoFalas.shift();
  } else if (canal === "dervs:acao") {
    historicoAcoes.push(dado);
    if (historicoAcoes.length > MAX_HISTORICO) historicoAcoes.shift();
  }
  if (janelaViva(janela)) janela.webContents.send(canal, dado);
  if (janelaViva(painel)) painel.webContents.send(canal, dado);
}

const TOOLTIPS = {
  ocioso: "DERVS",
  ouvindo: "DERVS — ouvindo você",
  pensando: "DERVS — pensando",
  falando: "DERVS — respondendo",
  erro: "DERVS — precisa de atenção",
};

function enviarAoPython(objeto) {
  // Único canal de saída: uma linha de JSON terminada em \n no stdout.
  process.stdout.write(JSON.stringify(objeto) + "\n");
}

// Onde o widget nasce: ancorado no canto superior direito da tela principal,
// como os HUDs de referência do dono (Rainmeter/JARVIS) — nunca centralizado,
// para não competir com a janela em que ele está trabalhando (design.md,
// "contradicoes_resolvidas" da esteira dervs-painel-completo).
const LARGURA = 420;
const ALTURA = 700; // 560 → 620 (botão do microfone) → 700 (23/09: cartão do diário + cartão de erro visível ao mesmo tempo cortavam o rodapé)
const MARGEM_CANTO = 24;

function posicaoDeCanto() {
  const area = screen.getPrimaryDisplay().workArea;
  return {
    x: area.x + area.width - LARGURA - MARGEM_CANTO,
    y: area.y + MARGEM_CANTO,
  };
}

function criarJanela() {
  const { x, y } = posicaoDeCanto();
  janela = new BrowserWindow({
    width: LARGURA,
    height: ALTURA,
    x,
    y,
    minWidth: 360,
    frame: false,
    // Fundo de vidro: transparente de verdade (não um cinza escuro) — o
    // desktop atrás da janela aparece por baixo do tom ciano translúcido do
    // CSS (estilo.css, --vidro-bg). TESTADO em bancada em 17/09/2026: NÃO
    // ligar `backgroundMaterial: "acrylic"` aqui — nesta versão do Electron
    // (33.2.1) ele CONFLITA com `transparent: true` e a janela volta a
    // ficar opaca de verdade (comprovado com um teste de cor: um fundo
    // vermelho a 30% de opacidade apareceu SÓLIDO com os dois juntos, e
    // translúcido de verdade sem `backgroundMaterial`). Sem ele, sobra
    // "vidro liso" (sem borrão do que está atrás) em vez de "vidro fosco"
    // — aceitável: o pedido do dono era "transparente/espelhado", que isto
    // cumpre; o borrão de verdade fica para quando o Electron tratar bem
    // essa combinação (ver GitHub electron/electron#38532).
    transparent: true,
    backgroundColor: "#00000000",
    // Sempre visível por cima de outras janelas — resolve o "sumiço atrás
    // do VS Code/navegador" que fazia o dono achar o DERVS morto. Nível
    // "screen-saver" fica acima até de outras janelas alwaysOnTop comuns,
    // igual a um widget de desktop de verdade.
    alwaysOnTop: true,
    show: false,
    icon: path.join(__dirname, "assets", "bandeja-32.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  janela.setAlwaysOnTop(true, "screen-saver");
  // Aparece em todo espaço de trabalho do Windows (não só o de quando abriu)
  // — mesmo espírito do alwaysOnTop: um widget não deveria sumir ao trocar
  // de área de trabalho virtual.
  janela.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  janela.loadFile(path.join(__dirname, "renderer", "index.html"));

  // O conteúdo é local e é hostil por definição (transcrição, resposta do
  // cérebro): nada de abrir janela nova nem navegar para fora.
  janela.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  janela.webContents.on("will-navigate", (evento) => {
    evento.preventDefault();
  });

  janela.webContents.on("did-finish-load", () => {
    enviarAoPython({ verbo: "pronto" });
  });

  // A janela é um widget sem moldura: nada a minimiza de propósito, e uma
  // janela presa minimizada (posição -32000,-32000) some sem deixar rastro —
  // o "DERVS sumiu". Quem minimiza (Win+D, Mostrar Área de Trabalho) é
  // desfeito na hora; esconder de propósito é o atalho global ou o X.
  janela.on("minimize", () => {
    setImmediate(() => {
      if (janela && !janela.isDestroyed() && janela.isMinimized()) {
        janela.restore();
        janela.showInactive();
      }
    });
  });

  janela.once("ready-to-show", () => {
    janela.show();
  });

  // Fechar a janela (X, Alt+F4) só esconde — espelho de dervs.py:1487-1488
  // (closeEvent: e.ignore(); self.hide()). O DERVS continua vivo na bandeja.
  janela.on("close", (evento) => {
    if (!app.isQuitting) {
      evento.preventDefault();
      janela.hide();
    }
  });

  return janela;
}

function mostrarJanela() {
  if (!janela) return;
  if (janela.isMinimized()) janela.restore();
  janela.show();
  janela.focus();
}

// Atalho global Ctrl+Alt+D: visível e não minimizada → esconde; senão traz
// de volta e foca.
// Ctrl+Alt+D alterna o PAINEL GRANDE (janela JARVIS). O widget compacto passa a
// ter o seu próprio atalho, Ctrl+Alt+Shift+D, e continua na bandeja/menu.
const ATALHO_GLOBAL = "Control+Alt+D";
const ATALHO_WIDGET = "Control+Alt+Shift+D";

function alternarJanela() {
  if (!janela) return;
  if (janela.isVisible() && !janela.isMinimized()) {
    janela.hide();
  } else {
    mostrarJanela();
  }
}

function registrarAtalhoGlobal() {
  for (const [atalho, acao] of [[ATALHO_GLOBAL, alternarPainel], [ATALHO_WIDGET, alternarJanela]]) {
    try {
      if (!globalShortcut.register(atalho, acao)) {
        console.error(`electron: atalho ${atalho} já é de outro programa, sem atalho global`);
      }
    } catch (erro) {
      console.error(`electron: não consegui registrar ${atalho}: ${erro.message}`);
    }
  }
}

// ---- painel grande (JARVIS) -----------------------------------------------
// Janela própria, frameless e translúcida como o widget, mas NÃO fica por cima
// de tudo (é uma tela de trabalho, não um adorno). Fechar só esconde. Enquanto
// está aberta, o widget some (senão ele taparia o canto do painel) e volta
// quando o painel fecha, se estava visível.

const PAINEL_LARGURA = 1280;
const PAINEL_ALTURA = 800;

function criarPainel() {
  const area = screen.getPrimaryDisplay().workArea;
  const largura = Math.min(PAINEL_LARGURA, area.width);
  const altura = Math.min(PAINEL_ALTURA, area.height);
  painel = new BrowserWindow({
    width: largura,
    height: altura,
    x: area.x + Math.round((area.width - largura) / 2),
    y: area.y + Math.round((area.height - altura) / 2),
    minWidth: 960,
    minHeight: 620,
    frame: false,
    transparent: true,           // vidro, como o widget (sem backgroundMaterial: ver criarJanela)
    backgroundColor: "#00000000",
    show: false,
    title: "DERVS Painel",
    icon: path.join(__dirname, "assets", "bandeja-32.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  painel.loadFile(path.join(__dirname, "renderer", "painel.html"));
  painel.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  painel.webContents.on("will-navigate", (evento) => { evento.preventDefault(); });

  // Nasce já preenchido: repete o último valor de cada canal de estado e o
  // histórico de conversa/ações que o widget também recebeu.
  painel.webContents.on("did-finish-load", () => {
    if (!janelaViva(painel)) return;
    for (const [canal, dado] of ultimosPorCanal) painel.webContents.send(canal, dado);
    for (const f of historicoFalas) painel.webContents.send("dervs:fala", f);
    for (const a of historicoAcoes) painel.webContents.send("dervs:acao", a);
  });

  painel.on("close", (evento) => {
    if (!app.isQuitting) {
      evento.preventDefault();
      esconderPainel();
    }
  });
  painel.on("minimize", () => {
    setImmediate(() => { if (janelaViva(painel) && painel.isMinimized()) painel.restore(); });
  });
  return painel;
}

function painelVisivel() {
  return janelaViva(painel) && painel.isVisible() && !painel.isMinimized();
}

function mostrarPainel() {
  if (!painel || painel.isDestroyed()) criarPainel();
  if (janelaViva(janela)) {
    // só lembra o estado do widget ANTES de o painel estar na tela: abrir o painel
    // de novo (pela bandeja) com ele já aberto gravava "escondido" e o widget
    // não voltava ao fechar.
    if (!painelVisivel()) widgetEstavaVisivel = janela.isVisible();
    if (janela.isVisible()) janela.hide();
  }
  if (painel.isMinimized()) painel.restore();
  painel.show();
  painel.focus();
}

function esconderPainel() {
  if (!janelaViva(painel)) return;
  painel.hide();
  if (janelaViva(janela) && widgetEstavaVisivel) janela.showInactive();
}

function alternarPainel() {
  if (painelVisivel()) esconderPainel();
  else mostrarPainel();
}

// "Ocupar a tela / voltar": a janela é transparente, então o maximize do
// Windows não é confiável — troca os limites à mão.
function ampliarPainel() {
  if (!janelaViva(painel)) return;
  if (!painelAmpliado) {
    painelAntes = painel.getBounds();
    const area = screen.getDisplayMatching(painelAntes).workArea;
    painel.setBounds(area);
    painelAmpliado = true;
  } else {
    if (painelAntes) painel.setBounds(painelAntes);
    painelAmpliado = false;
  }
}

function redimensionarPainel(dado) {
  if (!janelaViva(painel) || !dado || !Number.isFinite(dado.x) || !Number.isFinite(dado.y)) return;
  if (dado.fase === "inicio") {
    const b = painel.getBounds();
    arrastoAlca = { x: dado.x, y: dado.y, largura: b.width, altura: b.height };
  } else if (dado.fase === "mover" && arrastoAlca) {
    const b = painel.getBounds();
    const [minL, minA] = painel.getMinimumSize();
    painel.setBounds({
      x: b.x, y: b.y,
      width: Math.max(minL, Math.round(arrastoAlca.largura + dado.x - arrastoAlca.x)),
      height: Math.max(minA, Math.round(arrastoAlca.altura + dado.y - arrastoAlca.y)),
    });
    painelAmpliado = false;
  }
}

function recolherJanela() {
  if (!janela) return;
  janela.hide();
}

function sairDoDervs() {
  // Avisa o Python e dá 3s para ele encerrar tudo (encerrar_tudo, posse.soltar
  // etc.) e fechar este stdin — o que já dispara app.quit() no listener de
  // stdin abaixo. Só nos autoencerramos se isso não acontecer.
  enviarAoPython({ verbo: "sair" });
  setTimeout(() => {
    if (!app.isQuitting) {
      app.isQuitting = true;
      app.quit();
    }
  }, 3000);
}

function montarBandeja() {
  const icone = nativeImage.createFromPath(path.join(__dirname, "assets", "bandeja-16.png"));
  bandeja = new Tray(icone);
  bandeja.setToolTip(TOOLTIPS.ocioso);

  const menu = Menu.buildFromTemplate([
    { label: "Abrir painel grande", click: mostrarPainel },
    { label: "Abrir DERVS (widget)", click: mostrarJanela },
    { label: "Recolher janela", click: recolherJanela },
    { label: "Sair do DERVS", click: sairDoDervs },
  ]);
  bandeja.setContextMenu(menu);
  bandeja.on("click", mostrarJanela);
}

function atualizarTooltip(valor) {
  if (!bandeja) return;
  bandeja.setToolTip(TOOLTIPS[valor] || TOOLTIPS.ocioso);
}

function tratarLinhaDoPython(linha) {
  if (!linha) return;
  if (Buffer.byteLength(linha, "utf8") > LIMITE_LINHA) {
    console.error("electron: linha do Python maior que 64 KiB, descartada");
    return;
  }

  let mensagem;
  try {
    mensagem = JSON.parse(linha);
  } catch (erro) {
    console.error(`electron: linha que não é JSON válido, ignorada: ${erro.message}`);
    return;
  }

  const verbo = mensagem && mensagem.verbo;
  if (!janela) {
    console.error(`electron: verbo "${verbo}" chegou antes da janela existir, ignorado`);
    return;
  }

  switch (verbo) {
    case "estado":
      if (typeof mensagem.valor !== "string") {
        console.error("electron: verbo estado sem campo valor, ignorado");
        return;
      }
      atualizarTooltip(mensagem.valor);
      difundir("dervs:estado", {
        valor: mensagem.valor,
        texto: mensagem.texto || "",
        apoio: mensagem.apoio || "",
      });
      break;
    case "volume":
      if (typeof mensagem.valor !== "number") {
        console.error("electron: verbo volume sem campo valor numérico, ignorado");
        return;
      }
      difundir("dervs:volume", mensagem.valor);
      break;
    case "fala":
      if (typeof mensagem.papel !== "string" || typeof mensagem.texto !== "string") {
        console.error("electron: verbo fala com campo faltando, ignorado");
        return;
      }
      difundir("dervs:fala", { papel: mensagem.papel, texto: mensagem.texto });
      break;
    case "plano":
      difundir("dervs:plano", {
        passos: Array.isArray(mensagem.passos) ? mensagem.passos : [],
        nivel: mensagem.nivel || "reversivel",
        pergunta: mensagem.pergunta || "",
        // `cartao_id` é extensão do protocolo (correção de concorrência,
        // ver dervs_ponte_electron.py) — repassado como veio, `null` quando
        // ausente (cartão que não espera resposta, ex.: lista vazia).
        cartaoId: "cartao_id" in mensagem ? mensagem.cartao_id : null,
      });
      // O cartão de plano (confirmar/cancelar) mora no widget. Com o painel
      // grande aberto o widget está escondido: traz ele de volta, sem roubar
      // o foco, para o pedido de confirmação nunca ficar invisível.
      if (Array.isArray(mensagem.passos) && mensagem.passos.length > 0
          && painelVisivel() && janelaViva(janela) && !janela.isVisible()) {
        janela.showInactive();
      }
      break;
    case "mostrar":
      // Traz a janela para frente; substitui o Ponte.chegou do Qt. Não passa
      // pelo renderer — é ação do processo principal sobre a janela.
      mostrarJanela();
      break;
    case "sistema":
      // Extensão do protocolo (fase 1 da esteira dervs-painel-completo):
      // CPU/RAM/disco reais, mandados por dervs_sistema.py a cada ~2s.
      // Campo faltando ou não numérico: ignora a mensagem inteira (nunca
      // manda dado pela metade para o painel desenhar).
      if (["cpu", "ram", "disco_livre_gb", "disco_total_gb"].every(
        (campo) => typeof mensagem[campo] === "number")) {
        difundir("dervs:sistema", {
          cpu: mensagem.cpu,
          ram: mensagem.ram,
          discoLivreGb: mensagem.disco_livre_gb,
          discoTotalGb: mensagem.disco_total_gb,
          // Rede (KB/s): opcional; só vale se AMBOS forem numéricos.
          redeBaixaKbs: typeof mensagem.rede_baixa_kbs === "number" && typeof mensagem.rede_sobe_kbs === "number"
            ? mensagem.rede_baixa_kbs : null,
          redeSobeKbs: typeof mensagem.rede_baixa_kbs === "number" && typeof mensagem.rede_sobe_kbs === "number"
            ? mensagem.rede_sobe_kbs : null,
        });
      } else {
        console.error("electron: verbo sistema com campo faltando/invalido, ignorado");
      }
      break;
    case "microfone":
      // A escuta abriu ou fechou (Python é o dono do microfone — o HUD só
      // reflete). Só o booleano de verdade vale.
      if (typeof mensagem.ligado !== "boolean") {
        console.error("electron: verbo microfone sem campo ligado booleano, ignorado");
        return;
      }
      difundir("dervs:microfone", { ligado: mensagem.ligado });
      break;
    case "diario":
      // Cartão do diário do porteiro: só dois inteiros, nunca texto.
      if (Number.isInteger(mensagem.ouvidas) && Number.isInteger(mensagem.acordou)) {
        difundir("dervs:diario", {
          ouvidas: mensagem.ouvidas, acordou: mensagem.acordou });
      } else {
        console.error("electron: verbo diario com campo faltando/invalido, ignorado");
      }
      break;
    case "reuniao":
      // Segundos que faltam do modo reunião (inteiro) ou null (sem reunião).
      if (mensagem.restante_s === null
          || (Number.isInteger(mensagem.restante_s) && mensagem.restante_s >= 0)) {
        difundir("dervs:reuniao", { restanteS: mensagem.restante_s });
      } else {
        console.error("electron: verbo reuniao com restante_s invalido, ignorado");
      }
      break;
    case "gasto":
      // Gasto ESTIMADO do dia em dólar (painel grande). Só números finitos.
      if (["total", "tts", "stt", "cerebro"].every((c) => Number.isFinite(mensagem[c]))) {
        difundir("dervs:gasto", {
          total: mensagem.total, tts: mensagem.tts, stt: mensagem.stt, cerebro: mensagem.cerebro });
      } else {
        console.error("electron: verbo gasto com campo faltando/invalido, ignorado");
      }
      break;
    case "agenda":
      if (Array.isArray(mensagem.itens)) {
        difundir("dervs:agenda", { itens: mensagem.itens.slice(0, 50).map((i) => ({
          quando: String((i && i.quando) || ""),
          quando_txt: String((i && i.quando_txt) || ""),
          texto: String((i && i.texto) || "") })) });
      } else {
        console.error("electron: verbo agenda sem lista de itens, ignorado");
      }
      break;
    case "diario_entradas":
      if (Array.isArray(mensagem.entradas)) {
        difundir("dervs:diario-entradas", { entradas: mensagem.entradas.slice(0, 50).map((e) => ({
          hora: String((e && e.hora) || ""),
          acordou: Boolean(e && e.acordou === true),
          palavras: Number.isInteger(e && e.palavras) ? e.palavras : 0,
          duracao_s: Number.isFinite(e && e.duracao_s) ? e.duracao_s : 0 })) });
      } else {
        console.error("electron: verbo diario_entradas sem lista, ignorado");
      }
      break;
    case "voz":
      if (mensagem.motor === "nuvem" || mensagem.motor === "local") {
        difundir("dervs:voz", { motor: mensagem.motor });
      } else {
        console.error("electron: verbo voz com motor invalido, ignorado");
      }
      break;
    case "acao":
      if (typeof mensagem.texto === "string") {
        difundir("dervs:acao", { papel: String(mensagem.papel || ""), texto: mensagem.texto, ts: Date.now() });
      } else {
        console.error("electron: verbo acao sem texto, ignorado");
      }
      break;
    default:
      console.error(`electron: verbo desconhecido do Python, ignorado: ${String(verbo)}`);
  }
}

function ligarCanalDoPython() {
  // A porta é o ÚLTIMO argumento da linha de comando (o Python sempre manda
  // assim em dervs_ponte_electron.py). Não usar um índice fixo de
  // `process.argv` porque o Electron, rodando "sem empacotar" (apontando
  // para uma pasta), pode inserir o próprio caminho do app em posições
  // diferentes dependendo da versão.
  const porta = Number(process.argv[process.argv.length - 1]);
  if (!Number.isInteger(porta) || porta <= 0) {
    console.error(`electron: porta do soquete do Python inválida: ${process.argv[process.argv.length - 1]}`);
    return;
  }
  const soquete = net.createConnection({ host: "127.0.0.1", port: porta }, () => {
    const rl = readline.createInterface({ input: soquete, terminal: false });
    rl.on("line", tratarLinhaDoPython);
  });
  // O soquete fechar/dar erro significa que o processo pai (Python) morreu
  // — a lição do "neto órfão" (test_dervs_arvore_de_processos.py). Sem
  // isto, o Electron fica vivo sozinho, sem cérebro, para sempre.
  soquete.on("close", () => {
    app.isQuitting = true;
    app.quit();
  });
  soquete.on("error", (erro) => {
    console.error(`electron: soquete com o Python deu erro: ${erro.message}`);
  });
}

// Resposta do cartão de plano vinda do renderer (via preload/contextBridge).
// `dado` é `{ resposta, autorizado, cartaoId }` (preload.js atual); aceita
// também uma string solta por compatibilidade com um preload mais velho.
ipcMain.on("dervs:responder-plano", (_evento, dado) => {
  const resposta = dado && typeof dado === "object" ? dado.resposta : dado;
  const autorizado = Boolean(dado && typeof dado === "object" && dado.autorizado);
  const cartaoId = dado && typeof dado === "object" && "cartaoId" in dado
    ? dado.cartaoId : null;
  if (resposta !== "confirmar" && resposta !== "cancelar") {
    console.error(`electron: resposta de plano inválida, ignorada: ${String(resposta)}`);
    return;
  }
  enviarAoPython({ verbo: "plano", resposta, autorizado, cartao_id: cartaoId });
});

// Botão liga/desliga do microfone: só PEDE — quem abre ou fecha o microfone
// é o Python (o Electron nunca captura áudio, ver dervs_nivel.py). O botão só
// muda de cara quando o Python responde com o verbo `microfone`.
ipcMain.on("dervs:alternar-microfone", (_evento, ligar) => {
  if (typeof ligar !== "boolean") {
    console.error(`electron: pedido de microfone inválido, ignorado: ${String(ligar)}`);
    return;
  }
  enviarAoPython({ verbo: "microfone", ligar });
});

// Botão "Reunião 1h": só PEDE — o temporizador e o microfone são do Python.
// Booleano estrito, como o do microfone.
ipcMain.on("dervs:alternar-reuniao", (_evento, ligar) => {
  if (typeof ligar !== "boolean") {
    console.error(`electron: pedido de reunião inválido, ignorado: ${String(ligar)}`);
    return;
  }
  enviarAoPython({ verbo: "reuniao", ligar });
});

// Botão "Abrir DERVS App" do HUD — só ABRE a URL no navegador padrão do
// dono, nunca navega dentro desta janela (fase 1 da esteira
// dervs-painel-completo; a integração de verdade com o outro projeto é fase
// 2, combinada à parte). `shell.openExternal` é o único jeito seguro: o
// renderer não tem `require`, rede nem `window.open` (CSP + contextIsolation
// + setWindowOpenHandler já bloqueiam isso).
ipcMain.on("dervs:abrir-app-dervs", () => {
  shell.openExternal(urlDoDervsApp());
});

// Painel grande: os botões da janela só PEDEM; quem mexe na janela é este processo.
ipcMain.on("dervs:alternar-painel", alternarPainel);
ipcMain.on("dervs:painel-esconder", esconderPainel);
ipcMain.on("dervs:painel-ampliar", ampliarPainel);
ipcMain.on("dervs:painel-redimensionar", (_evento, dado) => redimensionarPainel(dado));

app.whenReady().then(() => {
  criarJanela();
  montarBandeja();
  registrarAtalhoGlobal();
  ligarCanalDoPython();
});

// Sair solta o atalho global — senão a combinação fica presa até o Windows
// perceber que o dono morreu.
app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

// window-all-closed NÃO encerra o app — de propósito, não é o padrão do
// framework. A janela só se esconde (ver o handler de "close" acima); quem
// encerra de fato é "Sair do DERVS" na bandeja ou o pai morrendo (stdin
// fechado).
app.on("window-all-closed", () => {
  // Intencionalmente vazio.
});
