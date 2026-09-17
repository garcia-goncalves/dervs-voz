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

const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, screen, shell } = require("electron");
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

let janela = null;
let bandeja = null;

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
const ALTURA = 560;
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
    { label: "Abrir DERVS", click: mostrarJanela },
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
      janela.webContents.send("dervs:estado", {
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
      janela.webContents.send("dervs:volume", mensagem.valor);
      break;
    case "fala":
      if (typeof mensagem.papel !== "string" || typeof mensagem.texto !== "string") {
        console.error("electron: verbo fala com campo faltando, ignorado");
        return;
      }
      janela.webContents.send("dervs:fala", { papel: mensagem.papel, texto: mensagem.texto });
      break;
    case "plano":
      janela.webContents.send("dervs:plano", {
        passos: Array.isArray(mensagem.passos) ? mensagem.passos : [],
        nivel: mensagem.nivel || "reversivel",
        pergunta: mensagem.pergunta || "",
        // `cartao_id` é extensão do protocolo (correção de concorrência,
        // ver dervs_ponte_electron.py) — repassado como veio, `null` quando
        // ausente (cartão que não espera resposta, ex.: lista vazia).
        cartaoId: "cartao_id" in mensagem ? mensagem.cartao_id : null,
      });
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
        janela.webContents.send("dervs:sistema", {
          cpu: mensagem.cpu,
          ram: mensagem.ram,
          discoLivreGb: mensagem.disco_livre_gb,
          discoTotalGb: mensagem.disco_total_gb,
        });
      } else {
        console.error("electron: verbo sistema com campo faltando/invalido, ignorado");
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

// Botão "Abrir DERVS App" do HUD — só ABRE a URL no navegador padrão do
// dono, nunca navega dentro desta janela (fase 1 da esteira
// dervs-painel-completo; a integração de verdade com o outro projeto é fase
// 2, combinada à parte). `shell.openExternal` é o único jeito seguro: o
// renderer não tem `require`, rede nem `window.open` (CSP + contextIsolation
// + setWindowOpenHandler já bloqueiam isso).
ipcMain.on("dervs:abrir-app-dervs", () => {
  shell.openExternal(urlDoDervsApp());
});

app.whenReady().then(() => {
  criarJanela();
  montarBandeja();
  ligarCanalDoPython();
});

// window-all-closed NÃO encerra o app — de propósito, não é o padrão do
// framework. A janela só se esconde (ver o handler de "close" acima); quem
// encerra de fato é "Sair do DERVS" na bandeja ou o pai morrendo (stdin
// fechado).
app.on("window-all-closed", () => {
  // Intencionalmente vazio.
});
