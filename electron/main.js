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
const { decidirJanela } = require("./janela-estado.js");
const net = require("net");
const readline = require("readline");

// URL do outro projeto do dono ("DERVS App", garcia-goncalves/dervs) que o
// botão "Abrir DERVS App" do painel abre no navegador — nunca navegado DENTRO
// desta janela (CSP do renderer já proíbe isso, ver painel.html). Chega por
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

let painel = null;       // a janela única do DERVS (JARVIS)
let bandeja = null;
let painelAmpliado = false;
let painelAntes = null;  // bounds antes de "ocupar a tela"
let arrastoAlca = null;  // { x, y, largura, altura } no começo do arrasto

// Últimas mensagens do Python, guardadas para a janela grande (criada sob
// demanda) nascer já com tudo preenchido, sem esperar a próxima leitura.
const ultimosPorCanal = new Map();   // canal -> último dado (só canais "de estado")
const CANAIS_DE_ESTADO = new Set([
  "dervs:estado", "dervs:microfone", "dervs:modo-escuta", "dervs:sistema", "dervs:diario", "dervs:reuniao",
  "dervs:agenda", "dervs:diario-entradas", "dervs:gasto", "dervs:voz", "dervs:cofre",
  "dervs:plano"]);   // reload do painel com cartão pendente repõe o cartão
const MODOS_DE_ESCUTA = new Set(["desligado", "atalho", "voz"]);
let pastaDoCofre = null;             // pasta do cofre de notas, só neste processo (verbo "cofre")
const historicoFalas = [];           // últimas falas da conversa
const historicoAcoes = [];           // últimas ações
const MAX_HISTORICO = 30;

function janelaViva(j) {
  return j && !j.isDestroyed() && !j.webContents.isDestroyed();
}

// Manda o evento ao painel (se existir).
function difundir(canal, dado) {
  if (CANAIS_DE_ESTADO.has(canal)) ultimosPorCanal.set(canal, dado);
  if (canal === "dervs:fala") {
    historicoFalas.push(dado);
    if (historicoFalas.length > MAX_HISTORICO) historicoFalas.shift();
  } else if (canal === "dervs:acao") {
    historicoAcoes.push(dado);
    if (historicoAcoes.length > MAX_HISTORICO) historicoAcoes.shift();
  }
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

// Atalho global Ctrl+Alt+D: alterna o painel (esconde se está à vista, senão
// traz de volta e foca). É o único atalho do DERVS.
const ATALHO_GLOBAL = "Control+Alt+D";

function registrarAtalhoGlobal() {
  try {
    if (!globalShortcut.register(ATALHO_GLOBAL, alternarPainel)) {
      console.error(`electron: atalho ${ATALHO_GLOBAL} já é de outro programa, sem atalho global`);
    }
  } catch (erro) {
    console.error(`electron: não consegui registrar ${ATALHO_GLOBAL}: ${erro.message}`);
  }
}

// ---- painel único (JARVIS) ------------------------------------------------
// A única janela do DERVS: frameless e translúcida, NÃO fica por cima de tudo
// (é uma tela de trabalho, não um adorno). Fechar só esconde (vai para a
// bandeja); minimizar minimiza de verdade. A lógica de abrir/esconder/minimizar
// é a função pura de janela-estado.js (com teste em Node).

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
    // Vidro: transparente de verdade. NÃO ligar `backgroundMaterial: "acrylic"`
    // junto — conflita com `transparent: true` e a janela volta a ficar opaca
    // (testado em bancada em 17/09/2026; GitHub electron/electron#38532).
    transparent: true,
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
  // O conteúdo é local e é hostil por definição (transcrição, resposta do
  // cérebro): nada de abrir janela nova nem navegar para fora.
  painel.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  painel.webContents.on("will-navigate", (evento) => { evento.preventDefault(); });

  // Nasce já preenchido: repete o último valor de cada canal de estado e o
  // histórico de conversa/ações. O verbo `pronto` avisa o Python de que o
  // renderer existe (era do widget; agora é do painel).
  painel.webContents.on("did-finish-load", () => {
    if (!janelaViva(painel)) return;
    for (const [canal, dado] of ultimosPorCanal) painel.webContents.send(canal, dado);
    for (const f of historicoFalas) painel.webContents.send("dervs:fala", f);
    for (const a of historicoAcoes) painel.webContents.send("dervs:acao", a);
    enviarAoPython({ verbo: "pronto" });
  });

  // Fechar (X, Alt+F4) só esconde — o DERVS continua vivo na bandeja.
  painel.on("close", (evento) => {
    if (executarAcao(decidirJanela(estadoDoPainel(), "fechar")) === "esconder") {
      evento.preventDefault();
    }
  });
  return painel;
}

