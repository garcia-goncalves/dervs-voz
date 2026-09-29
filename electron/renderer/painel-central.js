// painel-central.js — a Central do PC dentro do painel (onda D).
//
// Duas partes: funções PURAS (formatar, decidir o que o clique pode aprovar) que
// têm teste em Node, e a parte de tela, que só roda dentro do Electron.
//
// Segurança dura do projeto: tudo que chega do Python (nome de arquivo, de
// programa, texto de evento) é conteúdo hostil — sempre textContent, nunca
// innerHTML. O CARTÃO que acompanha o relatório fica só numa variável desta
// função e volta uma vez, no clique de aprovar; a caixa de aprovar começa
// SEMPRE desmarcada e não existe "marcar tudo".

(function (raiz, fabrica) {
  const api = fabrica();
  if (typeof module === "object" && module.exports) module.exports = api;
  else raiz.PainelCentral = api;
  if (typeof document !== "undefined" && raiz.dervs && raiz.dervs.aoCentral) api.iniciarTela(raiz, document);
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function virgula(n, casas) {
    return n.toFixed(casas).replace(".", ",");
  }

  function formatarBytes(n) {
    if (!Number.isFinite(n) || n < 0) return "--";
    if (n >= 1024 ** 3) return `${virgula(n / 1024 ** 3, 1)} GB`;
    if (n >= 1024 ** 2) return `${Math.round(n / 1024 ** 2)} MB`;
    if (n >= 1024) return `${Math.round(n / 1024)} KB`;
    return `${Math.round(n)} B`;
  }

  // "ok" a partir de 80, "atencao" de 50 a 79, "alerta" abaixo — só cor e texto de apoio.
  function faixaDaNota(nota) {
    if (!Number.isFinite(nota)) return "sem";
    if (nota >= 80) return "ok";
    if (nota >= 50) return "atencao";
    return "alerta";
  }

  function rotuloDaFaixa(faixa) {
    return { ok: "em ordem", atencao: "pede atenção", alerta: "pede cuidado", sem: "ainda não analisado" }[faixa];
  }

  function rotuloRisco(risco) {
    return { baixo: "risco baixo", medio: "risco médio", alto: "risco alto" }[risco] || "risco desconhecido";
  }

  // "Valid" é assinado; "NotSigned" não tem assinatura; qualquer outra coisa
  // legível é assinatura com problema; sem leitura, não afirma nada.
  function rotuloAssinatura(status) {
    if (status === "Valid") return "assinado";
    if (status === "NotSigned") return "sem assinatura";
    if (!status || status === "Desconhecida") return "";
    return "assinatura com problema";
  }

  function nomeDoCaminho(caminho) {
    const partes = String(caminho || "").split(/[\\/]/).filter(Boolean);
    return partes.length ? partes[partes.length - 1] : String(caminho || "");
  }

  // O que o clique manda: só os itens MARCADOS. Risco alto pede a segunda caixa,
  // e sem ela o botão fica desligado (o motor confere de novo do outro lado).
  function decidirAprovacao(itens, marcados, confirmadosAlto) {
    const ids = [];
    const dupla = [];
    let faltaConfirmar = false;
    for (const item of itens) {
      if (!marcados.has(item.id)) continue;
      ids.push(item.id);
      if (item.risco === "alto") {
        if (confirmadosAlto.has(item.id)) dupla.push(item.id);
        else faltaConfirmar = true;
      }
    }
    return { ids, dupla, pode: ids.length > 0 && !faltaConfirmar, faltaConfirmar };
  }

  function haQuantoTempoLeitura(iso, agoraMs) {
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return "";
    const min = Math.max(0, Math.round((agoraMs - t) / 60000));
    if (min < 1) return "agora há pouco";
    if (min < 60) return `há ${min} min`;
    if (min < 1440) return `há ${Math.round(min / 60)} h`;
    return `há ${Math.round(min / 1440)} dia(s)`;
  }

  // ------------------------------------------------------------------ tela
  function iniciarTela(janela, doc) {
    const $ = (id) => doc.getElementById(id);
    const dialogo = $("p-dialogo-central");
    if (!dialogo) return;
    const d = janela.dervs;
    const estado = { relatorio: null, cartao: null, marcados: new Set(), altos: new Set(), enviando: false };

    function el(tag, classe, texto) {
      const e = doc.createElement(tag);
      if (classe) e.className = classe;
      if (texto !== undefined) e.textContent = texto;
      return e;
    }

    function preencher(lista, itens, montar, vazio) {
      lista.replaceChildren(...itens.map(montar));
      const aviso = vazio && $(vazio);
      if (aviso) aviso.hidden = itens.length > 0;
    }

    function linha(...partes) {
      const li = el("li", "central-linha");
      for (const [classe, texto] of partes) li.appendChild(el("span", classe, texto));
      return li;
    }

    function desenharVisao(v) {
      const faixa = faixaDaNota(v.nota);
      const nota = $("central-nota");
      nota.textContent = v.nota === null || v.nota === undefined ? "--" : String(v.nota);
      nota.setAttribute("data-faixa", faixa);
      $("central-faixa").textContent = rotuloDaFaixa(faixa);
      $("p-central-nota").textContent = nota.textContent;
      $("p-abrir-central").setAttribute("data-estado", faixa === "alerta" ? "alerta" : faixa === "ok" ? "ok" : "");
      $("central-quando").textContent = v.coletado_em ? `análise ${haQuantoTempoLeitura(v.coletado_em, Date.now())}` : "";
      $("central-analisar").disabled = Boolean(v.em_andamento);
      if (!v.em_andamento) $("central-progresso").textContent = "";
      const tend = v.tendencia || {};
      const resumo = (v.resumo || []).slice();
      if (Number.isFinite(tend.nota_ha_7_dias) && Number.isFinite(v.nota)) {
        const dif = v.nota - tend.nota_ha_7_dias;
        resumo.push(dif === 0 ? "A nota está igual à de 7 dias atrás."
          : `A nota ${dif > 0 ? "subiu" : "caiu"} ${Math.abs(dif)} ponto(s) em relação a 7 dias atrás.`);
      }
      preencher($("central-resumo"), resumo, (t) => el("li", "central-frase", t));
      const semLeitura = (v.sem_leitura || []).length;
      const admin = (v.precisa_admin || []).length;
      $("central-aviso-leitura").textContent = [
        semLeitura ? `${semLeitura} leitura(s) falharam, então a nota pode estar incompleta.` : "",
        admin ? `${admin} leitura(s) só funcionam abrindo o DERVS como administrador.` : "",
      ].filter(Boolean).join(" ");
      $("central-aviso-leitura").hidden = !semLeitura && !admin;

      preencher($("central-descontos"), v.descontos || [], (x) => {
        const li = el("li", "central-desconto");
        li.appendChild(el("span", "central-pontos", `−${x.pontos}`));
        const corpo = el("span", "central-desconto-corpo");
        corpo.appendChild(el("strong", "", x.frase));
        if (x.explicacao) corpo.appendChild(el("span", "central-nota-pequena", x.explicacao));
        li.appendChild(corpo);
        const b = el("button", "p-mini", "EXPLICAR MELHOR");
        b.type = "button";
        b.title = "Manda só este item ao Claude, que explica em palavras simples";
        b.addEventListener("click", () => { d.centralExplicar(x.codigo); b.disabled = true; });
        li.appendChild(b);
        return li;
      }, "central-descontos-vazio");

      preencher($("central-discos"), v.discos || [], (x) => {
        const li = el("li", "central-disco");
        li.appendChild(linha(["central-rotulo", x.volume],
          ["", `${virgula(Number(x.pct_livre) || 0, 0)}% livre · ${formatarBytes(x.livre_bytes)} de ${formatarBytes(x.total_bytes)}`],
          ["central-nota-pequena", x.saude && x.saude !== "Desconhecida" ? `saúde: ${x.saude}` : ""]));
        const barra = el("div", "p-barra");
        const cheia = el("span", "p-barra-cheia");
        cheia.style.width = `${Math.min(100, Math.max(0, 100 - (Number(x.pct_livre) || 0)))}%`;
        barra.appendChild(cheia);
        li.appendChild(barra);
        return li;
      });
      const enche = Object.entries(tend.enche_em_dias || {}).filter(([, dias]) => Number.isFinite(dias));
      $("central-tendencia").textContent = enche
        .map(([vol, dias]) => `No ritmo atual, ${vol} enche em cerca de ${Math.round(dias)} dia(s).`).join(" ");

      preencher($("central-temporarios"), v.temporarios || [], (t) =>
        linha(["central-rotulo", t.nome], ["", formatarBytes(t.tamanho_bytes)],
          ["central-nota-pequena", t.antigos_bytes ? `${formatarBytes(t.antigos_bytes)} com mais de 7 dias` : ""]));
      preencher($("central-informativos"), v.so_informativos || [], (t) =>
        linha(["central-rotulo", t.nome], ["", formatarBytes(t.tamanho_bytes)],
          ["central-nota-pequena", "só informação: use a Limpeza de Disco do Windows"]));

      preencher($("central-eventos"), v.eventos || [], (e) =>
        linha(["central-rotulo", `${e.fonte} #${e.id}`], ["", `${e.quantidade}×`],
          ["central-nota-pequena", e.explicacao]), "central-eventos-vazio");
      preencher($("central-programas"), v.programas_desatualizados || [], (p) =>
        linha(["central-rotulo", p.nome], ["", `${p.versao_instalada} → ${p.versao_nova}`]),
        "central-programas-vazio");
      const ini = v.inicializacao || { total: 0, ativos: [] };
      $("central-inicializacao").textContent = ini.total
        ? `${ini.ativos.length} de ${ini.total} programas abrem sozinhos com o Windows: ${ini.ativos.join(", ")}.` : "";
      preencher($("central-processos"), v.processos || [], (p) =>
        linha(["central-rotulo", p.nome], ["", `${virgula(Number(p.cpu_pct) || 0, 1)}% CPU · ${formatarBytes(p.memoria_bytes)}`],
          ["central-nota-pequena", rotuloAssinatura(p.assinatura)]));
      preencher($("central-repositorios"), v.repositorios || [], (r) =>
        linha(["central-rotulo", r.nome], ["", r.ahead ? `${r.ahead} commit(s) sem push` : ""],
          ["central-nota-pequena", r.sujo ? "há mudanças não salvas" : ""]), "central-repositorios-vazio");
      desenharQuarentena(v.quarentena || []);
    }

    function desenharQuarentena(itens) {
      preencher($("central-quarentena"), itens, (q) => {
        const li = el("li", "central-linha");
        li.appendChild(el("span", "central-rotulo", nomeDoCaminho(q.alvo)));
        li.appendChild(el("span", "", formatarBytes(q.tamanho_bytes)));
        li.appendChild(el("span", "central-nota-pequena", `de ${q.quando}`));
        const b = el("button", "p-mini", "DESFAZER");
        b.type = "button";
        b.addEventListener("click", () => { b.disabled = true; d.centralDesfazer(q.desfazer_id); });
        li.appendChild(b);
        return li;
      }, "central-quarentena-vazio");
    }

    function reavaliarAprovar() {
      const itens = estado.relatorio ? estado.relatorio.itens : [];
      const r = decidirAprovacao(itens, estado.marcados, estado.altos);
      $("central-aprovar").disabled = !r.pode || estado.enviando;
      $("central-aprovar-dica").textContent = r.faltaConfirmar
        ? "Item de risco alto marcado: confirme na segunda caixa dele." : "";
    }

    function desenharRelatorio(rel) {
      estado.marcados = new Set();
      estado.altos = new Set();
      $("central-relatorio").hidden = false;
      $("central-relatorio-resumo").textContent = rel.itens.length
        ? `${rel.itens.length} item(ns), ${formatarBytes(rel.total_bytes)} no total. Marque um a um o que pode ir para a quarentena. Este relatório vale 15 minutos.`
        : "Nada seguro para limpar nesta análise.";
      preencher($("central-relatorio-itens"), rel.itens, (i) => {
        const li = el("li", "central-item");
        li.setAttribute("data-risco", i.risco);
        const rotulo = el("label", "central-item-titulo");
        const caixa = doc.createElement("input");
        caixa.type = "checkbox";
        caixa.checked = false;
        caixa.addEventListener("change", () => {
          if (caixa.checked) estado.marcados.add(i.id); else { estado.marcados.delete(i.id); estado.altos.delete(i.id); }
          reavaliarAprovar();
        });
        rotulo.appendChild(caixa);
        rotulo.appendChild(el("strong", "", ` ${nomeDoCaminho(i.alvo)} `));
        rotulo.appendChild(el("span", "central-nota-pequena", `${formatarBytes(i.tamanho_bytes)} · ${rotuloRisco(i.risco)}`));
        li.appendChild(rotulo);
        li.appendChild(el("p", "central-detalhe", `O que é: ${i.o_que_e}`));
        li.appendChild(el("p", "central-detalhe", `Por que é seguro: ${i.por_que_seguro}`));
        li.appendChild(el("p", "central-detalhe", `O que muda: ${i.o_que_muda}`));
        li.appendChild(el("p", "central-detalhe", `Como desfazer: ${i.como_desfazer}`));
        li.appendChild(el("p", "central-nota-pequena", `${i.onde} · ${i.data}`));
        if (i.risco === "alto") {
          const conf = el("label", "central-item-titulo central-confirma");
          const c2 = doc.createElement("input");
          c2.type = "checkbox";
          c2.addEventListener("change", () => {
            if (c2.checked) estado.altos.add(i.id); else estado.altos.delete(i.id);
            reavaliarAprovar();
          });
          conf.appendChild(c2);
          conf.appendChild(el("span", "", " Confirmo: este item é de risco alto"));
          li.appendChild(conf);
        }
        return li;
      });
      preencher($("central-relatorio-recusados"), rel.recusados || [], (r) =>
        linha(["central-rotulo", nomeDoCaminho(r.alvo)], ["central-nota-pequena", `não entra: ${r.motivo}`]));
      $("central-relatorio-recusados-titulo").hidden = !(rel.recusados || []).length;
      reavaliarAprovar();
    }

    function abrir() {
      if (!dialogo.open) dialogo.showModal();
      d.centralPedir();
    }

    $("p-abrir-central").addEventListener("click", abrir);
    $("central-fechar").addEventListener("click", () => dialogo.close());
    $("central-analisar").addEventListener("click", () => {
      $("central-analisar").disabled = true;
      $("central-progresso").textContent = "Começando a análise...";
      d.centralAnalisar();
    });
    $("central-propor").addEventListener("click", () => {
      $("central-resultado").textContent = "Montando o relatório de limpeza...";
      d.centralProporLimpeza();
    });
    $("central-aprovar").addEventListener("click", () => {
      const r = decidirAprovacao(estado.relatorio ? estado.relatorio.itens : [], estado.marcados, estado.altos);
      if (!r.pode || !estado.cartao) return;
      estado.enviando = true;
      $("central-aprovar").disabled = true;
      $("central-resultado").textContent = "Movendo para a quarentena...";
      const pedido = { relatorioId: estado.relatorio.id, ids: r.ids, cartao: estado.cartao, dupla: r.dupla };
      estado.cartao = null;   // o cartão vale uma vez só
      d.centralAprovar(pedido);
    });

    d.aoCentral(desenharVisao);
    d.aoCentralProgresso((p) => {
      if (p && Number.isInteger(p.feitos) && Number.isInteger(p.total)) {
        $("central-progresso").textContent = `Lendo o computador... ${p.feitos} de ${p.total}`;
      }
    });
    d.aoCentralRelatorio((m) => {
      if (!m || !m.relatorio) return;
      estado.relatorio = m.relatorio;
      estado.cartao = m.cartao;
      estado.enviando = false;
      $("central-resultado").textContent = "";
      desenharRelatorio(m.relatorio);
    });
    d.aoCentralResultado((r) => {
      estado.enviando = false;
      const falhas = (r.itens || []).filter((i) => !i.ok);
      $("central-resultado").textContent = [r.motivo, ...falhas.map((i) => `${i.id}: ${i.motivo}`)].join(" ");
      $("central-resultado").setAttribute("data-ok", r.ok ? "1" : "0");
      if (r.itens && r.itens.length) { $("central-relatorio").hidden = true; estado.relatorio = null; }
      d.centralPedir();   // atualiza a lista da quarentena
    });
  }

  return { formatarBytes, faixaDaNota, rotuloDaFaixa, rotuloRisco, rotuloAssinatura, nomeDoCaminho, decidirAprovacao,
    haQuantoTempoLeitura, iniciarTela };
});
