"use strict";
// Testes das funções puras da tela de permissões. Rodar: node --test electron/renderer
const test = require("node:test");
const assert = require("node:assert/strict");
const P = require("./painel-permissoes.js");

test("rotuloDoNivel: português claro para os três níveis", () => {
  assert.equal(P.rotuloDoNivel("analisa"), "Só analisa");
  assert.equal(P.rotuloDoNivel("pergunta"), "Pergunta antes");
  assert.equal(P.rotuloDoNivel("sozinho"), "Faz sozinho");
});

test("niveisDaCategoria mostra SÓ os níveis permitidos, na ordem fixa", () => {
  const permitidos = { apagar: ["pergunta", "analisa"], ler: ["sozinho", "pergunta"], x: [] };
  assert.deepEqual(P.niveisDaCategoria(permitidos, "apagar"), ["analisa", "pergunta"]);
  assert.deepEqual(P.niveisDaCategoria(permitidos, "ler"), ["pergunta", "sozinho"]);
  assert.deepEqual(P.niveisDaCategoria(permitidos, "x"), []);
  assert.deepEqual(P.niveisDaCategoria(permitidos, "inventada"), []);
  assert.deepEqual(P.niveisDaCategoria(null, "ler"), []);
});

test("lerTeto aceita vírgula ou ponto e recusa fora de 0,01 a 1000", () => {
  assert.equal(P.lerTeto("3"), 3);
  assert.equal(P.lerTeto(" 0,5 "), 0.5);
  assert.equal(P.lerTeto("0.01"), 0.01);
  assert.equal(P.lerTeto("1000"), 1000);
  for (const ruim of ["0", "0,00", "1000,01", "1001", "-1", "", "abc", "1e3", "1,234", null, 5])
    assert.equal(P.lerTeto(ruim), null, String(ruim));
});

test("formatarUsd e frasePorGasto usam vírgula e duas casas", () => {
  assert.equal(P.formatarUsd(0.5), "US$ 0,50");
  assert.equal(P.formatarUsd("x"), "US$ 0,00");
  assert.equal(P.frasePorGasto(1.234, 3), "Gasto de hoje: US$ 1,23 de um teto de US$ 3,00.");
  assert.equal(P.textoDoTeto(3), "3");
  assert.equal(P.textoDoTeto(0.5), "0,5");
});

test("linhaRecente usa o rótulo vindo do Python", () => {
  const l = P.linhaRecente({ quando: "2026-10-02 10:00:00", categoria: "ler", ferramenta: "Read", resumo: "a.txt" },
    { ler: "Ler arquivos" });
  assert.equal(l.titulo, "2026-10-02 10:00:00 · Ler arquivos");
  assert.equal(l.detalhe, "Read a.txt");
});

test("o tempo de resposta da tela é curto o bastante para não prender o dono", () => {
  const { TEMPO_RESPOSTA_MS } = require("./painel-permissoes.js");
  assert.ok(TEMPO_RESPOSTA_MS >= 1000 && TEMPO_RESPOSTA_MS <= 10000);
});