function estadoDoPainel() {
  const viva = janelaViva(painel);
  return {
    existe: viva,
    visivel: viva && painel.isVisible(),
    minimizada: viva && painel.isMinimized(),
    saindo: Boolean(app.isQuitting),
  };
}

// Executa a ação decidida por decidirJanela; devolve a ação (para quem precisa
// saber se deve segurar o evento "close").
function executarAcao(acao) {
  switch (acao) {
    case "criar-e-mostrar":
      criarPainel();
      // fallthrough
    case "mostrar":
      if (painel.isMinimized()) painel.restore();
      painel.show();
      painel.focus();
      break;
    case "esconder":
      painel.hide();
      break;
    case "minimizar":
      painel.minimize();
      break;
    default:
      break;
  }
  return acao;
}

function mostrarPainel() { executarAcao(decidirJanela(estadoDoPainel(), "mostrar")); }
function esconderPainel() { executarAcao(decidirJanela(estadoDoPainel(), "esconder")); }
function minimizarPainel() { executarAcao(decidirJanela(estadoDoPainel(), "minimizar")); }
function alternarPainel() { executarAcao(decidirJanela(estadoDoPainel(), "alternar")); }

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
    { label: "Abrir DERVS", click: mostrarPainel },
    { label: "Sair do DERVS", click: sairDoDervs },
  ]);
  bandeja.setContextMenu(menu);
  bandeja.on("click", alternarPainel);
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
  if (!painel) {
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
      // O cartão de plano (confirmar/cancelar) mora no painel: traz o painel
      // para frente para o pedido de confirmação nunca ficar invisível.
      if (Array.isArray(mensagem.passos) && mensagem.passos.length > 0) {
        mostrarPainel();
      }
      break;
    case "mostrar":
      // Traz o painel para frente; substitui o Ponte.chegou do Qt. Não passa
      // pelo renderer — é ação do processo principal sobre a janela.
      mostrarPainel();
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
    case "modo_escuta":
      // Modo de escuta atual (Python é o dono): só um dos três textos e, se há
      // desligamento automático correndo, os minutos que faltam (inteiro >= 0).
      if (!MODOS_DE_ESCUTA.has(mensagem.modo)) {
        console.error("electron: verbo modo_escuta com modo invalido, ignorado");
        return;
      }
      difundir("dervs:modo-escuta", {
        modo: mensagem.modo,
        fechaEmMin: Number.isInteger(mensagem.fecha_em_min) && mensagem.fecha_em_min >= 0
          ? mensagem.fecha_em_min : null,
      });
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
    case "cofre":
      // Segundo cérebro: a contagem vai para a tela; a PASTA fica só aqui (o botão "abrir"
      // pede, este processo abre). Pasta vem do Python (lado confiável), mas é conferida.
      if (Number.isInteger(mensagem.notas) && mensagem.notas >= 0
          && typeof mensagem.pasta === "string" && mensagem.pasta.length > 0 && mensagem.pasta.length <= 500) {
        pastaDoCofre = mensagem.pasta;
        difundir("dervs:cofre", { notas: mensagem.notas });
      } else {
        console.error("electron: verbo cofre com campo faltando/invalido, ignorado");
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
    case "claude_delta":
      // Onda B: pedaço da resposta do Claude Code (texto hostil: só textContent na tela).
      if (typeof mensagem.texto === "string") {
        difundir("dervs:claude-delta", { texto: mensagem.texto });
      } else {
        console.error("electron: verbo claude_delta sem texto, ignorado");
      }
      break;
    case "claude_ferramenta":
      if (typeof mensagem.nome === "string" && typeof mensagem.resumo === "string") {
        difundir("dervs:claude-ferramenta", { nome: mensagem.nome, resumo: mensagem.resumo });
      } else {
        console.error("electron: verbo claude_ferramenta com campo faltando, ignorado");
      }
      break;
    case "claude_pedido":
      // O Claude pede permissão: o pedido mora no painel, então traz o painel
      // para frente — pedido invisível é pedido que estoura em 5 min.
      if (typeof mensagem.id === "string" && mensagem.id
          && typeof mensagem.ferramenta === "string" && typeof mensagem.resumo === "string") {
        difundir("dervs:claude-pedido", {
          id: mensagem.id,
          ferramenta: mensagem.ferramenta,
          resumo: mensagem.resumo,
          entradaCortada: typeof mensagem.entrada_cortada === "string" ? mensagem.entrada_cortada : "",
          escondidos: Number.isInteger(mensagem.escondidos) && mensagem.escondidos > 0 ? mensagem.escondidos : 0,
          rede: mensagem.rede === true,
          nivel: typeof mensagem.nivel === "string" ? mensagem.nivel : "muda_estado",
          expiraS: Number.isFinite(mensagem.expira_s) ? mensagem.expira_s : 300,
        });
        mostrarPainel();
      } else {
        console.error("electron: verbo claude_pedido com campo faltando, ignorado");
      }
      break;
    case "claude_fim":
      if (typeof mensagem.ok === "boolean") {
        difundir("dervs:claude-fim", {
          ok: mensagem.ok,
          custo: Number.isFinite(mensagem.custo) ? mensagem.custo : 0,
          erro: typeof mensagem.erro === "string" ? mensagem.erro : null,
        });
      } else {
        console.error("electron: verbo claude_fim sem ok booleano, ignorado");
      }
      break;
    // Central do PC (onda D): a tela só desenha; todo texto entra por textContent.
    case "central":
      if (Array.isArray(mensagem.resumo)) {
        const { verbo: _v, ...visao } = mensagem;
        difundir("dervs:central", visao);
      } else {
        console.error("electron: verbo central sem resumo, ignorado");
      }
      break;
    case "central_progresso":
      if (typeof mensagem.coletor === "string" && Number.isInteger(mensagem.feitos)
          && Number.isInteger(mensagem.total)) {
        difundir("dervs:central-progresso", {
          coletor: mensagem.coletor, feitos: mensagem.feitos, total: mensagem.total });
      } else {
        console.error("electron: verbo central_progresso com campo faltando, ignorado");
      }
      break;
    case "central_relatorio":
      if (mensagem.relatorio && typeof mensagem.relatorio === "object"
          && Array.isArray(mensagem.relatorio.itens)) {
        difundir("dervs:central-relatorio", {
          relatorio: mensagem.relatorio,
          cartao: typeof mensagem.cartao === "string" ? mensagem.cartao : null });
        mostrarPainel();
      } else {
        console.error("electron: verbo central_relatorio sem relatorio, ignorado");
      }
      break;
    case "central_resultado":
      if (typeof mensagem.ok === "boolean" && typeof mensagem.motivo === "string") {
        const { verbo: _r, ...resultado } = mensagem;
        difundir("dervs:central-resultado", resultado);
      } else {
        console.error("electron: verbo central_resultado com campo faltando, ignorado");
      }
      break;
    // Tela Integração (cérebro, painel web, terminal SSH): a tela só desenha; todo texto
    // (inclusive a saída de um comando no servidor) entra por textContent.
    case "integracao":
      if (typeof mensagem.parte === "string" && PARTES_INTEGRACAO.has(mensagem.parte)) {
        const { verbo: _i, ...parte } = mensagem;
        difundir("dervs:integracao", parte);
        if (mensagem.parte === "ssh_cartao") mostrarPainel();   // o cartão espera o dono: não pode ficar escondido
      } else {
        console.error("electron: verbo integracao com parte desconhecida, ignorado");
      }
      break;
    // Tela "O que o DERVS pode fazer": a tela só desenha; texto só por textContent.
    case "permissoes":
      if (typeof mensagem.parte === "string" && PARTES_PERMISSOES.has(mensagem.parte)) {
        const { verbo: _pm, ...parte } = mensagem;
        difundir("dervs:permissoes", parte);
      } else {
        console.error("electron: verbo permissoes com parte desconhecida, ignorado");
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
  // Segredo da ponte: 127.0.0.1 é alcançável por qualquer programa da máquina, então
  // o Python só aceita quem abre a conversa com este token (variável de ambiente,
  // nunca argumento). Sem ele, nem conecta: o Python recusaria de qualquer jeito.
  const token = process.env.DERVS_PONTE_TOKEN;
  delete process.env.DERVS_PONTE_TOKEN;   // não herdar para processos filhos
  if (!token) {
    console.error("electron: sem DERVS_PONTE_TOKEN — a ponte com o Python não abre");
    return;
  }
  const soquete = net.createConnection({ host: "127.0.0.1", port: porta }, () => {
    soquete.write(token + "\n");          // primeira linha: o segredo
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
// Logoff/shutdown do Windows não pode ser bloqueado pelo "fechar esconde".
app.on("before-quit", () => { app.isQuitting = true; });

ipcMain.on("dervs:responder-plano", (_evento, dado) => {
  ultimosPorCanal.delete("dervs:plano");   // respondido: reload não reabre o cartão
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

// Seletor de modos de escuta (Desligado / Atalho / Voz): só PEDE — o Python
// decide e responde com o verbo `modo_escuta`. Só os três textos valem.
ipcMain.on("dervs:definir-modo-escuta", (_evento, modo) => {
  if (!MODOS_DE_ESCUTA.has(modo)) {
    console.error(`electron: pedido de modo de escuta inválido, ignorado: ${String(modo)}`);
    return;
  }
  enviarAoPython({ verbo: "modo_escuta", modo });
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

// Botão "Abrir DERVS App" do painel — só ABRE a URL no navegador padrão do
// dono, nunca navega dentro desta janela (fase 1 da esteira
// dervs-painel-completo; a integração de verdade com o outro projeto é fase
// 2, combinada à parte). `shell.openExternal` é o único jeito seguro: o
// renderer não tem `require`, rede nem `window.open` (CSP + contextIsolation
// + setWindowOpenHandler já bloqueiam isso).
ipcMain.on("dervs:abrir-app-dervs", () => {
  shell.openExternal(urlDoDervsApp());
});

// Botão "COFRE": abre a pasta de notas no Explorer. A tela não sabe o caminho nem manda um:
// só pede, e este processo abre o que o Python informou.
ipcMain.on("dervs:abrir-cofre", () => {
  if (pastaDoCofre) shell.openPath(pastaDoCofre);
});

// Claude Code (onda B): a tela só PEDE; o Python valida de novo (não há confiança
// em cascata) e decide. Formato conferido aqui — o que fugir dele nem sai.
const LIMITE_PERGUNTA = 8000;

ipcMain.on("dervs:claude-perguntar", (_evento, texto) => {
  if (typeof texto !== "string" || !texto.trim() || texto.length > LIMITE_PERGUNTA) {
    console.error("electron: pergunta ao Claude inválida (vazia, longa ou não é texto), ignorada");
    return;
  }
  enviarAoPython({ verbo: "claude_perguntar", texto });
});

ipcMain.on("dervs:claude-parar", () => {
  enviarAoPython({ verbo: "claude_parar" });
});

ipcMain.on("dervs:claude-responder", (_evento, dado) => {
  const valido = dado && typeof dado === "object" && typeof dado.id === "string"
    && dado.id && dado.id.length <= 64 && typeof dado.permitir === "boolean";
  if (!valido) {
    console.error("electron: resposta ao pedido do Claude inválida, ignorada");
    return;
  }
  enviarAoPython({
    verbo: "claude_resposta", id: dado.id, permitir: dado.permitir,
    cartao_id: typeof dado.cartaoId === "string" ? dado.cartaoId : null });
});

ipcMain.on("dervs:claude-nova-conversa", () => {
  enviarAoPython({ verbo: "claude_nova_conversa" });
});

// Central do PC (onda D): a tela só PEDE. O clique de aprovar leva o cartão que o
// Python entregou junto do relatório; o motor confere tudo de novo do lado de lá.
const ID_CURTO = /^[A-Za-z0-9_-]{1,64}$/;
const listaDeIds = (v) => Array.isArray(v) && v.length <= 50 && v.every((i) => typeof i === "string" && ID_CURTO.test(i));

for (const [canal, verbo] of [["dervs:central-pedir", "central_pedir"],
    ["dervs:central-analisar", "central_analisar"],
    ["dervs:central-propor-limpeza", "central_propor_limpeza"]]) {
  ipcMain.on(canal, () => { enviarAoPython({ verbo }); });
}

ipcMain.on("dervs:central-aprovar", (_evento, dado) => {
  const valido = dado && typeof dado === "object" && typeof dado.relatorioId === "string"
    && ID_CURTO.test(dado.relatorioId) && typeof dado.cartao === "string"
    && dado.cartao.length > 0 && dado.cartao.length <= 200
    && listaDeIds(dado.ids) && dado.ids.length > 0 && listaDeIds(dado.dupla || []);
  if (!valido) {
    console.error("electron: aprovação da Central inválida, ignorada");
    return;
  }
  enviarAoPython({ verbo: "central_aprovar", relatorio_id: dado.relatorioId, ids: dado.ids,
    cartao: dado.cartao, dupla: dado.dupla || [] });
});

ipcMain.on("dervs:central-desfazer", (_evento, desfazerId) => {
  if (typeof desfazerId !== "string" || !ID_CURTO.test(desfazerId)) {
    console.error("electron: desfazer da Central inválido, ignorado");
    return;
  }
  enviarAoPython({ verbo: "central_desfazer", desfazer_id: desfazerId });
});

ipcMain.on("dervs:central-explicar", (_evento, codigo) => {
  if (typeof codigo !== "string" || !/^[a-z_]{1,40}$/.test(codigo)) {
    console.error("electron: pedido de explicação da Central inválido, ignorado");
    return;
  }
  enviarAoPython({ verbo: "central_explicar", codigo });
});

// Tela Integração: a tela só PEDE; o Python valida de novo e decide. O clique da segunda
// confirmação do SSH leva só o id da proposta: a senha do clique nunca passa por aqui.
const PARTES_INTEGRACAO = new Set(["cerebros", "web", "fila", "avisos", "ssh", "ssh_cartao",
  "ssh_resultado", "ssh_cancelado", "mensagem"]);
const ID_PEDIDO_WEB = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const ID_LOCAL = /^[A-Za-z0-9]{1,40}$/;
const APELIDO_SSH = /^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/;
const LIMITE_COMANDO_SSH = 400;

// Tela de permissões: categoria e nível só das listas fixas, teto só número na faixa.
// O Python valida de novo (dervs_ponte_electron.py e dervs_painel_permissoes.py).
const PARTES_PERMISSOES = new Set(["estado", "mensagem"]);
const CATEGORIAS_PERMISSAO = new Set(["ler", "abrir", "instalar", "alterar_projeto", "apagar",
  "internet", "servidor", "gastar_api"]);
const NIVEIS_PERMISSAO = new Set(["analisa", "pergunta", "sozinho"]);

ipcMain.on("dervs:permissoes-pedir", () => { enviarAoPython({ verbo: "permissoes_pedir" }); });

// Os verbos que MUDAM permissão só valem vindos da janela do painel (nenhuma outra página/frame).
function veioDoPainel(evento) {
  return Boolean(painel) && evento.sender === painel.webContents;
}

ipcMain.on("dervs:permissoes-definir", (evento, dado) => {
  if (!veioDoPainel(evento)) {
    console.error("electron: permissoes-definir de origem estranha, ignorado");
    return;
  }
  if (!dado || typeof dado.categoria !== "string" || !CATEGORIAS_PERMISSAO.has(dado.categoria)
      || typeof dado.nivel !== "string" || !NIVEIS_PERMISSAO.has(dado.nivel)) {
    console.error("electron: permissoes-definir inválido, ignorado");
    return;
  }
  enviarAoPython({ verbo: "permissoes_definir", categoria: dado.categoria, nivel: dado.nivel });
});

ipcMain.on("dervs:permissoes-teto", (evento, valor) => {
  if (!veioDoPainel(evento)) {
    console.error("electron: permissoes-teto de origem estranha, ignorado");
    return;
  }
  if (typeof valor !== "number" || !Number.isFinite(valor) || valor < 0.01 || valor > 1000) {
    console.error("electron: permissoes-teto inválido, ignorado");
    return;
  }
  enviarAoPython({ verbo: "permissoes_teto", valor });
});

ipcMain.on("dervs:integracao-pedir", () => { enviarAoPython({ verbo: "integracao_pedir" }); });

ipcMain.on("dervs:integracao-cerebro", (_evento, nome) => {
  if (typeof nome !== "string" || !/^[a-z_]{1,20}$/.test(nome)) {
    console.error("electron: escolha de cérebro inválida, ignorada");
    return;
  }
  enviarAoPython({ verbo: "integracao_cerebro", nome });
});

ipcMain.on("dervs:integracao-dispensar", (_evento, id) => {
  if (typeof id !== "string" || !ID_PEDIDO_WEB.test(id)) {
    console.error("electron: dispensar pedido inválido, ignorado");
    return;
  }
  enviarAoPython({ verbo: "integracao_dispensar", id });
});

ipcMain.on("dervs:integracao-conserto", (_evento, avisoId) => {
  if (typeof avisoId !== "string" || !ID_LOCAL.test(avisoId)) {
    console.error("electron: pedido de conserto inválido, ignorado");
    return;
  }
  enviarAoPython({ verbo: "integracao_conserto", aviso_id: avisoId });
});

ipcMain.on("dervs:integracao-ssh-rodar", (_evento, dado) => {
  const valido = dado && typeof dado === "object" && typeof dado.apelido === "string"
    && APELIDO_SSH.test(dado.apelido) && typeof dado.comando === "string"
    && dado.comando.trim() !== "" && dado.comando.length <= LIMITE_COMANDO_SSH;
  if (!valido) {
    console.error("electron: comando SSH inválido (apelido, vazio ou longo demais), ignorado");
    return;
  }
  enviarAoPython({ verbo: "integracao_ssh_rodar", apelido: dado.apelido, comando: dado.comando });
});

ipcMain.on("dervs:integracao-ssh-confirmar", (evento, propostaId) => {
  // só a janela do painel pode confirmar (nenhuma outra página/frame)
  if (!painel || evento.sender !== painel.webContents) {
    console.error("electron: confirmação SSH de origem estranha, ignorada");
    return;
  }
  if (typeof propostaId !== "string" || !ID_LOCAL.test(propostaId)) {
    console.error("electron: confirmação SSH inválida, ignorada");
    return;
  }
  enviarAoPython({ verbo: "integracao_ssh_confirmar", proposta_id: propostaId, segunda: true });
});

ipcMain.on("dervs:integracao-ssh-cancelar", (_evento, propostaId) => {
  if (typeof propostaId !== "string" || !ID_LOCAL.test(propostaId)) {
    console.error("electron: cancelamento SSH inválido, ignorado");
    return;
  }
  enviarAoPython({ verbo: "integracao_ssh_cancelar", proposta_id: propostaId });
});

// Painel grande: os botões da janela só PEDEM; quem mexe na janela é este processo.
ipcMain.on("dervs:painel-esconder", esconderPainel);
ipcMain.on("dervs:painel-minimizar", minimizarPainel);
ipcMain.on("dervs:painel-ampliar", ampliarPainel);
ipcMain.on("dervs:painel-redimensionar", (_evento, dado) => redimensionarPainel(dado));

// O cache do Chromium (userData) sai de %APPDATA%\dervs, onde moram o
// config.json e o lembretes.json do Python, e vai para uma subpasta própria —
// assim "manter meus dados" na desinstalação não mistura as duas coisas.
// Precisa rodar antes do evento `ready`.
if (process.env.APPDATA) {
  app.setPath("userData", path.join(process.env.APPDATA, "dervs", "electron"));
}

app.whenReady().then(() => {
  mostrarPainel();
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
