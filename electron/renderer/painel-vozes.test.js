"use strict";
// Testes das funções puras da tela Vozes. Rodar: node --test electron/renderer/painel-vozes.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const V = require("./painel-vozes.js");

test("rotuloDoMotor: nomes claros e 'Parada' sem motor", () => {
  assert.equal(V.rotuloDoMotor({ motor_ativo: "gemini_live" }), "Google (grátis)");
  assert.equal(V.rotuloDoMotor({ motor_ativo: "cascata" }), "Econômico");
  assert.equal(V.rotuloDoMotor({ motor_ativo: "openai_realtime" }), "Premium (OpenAI)");
  assert.equal(V.rotuloDoMotor({ motor_ativo: null }), "Parada — liga quando você chamar o DERVS");
  assert.equal(V.rotuloDoMotor({ motor_ativo: "invento" }), "Parada — liga quando você chamar o DERVS");
  assert.equal(V.rotuloDoMotor(null), "Parada — liga quando você chamar o DERVS");
});

test("avisoDaTrava: traduz o aviso do Python e ignora texto desconhecido", () => {
  assert.equal(V.avisoDaTrava({ locutor_aviso: "grave sua voz" }), "Grave sua voz para o DERVS só atender você.");
  assert.match(V.avisoDaTrava({ locutor_aviso: "nenhum perfil ativo" }), /Nenhuma voz está ativa/);
  assert.match(V.avisoDaTrava({ locutor_aviso: "trava de voz desligada" }), /desligada/);
  assert.match(V.avisoDaTrava({ locutor_aviso: "grave sua voz de novo" }), /Grave a sua de novo/);
  assert.equal(V.avisoDaTrava({ locutor_aviso: null }), "");
  assert.equal(V.avisoDaTrava({ locutor_aviso: "<b>x</b>" }), "");
  assert.equal(V.avisoDaTrava(undefined), "");
});

test("statusDaTrava: diz quem o DERVS escuta", () => {
  assert.equal(V.statusDaTrava({ locutor_ativo: true, perfis_ativos: ["Thiago", "Lia"] }),
    "Trava de voz ligada: só escuto Thiago, Lia.");
  assert.match(V.statusDaTrava({ locutor_ativo: false, perfis_ativos: [], locutor_aviso: "grave sua voz" }), /qualquer pessoa/);
  assert.match(V.statusDaTrava({ locutor_ativo: true, perfis_ativos: [], locutor_aviso: "nenhum perfil ativo" }), /sem nenhuma voz ativa/);
  assert.match(V.statusDaTrava({ locutor_ativo: true, perfis_ativos: [], locutor_aviso: "grave sua voz de novo" }), /não escuto ninguém/);
  assert.equal(V.statusDaTrava(null), "Carregando...");
});

test("podeGravarDono: 1º cadastro livre; depois só com dono confirmado", () => {
  const dono = [{ nome: "A", papel: "dono", ativo: true }];
  const conv = [{ nome: "B", papel: "convidado", ativo: true }];
  assert.equal(V.podeGravarDono([], { dono_confirmado: false }), true);
  assert.equal(V.podeGravarDono(conv, { dono_confirmado: false }), true);
  assert.equal(V.podeGravarDono(dono, { dono_confirmado: false }), false);
  assert.equal(V.podeGravarDono(dono, { dono_confirmado: true }), true);
  assert.equal(V.podeGravarDono(dono, {}), true);          // Python antigo: ele mesmo recusa
});

test("validarNome: corta espaços, recusa vazio e nome longo", () => {
  assert.deepEqual(V.validarNome("  Lia "), { ok: true, nome: "Lia" });
  assert.equal(V.validarNome("   ").ok, false);
  assert.equal(V.validarNome(null).ok, false);
  assert.equal(V.validarNome("x".repeat(41)).ok, false);
  assert.equal(V.validarNome("x".repeat(40)).ok, true);
});

test("progresso: fração vira segundos entre 0 e 30", () => {
  assert.equal(V.segundosGravados(0), 0);
  assert.equal(V.segundosGravados(0.5), 15);
  assert.equal(V.segundosGravados(1.7), 30);
  assert.equal(V.segundosGravados(-1), 0);
  assert.equal(V.segundosGravados("lixo"), 0);
  assert.match(V.fraseDoProgresso(0.4), /12 de 30 segundos/);
});

test("mensagemDoResultado: erro do Python passa inteiro; sucesso por ação", () => {
  assert.deepEqual(V.mensagemDoResultado("gravar", { ok: false, erro: "Preciso de pelo menos 15 segundos de fala." }, "Lia"),
    { texto: "Preciso de pelo menos 15 segundos de fala.", ok: false });
  assert.deepEqual(V.mensagemDoResultado("gravar", { ok: true }, "Lia"), { texto: "Voz de Lia gravada.", ok: true });
  assert.deepEqual(V.mensagemDoResultado("apagar", { ok: true }, "Lia"), { texto: "Voz de Lia apagada.", ok: true });
  assert.equal(V.mensagemDoResultado("ativar", { ok: true }, "Lia"), null);
  assert.equal(V.mensagemDoResultado("gravar", { ok: false }, "Lia").texto, "Não consegui fazer isso.");
  assert.equal(V.mensagemDoResultado("gravar", null, "Lia"), null);
});

test("texto de leitura tem tamanho de ~30 s (70 a 110 palavras)", () => {
  const n = V.TEXTO_LEITURA.split(/\s+/).length;
  assert.ok(n >= 70 && n <= 110, `palavras: ${n}`);
});
