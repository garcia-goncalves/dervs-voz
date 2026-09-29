// painel-formato.js — funções PURAS do painel grande (formatação e cadência).
//
// Sem DOM, sem Electron: roda no navegador (window.PainelFormato) e no Node
// (require), e por isso tem teste automático (painel-formato.test.js, chamado
// por test_dervs_painel_js.py). Tudo que o painel decide "de cabeça" mora aqui.

(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) module.exports = api;
  else raiz.PainelFormato = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Cadência da animação (critério 5). Escondida: parada (0 quadros, que é
  // "no máximo 10"). Visível mas sem foco: 10 quadros/s. Com foco: 30.
  const MS_QUADRO_FOCADO = 33;
  const MS_QUADRO_SEM_FOCO = 100;

  function msPorQuadro({ visivel, focada }) {
    if (!visivel) return null;
    return focada ? MS_QUADRO_FOCADO : MS_QUADRO_SEM_FOCO;
  }

  function virgula(n, casas) {
    return n.toFixed(casas).replace(".", ",");
  }

  function formatarUsd(valor) {
    const v = Number.isFinite(valor) && valor > 0 ? valor : 0;
    const casas = v > 0 && v < 0.01 ? 3 : 2;
    return "US$ " + virgula(v, casas);
  }

  function formatarKbs(kbs) {
    if (!Number.isFinite(kbs) || kbs < 0) return "-- KB/s";
    if (kbs >= 1024) return virgula(kbs / 1024, 1) + " MB/s";
    return (kbs >= 10 ? Math.round(kbs).toString() : virgula(kbs, 1)) + " KB/s";
  }

  function formatarPercentual(p) {
    return Number.isFinite(p) ? Math.round(p) + "%" : "--%";
  }

  function formatarDisco(livreGb, totalGb) {
    if (!Number.isFinite(livreGb) || !Number.isFinite(totalGb) || totalGb <= 0) return "-- / -- GB";
    return Math.round(livreGb) + " / " + Math.round(totalGb) + " GB livres";
  }

  // Empurra um valor no histórico, mantendo só os últimos `max` (novo array).
  function empurrar(historico, valor, max) {
    const novo = historico.concat([valor]);
    return novo.length > max ? novo.slice(novo.length - max) : novo;
  }

  // Pontos [x, y] de uma sparkline. `teto` fixo (ex.: 100 para %); sem `teto`,
  // escala pelo maior valor do histórico (mínimo 1, para rede parada não "explodir").
  function pontosSparkline(historico, largura, altura, teto) {
    if (!historico.length) return [];
    const maximo = teto || Math.max(1, ...historico);
    const passo = historico.length > 1 ? largura / (historico.length - 1) : 0;
    return historico.map((v, i) => {
      const proporcao = Math.max(0, Math.min(1, v / maximo));
      return [i * passo, altura - proporcao * altura];
    });
  }

  function tempoRestante(segundos) {
    const m = Math.floor(segundos / 60);
    const s = segundos % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  // "há 5 s" / "há 3 min" / "há 2 h", para a lista de ações e a conversa.
  function haQuanto(agoraMs, quandoMs) {
    const s = Math.max(0, Math.round((agoraMs - quandoMs) / 1000));
    if (s < 60) return "há " + s + " s";
    if (s < 3600) return "há " + Math.floor(s / 60) + " min";
    return "há " + Math.floor(s / 3600) + " h";
  }

  // Texto que acompanha o estado da máquina de estados do DERVS.
  const ROTULOS_ESTADO = {
    ocioso: "EM ESPERA",
    ouvindo: "OUVINDO",
    pensando: "PENSANDO",
    falando: "FALANDO",
    erro: "ATENÇÃO",
  };

  function rotuloDoEstado(estado) {
    return ROTULOS_ESTADO[estado] || ROTULOS_ESTADO.ocioso;
  }

  // O nome interno da ferramenta do Claude, em português para quem não é técnico.
  const ROTULOS_FERRAMENTA = {
    Bash: "executar um comando", PowerShell: "executar um comando", Write: "criar ou substituir um arquivo",
    Edit: "editar um arquivo", NotebookEdit: "editar um caderno", Read: "ler um arquivo",
    Glob: "procurar arquivos", Grep: "procurar texto nos arquivos", WebFetch: "abrir uma página da internet",
    WebSearch: "pesquisar na internet",
  };

  function rotuloDaFerramenta(nome) {
    const n = String(nome || "");
    if (ROTULOS_FERRAMENTA[n]) return ROTULOS_FERRAMENTA[n];
    if (n.startsWith("mcp__playwright")) return "usar o navegador";
    if (n.includes("propor_acao")) return "propor uma limpeza ou mudança (você aprova depois, item a item)";
    if (n.startsWith("mcp__")) return "usar uma ferramenta extra";
    return n ? `usar ${n}` : "fazer uma ação";
  }

  return {
    MS_QUADRO_FOCADO, MS_QUADRO_SEM_FOCO, msPorQuadro,
    formatarUsd, formatarKbs, formatarPercentual, formatarDisco,
    empurrar, pontosSparkline, tempoRestante, haQuanto, rotuloDoEstado,
    rotuloDaFerramenta,
  };
});
