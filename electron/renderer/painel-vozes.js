// painel-vozes.js — a tela "Vozes": quem o DERVS escuta e a gravação da sua voz.
//
// Duas partes: funções PURAS (estado -> texto) que têm teste em Node, e a parte de tela, que
// só roda dentro do Electron. Quem decide é o Python (dervs_conversa_natural.Vozes): a tela só
// PEDE e desenha o que volta. Todo texto entra por textContent, nunca innerHTML.

(function (raiz, fabrica) {
  const api = fabrica();
  if (typeof module === "object" && module.exports) module.exports = api;
  else raiz.PainelVozes = api;
  if (typeof document !== "undefined" && raiz.dervs && raiz.dervs.aoVozes) api.iniciarTela(raiz, document);
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SEGUNDOS = 30;            // a gravação do Python dura ~30 s
  const LIMITE_NOME = 40;
  const TEMPO_RESPOSTA_MS = 6000;

  // Texto de ~30 s de leitura em ritmo normal, com sons variados do português.
  const TEXTO_LEITURA = "Meu nome é o que eu escolhi para esta gravação, e eu estou falando com calma, "
    + "do jeito que falo todos os dias. Hoje o céu está claro, o café está quente e a agenda tem "
    + "poucos compromissos. Quando eu pedir, quero que o assistente abra um programa, diga as horas, "
    + "procure uma pasta ou me lembre de ligar para a minha família. Ele precisa reconhecer a minha "
    + "voz mesmo quando eu estiver cansado, com pressa ou um pouco longe do microfone. Um, dois, "
    + "três, quatro, cinco, seis, sete, oito, nove, dez. Agora vou terminar de ler este texto.";

  const MOTORES = {
    gemini_live: "Google (grátis)",
    cascata: "Econômico",
    openai_realtime: "Premium (OpenAI)",
  };

  const AVISOS = {
    "grave sua voz": "Grave sua voz para o DERVS só atender você.",
    "nenhum perfil ativo": "Nenhuma voz está ativa. Ative uma para o DERVS te ouvir.",
    "grave sua voz de novo": "Todas as vozes foram apagadas. Grave a sua de novo: até lá o DERVS não atende ninguém.",
    "trava de voz desligada": "A trava de voz está desligada: o DERVS ouve qualquer pessoa.",
  };

  function rotuloDoMotor(estado) {
    const m = estado && estado.motor_ativo;
    return (typeof m === "string" && MOTORES[m]) || "Modo antigo";
  }

  // Aviso do Python em português claro; texto desconhecido não é mostrado como veio.
  function avisoDaTrava(estado) {
    const a = estado && estado.locutor_aviso;
    return typeof a === "string" && AVISOS[a] ? AVISOS[a] : "";
  }

  function statusDaTrava(estado) {
    if (!estado) return "Carregando...";
    const ativos = Array.isArray(estado.perfis_ativos) ? estado.perfis_ativos : [];
    if (estado.locutor_ativo && ativos.length) return `Trava de voz ligada: só escuto ${ativos.join(", ")}.`;
    if (estado.locutor_aviso === "grave sua voz") return "Trava de voz sem nenhuma voz gravada: escuto qualquer pessoa.";
    if (estado.locutor_aviso === "grave sua voz de novo") return "Trava de voz ligada, sem nenhuma voz gravada: não escuto ninguém até você gravar a sua de novo.";
    if (estado.locutor_aviso === "trava de voz desligada") return "Trava de voz desligada: escuto qualquer pessoa.";
    return "Trava de voz ligada, mas sem nenhuma voz ativa.";
  }

  function rotuloDoPapel(papel) {
    return papel === "dono" ? "Dono" : "Convidado";
  }

  function temDono(lista) {
    return Array.isArray(lista) && lista.some((p) => p && p.papel === "dono");
  }

  // Novo dono: no 1º cadastro sempre; depois, só se o Python disser que a conversa atual
  // foi confirmada como dono. Sem a informação, deixa pedir e o Python recusa com o motivo.
  function podeGravarDono(lista, estado) {
    if (!temDono(lista)) return true;
    return !estado || estado.dono_confirmado !== false;
  }

  const EXPLICA_DONO = "Já existe um dono. Para cadastrar outro, fale com o DERVS antes, com a voz de "
    + "um dono já gravado, e volte aqui.";

  function validarNome(texto) {
    const nome = typeof texto === "string" ? texto.trim() : "";
    if (!nome) return { ok: false, erro: "Escreva um nome para esta voz." };
    if (nome.length > LIMITE_NOME) return { ok: false, erro: `O nome pode ter no máximo ${LIMITE_NOME} letras.` };
    return { ok: true, nome };
  }

  function segundosGravados(fracao) {
    const f = Number(fracao);
    if (!Number.isFinite(f)) return 0;
    return Math.round(Math.min(1, Math.max(0, f)) * SEGUNDOS);
  }

  function fraseDoProgresso(fracao) {
    return `Gravando... ${segundosGravados(fracao)} de ${SEGUNDOS} segundos. Leia o texto em voz alta.`;
  }

  // Resposta do Python a uma ação: texto e se deu certo. `pedir`/`ativar` com ok não dizem nada.
  function mensagemDoResultado(acao, resultado, nome) {
    if (!resultado || typeof resultado !== "object") return null;
    if (resultado.ok !== true) {
      return { texto: typeof resultado.erro === "string" && resultado.erro ? resultado.erro : "Não consegui fazer isso.", ok: false };
    }
    if (acao === "gravar") return { texto: `Voz de ${nome} gravada.`, ok: true };
    if (acao === "apagar") return { texto: `Voz de ${nome} apagada.`, ok: true };
    return null;
  }

  // ------------------------------------------------------------------ tela
  function iniciarTela(janela, doc) {
    const $ = (id) => doc.getElementById(id);
    const dialogo = $("p-dialogo-vozes");
    if (!dialogo) return;
    const d = janela.dervs;
    let lista = [];
    let estado = null;
    let gravando = false;
    let apagando = null;      // nome esperando o "sim" inline
    let acao = null;          // { tipo, nome } da última ação pedida
    let relogio = null;

    function el(tag, classe, texto) {
      const e = doc.createElement(tag);
      if (classe) e.className = classe;
      if (texto !== undefined) e.textContent = texto;
      return e;
    }

    function mensagem(texto, ok) {
      const m = $("voz-mensagem");
      m.textContent = texto || "";
      if (ok === undefined) m.removeAttribute("data-ok");
      else m.setAttribute("data-ok", ok ? "1" : "0");
    }

    // Sem resposta do Python em 6 s, avisa em vez de ficar preso em "Carregando...".
    function esperar(texto) {
      mensagem(texto);
      clearTimeout(relogio);
      relogio = setTimeout(() => mensagem("O DERVS não respondeu. Feche e abra esta tela para tentar de novo.", false),
        TEMPO_RESPOSTA_MS);
    }

    function focar(nome, seletor) {
      const li = Array.from($("voz-lista").children).find((x) => x.dataset.nome === nome);
      const alvo = li && li.querySelector(seletor);
      if (alvo) alvo.focus();
    }

    function desenharLinha(p) {
      const li = el("li", "integ-item voz-item");
      li.dataset.nome = p.nome;
      const corpo = el("div", "integ-item-corpo");
      corpo.appendChild(el("strong", "central-rotulo", p.nome));
      corpo.appendChild(el("span", "central-nota-pequena", rotuloDoPapel(p.papel)));
      li.appendChild(corpo);
      const acoes = el("div", "voz-acoes");
      const alt = el("button", "p-mini voz-ativo", p.ativo ? "ATIVO" : "INATIVO");
      alt.type = "button";
      alt.setAttribute("aria-pressed", p.ativo ? "true" : "false");
      alt.setAttribute("aria-label", `${p.nome}: ${p.ativo ? "ativo, clique para desativar" : "inativo, clique para ativar"}`);
      alt.disabled = gravando;
      alt.addEventListener("click", () => {
        acao = { tipo: "ativar", nome: p.nome };
        esperar("Salvando...");
        d.vozesAtivar(p.nome, !p.ativo);
      });
      acoes.appendChild(alt);
      if (apagando === p.nome) {
        acoes.appendChild(el("span", "central-nota-pequena voz-pergunta", `Apagar a voz de ${p.nome}?`));
        const sim = el("button", "p-mini p-mini-perigo voz-sim", "SIM, APAGAR");
        sim.type = "button";
        sim.addEventListener("click", () => {
          apagando = null;
          acao = { tipo: "apagar", nome: p.nome };
          esperar("Apagando...");
          d.vozesApagar(p.nome);
        });
        const nao = el("button", "p-mini voz-nao", "CANCELAR");
        nao.type = "button";
        nao.addEventListener("click", () => { apagando = null; desenhar(); focar(p.nome, ".voz-apagar"); });
        acoes.append(sim, nao);
      } else {
        const ap = el("button", "p-mini p-mini-perigo voz-apagar", "APAGAR");
        ap.type = "button";
        ap.setAttribute("aria-label", `Apagar a voz de ${p.nome}`);
        ap.disabled = gravando;
        ap.addEventListener("click", () => {
          apagando = p.nome;
          desenhar();
          focar(p.nome, ".voz-nao");
        });
        acoes.appendChild(ap);
      }
      li.appendChild(acoes);
      return li;
    }

    function desenhar() {
      // Recriar a lista tira o foco de quem usa o teclado: guarda e devolve.
      const ativoEl = doc.activeElement;
      const li = ativoEl && ativoEl.closest ? ativoEl.closest("li.voz-item") : null;
      const nomeFoco = li ? li.dataset.nome : null;
      const eraAtivo = Boolean(li) && ativoEl.classList.contains("voz-ativo");
      $("voz-motor").textContent = rotuloDoMotor(estado);
      $("voz-trava").textContent = statusDaTrava(estado);
      const aviso = avisoDaTrava(estado);
      $("voz-aviso").textContent = aviso;
      $("voz-aviso").hidden = !aviso;
      $("voz-lista").replaceChildren(...lista.map(desenharLinha));
      $("voz-vazio").hidden = lista.length > 0;
      if (nomeFoco && eraAtivo) focar(nomeFoco, ".voz-ativo");
      desenharFormulario();
    }

    function desenharFormulario() {
      const podeDono = podeGravarDono(lista, estado);
      const sel = $("voz-papel");
      sel.querySelector('option[value="dono"]').disabled = !podeDono;
      if (!podeDono && sel.value === "dono") sel.value = "convidado";
      if (!temDono(lista) && !sel.dataset.tocado) sel.value = "dono";
      $("voz-papel-ajuda").textContent = podeDono ? "" : EXPLICA_DONO;
      for (const id of ["voz-nome", "voz-papel", "voz-iniciar"]) $(id).disabled = gravando;
      $("voz-cancelar").hidden = !gravando;
      $("voz-progresso-area").hidden = !gravando;
    }

    function mostrarProgresso(fracao) {
      const s = segundosGravados(fracao);
      const barra = $("voz-barra");
      barra.value = s;
      barra.textContent = `${s} de ${SEGUNDOS} segundos`;
      $("voz-progresso-texto").textContent = fraseDoProgresso(fracao);
    }

    function abrir() {
      if (!dialogo.open) dialogo.showModal();
      $("voz-titulo").focus();
      esperar("Carregando...");
      d.vozesPedir();
    }

    $("p-abrir-vozes").addEventListener("click", abrir);
    $("voz-fechar").addEventListener("click", () => dialogo.close());
    $("voz-papel").addEventListener("change", () => { $("voz-papel").dataset.tocado = "1"; });
    $("voz-texto").textContent = TEXTO_LEITURA;
    $("voz-barra").max = SEGUNDOS;

    $("voz-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (gravando) return;
      const v = validarNome($("voz-nome").value);
      if (!v.ok) { mensagem(v.erro, false); $("voz-nome").focus(); return; }
      const papel = $("voz-papel").value === "dono" ? "dono" : "convidado";
      gravando = true;
      acao = { tipo: "gravar", nome: v.nome };
      clearTimeout(relogio);
      mensagem("");
      mostrarProgresso(0);
      desenhar();
      d.vozesGravar(v.nome, papel);
    });

    // O Python não tem comando para interromper a gravação (~30 s): "Cancelar" solta a tela
    // e ignora o resultado; o perfil só nasce se o Python concluir, e então a lista aparece.
    $("voz-cancelar").addEventListener("click", () => {
      gravando = false;
      acao = null;
      mensagem("Gravação cancelada nesta tela. Se o DERVS terminar de gravar, a voz aparece na lista.");
      desenhar();
      $("voz-nome").focus();
    });

    d.aoVozes((m) => {
      if (!m || typeof m !== "object") return;
      clearTimeout(relogio);
      if (Array.isArray(m.lista)) lista = m.lista.filter((p) => p && typeof p.nome === "string");
      if (m.estado && typeof m.estado === "object") estado = m.estado;
      if (typeof m.gravando === "number") {
        if (gravando) mostrarProgresso(m.gravando);
        return;
      }
      if (m.resultado) {
        const era = acao;
        const msg = era ? mensagemDoResultado(era.tipo, m.resultado, era.nome) : null;
        if (era && era.tipo === "gravar") gravando = false;
        if (msg) mensagem(msg.texto, msg.ok);
        else if (m.resultado.ok === false) mensagem(mensagemDoResultado("", m.resultado).texto, false);
        else mensagem("");
        if (msg && msg.ok && era.tipo === "gravar") $("voz-nome").value = "";
        acao = null;
      } else if ($("voz-mensagem").textContent === "Carregando...") {
        mensagem("");
      }
      desenhar();
    });
  }

  return { rotuloDoMotor, avisoDaTrava, statusDaTrava, rotuloDoPapel, temDono, podeGravarDono,
    validarNome, segundosGravados, fraseDoProgresso, mensagemDoResultado, iniciarTela,
    TEXTO_LEITURA, EXPLICA_DONO, SEGUNDOS, LIMITE_NOME };
});
