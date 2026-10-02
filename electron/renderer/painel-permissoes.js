// painel-permissoes.js — a tela "O que o DERVS pode fazer": liga e desliga permissões.
//
// Duas partes: funções PURAS (rótulos, teto, linhas) que têm teste em Node, e a parte de
// tela, que só roda dentro do Electron. Os rótulos das categorias e os níveis permitidos
// de cada uma VÊM DO PYTHON: aqui só se traduz o nível em português claro.
//
// Segurança dura do projeto: todo texto entra por textContent, nunca innerHTML. A tela só
// PEDE; quem valida e grava é o Python (e ele recusa o que a política não permite).

(function (raiz, fabrica) {
  const api = fabrica();
  if (typeof module === "object" && module.exports) module.exports = api;
  else raiz.PainelPermissoes = api;
  if (typeof document !== "undefined" && raiz.dervs && raiz.dervs.aoPermissoes) api.iniciarTela(raiz, document);
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TETO_MIN = 0.01;
  const TETO_MAX = 1000;
  // Se o Python não responder neste tempo, a tela avisa e oferece "Tentar de novo"
  // em vez de ficar presa em "Carregando..." para sempre.
  const TEMPO_RESPOSTA_MS = 6000;

  const NIVEIS = {
    analisa: { rotulo: "Só analisa", dica: "O DERVS olha e explica, mas não age." },
    pergunta: { rotulo: "Pergunta antes", dica: "O DERVS mostra um cartão e espera o seu sim." },
    sozinho: { rotulo: "Faz sozinho", dica: "O DERVS faz sem perguntar e registra aqui embaixo." },
  };

  function rotuloDoNivel(nivel) {
    return (NIVEIS[nivel] || { rotulo: String(nivel) }).rotulo;
  }

  function dicaDoNivel(nivel) {
    return (NIVEIS[nivel] || { dica: "" }).dica;
  }

  // Só os níveis que o Python disse serem permitidos para a categoria, na ordem fixa.
  function niveisDaCategoria(permitidos, categoria) {
    const lista = permitidos && Array.isArray(permitidos[categoria]) ? permitidos[categoria] : [];
    return Object.keys(NIVEIS).filter((n) => lista.includes(n));
  }

  // "0,5" e "0.5" valem; vazio, lixo ou fora de 0,01 a 1000 devolvem null.
  function lerTeto(texto) {
    if (typeof texto !== "string") return null;
    const limpo = texto.trim().replace(",", ".");
    if (!/^\d{1,4}(\.\d{1,2})?$/.test(limpo)) return null;
    const n = Number(limpo);
    return n >= TETO_MIN && n <= TETO_MAX ? n : null;
  }

  function formatarUsd(valor) {
    const n = Number(valor);
    return `US$ ${(Number.isFinite(n) ? n : 0).toFixed(2).replace(".", ",")}`;
  }

  function textoDoTeto(valor) {
    const n = Number(valor);
    return Number.isFinite(n) ? String(n).replace(".", ",") : "";
  }

  function frasePorGasto(gasto, teto) {
    return `Gasto de hoje: ${formatarUsd(gasto)} de um teto de ${formatarUsd(teto)}.`;
  }

  function linhaRecente(r, rotulos) {
    const cat = (rotulos && rotulos[r.categoria]) || r.categoria || "";
    return { titulo: `${r.quando || ""} · ${cat}`.trim(), detalhe: `${r.ferramenta || ""} ${r.resumo || ""}`.trim() };
  }

  // ------------------------------------------------------------------ tela
  function iniciarTela(janela, doc) {
    const $ = (id) => doc.getElementById(id);
    const dialogo = $("p-dialogo-permissoes");
    if (!dialogo) return;
    const d = janela.dervs;
    let ultimo = null;
    let relogio = null;
    const tentar = doc.createElement("button");
    tentar.type = "button";
    tentar.className = "p-mini";
    tentar.id = "perm-tentar";
    tentar.textContent = "TENTAR DE NOVO";
    tentar.hidden = true;
    $("perm-mensagem").after(tentar);

    function el(tag, classe, texto) {
      const e = doc.createElement(tag);
      if (classe) e.className = classe;
      if (texto !== undefined) e.textContent = texto;
      return e;
    }

    // Espera a resposta do Python; sem ela em 6 s, avisa e mostra o botão de repetir.
    function esperarResposta(texto, repetir) {
      mensagem(texto);
      tentar.hidden = true;
      clearTimeout(relogio);
      relogio = setTimeout(() => {
        mensagem("O DERVS não respondeu. Tente de novo.", false);
        tentar.onclick = repetir;
        tentar.hidden = false;
      }, TEMPO_RESPOSTA_MS);
    }

    function respondeu() {
      clearTimeout(relogio);
      tentar.hidden = true;
    }

    function mensagem(texto, ok) {
      const m = $("perm-mensagem");
      m.textContent = texto || "";
      if (ok === undefined) m.removeAttribute("data-ok");
      else m.setAttribute("data-ok", ok ? "1" : "0");
    }

    function desenharCategoria(cat, e) {
      const li = el("li", "integ-item perm-item");
      const corpo = el("div", "integ-item-corpo");
      corpo.appendChild(el("strong", "central-rotulo", (e.rotulos && e.rotulos[cat]) || cat));
      li.appendChild(corpo);
      const grupo = el("div", "perm-niveis");
      grupo.setAttribute("role", "group");
      grupo.setAttribute("aria-label", (e.rotulos && e.rotulos[cat]) || cat);
      for (const nivel of niveisDaCategoria(e.permitidos, cat)) {
        const b = el("button", "p-mini perm-nivel", rotuloDoNivel(nivel));
        b.type = "button";
        b.dataset.cat = cat;
        b.dataset.nivel = nivel;
        b.title = dicaDoNivel(nivel);
        const atual = e.niveis && e.niveis[cat] === nivel;
        b.setAttribute("aria-pressed", atual ? "true" : "false");
        b.addEventListener("click", () => {
          if (e.niveis && e.niveis[cat] === nivel) return;
          esperarResposta("Salvando...", () => d.permissoesDefinir(cat, nivel));
          d.permissoesDefinir(cat, nivel);
        });
        grupo.appendChild(b);
      }
      li.appendChild(grupo);
      return li;
    }

    function desenhar(e) {
      ultimo = e;
      // Recriar os botões tira o foco de quem usa o teclado: guarda e devolve.
      const foco = doc.activeElement && doc.activeElement.dataset && doc.activeElement.dataset.cat
        ? { cat: doc.activeElement.dataset.cat, nivel: doc.activeElement.dataset.nivel } : null;
      const cats = Array.isArray(e.categorias) ? e.categorias : [];
      $("perm-lista").replaceChildren(...cats.map((c) => desenharCategoria(c, e)));
      if (foco) {
        const volta = Array.from($("perm-lista").querySelectorAll("button")).find(
          (x) => x.dataset.cat === foco.cat && x.dataset.nivel === foco.nivel);
        if (volta) volta.focus();
      }
      $("perm-gasto").textContent = frasePorGasto(e.gasto_hoje, e.teto);
      const campo = $("perm-teto");
      if (doc.activeElement !== campo) campo.value = textoDoTeto(e.teto);
      const rec = Array.isArray(e.recentes) ? e.recentes : [];
      $("perm-recentes").replaceChildren(...rec.map((r) => {
        const li = el("li", "integ-item");
        const corpo = el("div", "integ-item-corpo");
        const linha = linhaRecente(r, e.rotulos);
        corpo.appendChild(el("strong", "central-rotulo", linha.titulo));
        corpo.appendChild(el("span", "central-nota-pequena perm-texto", linha.detalhe));
        li.appendChild(corpo);
        return li;
      }));
      $("perm-recentes-vazio").hidden = rec.length > 0;
    }

    function abrir() {
      if (!dialogo.open) dialogo.showModal();
      $("perm-titulo").focus();
      esperarResposta("Carregando...", abrir);
      d.permissoesPedir();
    }

    $("p-abrir-permissoes").addEventListener("click", abrir);
    $("perm-fechar").addEventListener("click", () => dialogo.close());
    $("perm-teto-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const valor = lerTeto($("perm-teto").value);
      if (valor === null) {
        mensagem("O teto diário precisa ficar entre US$ 0,01 e US$ 1000. Nada foi mudado.", false);
        return;
      }
      esperarResposta("Salvando...", () => d.permissoesTeto(valor));
      d.permissoesTeto(valor);
    });

    d.aoPermissoes((m) => {
      if (!m || typeof m.parte !== "string") return;
      respondeu();
      if (m.parte === "estado" && m.niveis && typeof m.niveis === "object") {
        desenhar(m);
        if ($("perm-mensagem").textContent === "Carregando...") mensagem("");
      } else if (m.parte === "mensagem") {
        mensagem(typeof m.texto === "string" ? m.texto : "", m.ok === true);
        if (m.ok !== true && ultimo) desenhar(ultimo);   // volta ao que está de fato salvo
      }
    });
  }

  return { rotuloDoNivel, dicaDoNivel, niveisDaCategoria, lerTeto, formatarUsd, textoDoTeto,
    frasePorGasto, linhaRecente, iniciarTela, TEMPO_RESPOSTA_MS };
});
