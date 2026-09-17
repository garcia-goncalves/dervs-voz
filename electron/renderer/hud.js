// hud.js — o núcleo, os anéis e os cinco estados do DERVS.
//
// Canvas 2D, um único requestAnimationFrame (régua de CPU do C10 — nenhuma
// segunda camada animada). O volume que chega da ponte Python é estrangulado
// a 50ms do lado de lá; aqui ele passa por uma suavização (média móvel curta)
// para a onda não tremer em degraus. Quando a janela está escondida, o laço
// para — ela só volta a rodar quando document.hidden vira falso de novo.
//
// Segurança dura do projeto: texto vindo de fora (transcrição, resposta do
// cérebro, frase de erro) é conteúdo hostil por definição — sempre
// textContent, nunca innerHTML, em qualquer lugar deste arquivo.

(() => {
  "use strict";

  const CORES = {
    acento: "#00E5FF",
    acentoFraco: "#0A6E82",
    nucleoQuente: "#FFFFFF",
    erro: "#FF3B3B",
    bg: "#050810",
  };

  const ROTULOS = {
    ocioso: "",
    ouvindo: "ouvindo",
    pensando: "pensando",
    falando: "falando",
    erro: "",
  };

  // --- estado do HUD, atualizado pelos callbacks de window.dervs --------

  const hud = {
    estado: "ocioso",
    volumeAlvo: 0,
    volumeSuave: 0,
    // ângulo e velocidade de cada anel; a velocidade se aproxima do alvo aos
    // poucos (lerp), para a mudança de estado não ser um corte seco.
    rotacao: [0, 0, 0],
    velocidade: [0.15, -0.1, 0.08],
  };

  // --- elementos ----------------------------------------------------------

  const canvas = document.getElementById("canvas");
  const ctx = canvas.getContext("2d");
  const elRotuloEstado = document.getElementById("rotulo-estado");
  const elAmp = document.getElementById("leitura-amp");

  const elFalaDono = document.getElementById("fala-dono");
  const elFalaDonoTexto = document.getElementById("fala-dono-texto");
  const elFalaDervs = document.getElementById("fala-dervs");
  const elFalaDervsTexto = document.getElementById("fala-dervs-texto");

  const elCartaoErro = document.getElementById("cartao-erro");
  const elCartaoErroFrase = document.getElementById("cartao-erro-frase");
  const elCartaoErroApoio = document.getElementById("cartao-erro-apoio");

  const elCartaoPlano = document.getElementById("cartao-plano");
  const elCartaoPlanoPergunta = document.getElementById("cartao-plano-pergunta");
  const elCartaoPlanoPassos = document.getElementById("cartao-plano-passos");
  const elCartaoPlanoComando = document.getElementById("cartao-plano-comando");
  const elCartaoAutorizacaoEnvolucro = document.getElementById("cartao-plano-autorizacao-envolucro");
  const elCartaoAutorizacaoCaixa = document.getElementById("cartao-plano-autorizacao-caixa");
  const elCartaoAutorizacaoTexto = document.getElementById("cartao-plano-autorizacao-texto");
  const botaoConfirmar = document.getElementById("botao-confirmar");
  const botaoCancelar = document.getElementById("botao-cancelar");

  // Estado do cartão de plano em relação à caixa "tenho autorização" — só o
  // clique em Confirmar lê isto, não há validação em tempo real do lado de
  // cá (a checagem de verdade é sempre do lado Python).
  let cartaoPrecisaAutorizacao = false;

  // Identidade do cartão em tela (correção de concorrência — ver
  // dervs_electron.py, `_construir_ao_plano`): mandado de volta junto com a
  // resposta, para o Python descartar clique numa mensagem desatualizada.
  let cartaoAtual = null;

  // --- canvas responsivo ----------------------------------------------------
  // O elemento encolhe por CSS (width/height: 100% do .nucleo-area); aqui só
  // ajustamos os pixels reais do canvas para acompanhar o devicePixelRatio e
  // o tamanho exibido, senão o desenho fica borrado ou cortado.

  function ajustarCanvas() {
    const dpr = window.devicePixelRatio || 1;
    const lado = canvas.clientWidth || 320;
    const pixels = Math.round(lado * dpr);
    if (canvas.width !== pixels || canvas.height !== pixels) {
      canvas.width = pixels;
      canvas.height = pixels;
    }
  }

  window.addEventListener("resize", ajustarCanvas);

  // --- rótulo de estado e leitura técnica ---------------------------------

  function aplicarRotuloEstado() {
    const texto = ROTULOS[hud.estado] || "";
    elRotuloEstado.textContent = texto;
    if (hud.estado === "erro") {
      elRotuloEstado.setAttribute("data-erro", "1");
    } else {
      elRotuloEstado.removeAttribute("data-erro");
    }
  }

  function aplicarLeituraAmp() {
    elAmp.textContent = `AMP ${hud.volumeSuave.toFixed(2)}`;
  }

  // --- desenho do núcleo e dos anéis ---------------------------------------

  function corDeEstado() {
    return hud.estado === "erro" ? CORES.erro : CORES.acento;
  }

  function velocidadeAlvo() {
    switch (hud.estado) {
      case "ouvindo":
      case "falando":
        return 0.6 + hud.volumeSuave * 3.2;
      case "pensando":
        return 1.1;
      case "erro":
        return 0.08;
      case "ocioso":
      default:
        return 0.18;
    }
  }

  function desenhar(agora, deltaS) {
    ajustarCanvas();

    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const raioBase = Math.min(w, h) / 2;

    ctx.clearRect(0, 0, w, h);

    const cor = corDeEstado();

    // Pulso próprio, sempre presente (mesmo em ocioso) — "o sistema nunca
    // aparenta estar desligado" (design.md).
    const pulso = (Math.sin(agora / 900) + 1) / 2; // 0..1, devagar
    const brilhoVolume = hud.estado === "erro" ? 0.15 : hud.volumeSuave;
    const brilho = 0.35 + pulso * 0.25 + brilhoVolume * 0.9;

    // Velocidade de rotação segue o alvo do estado, com suavização própria
    // para a mudança de estado (ex. entrar em erro) desacelerar aos poucos
    // em vez de travar de repente.
    const alvo = velocidadeAlvo();
    const sinais = [1, -0.75, 0.5];
    for (let i = 0; i < 3; i++) {
      const velAlvo = alvo * sinais[i];
      hud.velocidade[i] += (velAlvo - hud.velocidade[i]) * Math.min(1, deltaS * 1.5);
      hud.rotacao[i] += hud.velocidade[i] * deltaS;
    }

    // Ticks radiais tipo dial, no raio externo.
    const numTicks = 28;
    const raioTicksIni = raioBase * 0.86;
    const raioTicksFim = raioBase * 0.93;
    ctx.strokeStyle = CORES.acentoFraco;
    ctx.lineWidth = Math.max(1, w * 0.004);
    for (let i = 0; i < numTicks; i++) {
      const ang = (i / numTicks) * Math.PI * 2 + hud.rotacao[0] * 0.3;
      const x1 = cx + Math.cos(ang) * raioTicksIni;
      const y1 = cy + Math.sin(ang) * raioTicksIni;
      const x2 = cx + Math.cos(ang) * raioTicksFim;
      const y2 = cy + Math.sin(ang) * raioTicksFim;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    // Anéis segmentados girando — três raios diferentes, cada um com seu
    // ângulo próprio (hud.rotacao[i]), formando arcos com espaço entre eles.
    const raiosAneis = [raioBase * 0.78, raioBase * 0.63, raioBase * 0.5];
    const segmentos = [6, 5, 4];
    ctx.lineCap = "round";
    for (let anel = 0; anel < raiosAneis.length; anel++) {
      const raio = raiosAneis[anel];
      const n = segmentos[anel];
      const vaoRad = (Math.PI * 2) / n;
      const arcoRad = vaoRad * 0.6;
      ctx.strokeStyle = cor;
      ctx.globalAlpha = 0.85 - anel * 0.15;
      ctx.lineWidth = Math.max(1.5, w * 0.012);
      for (let i = 0; i < n; i++) {
        const inicio = hud.rotacao[anel] + i * vaoRad;
        ctx.beginPath();
        ctx.arc(cx, cy, raio, inicio, inicio + arcoRad);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // Núcleo — gradiente radial do branco (centro) para a cor de estado, com
    // shadowBlur proporcional ao volume/pulso.
    const raioNucleo = raioBase * (0.16 + brilhoVolume * 0.06);
    const gradiente = ctx.createRadialGradient(cx, cy, 0, cx, cy, raioNucleo * 1.6);
    gradiente.addColorStop(0, CORES.nucleoQuente);
    gradiente.addColorStop(0.45, cor);
    gradiente.addColorStop(1, "rgba(0,0,0,0)");

    ctx.save();
    ctx.shadowColor = cor;
    ctx.shadowBlur = raioBase * brilho * 0.5;
    ctx.fillStyle = gradiente;
    ctx.beginPath();
    ctx.arc(cx, cy, raioNucleo * 1.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.fillStyle = CORES.nucleoQuente;
    ctx.beginPath();
    ctx.arc(cx, cy, raioNucleo * 0.45, 0, Math.PI * 2);
    ctx.fill();
  }

  // --- laço único de animação ----------------------------------------------

  let rodando = false;
  let ultimoTs = 0;

  function passo(ts) {
    if (!rodando) return;
    const deltaS = ultimoTs ? Math.min(0.1, (ts - ultimoTs) / 1000) : 0.016;
    ultimoTs = ts;

    // Suavização do volume: média móvel curta em direção ao valor recebido,
    // para o estrangulamento de 50ms do lado Python não tremer na tela.
    hud.volumeSuave += (hud.volumeAlvo - hud.volumeSuave) * Math.min(1, deltaS * 6);

    desenhar(ts, deltaS);
    aplicarLeituraAmp();

    requestAnimationFrame(passo);
  }

  function iniciarLaco() {
    if (rodando) return;
    rodando = true;
    ultimoTs = 0;
    requestAnimationFrame(passo);
  }

  function pararLaco() {
    rodando = false;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      pararLaco();
    } else {
      iniciarLaco();
    }
  });

  // --- conversa: só a última troca -----------------------------------------

  function papelEhDono(papel) {
    return papel === "dono";
  }

  function aoFala({ papel, texto } = {}) {
    if (typeof texto !== "string") return;
    if (papelEhDono(papel)) {
      elFalaDonoTexto.textContent = texto;
      elFalaDono.hidden = false;
    } else {
      // dervs, resultado ou erro: as três falam na voz do DERVS na conversa
      // (o estado "erro" da tela, separado, é quem cuida do cartão de aviso).
      elFalaDervsTexto.textContent = texto;
      elFalaDervs.hidden = false;
    }
  }

  // --- cartão de erro --------------------------------------------------------

  function aoEstado({ valor, texto, apoio } = {}) {
    if (typeof valor !== "string" || !(valor in ROTULOS)) return;
    hud.estado = valor;
    aplicarRotuloEstado();

    if (valor === "erro") {
      elCartaoErroFrase.textContent = texto || "";
      if (apoio) {
        elCartaoErroApoio.textContent = apoio;
        elCartaoErroApoio.hidden = false;
      } else {
        elCartaoErroApoio.textContent = "";
        elCartaoErroApoio.hidden = true;
      }
      elCartaoErro.hidden = false;
    } else {
      elCartaoErro.hidden = true;
    }
  }

  // --- volume -------------------------------------------------------------

  function aoVolume(valor) {
    if (typeof valor !== "number" || Number.isNaN(valor)) return;
    hud.volumeAlvo = Math.max(0, Math.min(1, valor));
  }

  // --- cartão de plano ------------------------------------------------------

  function aoPlano({ passos, nivel, pergunta, cartaoId } = {}) {
    // Todo evento novo de cartão — inclusive o que limpa a tela — é o
    // "próximo aoPlano" que reabilita os botões (complemento barato pedido
    // pelo revisor: evita clique repetido na mesma janela de tempo, além
    // da proteção por cartaoId).
    botaoConfirmar.disabled = false;
    botaoCancelar.disabled = false;
    cartaoAtual = cartaoId !== undefined ? cartaoId : null;

    const lista = Array.isArray(passos) ? passos : [];
    if (lista.length === 0) {
      elCartaoPlano.hidden = true;
      elCartaoPlanoPassos.textContent = "";
      elCartaoPlanoComando.hidden = true;
      elCartaoPlanoComando.textContent = "";
      elCartaoAutorizacaoEnvolucro.hidden = true;
      elCartaoAutorizacaoCaixa.checked = false;
      cartaoPrecisaAutorizacao = false;
      return;
    }

    elCartaoPlanoPergunta.textContent = pergunta || "";

    // Nunca innerHTML: cada passo vira um <li> criado por código, com
    // textContent puro para o rótulo que o Python mandou.
    while (elCartaoPlanoPassos.firstChild) {
      elCartaoPlanoPassos.removeChild(elCartaoPlanoPassos.firstChild);
    }
    for (const passo of lista) {
      const li = document.createElement("li");
      li.textContent = (passo && typeof passo.rotulo === "string") ? passo.rotulo : "";
      const nivelPasso = (passo && typeof passo.nivel === "string") ? passo.nivel : "reversivel";
      li.setAttribute("data-nivel", nivelPasso);
      elCartaoPlanoPassos.appendChild(li);
    }

    // Extensão do protocolo (ver dervs_ponte_electron.py, cabeçalho): um
    // cartão de PASSO ÚNICO (risco de um passo destrutivo dentro do plano)
    // também traz `comando`, `precisa_autorizacao`, `texto_autorizacao` e
    // `dupla_confirmacao`. O cartão do PLANO inteiro (vários passos, só
    // rotulo/nivel) não tem esses campos — por isso só o passo único é
    // considerado aqui.
    const passoUnico = lista.length === 1 ? lista[0] : null;

    if (passoUnico && typeof passoUnico.comando === "string" && passoUnico.comando) {
      elCartaoPlanoComando.textContent = passoUnico.comando;
      elCartaoPlanoComando.hidden = false;
    } else {
      elCartaoPlanoComando.textContent = "";
      elCartaoPlanoComando.hidden = true;
    }

    cartaoPrecisaAutorizacao = !!(passoUnico && passoUnico.precisa_autorizacao);
    if (cartaoPrecisaAutorizacao) {
      elCartaoAutorizacaoTexto.textContent =
        typeof passoUnico.texto_autorizacao === "string" && passoUnico.texto_autorizacao
          ? passoUnico.texto_autorizacao
          : "Tenho autorização (é meu, laboratório, ou por escrito)";
      elCartaoAutorizacaoCaixa.checked = false;
      elCartaoAutorizacaoEnvolucro.hidden = false;
    } else {
      elCartaoAutorizacaoEnvolucro.hidden = true;
      elCartaoAutorizacaoCaixa.checked = false;
    }

    elCartaoPlano.hidden = false;
  }

  botaoConfirmar.addEventListener("click", () => {
    // Passo que pede autorização e a caixa não está marcada: não manda —
    // o Python não deveria receber um "confirmar" sem autorização real, e a
    // checagem de verdade é sempre do lado de lá, mas não faz sentido nem
    // tentar mandar sem a caixa marcada.
    if (cartaoPrecisaAutorizacao && !elCartaoAutorizacaoCaixa.checked) return;
    // Desabilita assim que clicado — só reabilita no próximo aoPlano (ver
    // acima). Evita clique repetido na mesma janela de tempo, complemento
    // barato à proteção por cartaoId do lado Python.
    botaoConfirmar.disabled = true;
    botaoCancelar.disabled = true;
    window.dervs.responderPlano("confirmar", elCartaoAutorizacaoCaixa.checked, cartaoAtual);
  });

  botaoCancelar.addEventListener("click", () => {
    botaoConfirmar.disabled = true;
    botaoCancelar.disabled = true;
    window.dervs.responderPlano("cancelar", false, cartaoAtual);
  });

  // --- ligação com a ponte (window.dervs, exposta pelo preload.js) ---------

  window.dervs.aoEstado(aoEstado);
  window.dervs.aoVolume(aoVolume);
  window.dervs.aoFala(aoFala);
  window.dervs.aoPlano(aoPlano);

  aplicarRotuloEstado();
  aplicarLeituraAmp();
  ajustarCanvas();

  if (!document.hidden) {
    iniciarLaco();
  }
})();
