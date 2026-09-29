// painel.js — a janela grande do DERVS (JARVIS).
//
// Um único laço de animação (o reator central), com cadência decidida por
// PainelFormato.msPorQuadro: 30 quadros/s com foco, 10 sem foco, parado quando a
// janela está escondida (Page Visibility + focus/blur). Todo o resto (sistema,
// agenda, diário, conversa, ações, gasto) é dado que chega por eventos e só
// mexe no DOM quando chega — nada roda em laço.
//
// Segurança dura do projeto: texto vindo de fora (conversa, título de lembrete,
// frase de erro) é conteúdo hostil — sempre textContent, nunca innerHTML.

(() => {
  "use strict";

  const F = window.PainelFormato;
  const CORES = {
    acento: "#00E5FF",
    acentoFraco: "#0A6E82",
    nucleoQuente: "#FFFFFF",
    erro: "#FF3B3B",
  };
  const PONTOS_HISTORICO = 30;      // 30 leituras x ~2 s = últimos ~60 s
  const MAX_CONVERSA = 6;
  const MAX_ACOES = 6;
  const MAX_AGENDA = 6;
  const MAX_DIARIO = 5;

  const $ = (id) => document.getElementById(id);

  // ---- estado -------------------------------------------------------------

  const painel = {
    estado: "ocioso",
    volumeAlvo: 0,
    volumeSuave: 0,
    rotacao: [0, 0, 0, 0],
    velocidade: [0.15, -0.1, 0.08, -0.05],
    cpu: [], ram: [], rede: [],
    microfoneLigado: null,
    reuniaoAtiva: false,
    acoes: [],           // { quandoMs, papel, texto }
  };

  const relogioTexto = $("p-relogio");
  const dataTexto = $("p-data");

  // ---- relógio ---------------------------------------------------------------

  const FORMATADOR_HORA = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const FORMATADOR_DATA = new Intl.DateTimeFormat("pt-BR", {
    weekday: "long", day: "2-digit", month: "long" });

  function atualizarRelogio() {
    const agora = new Date();
    relogioTexto.textContent = FORMATADOR_HORA.format(agora);
    dataTexto.textContent = FORMATADOR_DATA.format(agora);
  }

  // ---- sparklines e medidores -----------------------------------------------

  function desenharSpark(canvas, historico, teto) {
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(canvas.clientWidth * dpr);
    const h = Math.round(canvas.clientHeight * dpr);
    if (!w || !h) return;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    const c = canvas.getContext("2d");
    c.clearRect(0, 0, w, h);
    const pts = F.pontosSparkline(historico, w, h - 3 * dpr, teto);
    if (pts.length < 2) return;
    c.beginPath();
    c.moveTo(pts[0][0], pts[0][1] + 1.5 * dpr);
    for (const [x, y] of pts) c.lineTo(x, y + 1.5 * dpr);
    c.lineWidth = 1.6 * dpr;
    c.strokeStyle = CORES.acento;
    c.stroke();
    c.lineTo(w, h);
    c.lineTo(0, h);
    c.closePath();
    c.globalAlpha = 0.14;
    c.fillStyle = CORES.acento;
    c.fill();
    c.globalAlpha = 1;
  }

  function redesenharSparks() {
    desenharSpark($("s-cpu"), painel.cpu, 100);
    desenharSpark($("s-ram"), painel.ram, 100);
    desenharSpark($("s-rede"), painel.rede);
  }

  function aoSistema(d) {
    if (!d || typeof d.cpu !== "number" || typeof d.ram !== "number") return;
    painel.cpu = F.empurrar(painel.cpu, d.cpu, PONTOS_HISTORICO);
    painel.ram = F.empurrar(painel.ram, d.ram, PONTOS_HISTORICO);
    $("v-cpu").textContent = F.formatarPercentual(d.cpu);
    $("v-ram").textContent = F.formatarPercentual(d.ram);
    if (typeof d.discoLivreGb === "number" && typeof d.discoTotalGb === "number" && d.discoTotalGb > 0) {
      const usado = 100 * (1 - d.discoLivreGb / d.discoTotalGb);
      $("v-disco-pct").textContent = F.formatarPercentual(usado);
      $("v-disco").textContent = F.formatarDisco(d.discoLivreGb, d.discoTotalGb);
      $("b-disco").style.width = Math.max(0, Math.min(100, usado)) + "%";
    }
    if (typeof d.redeBaixaKbs === "number" && typeof d.redeSobeKbs === "number") {
      painel.rede = F.empurrar(painel.rede, d.redeBaixaKbs, PONTOS_HISTORICO);
      $("v-rede-baixa").textContent = F.formatarKbs(d.redeBaixaKbs);
      $("v-rede-sobe").textContent = F.formatarKbs(d.redeSobeKbs);
    }
    $("p-sistema-vazio").hidden = true;
    if (!document.hidden) redesenharSparks();
  }

  // ---- estado, volume, erro -------------------------------------------------

  function aoEstado({ valor, texto, apoio } = {}) {
    if (typeof valor !== "string") return;
    painel.estado = valor;
    const rot = $("p-estado");
    rot.textContent = F.rotuloDoEstado(valor);
    if (valor === "erro") rot.setAttribute("data-erro", "1"); else rot.removeAttribute("data-erro");
    const erro = $("p-cartao-erro");
    if (valor === "erro") {
      $("p-erro-frase").textContent = texto || "";
      const apoioEl = $("p-erro-apoio");
      apoioEl.textContent = apoio || "";
      apoioEl.hidden = !apoio;
      erro.hidden = false;
    } else {
      erro.hidden = true;
    }
  }

  function aoVolume(v) {
    if (typeof v !== "number" || Number.isNaN(v)) return;
    painel.volumeAlvo = Math.max(0, Math.min(1, v));
  }

  // ---- barra de status ------------------------------------------------------

  function marcarChip(id, estado, textoId, texto) {
    $(id).setAttribute("data-estado", estado);
    $(textoId).textContent = texto;
  }

  function aoMicrofone({ ligado } = {}) {
    if (typeof ligado !== "boolean") return;
    painel.microfoneLigado = ligado;
    $("p-chip-microfone").setAttribute("aria-pressed", String(ligado));
    marcarChip("p-chip-microfone", ligado ? "ok" : "alerta", "p-microfone", ligado ? "LIGADO" : "DESLIGADO");
  }

  function aoVoz({ motor } = {}) {
    if (motor === "nuvem") marcarChip("p-chip-voz", "ok", "p-voz", "NUVEM");
    else if (motor === "local") marcarChip("p-chip-voz", "ok", "p-voz", "LOCAL");
  }

  function atualizarInternet() {
    const on = navigator.onLine;
    marcarChip("p-chip-internet", on ? "ok" : "alerta", "p-internet", on ? "ONLINE" : "SEM INTERNET");
  }

  function aoGasto(g) {
    if (!g || typeof g.total !== "number") return;
    $("p-gasto").textContent = F.formatarUsd(g.total);
    const n = (v) => F.formatarUsd(v).replace("US$ ", "");
    $("p-gasto-detalhe").textContent =
      `voz ${n(g.tts || 0)} · escuta ${n(g.stt || 0)} · cérebro ${n(g.cerebro || 0)}`;
  }

  // O Python é dono do temporizador da reunião: o clique só PEDE, e o botão só
  // muda de cara quando o Python responde (mesma regra do microfone).
  function aoReuniao({ restanteS } = {}) {
    const chip = $("p-chip-reuniao");
    if (restanteS === null) {
      painel.reuniaoAtiva = false;
      chip.setAttribute("aria-pressed", "false");
      chip.removeAttribute("data-estado");
      $("p-reuniao").textContent = "--";
      return;
    }
    if (!Number.isInteger(restanteS) || restanteS < 0) return;
    painel.reuniaoAtiva = true;
    chip.setAttribute("aria-pressed", "true");
    chip.setAttribute("data-estado", "ok");
    $("p-reuniao").textContent = F.tempoRestante(restanteS);
  }

  // ---- cartão de plano (diálogo modal) ----------------------------------------
  // O Python manda o plano/passo a confirmar; sem resposta nada executa. Todo
  // texto entra por textContent. `cartaoId` volta junto na resposta (o Python
  // descarta duplicata/atraso).

  const dialogoPlano = $("p-dialogo-plano");
  const elPlanoPergunta = $("cartao-plano-pergunta");
  const elPlanoPassos = $("cartao-plano-passos");
  const elPlanoComando = $("cartao-plano-comando");
  const elAutorizacaoEnvolucro = $("cartao-plano-autorizacao-envolucro");
  const elAutorizacaoCaixa = $("cartao-plano-autorizacao-caixa");
  const elAutorizacaoTexto = $("cartao-plano-autorizacao-texto");
  const botaoConfirmar = $("botao-confirmar");
  const botaoCancelar = $("botao-cancelar");
  let planoPrecisaAutorizacao = false;
  let planoCartaoId = null;
  let planoPendente = false;   // cartão aberto e ainda sem resposta

  function fecharDialogoPlano() {
    planoPendente = false;
    if (dialogoPlano.open) dialogoPlano.close();
    elPlanoPassos.textContent = "";
    elPlanoComando.hidden = true;
    elPlanoComando.textContent = "";
    elAutorizacaoEnvolucro.hidden = true;
    elAutorizacaoCaixa.checked = false;
    planoPrecisaAutorizacao = false;
  }

  function aoPlano({ passos, pergunta, cartaoId } = {}) {
    // Todo evento novo de cartão (inclusive o que limpa a tela) reabilita os
    // botões: evita clique repetido, além da proteção por cartaoId.
    botaoConfirmar.disabled = false;
    botaoCancelar.disabled = false;
    planoCartaoId = cartaoId !== undefined ? cartaoId : null;

    const lista = Array.isArray(passos) ? passos : [];
    if (lista.length === 0) { fecharDialogoPlano(); return; }

    elPlanoPergunta.textContent = pergunta || "";
    limpar(elPlanoPassos);
    for (const passo of lista) {
      const li = criar("li", "", (passo && typeof passo.rotulo === "string") ? passo.rotulo : "");
      li.setAttribute("data-nivel", (passo && typeof passo.nivel === "string") ? passo.nivel : "reversivel");
      elPlanoPassos.appendChild(li);
    }

    // Só o cartão de PASSO ÚNICO traz comando e pedido de autorização.
    const unico = lista.length === 1 ? lista[0] : null;
    if (unico && typeof unico.comando === "string" && unico.comando) {
      elPlanoComando.textContent = unico.comando;
      elPlanoComando.hidden = false;
    } else {
      elPlanoComando.textContent = "";
      elPlanoComando.hidden = true;
    }
    planoPrecisaAutorizacao = Boolean(unico && unico.precisa_autorizacao);
    elAutorizacaoCaixa.checked = false;
    if (planoPrecisaAutorizacao) {
      elAutorizacaoTexto.textContent =
        typeof unico.texto_autorizacao === "string" && unico.texto_autorizacao
          ? unico.texto_autorizacao
          : "Tenho autorização (é meu, laboratório, ou por escrito)";
    }
    elAutorizacaoEnvolucro.hidden = !planoPrecisaAutorizacao;

    planoPendente = true;
    if (!dialogoPlano.open) dialogoPlano.showModal();
    // O foco inicial vai para Cancelar: um Enter/Espaço que o dono já estava
    // apertando em outro programa nunca confirma um plano sem ele ter lido.
    botaoCancelar.focus();
  }

  botaoConfirmar.addEventListener("click", () => {
    // Passo que pede autorização sem a caixa marcada: não manda (a checagem de
    // verdade é sempre do lado do Python).
    if (planoPrecisaAutorizacao && !elAutorizacaoCaixa.checked) return;
    botaoConfirmar.disabled = true;
    botaoCancelar.disabled = true;
    window.dervs.responderPlano("confirmar", elAutorizacaoCaixa.checked, planoCartaoId);
    fecharDialogoPlano();
  });

  botaoCancelar.addEventListener("click", () => {
    botaoConfirmar.disabled = true;
    botaoCancelar.disabled = true;
    window.dervs.responderPlano("cancelar", false, planoCartaoId);
    fecharDialogoPlano();
  });

  // Esc não pode fechar o cartão sem resposta: só os dois botões respondem.
  dialogoPlano.addEventListener("cancel", (e) => e.preventDefault());
  // O Chromium deixa o Esc repetido fechar mesmo com preventDefault: se o cartão
  // fechou sem resposta, reabre — o Python continua esperando esse cartaoId.
  dialogoPlano.addEventListener("close", () => {
    if (planoPendente && !dialogoPlano.open) dialogoPlano.showModal();
  });

  // ---- listas ---------------------------------------------------------------

  function limpar(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function criar(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function aoAgenda({ itens } = {}) {
    if (!Array.isArray(itens)) return;
    const lista = $("p-agenda");
    limpar(lista);
    for (const it of itens.slice(0, MAX_AGENDA)) {
      const li = criar("li");
      li.appendChild(criar("span", "p-item-quando", String(it.quando_txt || "")));
      li.appendChild(criar("span", "p-item-texto", String(it.texto || "(sem texto)")));
      lista.appendChild(li);
    }
    $("p-agenda-vazio").hidden = itens.length > 0;
    $("p-agenda-contagem").textContent = itens.length ? `${itens.length} pendente${itens.length > 1 ? "s" : ""}` : "";
  }

  function aoDiarioEntradas({ entradas } = {}) {
    if (!Array.isArray(entradas)) return;
    const lista = $("p-diario");
    limpar(lista);
    for (const e of entradas.slice(0, MAX_DIARIO)) {
      const li = criar("li");
      li.setAttribute("data-acordou", e.acordou ? "1" : "0");
      li.appendChild(criar("span", "p-item-quando", String(e.hora || "")));
      li.appendChild(criar("span", "p-item-texto", e.acordou ? "me chamaram" : "ouvi e ignorei"));
      const p = Number.isInteger(e.palavras) ? e.palavras : 0;
      const d = typeof e.duracao_s === "number" ? e.duracao_s.toFixed(1).replace(".", ",") : "0";
      li.appendChild(criar("span", "p-item-nota", `${p} palavra${p === 1 ? "" : "s"} · ${d} s`));
      lista.appendChild(li);
    }
    $("p-diario-vazio").hidden = entradas.length > 0;
  }

  function aoDiario({ ouvidas, acordou } = {}) {
    if (!Number.isInteger(ouvidas) || !Number.isInteger(acordou)) return;
    $("p-diario-resumo").textContent = `hoje: ${ouvidas} ouvida${ouvidas === 1 ? "" : "s"} · ${acordou} chamada${acordou === 1 ? "" : "s"}`;
  }

  function aoFala({ papel, texto } = {}) {
    if (typeof texto !== "string" || !texto.trim()) return;
    const lista = $("p-conversa");
    const quem = papel === "dono" ? "você" : papel === "erro" ? "erro" : papel === "resultado" ? "resultado" : "DERVS";
    const li = criar("li");
    li.setAttribute("data-papel", papel === "dono" ? "dono" : papel === "erro" ? "erro" : "dervs");
    li.appendChild(criar("span", "p-fala-quem", quem.toUpperCase()));
    li.appendChild(criar("span", "p-fala-texto", texto));
    lista.appendChild(li);
    while (lista.children.length > MAX_CONVERSA) lista.removeChild(lista.firstChild);
    $("p-conversa-vazio").hidden = true;
  }

  function desenharAcoes() {
    const lista = $("p-acoes");
    limpar(lista);
    const agora = Date.now();
    for (const a of painel.acoes.slice(-MAX_ACOES).reverse()) {
      const li = criar("li");
      li.setAttribute("data-papel", a.papel);
      li.appendChild(criar("span", "p-item-quando", F.haQuanto(agora, a.quandoMs)));
      li.appendChild(criar("span", "p-item-texto", a.texto));
      lista.appendChild(li);
    }
    $("p-acoes-vazio").hidden = painel.acoes.length > 0;
  }

  function aoAcao({ papel, texto, ts } = {}) {
    if (typeof texto !== "string" || !texto.trim()) return;
    painel.acoes.push({ quandoMs: Number.isFinite(ts) ? ts : Date.now(), papel: papel === "erro" ? "erro" : "ok", texto: texto.slice(0, 200) });
    if (painel.acoes.length > 30) painel.acoes.shift();
    desenharAcoes();
  }

  // ---- Claude Code (onda B) ---------------------------------------------------
  // A caixa de texto, a resposta em streaming e o pedido de permissão. Tudo que
  // o Claude escreve é DADO hostil: entra só por textContent ou por
  // PainelMarkdown (que também nunca usa innerHTML). Quem decide o que roda é o
  // Python; aqui só se mostra, se pede e se responde.

  const MAX_MSG_CLAUDE = 60;
  const MAX_TEXTO_CLAUDE = 400000;
  const MAX_FILA_PEDIDOS = 20;
  const elConversaClaude = $("p-claude-conversa");
  const elTextoClaude = $("p-claude-texto");
  const claude = { ocupado: false, corpo: null, texto: "", desenhoAgendado: false };

  function claudeOcupado(ligado) {
    claude.ocupado = ligado;
    $("p-claude-estado").textContent = ligado ? "trabalhando…" : "pronto";
    $("p-claude-parar").hidden = !ligado;
    $("p-claude-enviar").disabled = ligado;
  }

  function claudePertoDoFim() {
    return elConversaClaude.scrollHeight - elConversaClaude.scrollTop - elConversaClaude.clientHeight < 48;
  }

  function claudeRolar() { elConversaClaude.scrollTop = elConversaClaude.scrollHeight; }

  function claudeNovaMensagem(papel, quem) {
    const msg = criar("div", "p-claude-msg");
    msg.setAttribute("data-papel", papel);
    msg.appendChild(criar("span", "p-claude-quem", quem));
    const corpo = criar("div", "p-claude-corpo");
    msg.appendChild(corpo);
    claudeAnexar(msg);
    return corpo;
  }

  function claudeAnexar(no) {
    const seguir = claudePertoDoFim();
    elConversaClaude.appendChild(no);
    while (elConversaClaude.children.length > MAX_MSG_CLAUDE) {
      elConversaClaude.removeChild(elConversaClaude.firstChild);
    }
    $("p-claude-vazio").hidden = true;
    if (seguir) claudeRolar();
  }

  // Redesenha a resposta em andamento: no máximo uma vez por quadro (o rAF
  // também some com a janela escondida — o texto acumula e desenha ao voltar).
  function claudeDesenhar() {
    claude.desenhoAgendado = false;
    if (!claude.corpo) return;
    const seguir = claudePertoDoFim();
    limpar(claude.corpo);
    claude.corpo.appendChild(window.PainelMarkdown.renderizar(document, claude.texto));
    if (seguir) claudeRolar();
  }

  function claudeEncerrarBolha() {
    claudeDesenhar();
    claude.corpo = null;
    claude.texto = "";
  }

  function aoClaudeDelta({ texto } = {}) {
    if (typeof texto !== "string" || !texto) return;
    if (!claude.ocupado) claudeOcupado(true);      // resposta puxada por voz
    if (!claude.corpo) {
      claude.corpo = claudeNovaMensagem("claude", "CLAUDE");
      claude.texto = "";
    }
    if (claude.texto.length < MAX_TEXTO_CLAUDE) claude.texto += texto;
    if (!claude.desenhoAgendado) {
      claude.desenhoAgendado = true;
      requestAnimationFrame(claudeDesenhar);
    }
  }

  function aoClaudeFerramenta({ nome, resumo } = {}) {
    if (typeof nome !== "string" || typeof resumo !== "string") return;
    if (!claude.ocupado) claudeOcupado(true);
    claudeEncerrarBolha();                         // o texto seguinte abre outra bolha
    claudeAnexar(criar("div", "p-claude-ferramenta", `▸ ${nome}: ${resumo.slice(0, 200)}`));
  }

  function aoClaudeFim({ ok, custo, erro } = {}) {
    claudeEncerrarBolha();
    if (ok === false) {
      claudeAnexar(criar("div", "p-claude-erro", erro ? `⚠ ${erro}` : "⚠ não terminou"));
    } else if (Number.isFinite(custo) && custo > 0) {
      claudeAnexar(criar("div", "p-claude-nota",
        `uso equivalente ${F.formatarUsd(custo)} (assinatura — não é cobrança)`));
    }
    claudeOcupado(false);
    claudeFecharPedidos();                         // o Python já negou o que sobrou
  }

  function claudeEnviar() {
    const texto = elTextoClaude.value.trim();
    if (!texto || claude.ocupado) return;
    claudeNovaMensagem("voce", "VOCÊ").textContent = texto;
    elTextoClaude.value = "";
    claudeOcupado(true);
    window.dervs.claudePerguntar(texto);
    claudeRolar();
  }

  $("p-claude-form").addEventListener("submit", (e) => { e.preventDefault(); claudeEnviar(); });
  elTextoClaude.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); claudeEnviar(); }
  });
  $("p-claude-parar").addEventListener("click", () => window.dervs.claudeParar());
  $("p-claude-nova").addEventListener("click", () => {
    limpar(elConversaClaude);
    $("p-claude-vazio").hidden = false;
    claude.corpo = null;
    claude.texto = "";
    claudeOcupado(false);
    claudeFecharPedidos();
    window.dervs.claudeNovaConversa();
  });

  // ---- pedido de permissão do Claude (diálogo modal) ---------------------------
  // Foco INICIAL em Negar, nunca em Permitir (lição da revisão da onda A): um
  // Enter que o dono já apertava em outro programa não aprova nada. Esc = Negar.
  // Um pedido de cada vez; o resto espera na fila. O `id` volta na resposta e
  // vale uma vez só no Python.

  const dialogoClaude = $("p-dialogo-claude");
  const botaoPermitirClaude = $("claude-pedido-permitir");
  const botaoNegarClaude = $("claude-pedido-negar");
  const filaPedidos = [];
  let pedidoAtual = null;   // { id, timer, liberar }
  let pedidosRecusadosPorExcesso = 0;
  // Permitir só habilita depois deste atraso, a cada abertura: um duplo clique (ou
  // um Enter que sobrou) não aprova o pedido seguinte sem o dono ter lido.
  const ATRASO_PERMITIR_MS = 700;

  function claudeAbrirProximoPedido() {
    const p = filaPedidos.shift();
    if (!p) return;
    const prazoMs = Math.max(1, Number(p.expiraS) || 300) * 1000;
    pedidoAtual = { id: p.id, timer: setTimeout(claudeFecharPedidoAtual, prazoMs), liberar: null };
    $("claude-pedido-titulo").textContent = `O Claude pede sua permissão para ${F.rotuloDaFerramenta(p.ferramenta)}.`;
    $("claude-pedido-resumo").textContent = p.resumo;
    $("claude-pedido-entrada").textContent = p.entradaCortada || "";
    const corte = $("claude-pedido-corte");
    const escondidos = Number.isInteger(p.escondidos) ? p.escondidos : 0;
    corte.textContent = escondidos > 0 ? `(cortado: ${escondidos} caracteres escondidos)` : "";
    corte.hidden = escondidos <= 0;
    const aviso = $("claude-pedido-aviso");
    const texto = p.rede === true ? "Isto acessa a internet ou manda dados para fora deste PC."
      : p.nivel === "destrutivo" ? "Atenção: isto pode apagar ou quebrar coisas."
      : p.nivel === "muda_estado" ? "Isto muda algo neste PC." : "";
    aviso.textContent = texto;
    aviso.hidden = !texto;
    dialogoClaude.setAttribute("data-nivel", typeof p.nivel === "string" ? p.nivel : "muda_estado");
    // Negar fica sempre pronto (e com o foco); Permitir espera o atraso.
    botaoNegarClaude.disabled = false;
    botaoPermitirClaude.disabled = true;
    claudeMostrarFila();
    const id = p.id;
    pedidoAtual.liberar = setTimeout(() => {
      if (pedidoAtual && pedidoAtual.id === id) botaoPermitirClaude.disabled = false;
    }, ATRASO_PERMITIR_MS);
    if (!dialogoClaude.open) dialogoClaude.showModal();
    botaoNegarClaude.focus();
  }

  // "N pedidos aguardando" (e quantos foram recusados por excesso) dentro do diálogo.
  function claudeMostrarFila() {
    const el = $("claude-pedido-fila");
    const partes = [];
    if (filaPedidos.length) partes.push(`${filaPedidos.length} pedido(s) aguardando`);
    if (pedidosRecusadosPorExcesso) partes.push(`${pedidosRecusadosPorExcesso} recusado(s) por excesso`);
    el.textContent = partes.join(" · ");
    el.hidden = partes.length === 0;
  }

  function aoClaudePedido(p) {
    if (!p || typeof p.id !== "string" || !p.id) return;
    if (filaPedidos.length >= MAX_FILA_PEDIDOS) {
      // Fila cheia: NEGA explicitamente o excedente (nunca some em silêncio).
      pedidosRecusadosPorExcesso += 1;
      window.dervs.claudeResponder(p.id, false, p.id);
      claudeMostrarFila();
      return;
    }
    filaPedidos.push(p);
    if (!pedidoAtual) claudeAbrirProximoPedido(); else claudeMostrarFila();
  }

  function claudeFecharPedidoAtual() {
    if (pedidoAtual) { clearTimeout(pedidoAtual.timer); clearTimeout(pedidoAtual.liberar); pedidoAtual = null; }
    if (dialogoClaude.open) dialogoClaude.close();
    if (filaPedidos.length) claudeAbrirProximoPedido();
  }

  function claudeFecharPedidos() {
    filaPedidos.length = 0;
    pedidosRecusadosPorExcesso = 0;
    if (pedidoAtual) { clearTimeout(pedidoAtual.timer); clearTimeout(pedidoAtual.liberar); pedidoAtual = null; }
    if (dialogoClaude.open) dialogoClaude.close();
  }

  function claudeResponderPedido(permitir) {
    if (!pedidoAtual) return;
    const id = pedidoAtual.id;
    botaoPermitirClaude.disabled = true;
    botaoNegarClaude.disabled = true;
    window.dervs.claudeResponder(id, permitir, id);
    claudeFecharPedidoAtual();
  }

  botaoPermitirClaude.addEventListener("click", () => claudeResponderPedido(true));
  botaoNegarClaude.addEventListener("click", () => claudeResponderPedido(false));
  dialogoClaude.addEventListener("cancel", (e) => { e.preventDefault(); claudeResponderPedido(false); });

  window.dervs.aoClaudeDelta(aoClaudeDelta);
  window.dervs.aoClaudeFerramenta(aoClaudeFerramenta);
  window.dervs.aoClaudePedido(aoClaudePedido);
  window.dervs.aoClaudeFim(aoClaudeFim);

  // ---- reator (canvas) ------------------------------------------------------
  // Mesma linguagem do antigo núcleo do widget: ticks, anéis segmentados
  // girando, núcleo que brilha com a amplitude; aqui maior, com um anel a mais
  // e um arco-medidor que cresce com a voz.

  const canvas = $("p-canvas");
  const ctx = canvas.getContext("2d");
  const prefereMenosMovimento =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const FATOR_MOVIMENTO = prefereMenosMovimento ? 0.15 : 1;

  function ajustarCanvas() {
    const dpr = window.devicePixelRatio || 1;
    const lado = Math.round((canvas.clientWidth || 520) * dpr);
    if (canvas.width !== lado || canvas.height !== lado) {
      canvas.width = lado;
      canvas.height = lado;
    }
  }

  function velocidadeAlvo() {
    let base;
    switch (painel.estado) {
      case "ouvindo":
      case "falando": base = 0.6 + painel.volumeSuave * 3.2; break;
      case "pensando": base = 1.1; break;
      case "erro": base = 0.08; break;
      default: base = 0.18;
    }
    return base * FATOR_MOVIMENTO;
  }

  function desenhar(agora, deltaS) {
    ajustarCanvas();
    const w = canvas.width;
    const cx = w / 2;
    const raioBase = w / 2;
    ctx.clearRect(0, 0, w, w);
    const cor = painel.estado === "erro" ? CORES.erro : CORES.acento;

    const pulso = (Math.sin(agora / 900) + 1) / 2;
    const brilhoVolume = painel.estado === "erro" ? 0.15 : painel.volumeSuave;
    const brilho = 0.35 + pulso * 0.25 + brilhoVolume * 0.9;

    const alvo = velocidadeAlvo();
    const sinais = [1, -0.75, 0.5, -0.35];
    for (let i = 0; i < 4; i++) {
      painel.velocidade[i] += (alvo * sinais[i] - painel.velocidade[i]) * Math.min(1, deltaS * 1.5);
      painel.rotacao[i] += painel.velocidade[i] * deltaS;
    }

    // ticks radiais (dial), no raio externo
    ctx.strokeStyle = CORES.acentoFraco;
    ctx.lineWidth = Math.max(1, w * 0.003);
    const ticks = 60;
    for (let i = 0; i < ticks; i++) {
      const ang = (i / ticks) * Math.PI * 2 + painel.rotacao[0] * 0.2;
      const longo = i % 5 === 0;
      const r1 = raioBase * (longo ? 0.90 : 0.93);
      const r2 = raioBase * 0.97;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(ang) * r1, cx + Math.sin(ang) * r1);
      ctx.lineTo(cx + Math.cos(ang) * r2, cx + Math.sin(ang) * r2);
      ctx.stroke();
    }

    // arco-medidor da voz: cresce com a amplitude (0 a 300 graus)
    const arcoVoz = Math.min(1, painel.volumeSuave * 1.6) * Math.PI * 1.66;
    ctx.lineCap = "round";
    ctx.lineWidth = Math.max(2, w * 0.014);
    ctx.strokeStyle = cor;
    ctx.globalAlpha = 0.25;
    ctx.beginPath();
    ctx.arc(cx, cx, raioBase * 0.84, Math.PI * 0.67, Math.PI * 0.67 + Math.PI * 1.66);
    ctx.stroke();
    ctx.globalAlpha = 1;
    if (arcoVoz > 0.01) {
      ctx.beginPath();
      ctx.arc(cx, cx, raioBase * 0.84, Math.PI * 0.67, Math.PI * 0.67 + arcoVoz);
      ctx.stroke();
    }

    // anéis segmentados girando
    const aneis = [
      { r: 0.74, n: 7 }, { r: 0.6, n: 5 }, { r: 0.47, n: 4 }, { r: 0.35, n: 3 },
    ];
    for (let a = 0; a < aneis.length; a++) {
      const vao = (Math.PI * 2) / aneis[a].n;
      ctx.strokeStyle = cor;
      ctx.globalAlpha = 0.9 - a * 0.16;
      ctx.lineWidth = Math.max(1.5, w * 0.011);
      for (let i = 0; i < aneis[a].n; i++) {
        const ini = painel.rotacao[a] + i * vao;
        ctx.beginPath();
        ctx.arc(cx, cx, raioBase * aneis[a].r, ini, ini + vao * 0.6);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // núcleo: branco no centro, cor de estado na borda, brilho pela voz
    const raioNucleo = raioBase * (0.13 + brilhoVolume * 0.05);
    const grad = ctx.createRadialGradient(cx, cx, 0, cx, cx, raioNucleo * 1.6);
    grad.addColorStop(0, CORES.nucleoQuente);
    grad.addColorStop(0.45, cor);
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.save();
    ctx.shadowColor = cor;
    ctx.shadowBlur = raioBase * brilho * 0.45;
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cx, raioNucleo * 1.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    ctx.fillStyle = CORES.nucleoQuente;
    ctx.beginPath();
    ctx.arc(cx, cx, raioNucleo * 0.45, 0, Math.PI * 2);
    ctx.fill();
  }

  // ---- laço de animação com cadência controlada -------------------------------

  let rodando = false;
  let ultimoTs = 0;
  let temporizador = null;
  let rafId = null;

  function cadencia() {
    return F.msPorQuadro({ visivel: !document.hidden, focada: document.hasFocus() });
  }

  function passo(ts) {
    temporizador = null;
    rafId = null;
    if (!rodando) return;
    const deltaS = ultimoTs ? Math.min(0.25, (ts - ultimoTs) / 1000) : 0.033;
    ultimoTs = ts;
    painel.volumeSuave += (painel.volumeAlvo - painel.volumeSuave) * Math.min(1, deltaS * 6);
    desenhar(ts, deltaS);
    $("p-amp").textContent = `AMP ${painel.volumeSuave.toFixed(2)}`;
    agendar();
  }

  function agendar() {
    const ms = cadencia();
    if (ms === null) { rodando = false; return; }     // escondida: para de vez
    // setTimeout segura o intervalo (30 ou 10 quadros/s); o rAF alinha o desenho ao vídeo.
    temporizador = setTimeout(() => { temporizador = null; rafId = requestAnimationFrame(passo); }, ms);
  }

  // Um único laço vivo: o timeout OU o rAF pendente. Sem cancelar os dois, um
  // foco/blur entre um e outro criava uma segunda cadeia que nunca morria.
  function cancelarLaco() {
    if (temporizador) { clearTimeout(temporizador); temporizador = null; }
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
  }

  function reavaliarLaco() {
    cancelarLaco();
    if (cadencia() === null) { rodando = false; return; }
    rodando = true;
    ultimoTs = 0;
    if (!document.hidden) { redesenharSparks(); desenharAcoes(); }
    rafId = requestAnimationFrame(passo);
  }

  document.addEventListener("visibilitychange", reavaliarLaco);
  window.addEventListener("focus", reavaliarLaco);
  window.addEventListener("blur", reavaliarLaco);
  window.addEventListener("resize", () => { ajustarCanvas(); if (!document.hidden) redesenharSparks(); });
  window.addEventListener("online", atualizarInternet);
  window.addEventListener("offline", atualizarInternet);

  // ---- controles da janela ----------------------------------------------------

  $("p-botao-fechar").addEventListener("click", () => window.dervs.painelEsconder());
  $("p-botao-minimizar").addEventListener("click", () => window.dervs.painelMinimizar());
  $("p-botao-ampliar").addEventListener("click", () => window.dervs.painelAmpliar());
  $("p-chip-reuniao").addEventListener("click", () => window.dervs.alternarReuniao(!painel.reuniaoAtiva));
  $("p-abrir-app-dervs").addEventListener("click", () => window.dervs.abrirAppDervs());
  $("p-chip-microfone").addEventListener("click", () => {
    if (painel.microfoneLigado === null) return;
    window.dervs.alternarMicrofone(!painel.microfoneLigado);
  });

  const alca = $("p-alca");
  alca.addEventListener("pointerdown", (e) => {
    alca.setPointerCapture(e.pointerId);
    window.dervs.painelRedimensionar("inicio", e.screenX, e.screenY);
  });
  alca.addEventListener("pointermove", (e) => {
    if (alca.hasPointerCapture(e.pointerId)) window.dervs.painelRedimensionar("mover", e.screenX, e.screenY);
  });

  // ---- ligação com a ponte ----------------------------------------------------

  window.dervs.aoEstado(aoEstado);
  window.dervs.aoVolume(aoVolume);
  window.dervs.aoFala(aoFala);
  window.dervs.aoPlano(aoPlano);
  window.dervs.aoSistema(aoSistema);
  window.dervs.aoMicrofone(aoMicrofone);
  window.dervs.aoReuniao(aoReuniao);
  window.dervs.aoDiario(aoDiario);
  window.dervs.aoAgenda(aoAgenda);
  window.dervs.aoDiarioEntradas(aoDiarioEntradas);
  window.dervs.aoGasto(aoGasto);
  window.dervs.aoVoz(aoVoz);
  window.dervs.aoAcao(aoAcao);

  atualizarRelogio();
  atualizarInternet();
  ajustarCanvas();
  setInterval(() => { if (!document.hidden) atualizarRelogio(); }, 1000);
  setInterval(() => { if (!document.hidden) desenharAcoes(); }, 15000);
  reavaliarLaco();
})();
