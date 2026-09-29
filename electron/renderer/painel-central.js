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

  const VALIDADE_RELATORIO_MS = 15 * 60 * 1000;
  const PRAZO_SUGESTAO_MS = 45 * 1000;

  function virgula(n, casas) {
    return n.toFixed(casas).replace(".", ",");
  }

  function plural(n, singular, plur) {
    return `${n} ${n === 1 ? singular : plur}`;
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

  function rotuloSaude(saude) {
    return { Healthy: "boa", Warning: "com aviso", Unhealthy: "com problema" }[saude] || "";
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
    let bytes = 0;
    for (const item of itens) {
      if (!marcados.has(item.id)) continue;
      ids.push(item.id);
      bytes += Number(item.tamanho_bytes) || 0;
      if (item.risco === "alto") {
        if (confirmadosAlto.has(item.id)) dupla.push(item.id);
        else faltaConfirmar = true;
      }
    }
    return { ids, dupla, bytes, pode: ids.length > 0 && !faltaConfirmar, faltaConfirmar };
  }

  // O que o botão de aprovar diz a quem olha para ele — sempre uma frase, nunca só "apagado".
  function dicaDoBotao(decisao, vencido) {
    if (vencido) return "Este relatório não vale mais (passou o prazo ou já foi usado). Clique em VER SUGESTÃO DE LIMPEZA para montar outro.";
    if (decisao.ids.length === 0) return "Marque pelo menos um item da lista para liberar o botão.";
    if (decisao.faltaConfirmar) return "Falta a confirmação do item de risco alto (a segunda caixa dele).";
    return "";
  }

  function contadorDeMarcados(decisao) {
    if (decisao.ids.length === 0) return "Nenhum item marcado.";
    return `${plural(decisao.ids.length, "item marcado", "itens marcados")} · ${formatarBytes(decisao.bytes)}`;
  }

  function haQuantoTempoLeitura(iso, agoraMs) {
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return "";
    const min = Math.max(0, Math.round((agoraMs - t) / 60000));
    if (min < 1) return "agora há pouco";
    if (min < 60) return `há ${min} min`;
    if (min < 1440) return `há ${Math.round(min / 60)} h`;
    return `há ${plural(Math.round(min / 1440), "dia", "dias")}`;
  }

  // ------------------------------------------------------------------ tela
  function iniciarTela(janela, doc) {
    const $ = (id) => doc.getElementById(id);
    const dialogo = $("p-dialogo-central");
    if (!dialogo) return;
    const d = janela.dervs;
    const estado = { relatorio: null, cartao: null, marcados: new Set(), altos: new Set(),
      enviando: false, vencido: false, analisado: false, temporizador: null, prazoSugestao: null };

    function el(tag, classe, texto) {
      const e = doc.createElement(tag);
      if (classe) e.className = classe;
      if (texto !== undefined) e.textContent = texto;
      return e;
    }

    function preencher(lista, itens, montar, vazio) {
      lista.replaceChildren(...itens.map(montar));
      const aviso = vazio && $(vazio);
      if (aviso) aviso.hidden = itens.length > 0 || !estado.analisado;
    }

    function linha(...partes) {
      const li = el("li", "central-linha");
      for (const [classe, texto] of partes) if (texto !== "") li.appendChild(el("span", classe, texto));
      return li;
    }

    function limparResultado() {
      $("central-resultado").textContent = "";
      $("central-resultado").removeAttribute("data-ok");
    }

    function mostrarResultado(texto, ok) {
      $("central-resultado").textContent = texto;
      if (ok === undefined) $("central-resultado").removeAttribute("data-ok");
      else $("central-resultado").setAttribute("data-ok", ok ? "1" : "0");
    }

    function desenharVisao(v) {
      estado.analisado = Boolean(v.coletado_em);
      const faixa = faixaDaNota(v.nota);
      const nota = $("central-nota");
      nota.textContent = v.nota === null || v.nota === undefined ? "--" : String(v.nota);
      nota.setAttribute("data-faixa", faixa);
      nota.setAttribute("aria-label", faixa === "sem" ? "Nota de saúde: ainda não analisado"
        : `Nota de saúde: ${v.nota} de 100, ${rotuloDaFaixa(faixa)}`);
      $("central-faixa").textContent = rotuloDaFaixa(faixa);
      $("p-central-nota").textContent = nota.textContent;
      const chip = $("p-abrir-central");
      chip.setAttribute("data-estado", faixa === "alerta" ? "alerta" : faixa === "ok" ? "ok" : "");
      chip.setAttribute("aria-label", faixa === "sem" ? "Central do PC, ainda não analisado"
        : `Central do PC, nota ${v.nota} de 100, ${rotuloDaFaixa(faixa)}`);
      $("central-quando").textContent = v.coletado_em ? `Análise ${haQuantoTempoLeitura(v.coletado_em, Date.now())}` : "";
      $("central-sem-analise").hidden = estado.analisado;
      const ocupado = Boolean(v.em_andamento);
      $("central-analisar").disabled = ocupado;
      $("central-analisar").textContent = ocupado ? "ANALISANDO..." : "ANALISAR AGORA";
      $("central-analisar").setAttribute("aria-busy", ocupado ? "true" : "false");
      if (!ocupado) { $("central-progresso").textContent = ""; $("central-barra").hidden = true; }
      const tend = v.tendencia || {};
      // A nota já aparece grande; a frase "Nota de saúde: N" do resumo falado sobra aqui.
      const resumo = (v.resumo || []).filter((t) => !/^Nota de sa[uú]de/.test(t));
      if (Number.isFinite(tend.nota_ha_7_dias) && Number.isFinite(v.nota)) {
        const dif = v.nota - tend.nota_ha_7_dias;
        resumo.push(dif === 0 ? "A nota está igual à de 7 dias atrás."
          : `A nota ${dif > 0 ? "subiu" : "caiu"} ${plural(Math.abs(dif), "ponto", "pontos")} em relação a 7 dias atrás.`);
      }
      preencher($("central-resumo"), estado.analisado ? resumo : [], (t) => el("li", "central-frase", t));
      const semLeitura = (v.sem_leitura || []).length;
      const admin = (v.precisa_admin || []).length;
      $("central-aviso-leitura").textContent = [
        semLeitura ? `${plural(semLeitura, "leitura falhou", "leituras falharam")}, então a nota pode estar incompleta.` : "",
        admin ? "Uma parte da análise (o detalhe da saúde do disco) só funciona se o DERVS for aberto como administrador." : "",
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
        b.title = "Manda só este item ao Claude, que explica em palavras simples na caixa CLAUDE CODE";
        b.addEventListener("click", () => {
          d.centralExplicar(x.codigo);
          dialogo.close();   // a resposta aparece na caixa CLAUDE CODE, que está atrás desta janela
        });
        li.appendChild(b);
        return li;
      }, "central-descontos-vazio");

      preencher($("central-discos"), v.discos || [], (x) => {
        const li = el("li", "central-disco");
        const saude = rotuloSaude(x.saude);
        li.appendChild(linha(["central-rotulo", x.volume],
          ["", `${virgula(Number(x.pct_livre) || 0, 0)}% livre · ${formatarBytes(x.livre_bytes)} de ${formatarBytes(x.total_bytes)}`],
          ["central-nota-pequena", saude ? `saúde: ${saude}` : ""]));
        const barra = el("div", "p-barra");
        barra.setAttribute("aria-hidden", "true");
        const cheia = el("span", "p-barra-cheia");
        cheia.style.width = `${Math.min(100, Math.max(0, 100 - (Number(x.pct_livre) || 0)))}%`;
        barra.appendChild(cheia);
        li.appendChild(barra);
        return li;
      });
      const enche = Object.entries(tend.enche_em_dias || {}).filter(([, dias]) => Number.isFinite(dias));
      $("central-tendencia").textContent = enche
        .map(([vol, dias]) => `No ritmo atual, ${vol} enche em cerca de ${plural(Math.round(dias), "dia", "dias")}.`).join(" ");

      const soInfo = new Set((v.so_informativos || []).map((t) => t.nome));
      preencher($("central-temporarios"), v.temporarios || [], (t) =>
        linha(["central-rotulo", t.nome], ["", formatarBytes(t.tamanho_bytes)],
          ["central-nota-pequena", soInfo.has(t.nome) ? "só informação: use a Limpeza de Disco do Windows"
            : t.antigos_bytes ? `${formatarBytes(t.antigos_bytes)} com mais de 7 dias` : ""]));

      preencher($("central-eventos"), v.eventos || [], (e) => {
        const li = el("li", "central-linha");
        li.appendChild(el("span", "central-rotulo", `Erro nº ${e.id}`));
        li.appendChild(el("span", "", `${e.quantidade}×`));
        li.appendChild(el("span", "central-nota-pequena", e.explicacao));
        li.appendChild(el("code", "central-codigo", e.fonte));
        return li;
      }, "central-eventos-vazio");
      preencher($("central-programas"), v.programas_desatualizados || [], (p) =>
        linha(["central-rotulo", p.nome], ["", `${p.versao_instalada} → ${p.versao_nova}`]),
        "central-programas-vazio");
      const ini = v.inicializacao || { total: 0, ativos: [] };
      $("central-inicializacao").textContent = ini.total
        ? `${ini.ativos.length} de ${plural(ini.total, "programa", "programas")} abrem sozinhos com o Windows: ${ini.ativos.join(", ")}.` : "";
      preencher($("central-processos"), estado.analisado ? (v.processos || []) : [], (p) =>
        linha(["central-rotulo", p.nome], ["", `${virgula(Number(p.cpu_pct) || 0, 1)}% da CPU · ${formatarBytes(p.memoria_bytes)}`],
          ["central-nota-pequena", rotuloAssinatura(p.assinatura)]));
      preencher($("central-repositorios"), v.repositorios || [], (r) =>
        linha(["central-rotulo", r.nome], ["", r.ahead ? `${plural(r.ahead, "commit", "commits")} sem push` : ""],
          ["central-nota-pequena", r.sujo ? "há mudanças não salvas" : ""]), "central-repositorios-vazio");
      desenharQuarentena(v.quarentena || []);
    }

    function desenharQuarentena(itens) {
      preencher($("central-quarentena"), itens, (q) => {
        const li = el("li", "central-linha");
        li.appendChild(el("span", "central-rotulo", nomeDoCaminho(q.alvo)));
        li.appendChild(el("span", "", formatarBytes(q.tamanho_bytes)));
        li.appendChild(el("span", "central-nota-pequena", `guardado em ${q.quando}`));
        const b = el("button", "p-mini", "DESFAZER");
        b.type = "button";
        b.addEventListener("click", () => {
          b.disabled = true;
          b.textContent = "DESFAZENDO...";
          d.centralDesfazer(q.desfazer_id);
        });
        li.appendChild(b);
        return li;
      });
      $("central-quarentena-vazio").hidden = itens.length > 0;
    }

    function reavaliarAprovar() {
      const itens = estado.relatorio ? estado.relatorio.itens : [];
      const r = decidirAprovacao(itens, estado.marcados, estado.altos);
      const bloqueado = !r.pode || estado.enviando || estado.vencido || !estado.cartao;
      const botao = $("central-aprovar");
      botao.setAttribute("aria-disabled", bloqueado ? "true" : "false");
      botao.classList.toggle("p-mini-desligado", bloqueado);
      $("central-contador").textContent = contadorDeMarcados(r);
      $("central-aprovar-dica").textContent = estado.enviando ? "" : dicaDoBotao(r, estado.vencido || !estado.cartao && estado.relatorio !== null);
      itens.forEach((i) => {
        const confirma = doc.getElementById(`central-confirma-${i.id}`);
        if (confirma) confirma.hidden = !estado.marcados.has(i.id);
      });
    }

    function armarValidade() {
      clearTimeout(estado.temporizador);
      estado.vencido = false;
      estado.temporizador = setTimeout(() => { estado.vencido = true; reavaliarAprovar(); }, VALIDADE_RELATORIO_MS);
      const ate = new Date(Date.now() + VALIDADE_RELATORIO_MS);
      $("central-relatorio-validade").textContent =
        `Este relatório vale até ${String(ate.getHours()).padStart(2, "0")}:${String(ate.getMinutes()).padStart(2, "0")}.`;
    }

    function desenharItem(i) {
      const li = el("li", "central-item");
      li.setAttribute("data-risco", i.risco);
      const rotulo = el("label", "central-item-titulo");
      const caixa = doc.createElement("input");
      caixa.type = "checkbox";
      caixa.checked = false;
      caixa.addEventListener("change", () => {
        if (caixa.checked) estado.marcados.add(i.id); else { estado.marcados.delete(i.id); estado.altos.delete(i.id); }
        li.classList.toggle("central-item-marcado", caixa.checked);
        reavaliarAprovar();
      });
      rotulo.appendChild(caixa);
      rotulo.appendChild(el("strong", "central-item-nome", i.titulo || nomeDoCaminho(i.alvo)));
      rotulo.appendChild(el("span", "central-item-tamanho", formatarBytes(i.tamanho_bytes)));
      if (i.risco !== "baixo") rotulo.appendChild(el("span", "central-risco", i.risco === "alto" ? "ATENÇÃO" : "CUIDADO"));
      li.appendChild(rotulo);
      li.appendChild(el("p", "central-detalhe", i.o_que_e));
      li.appendChild(el("p", "central-detalhe", `O que muda: ${i.o_que_muda}`));
      const det = el("details", "central-mais");
      det.appendChild(el("summary", "", "Ver detalhes"));
      const dl = el("dl", "central-dl");
      for (const [nome, valor] of [["Por que é seguro", i.por_que_seguro], ["Como desfazer", i.como_desfazer],
        ["Nome do arquivo", nomeDoCaminho(i.alvo)], ["Onde está", i.onde], ["Data", i.data],
        ["Detalhe técnico", i.detalhe_tecnico || ""]]) {
        if (!valor) continue;
        dl.appendChild(el("dt", "", nome));
        dl.appendChild(el("dd", "", valor));
      }
      det.appendChild(dl);
      li.appendChild(det);
      if (i.risco === "alto") {
        const conf = el("label", "central-item-titulo central-confirma");
        conf.id = `central-confirma-${i.id}`;
        conf.hidden = true;
        const c2 = doc.createElement("input");
        c2.type = "checkbox";
        c2.addEventListener("change", () => {
          if (c2.checked) estado.altos.add(i.id); else estado.altos.delete(i.id);
          reavaliarAprovar();
        });
        conf.appendChild(c2);
        conf.appendChild(el("span", "", `Entendo o risco: ${i.o_que_muda} Quero mover mesmo assim.`));
        li.appendChild(conf);
      }
      return li;
    }

    function desenharRelatorio(rel) {
      estado.marcados = new Set();
      estado.altos = new Set();
      $("central-relatorio").hidden = false;
      $("central-relatorio-resumo").textContent = rel.itens.length
        ? `${plural(rel.itens.length, "item", "itens")}, ${formatarBytes(rel.total_bytes)} no total. Nada vai para a quarentena sem você marcar.`
        : "Seu computador está limpo por agora: nada seguro para limpar. Volte a olhar depois de uns dias de uso.";
      armarValidade();
      preencher($("central-relatorio-itens"), rel.itens, desenharItem);
      preencher($("central-relatorio-recusados"), rel.recusados || [], (r) =>
        linha(["central-rotulo", nomeDoCaminho(r.alvo)], ["central-nota-pequena", `por segurança, não entra: ${r.motivo}`]));
      $("central-relatorio-recusados-titulo").hidden = !(rel.recusados || []).length;
      $("central-relatorio").querySelector(".central-acao").hidden = rel.itens.length === 0;
      reavaliarAprovar();
      $("central-relatorio-resumo").scrollIntoView({ block: "start" });
      $("central-relatorio-resumo").focus();
    }

    function abrir() {
      if (!dialogo.open) dialogo.showModal();
      $("central-titulo").focus();
      d.centralPedir();
    }

    $("p-abrir-central").addEventListener("click", abrir);
    $("central-fechar").addEventListener("click", () => dialogo.close());
    $("central-analisar").addEventListener("click", () => {
      $("central-analisar").disabled = true;
      $("central-analisar").textContent = "ANALISANDO...";
      $("central-analisar").setAttribute("aria-busy", "true");
      $("central-barra").hidden = false;
      $("central-barra").value = 0;
      $("central-progresso").textContent = "Começando a análise...";
      d.centralAnalisar();
    });
    $("central-propor").addEventListener("click", () => {
      mostrarResultado("Montando o relatório de limpeza...");
      clearTimeout(estado.prazoSugestao);
      estado.prazoSugestao = setTimeout(() => {
        mostrarResultado("Demorou mais que o normal. Tente clicar em VER SUGESTÃO DE LIMPEZA de novo.", false);
      }, PRAZO_SUGESTAO_MS);
      d.centralProporLimpeza();
    });
    $("central-aprovar").addEventListener("click", () => {
      const r = decidirAprovacao(estado.relatorio ? estado.relatorio.itens : [], estado.marcados, estado.altos);
      if (!r.pode || !estado.cartao || estado.vencido || estado.enviando) return;   // botão "apagado" não age
      estado.enviando = true;
      reavaliarAprovar();
      mostrarResultado("Movendo para a quarentena...");
      const pedido = { relatorioId: estado.relatorio.id, ids: r.ids, cartao: estado.cartao, dupla: r.dupla };
      estado.cartao = null;   // o cartão vale uma vez só
      d.centralAprovar(pedido);
    });

    d.aoCentral(desenharVisao);
    d.aoCentralProgresso((p) => {
      if (p && Number.isInteger(p.feitos) && Number.isInteger(p.total)) {
        $("central-barra").max = Math.max(1, p.total);
        $("central-barra").value = p.feitos;
        $("central-progresso").textContent = `Lendo o computador... ${p.feitos} de ${p.total}`;
      }
    });
    d.aoCentralRelatorio((m) => {
      if (!m || !m.relatorio) return;
      clearTimeout(estado.prazoSugestao);
      estado.relatorio = m.relatorio;
      estado.cartao = m.cartao;
      estado.enviando = false;
      limparResultado();
      desenharRelatorio(m.relatorio);
    });
    d.aoCentralResultado((r) => {
      clearTimeout(estado.prazoSugestao);
      const eraAprovacao = estado.enviando;
      estado.enviando = false;
      const falhas = (r.itens || []).filter((i) => !i.ok);
      const nomes = estado.relatorio ? new Map(estado.relatorio.itens.map((i) => [i.id, i.titulo || nomeDoCaminho(i.alvo)])) : new Map();
      let texto = [r.motivo, ...falhas.map((i) => `${nomes.get(i.id) || "Um item"}: ${i.motivo}`)].join(" ");
      if (eraAprovacao && !(r.itens && r.itens.length)) {
        texto = `Não consegui mover. ${r.motivo} Clique em VER SUGESTÃO DE LIMPEZA para montar outro relatório.`;
        estado.cartao = null;
        reavaliarAprovar();
        $("central-propor").focus();
      }
      mostrarResultado(texto, r.ok);
      if (r.itens && r.itens.length) { $("central-relatorio").hidden = true; estado.relatorio = null; clearTimeout(estado.temporizador); }
      d.centralPedir();   // atualiza a lista da quarentena
    });
  }

  return { plural, formatarBytes, faixaDaNota, rotuloDaFaixa, rotuloRisco, rotuloSaude, rotuloAssinatura,
    nomeDoCaminho, decidirAprovacao, dicaDoBotao, contadorDeMarcados, haQuantoTempoLeitura, iniciarTela };
});
