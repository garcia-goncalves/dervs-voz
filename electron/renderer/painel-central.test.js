"use strict";
// Testes das funções puras da Central do PC. Rodar: node --test electron/renderer
const test = require("node:test");
const assert = require("node:assert/strict");
const C = require("./painel-central.js");

test("formatarBytes usa unidade certa e vírgula", () => {
  assert.equal(C.formatarBytes(512), "512 B");
  assert.equal(C.formatarBytes(2048), "2 KB");
  assert.equal(C.formatarBytes(5 * 1024 ** 2), "5 MB");
  assert.equal(C.formatarBytes(1.5 * 1024 ** 3), "1,5 GB");
  assert.equal(C.formatarBytes(-1), "--");
  assert.equal(C.formatarBytes(NaN), "--");
});

test("faixaDaNota: 80+ ok, 50-79 atenção, abaixo alerta, sem nota", () => {
  assert.equal(C.faixaDaNota(100), "ok");
  assert.equal(C.faixaDaNota(80), "ok");
  assert.equal(C.faixaDaNota(79), "atencao");
  assert.equal(C.faixaDaNota(50), "atencao");
  assert.equal(C.faixaDaNota(49), "alerta");
  assert.equal(C.faixaDaNota(null), "sem");
  assert.equal(C.rotuloDaFaixa("alerta"), "pede cuidado");
});

test("rotuloAssinatura não afirma o que não leu", () => {
  assert.equal(C.rotuloAssinatura("Valid"), "assinado");
  assert.equal(C.rotuloAssinatura("NotSigned"), "sem assinatura");
  assert.equal(C.rotuloAssinatura("HashMismatch"), "assinatura com problema");
  assert.equal(C.rotuloAssinatura("Desconhecida"), "");
  assert.equal(C.rotuloAssinatura(undefined), "");
});

test("nomeDoCaminho pega o último pedaço nos dois tipos de barra", () => {
  assert.equal(C.nomeDoCaminho("C:\\Users\\x\\Temp\\a.tmp"), "a.tmp");
  assert.equal(C.nomeDoCaminho("/tmp/b.log"), "b.log");
  assert.equal(C.nomeDoCaminho(""), "");
});

const itens = [
  { id: "item-1", risco: "baixo", tamanho_bytes: 1024 },
  { id: "item-2", risco: "alto", tamanho_bytes: 2048 },
  { id: "item-3", risco: "medio", tamanho_bytes: 1024 },
];

test("decidirAprovacao: nada marcado não aprova", () => {
  const r = C.decidirAprovacao(itens, new Set(), new Set());
  assert.equal(r.pode, false);
  assert.deepEqual(r.ids, []);
});

test("decidirAprovacao manda só o marcado, na ordem do relatório", () => {
  const r = C.decidirAprovacao(itens, new Set(["item-3", "item-1"]), new Set());
  assert.deepEqual(r.ids, ["item-1", "item-3"]);
  assert.equal(r.pode, true);
  assert.deepEqual(r.dupla, []);
});

test("risco alto sem a segunda caixa trava o botão; com ela, entra em dupla", () => {
  const sem = C.decidirAprovacao(itens, new Set(["item-2"]), new Set());
  assert.equal(sem.pode, false);
  assert.equal(sem.faltaConfirmar, true);
  const com = C.decidirAprovacao(itens, new Set(["item-2"]), new Set(["item-2"]));
  assert.equal(com.pode, true);
  assert.deepEqual(com.dupla, ["item-2"]);
});

test("confirmação de item que não foi marcado é ignorada", () => {
  const r = C.decidirAprovacao(itens, new Set(["item-1"]), new Set(["item-2"]));
  assert.deepEqual(r.ids, ["item-1"]);
  assert.deepEqual(r.dupla, []);
});

test("haQuantoTempoLeitura", () => {
  const agora = Date.parse("2026-09-29T12:00:00");
  assert.equal(C.haQuantoTempoLeitura("2026-09-29T11:59:40", agora), "agora há pouco");
  assert.equal(C.haQuantoTempoLeitura("2026-09-29T11:30:00", agora), "há 30 min");
  assert.equal(C.haQuantoTempoLeitura("2026-09-29T09:00:00", agora), "há 3 h");
  assert.equal(C.haQuantoTempoLeitura("2026-09-27T12:00:00", agora), "há 2 dias");
  assert.equal(C.haQuantoTempoLeitura("lixo", agora), "");
});

test("plural escolhe singular e plural sem parênteses", () => {
  assert.equal(C.plural(1, "item", "itens"), "1 item");
  assert.equal(C.plural(3, "item", "itens"), "3 itens");
  assert.equal(C.plural(0, "dia", "dias"), "0 dias");
});

test("rotuloSaude traduz e não inventa", () => {
  assert.equal(C.rotuloSaude("Healthy"), "boa");
  assert.equal(C.rotuloSaude("Unhealthy"), "com problema");
  assert.equal(C.rotuloSaude("Desconhecida"), "");
});

test("o botão de aprovar sempre explica por que está apagado", () => {
  const nada = C.decidirAprovacao(itens, new Set(), new Set());
  assert.match(C.dicaDoBotao(nada, false), /Marque pelo menos um item/);
  const alto = C.decidirAprovacao(itens, new Set(["item-2"]), new Set());
  assert.match(C.dicaDoBotao(alto, false), /risco alto/);
  const ok = C.decidirAprovacao(itens, new Set(["item-1"]), new Set());
  assert.equal(C.dicaDoBotao(ok, false), "");
  assert.match(C.dicaDoBotao(ok, true), /não vale mais/);
});

test("contador de marcados soma o tamanho e usa singular/plural", () => {
  assert.equal(C.contadorDeMarcados(C.decidirAprovacao(itens, new Set(), new Set())), "Nenhum item marcado.");
  assert.equal(C.contadorDeMarcados(C.decidirAprovacao(itens, new Set(["item-1"]), new Set())), "1 item marcado · 1 KB");
  assert.equal(C.contadorDeMarcados(C.decidirAprovacao(itens, new Set(["item-1", "item-3"]), new Set())), "2 itens marcados · 2 KB");
});
