// Testes das funções puras do painel grande. Rodar: node --test electron/renderer
// (o pytest chama isto em test_dervs_painel_js.py).
const test = require("node:test");
const assert = require("node:assert");
const F = require("./painel-formato.js");

test("cadência: escondida para, sem foco 10 fps, com foco 30 fps", () => {
  assert.strictEqual(F.msPorQuadro({ visivel: false, focada: true }), null);
  assert.strictEqual(F.msPorQuadro({ visivel: true, focada: false }), 100);
  assert.strictEqual(F.msPorQuadro({ visivel: true, focada: true }), 33);
  // sem foco nunca passa de 10 quadros por segundo
  assert.ok(1000 / F.msPorQuadro({ visivel: true, focada: false }) <= 10);
});

test("dólar: duas casas, três abaixo de um centavo, vírgula", () => {
  assert.strictEqual(F.formatarUsd(0), "US$ 0,00");
  assert.strictEqual(F.formatarUsd(1.234), "US$ 1,23");
  assert.strictEqual(F.formatarUsd(0.004), "US$ 0,004");
  assert.strictEqual(F.formatarUsd(NaN), "US$ 0,00");
  assert.strictEqual(F.formatarUsd(-3), "US$ 0,00");
});

test("rede: KB/s e MB/s", () => {
  assert.strictEqual(F.formatarKbs(0), "0,0 KB/s");
  assert.strictEqual(F.formatarKbs(5.5), "5,5 KB/s");
  assert.strictEqual(F.formatarKbs(120.4), "120 KB/s");
  assert.strictEqual(F.formatarKbs(2048), "2,0 MB/s");
  assert.strictEqual(F.formatarKbs(undefined), "-- KB/s");
});

test("percentual e disco", () => {
  assert.strictEqual(F.formatarPercentual(37.6), "38%");
  assert.strictEqual(F.formatarPercentual(undefined), "--%");
  assert.strictEqual(F.formatarDisco(120.4, 476.9), "120 / 477 GB livres");
  assert.strictEqual(F.formatarDisco(1, 0), "-- / -- GB");
});

test("histórico guarda só os últimos N, sem mutar", () => {
  const a = [1, 2, 3];
  const b = F.empurrar(a, 4, 3);
  assert.deepStrictEqual(b, [2, 3, 4]);
  assert.deepStrictEqual(a, [1, 2, 3]);
});

test("sparkline: escala com teto fixo e sem teto", () => {
  const p = F.pontosSparkline([0, 50, 100], 100, 40, 100);
  assert.deepStrictEqual(p, [[0, 40], [50, 20], [100, 0]]);
  const q = F.pontosSparkline([0, 0], 10, 10);
  assert.deepStrictEqual(q, [[0, 10], [10, 10]]);       // rede parada: linha no chão
  assert.deepStrictEqual(F.pontosSparkline([], 10, 10), []);
});

test("tempo restante e há quanto tempo", () => {
  assert.strictEqual(F.tempoRestante(125), "02:05");
  assert.strictEqual(F.haQuanto(10_000, 5_000), "há 5 s");
  assert.strictEqual(F.haQuanto(200_000, 0), "há 3 min");
  assert.strictEqual(F.haQuanto(7_300_000, 0), "há 2 h");
});

test("rótulo de estado desconhecido cai em espera", () => {
  assert.strictEqual(F.rotuloDoEstado("falando"), "FALANDO");
  assert.strictEqual(F.rotuloDoEstado("xis"), "EM ESPERA");
});

test("rotuloDaFerramenta traduz o nome interno para o leigo", () => {
  assert.strictEqual(F.rotuloDaFerramenta("Bash"), "executar um comando");
  assert.strictEqual(F.rotuloDaFerramenta("Write"), "criar ou substituir um arquivo");
  assert.strictEqual(F.rotuloDaFerramenta("mcp__playwright__browser_click"), "usar o navegador");
  assert.match(F.rotuloDaFerramenta("mcp__dervs__propor_acao"), /você aprova depois/);
  assert.strictEqual(F.rotuloDaFerramenta("Outra"), "usar Outra");
  assert.strictEqual(F.rotuloDaFerramenta(""), "fazer uma ação");
});

test("rótulo do microfone: aberto/fechado por modo, com prazo do desligamento", () => {
  assert.deepStrictEqual(F.rotuloMicrofone("voz", true, 7), { valor: "OUVINDO · FECHA EM 7 MIN", estado: "ok" });
  assert.deepStrictEqual(F.rotuloMicrofone("voz", true, null), { valor: "OUVINDO", estado: "ok" });
  assert.deepStrictEqual(F.rotuloMicrofone("voz", true, -1), { valor: "OUVINDO", estado: "ok" });
  assert.deepStrictEqual(F.rotuloMicrofone("atalho", true, null), { valor: "ABERTO (ATALHO)", estado: "ok" });
  assert.deepStrictEqual(F.rotuloMicrofone("atalho", false, null), { valor: "FECHADO · ATALHO", estado: "alerta" });
  assert.deepStrictEqual(F.rotuloMicrofone("desligado", false, null), { valor: "DESLIGADO", estado: "alerta" });
  assert.deepStrictEqual(F.rotuloMicrofone("sei-la", false, null), { valor: "DESLIGADO", estado: "alerta" });
});
