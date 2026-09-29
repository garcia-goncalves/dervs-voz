// painel-markdown.js — formatador Markdown MÍNIMO para a resposta do Claude Code.
//
// Só entende: **negrito**, `código`, listas (- * 1.), bloco ```cercado``` e
// títulos (#, mostrados em negrito). Nada mais: sem link, sem imagem, sem HTML.
//
// SEGURANÇA (regra dura do projeto): o texto do Claude é DADO hostil — pode
// trazer <img onerror>, <script>, "javascript:". Por isso este arquivo só cria
// nós com createElement/createTextNode/textContent e NUNCA usa innerHTML. O que
// parece marcação HTML aparece na tela como texto puro. O teste
// (painel-markdown.test.js) usa um documento falso que lança erro se alguém
// tocar em innerHTML.
//
// Duas partes: `analisar` (pura: texto -> blocos) e `renderizar` (blocos -> nós).
// Roda no navegador (window.PainelMarkdown) e no Node (require), para ter teste.

(function (raiz, fabrica) {
  "use strict";
  const api = fabrica();
  if (typeof module === "object" && module.exports) module.exports = api;
  else raiz.PainelMarkdown = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LIMITE_TEXTO = 400000; // acima disto o resto é ignorado (defesa de memória)

  // Pedaços em linha: **negrito** e `código`. Marcador sem fechar fica literal.
  const EM_LINHA = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/;

  function analisarEmLinha(texto) {
    const pedacos = [];
    for (const parte of texto.split(EM_LINHA)) {
      if (!parte) continue;
      if (parte.length > 4 && parte.startsWith("**") && parte.endsWith("**")) {
        pedacos.push({ t: "negrito", v: parte.slice(2, -2) });
      } else if (parte.length > 2 && parte.startsWith("`") && parte.endsWith("`")) {
        pedacos.push({ t: "codigo", v: parte.slice(1, -1) });
      } else {
        const ultimo = pedacos[pedacos.length - 1];
        if (ultimo && ultimo.t === "texto") ultimo.v += parte;
        else pedacos.push({ t: "texto", v: parte });
      }
    }
    return pedacos;
  }

  const ITEM_LISTA = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/;
  const CERCA = /^\s*```/;
  const TITULO = /^\s*#{1,6}\s+(.*)$/;

  function analisar(texto) {
    if (typeof texto !== "string" || !texto) return [];
    const linhas = texto.slice(0, LIMITE_TEXTO).replace(/\r\n?/g, "\n").split("\n");
    const blocos = [];
    let paragrafo = [];
    let lista = null;

    function fecharParagrafo() {
      if (paragrafo.length) {
        blocos.push({ tipo: "p", inline: analisarEmLinha(paragrafo.join("\n")) });
        paragrafo = [];
      }
    }
    function fecharLista() {
      if (lista) { blocos.push(lista); lista = null; }
    }

    for (let i = 0; i < linhas.length; i++) {
      const linha = linhas[i];
      if (CERCA.test(linha)) {
        fecharParagrafo(); fecharLista();
        const codigo = [];
        i++;
        while (i < linhas.length && !CERCA.test(linhas[i])) { codigo.push(linhas[i]); i++; }
        blocos.push({ tipo: "codigo", v: codigo.join("\n") });
        continue;
      }
      if (!linha.trim()) { fecharParagrafo(); fecharLista(); continue; }
      const item = ITEM_LISTA.exec(linha);
      if (item && item[3].trim()) {
        fecharParagrafo();
        const ordenada = item[2] !== undefined;
        if (!lista || lista.ordenada !== ordenada) {
          fecharLista();
          lista = { tipo: "lista", ordenada, itens: [] };
        }
        lista.itens.push(analisarEmLinha(item[3].trim()));
        continue;
      }
      const titulo = TITULO.exec(linha);
      if (titulo && titulo[1].trim()) {
        fecharParagrafo(); fecharLista();
        blocos.push({ tipo: "p", inline: [{ t: "negrito", v: titulo[1].trim() }] });
        continue;
      }
      fecharLista();
      paragrafo.push(linha);
    }
    fecharParagrafo(); fecharLista();
    return blocos;
  }

  function nosEmLinha(doc, pedacos, pai) {
    for (const p of pedacos) {
      if (p.t === "negrito") {
        const e = doc.createElement("strong");
        e.textContent = p.v;
        pai.appendChild(e);
      } else if (p.t === "codigo") {
        const e = doc.createElement("code");
        e.textContent = p.v;
        pai.appendChild(e);
      } else {
        pai.appendChild(doc.createTextNode(p.v));
      }
    }
  }

  // Devolve um DocumentFragment (ou o equivalente do `doc` recebido).
  function renderizar(doc, texto) {
    const frag = doc.createDocumentFragment();
    for (const b of analisar(texto)) {
      if (b.tipo === "p") {
        const e = doc.createElement("p");
        nosEmLinha(doc, b.inline, e);
        frag.appendChild(e);
      } else if (b.tipo === "lista") {
        const ul = doc.createElement(b.ordenada ? "ol" : "ul");
        for (const item of b.itens) {
          const li = doc.createElement("li");
          nosEmLinha(doc, item, li);
          ul.appendChild(li);
        }
        frag.appendChild(ul);
      } else {
        const pre = doc.createElement("pre");
        const code = doc.createElement("code");
        code.textContent = b.v;
        pre.appendChild(code);
        frag.appendChild(pre);
      }
    }
    return frag;
  }

  return { analisar, renderizar, LIMITE_TEXTO };
});
