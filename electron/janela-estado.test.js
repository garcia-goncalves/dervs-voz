// Testes da lógica de abrir/esconder/minimizar do painel único.
// Rodar: node --test electron/janela-estado.test.js
// (o pytest chama isto em test_dervs_painel_js.py).
const test = require("node:test");
const assert = require("node:assert");
const { decidirJanela } = require("./janela-estado.js");

const NAO_EXISTE = { existe: false, visivel: false, minimizada: false, saindo: false };
const VISIVEL = { existe: true, visivel: true, minimizada: false, saindo: false };
const ESCONDIDA = { existe: true, visivel: false, minimizada: false, saindo: false };
const MINIMIZADA = { existe: true, visivel: true, minimizada: true, saindo: false };

test("alternar: sem janela cria e mostra", () => {
  assert.strictEqual(decidirJanela(NAO_EXISTE, "alternar"), "criar-e-mostrar");
});
test("alternar: visível esconde", () => {
  assert.strictEqual(decidirJanela(VISIVEL, "alternar"), "esconder");
});
test("alternar: escondida mostra", () => {
  assert.strictEqual(decidirJanela(ESCONDIDA, "alternar"), "mostrar");
});
test("alternar: minimizada traz de volta em vez de esconder", () => {
  assert.strictEqual(decidirJanela(MINIMIZADA, "alternar"), "mostrar");
});
test("mostrar: sempre mostra (cria se preciso)", () => {
  assert.strictEqual(decidirJanela(NAO_EXISTE, "mostrar"), "criar-e-mostrar");
  assert.strictEqual(decidirJanela(VISIVEL, "mostrar"), "mostrar");
  assert.strictEqual(decidirJanela(MINIMIZADA, "mostrar"), "mostrar");
});
test("minimizar: só minimiza janela visível e não minimizada", () => {
  assert.strictEqual(decidirJanela(VISIVEL, "minimizar"), "minimizar");
  assert.strictEqual(decidirJanela(MINIMIZADA, "minimizar"), "nada");
  assert.strictEqual(decidirJanela(ESCONDIDA, "minimizar"), "nada");
  assert.strictEqual(decidirJanela(NAO_EXISTE, "minimizar"), "nada");
});
test("esconder: só age se a janela existe", () => {
  assert.strictEqual(decidirJanela(VISIVEL, "esconder"), "esconder");
  assert.strictEqual(decidirJanela(NAO_EXISTE, "esconder"), "nada");
});
test("fechar: vai para a bandeja; saindo do app deixa fechar de verdade", () => {
  assert.strictEqual(decidirJanela(VISIVEL, "fechar"), "esconder");
  assert.strictEqual(decidirJanela(MINIMIZADA, "fechar"), "esconder");
  assert.strictEqual(decidirJanela({ ...VISIVEL, saindo: true }, "fechar"), "deixar-fechar");
});
test("evento desconhecido não faz nada", () => {
  assert.strictEqual(decidirJanela(VISIVEL, "explodir"), "nada");
  assert.strictEqual(decidirJanela(null, "alternar"), "nada");
});
