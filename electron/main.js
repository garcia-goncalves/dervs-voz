// Processo principal do DERVS-Electron.
//
// Este processo é só casca: janela e bandeja. Todo o cérebro (STT, plano,
// trilhos de risco, execução) continua no processo Python-pai, que sobe este
// Electron como filho (dervs_ponte_electron.py). A ponte entre os dois é uma
// linha de JSON por vez: Python → Electron pelo stdin, Electron → Python pelo
// stdout. O contrato completo está em
// docs/superpowers/plans/dervs-cara-nova.md, seção "Contrato compartilhado".
//
// REGRA DURA: nada além dos verbos do contrato pode ir para o stdout —
// console.log é PROIBIDO neste processo porque sujaria o canal que carrega o
// protocolo. Diagnóstico só com console.error (vai para o stderr, que o
// Python relê e reescreve com prefixo "electron:").

const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain } = require("electron");
const path = require("path");
const readline = require("readline");

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

function criarJanela() {
  janela = new BrowserWindow({
    width: 420,
    height: 560,
    minWidth: 360,
    frame: false,
    backgroundColor: "#050810",
    show: false,
    icon: path.join(__dirname, "assets", "bandeja-32.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

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
    default:
      console.error(`electron: verbo desconhecido do Python, ignorado: ${String(verbo)}`);
  }
}

function ligarStdin() {
  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  rl.on("line", tratarLinhaDoPython);
  // stdin fechado significa que o processo pai (Python) morreu — a lição do
  // "neto órfão" (test_dervs_arvore_de_processos.py). Sem isto, o Electron
  // fica vivo sozinho, sem cérebro, para sempre.
  process.stdin.on("end", () => {
    app.isQuitting = true;
    app.quit();
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

app.whenReady().then(() => {
  criarJanela();
  montarBandeja();
  ligarStdin();
});

// window-all-closed NÃO encerra o app — de propósito, não é o padrão do
// framework. A janela só se esconde (ver o handler de "close" acima); quem
// encerra de fato é "Sair do DERVS" na bandeja ou o pai morrendo (stdin
// fechado).
app.on("window-all-closed", () => {
  // Intencionalmente vazio.
});
