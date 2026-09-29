// Testes do formatador Markdown mínimo do painel. Rodar: node --test electron/renderer
// (o pytest chama isto em test_dervs_painel_js.py).
//
// O ponto principal: o texto do Claude é DADO HOSTIL. O formatador só cria nós
// com createElement/textContent — nunca innerHTML. O documento falso abaixo
// FALHA se alguém tocar em innerHTML/outerHTML/insertAdjacentHTML.
const test = require("node:test");
const assert = require("node:assert");
const M = require("./painel-markdown.js");

function elementoFalso(tag) {
  const e = {
    tag, className: "", filhos: [], _texto: "",
    appendChild(f) { this.filhos.push(f); return f; },
    set textContent(v) { this._texto = String(v); },
    get textContent() { return this._texto; },
    insertAdjacentHTML() { throw new Error("insertAdjacentHTML proibido"); },
  };
  for (const nome of ["innerHTML", "outerHTML"]) {
    Object.defineProperty(e, nome, { set() { throw new Error(nome + " proibido"); },
      get() { throw new Error(nome + " proibido"); } });
  }
  return e;
}
const docFalso = {
  createElement: elementoFalso,
  createTextNode(v) { const e = elementoFalso("#texto"); e.textContent = v; return e; },
  createDocumentFragment() { return elementoFalso("#fragmento"); },
};

// achata a árvore em [tag, texto] para comparar fácil
function achatar(no) {
  const saida = [];
  for (const f of no.filhos) {
    saida.push([f.tag, f.textContent, f.filhos.length ? achatar(f) : undefined]);
  }
  return saida;
}

test("analisar: parágrafo simples", () => {
  assert.deepStrictEqual(M.analisar("Olá mundo"),
    [{ tipo: "p", inline: [{ t: "texto", v: "Olá mundo" }] }]);
});

test("analisar: negrito e código em linha", () => {
  const [b] = M.analisar("veja **isto** e `aquilo` aqui");
  assert.deepStrictEqual(b.inline, [
    { t: "texto", v: "veja " }, { t: "negrito", v: "isto" },
    { t: "texto", v: " e " }, { t: "codigo", v: "aquilo" }, { t: "texto", v: " aqui" }]);
});

test("analisar: marcador sem fechar fica como texto literal", () => {
  const [b] = M.analisar("2 ** 3 e `sem fim");
  assert.deepStrictEqual(b.inline, [{ t: "texto", v: "2 ** 3 e `sem fim" }]);
});

test("analisar: lista com - e * e numerada", () => {
  const blocos = M.analisar("- um\n- **dois**\n* três\n\n1. primeiro\n2) segundo");
  assert.strictEqual(blocos[0].tipo, "lista");
  assert.strictEqual(blocos[0].ordenada, false);
  assert.strictEqual(blocos[0].itens.length, 3);
  assert.deepStrictEqual(blocos[0].itens[1], [{ t: "negrito", v: "dois" }]);
  assert.strictEqual(blocos[1].tipo, "lista");
  assert.strictEqual(blocos[1].ordenada, true);
  assert.strictEqual(blocos[1].itens.length, 2);
});

test("analisar: bloco de código com cerca não interpreta o miolo", () => {
  const blocos = M.analisar("antes\n```powershell\nGet-Date **nao** `nada`\n- nem lista\n```\ndepois");
  assert.deepStrictEqual(blocos.map((b) => b.tipo), ["p", "codigo", "p"]);
  assert.strictEqual(blocos[1].v, "Get-Date **nao** `nada`\n- nem lista");
});

test("analisar: cerca sem fechar consome até o fim, sem quebrar", () => {
  const blocos = M.analisar("```\nlinha 1\nlinha 2");
  assert.deepStrictEqual(blocos, [{ tipo: "codigo", v: "linha 1\nlinha 2" }]);
});

test("analisar: título vira parágrafo em negrito", () => {
  assert.deepStrictEqual(M.analisar("## Resultado")[0],
    { tipo: "p", inline: [{ t: "negrito", v: "Resultado" }] });
});

test("analisar: linha em branco separa parágrafos; quebra simples é mantida", () => {
  const blocos = M.analisar("a\nb\n\nc");
  assert.strictEqual(blocos.length, 2);
  assert.deepStrictEqual(blocos[0].inline, [{ t: "texto", v: "a\nb" }]);
});

test("analisar: entrada estranha não quebra", () => {
  assert.deepStrictEqual(M.analisar(""), []);
  assert.deepStrictEqual(M.analisar(null), []);
  assert.deepStrictEqual(M.analisar(42), []);
  assert.doesNotThrow(() => M.analisar("****``````\n- \n1. \n```"));
});

test("renderizar: monta nós com textContent e as tags certas", () => {
  const frag = M.renderizar(docFalso, "oi **você**\n\n- a\n- b\n\n```\nx\n```");
  const [p, ul, pre] = achatar(frag);
  assert.strictEqual(p[0], "p");
  assert.deepStrictEqual(p[2].map((n) => [n[0], n[1]]), [["#texto", "oi "], ["strong", "você"]]);
  assert.strictEqual(ul[0], "ul");
  assert.deepStrictEqual(ul[2].map((n) => n[0]), ["li", "li"]);
  assert.strictEqual(pre[0], "pre");
  assert.strictEqual(pre[2][0][1], "x");
});

test("renderizar: HTML hostil vira TEXTO, nunca marcação (sem innerHTML)", () => {
  const hostil = '<img src=x onerror="alert(1)"> **<script>alert(2)</script>** `<b>x</b>`\n\n- <a href="javascript:1">l</a>';
  // o documento falso lança se alguém usar innerHTML/outerHTML/insertAdjacentHTML
  const frag = M.renderizar(docFalso, hostil);
  const todos = [];
  (function varrer(no) {
    for (const f of no.filhos) { todos.push(f); varrer(f); }
  })(frag);
  const tags = new Set(todos.map((n) => n.tag));
  for (const proibida of ["img", "script", "a", "b", "iframe"]) {
    assert.ok(!tags.has(proibida), "criou <" + proibida + ">");
  }
  const texto = todos.map((n) => n.textContent).join("|");
  assert.ok(texto.includes('<img src=x onerror="alert(1)">'));
  assert.ok(texto.includes("<script>alert(2)</script>"));
});

test("renderizar: nenhum atributo de evento nem href é definido", () => {
  const frag = M.renderizar(docFalso, "[clique](javascript:alert(1)) **x**");
  const texto = JSON.stringify(achatar(frag));
  assert.ok(texto.includes("javascript:alert(1)"), "link fica como texto puro");
});

test("o código-fonte do formatador não usa innerHTML", () => {
  const fs = require("node:fs");
  const fonte = fs.readFileSync(require.resolve("./painel-markdown.js"), "utf8")
    .split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
  for (const proibido of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("]) {
    assert.ok(!fonte.includes(proibido), "usa " + proibido);
  }
});
