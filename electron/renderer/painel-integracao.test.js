"use strict";
// Testes das funções puras da tela Integração. Rodar: node --test electron/renderer
const test = require("node:test");
const assert = require("node:assert/strict");
const I = require("./painel-integracao.js");

test("botaoDoCerebro: em uso, disponível, indisponível e JEV sem botão", () => {
  assert.deepEqual(I.botaoDoCerebro({ escolhivel: true, ativo: true, disponivel: true }),
    { visivel: true, texto: "EM USO", desligado: true });
  assert.deepEqual(I.botaoDoCerebro({ escolhivel: true, ativo: false, disponivel: true }),
    { visivel: true, texto: "USAR ESTE", desligado: false });
  assert.deepEqual(I.botaoDoCerebro({ escolhivel: true, ativo: false, disponivel: false }),
    { visivel: true, texto: "INDISPONÍVEL", desligado: true });
  const jev = I.botaoDoCerebro({ escolhivel: false, ativo: false, disponivel: true });
  assert.equal(jev.visivel, false);
  assert.equal(jev.desligado, true);
});

test("comandoValido: não vazio, só texto e até 400 caracteres", () => {
  assert.equal(I.comandoValido("uptime"), true);
  assert.equal(I.comandoValido("x".repeat(400)), true);
  assert.equal(I.comandoValido("x".repeat(401)), false);
  assert.equal(I.comandoValido("   "), false);
  assert.equal(I.comandoValido(""), false);
  assert.equal(I.comandoValido(null), false);
  assert.equal(I.comandoValido(["uptime"]), false);
});

test("podeExecutar exige servidor, comando e nada em andamento", () => {
  assert.equal(I.podeExecutar("prod", "uptime", false), true);
  assert.equal(I.podeExecutar("", "uptime", false), false);
  assert.equal(I.podeExecutar("prod", "", false), false);
  assert.equal(I.podeExecutar("prod", "uptime", true), false);
});

test("instrucaoDeHosts explica como cadastrar quando a lista é vazia", () => {
  const vazia = I.instrucaoDeHosts([], "C:\\Users\\x\\AppData\\Roaming\\dervs\\ssh_hosts.json");
  assert.match(vazia, /Nenhum servidor cadastrado/);
  assert.match(vazia, /ssh_hosts\.json/);
  assert.match(vazia, /"host"/);
  const cheia = I.instrucaoDeHosts(["a", "b"], "arq.json");
  assert.match(cheia, /cadastrados: 2/);
  assert.doesNotMatch(cheia, /Nenhum servidor/);
});

test("validadeDoCartao diz os minutos e a hora limite", () => {
  const t = new Date(2026, 8, 30, 10, 5).getTime();
  assert.match(I.validadeDoCartao(15, t), /^15 minutos \(até 10:20\)/);
});

test("tituloDoResultado: sucesso, código de saída, corte e recusa", () => {
  assert.match(I.tituloDoResultado({ ok: true, apelido: "prod", comando: "uptime", rc: 0 }), /terminou bem/);
  assert.match(I.tituloDoResultado({ ok: true, apelido: "prod", comando: "ls", rc: 2 }), /código 2/);
  assert.match(I.tituloDoResultado({ ok: true, apelido: "p", comando: "x", rc: 0, truncada: true }), /cortada/);
  const recusa = I.tituloDoResultado({ ok: false, apelido: "prod", motivo: "apelido fora da lista" });
  assert.match(recusa, /Não rodou em prod/);
  assert.match(recusa, /fora da lista/);
});

test("textoDaSaida: vazio vira aviso e recusa não mostra saída", () => {
  assert.equal(I.textoDaSaida({ ok: true, saida: "a\nb" }), "a\nb");
  assert.match(I.textoDaSaida({ ok: true, saida: "" }), /não escreveu nada/);
  assert.equal(I.textoDaSaida({ ok: false, saida: "x" }), "");
});

test("chipDaPonte: cada estado tem valor e cor; desconhecido é neutro", () => {
  assert.deepEqual(I.chipDaPonte("ligada"), { valor: "LIGADA", estado: "ok" });
  assert.equal(I.chipDaPonte("calma").estado, "");
  assert.equal(I.chipDaPonte("desligada").estado, "alerta");
  assert.deepEqual(I.chipDaPonte("qualquer"), { valor: "--", estado: "" });
});

test("rotuloDoTipo cobre os tipos do contrato e cai em Pedido", () => {
  assert.equal(I.rotuloDoTipo("propor"), "Proposta");
  assert.equal(I.rotuloDoTipo("avisar"), "Aviso");
  assert.equal(I.rotuloDoTipo("<script>"), "Pedido");
});
