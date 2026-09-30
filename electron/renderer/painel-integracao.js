// painel-integracao.js — a tela Integração do painel: cérebro, painel web e terminal SSH.
//
// Duas partes: funções PURAS (o que cada botão diz e quando está ligado) que têm teste
// em Node, e a parte de tela, que só roda dentro do Electron.
//
// Segurança dura do projeto: pedido do painel web, aviso e saída de comando no servidor
// são conteúdo de TERCEIRO — sempre textContent, nunca innerHTML. A tela só PEDE: quem
// decide e confere tudo de novo é o Python. A senha do clique do SSH nunca chega aqui;
// o botão do cartão manda só o id da proposta, e é o ÚNICO jeito de confirmar.

(function (raiz, fabrica) {
  const api = fabrica();
  if (typeof module === "object" && module.exports) module.exports = api;
  else raiz.PainelIntegracao = api;
  if (typeof document !== "undefined" && raiz.dervs && raiz.dervs.aoIntegracao) api.iniciarTela(raiz, document);
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LIMITE_COMANDO = 400;
  const ESPERA_CONFIRMAR_MS = 700;       // o botão do cartão só liga depois disto: clique por reflexo não passa
  const PRAZO_SSH_MS = 75 * 1000;        // o terminal desiste em 60 s; a tela desiste um pouco depois

  const TIPOS_DE_PEDIDO = { analisar: "Analisar", status: "Ver o estado", propor: "Proposta", avisar: "Aviso" };

  function rotuloDoTipo(tipo) {
    return TIPOS_DE_PEDIDO[tipo] || "Pedido";
  }

  // O que o botão de um cérebro diz e se está ligado. O JEV não tem botão: não conversa.
  function botaoDoCerebro(c) {
    if (!c.escolhivel) return { visivel: false, texto: "", desligado: true };
    if (c.ativo) return { visivel: true, texto: "EM USO", desligado: true };
    if (!c.disponivel) return { visivel: true, texto: "INDISPONÍVEL", desligado: true };
    return { visivel: true, texto: "USAR ESTE", desligado: false };
  }

  function comandoValido(texto) {
    return typeof texto === "string" && texto.trim() !== "" && texto.length <= LIMITE_COMANDO;
  }

  // Só liga o EXECUTAR com servidor escolhido, comando válido e nada em andamento.
  function podeExecutar(apelido, comando, ocupado) {
    return !ocupado && Boolean(apelido) && comandoValido(comando);
  }

  // A instrução de quem ainda não cadastrou nenhum servidor, em palavras simples.
  function instrucaoDeHosts(apelidos, arquivo) {
    if (apelidos && apelidos.length) {
      return `Servidores cadastrados: ${apelidos.length}. Para adicionar outro, edite o arquivo ${arquivo}.`;
    }
    return `Nenhum servidor cadastrado ainda. Para cadastrar, abra o arquivo ${arquivo} (o Bloco de Notas serve) `
      + `e escreva, por exemplo: {"meu-servidor": {"host": "exemplo.com", "usuario": "deploy", "porta": 22}}. `
      + "Salve e clique em INTEGRAÇÃO de novo. Só os servidores desse arquivo aparecem aqui.";
  }

  function validadeDoCartao(minutos, agoraMs) {
    const ate = new Date(agoraMs + minutos * 60000);
    const hh = String(ate.getHours()).padStart(2, "0");
    const mm = String(ate.getMinutes()).padStart(2, "0");
    return `${minutos} minutos (até ${hh}:${mm}). Depois disso o cartão some e é preciso enviar o comando de novo.`;
  }

  // O cabeçalho do resultado de um comando: sempre uma frase.
  function tituloDoResultado(r) {
    if (!r.ok) return `Não rodou em ${r.apelido || "o servidor"}. ${r.motivo || ""}`.trim();
    const fim = r.rc === 0 || r.rc === null ? "terminou bem" : `terminou com código ${r.rc} (pode ser um aviso do próprio comando)`;
    return `${r.apelido}: ${r.comando} — ${fim}.${r.truncada ? " A saída foi cortada: só o começo aparece." : ""}`;
  }

  function textoDaSaida(r) {
    if (!r.ok) return "";
    return r.saida ? r.saida : "(o comando não escreveu nada)";
  }

  // O que o chip da barra mostra sobre a ponte com o painel web.
  function chipDaPonte(codigo) {
    return {
      ligada: { valor: "LIGADA", estado: "ok" },
      calma: { valor: "CALMA", estado: "" },
      com_problema: { valor: "ATENÇÃO", estado: "alerta" },
      desligada: { valor: "DESLIGADA", estado: "alerta" },
    }[codigo] || { valor: "--", estado: "" };
  }

  // ------------------------------------------------------------------ tela
  function iniciarTela(janela, doc) {
    const $ = (id) => doc.getElementById(id);
    const dialogo = $("p-dialogo-integracao");
    if (!dialogo) return;
    const d = janela.dervs;
    const estado = { ocupado: false, propostaId: null, temporizadorCartao: null, prazoSsh: null,
      liberaConfirmar: null, apelidos: [], arquivo: "" };

    function el(tag, classe, texto) {
      const e = doc.createElement(tag);
      if (classe) e.className = classe;
      if (texto !== undefined) e.textContent = texto;
      return e;
    }

    function mensagem(texto, ok) {
      const m = $("integ-mensagem");
      m.textContent = texto || "";
      if (ok === undefined) m.removeAttribute("data-ok");
      else m.setAttribute("data-ok", ok ? "1" : "0");
    }

    function preencher(lista, itens, montar, vazio) {
      lista.replaceChildren(...itens.map(montar));
      if (vazio) $(vazio).hidden = itens.length > 0;
    }

    // ---- 1. cérebro
    function desenharCerebros(m) {
      preencher($("integ-cerebros"), m.cerebros || [], (c) => {
        const li = el("li", "integ-item");
        li.setAttribute("data-ativo", c.ativo ? "1" : "0");
        const corpo = el("div", "integ-item-corpo");
        corpo.appendChild(el("strong", "central-rotulo", c.rotulo));
        corpo.appendChild(el("span", "central-nota-pequena", c.frase));
        li.appendChild(corpo);
        const b = botaoDoCerebro(c);
        if (b.visivel) {
          const botao = el("button", "p-mini", b.texto);
          botao.type = "button";
          botao.disabled = b.desligado;
          if (c.ativo) botao.setAttribute("aria-pressed", "true");
          botao.addEventListener("click", () => {
            botao.disabled = true;
            mensagem("Trocando o cérebro...");
            d.integracaoEscolherCerebro(c.nome);
          });
          li.appendChild(botao);
        } else {
          li.appendChild(el("span", "integ-selo", "TRIAGEM"));
        }
        return li;
      });
    }

    // ---- 2. painel web
    function desenharWeb(w) {
      const p = $("integ-web");
      p.textContent = w.frase || "";
      p.setAttribute("data-estado", w.codigo || "");
      const chip = chipDaPonte(w.codigo);
      $("p-integracao-valor").textContent = chip.valor;
      $("p-abrir-integracao").setAttribute("data-estado", chip.estado);
    }

    function desenharFila(m) {
      preencher($("integ-fila"), m.itens || [], (i) => {
        const li = el("li", "integ-item");
        const corpo = el("div", "integ-item-corpo");
        corpo.appendChild(el("span", "central-nota-pequena",
          [rotuloDoTipo(i.tipo), i.alvo ? `sobre ${i.alvo}` : "", i.quando].filter(Boolean).join(" · ")));
        corpo.appendChild(el("p", "integ-texto-hostil", i.texto));
        li.appendChild(corpo);
        const b = el("button", "p-mini", "DISPENSAR");
        b.type = "button";
        b.title = "Tira o pedido da lista. Não executa nada.";
        b.addEventListener("click", () => {
          b.disabled = true;
          d.integracaoDispensar(i.id);
        });
        li.appendChild(b);
        return li;
      }, "integ-fila-vazio");
    }

    function desenharAvisos(m) {
      preencher($("integ-avisos"), m.itens || [], (a) => {
        const li = el("li", "integ-item");
        const corpo = el("div", "integ-item-corpo");
        corpo.appendChild(el("span", "central-nota-pequena",
          [a.alvo ? `sobre ${a.alvo}` : "", a.quando].filter(Boolean).join(" · ")));
        corpo.appendChild(el("p", "integ-texto-hostil", a.texto));
        if (a.conserto) corpo.appendChild(el("p", "integ-resposta", a.conserto));
        li.appendChild(corpo);
        if (a.pode_conserto) {
          const b = el("button", "p-mini", "PEDIR CONSERTO");
          b.type = "button";
          b.title = "Pede ao painel web que prepare o conserto. Ele só anda quando você der o Pode fazer lá.";
          b.addEventListener("click", () => {
            b.disabled = true;
            mensagem("Pedindo o conserto ao painel web...");
            d.integracaoPedirConserto(a.id);
          });
          li.appendChild(b);
        }
        return li;
      }, "integ-avisos-vazio");
    }

    // ---- 3. terminal SSH
    function reavaliarExecutar() {
      const apelido = $("integ-ssh-apelido").value;
      const temServidor = estado.apelidos.length > 0;
      $("integ-ssh-apelido").disabled = !temServidor || estado.ocupado;
      $("integ-ssh-comando").disabled = !temServidor;
      $("integ-ssh-rodar").disabled = !podeExecutar(apelido, $("integ-ssh-comando").value, estado.ocupado);
      $("integ-ssh-rodar").textContent = estado.ocupado ? "EXECUTANDO..." : "EXECUTAR";
    }

    function ocupar(sim) {
      estado.ocupado = sim;
      clearTimeout(estado.prazoSsh);
      if (sim) {
        estado.prazoSsh = setTimeout(() => {
          estado.ocupado = false;
          mensagem("O servidor demorou demais para responder. Tente de novo.", false);
          reavaliarExecutar();
        }, PRAZO_SSH_MS);
      }
      reavaliarExecutar();
    }

    function desenharSsh(m) {
      estado.apelidos = m.apelidos || [];
      estado.arquivo = m.arquivo_hosts || "";
      const sel = $("integ-ssh-apelido");
      const escolhido = sel.value;
      sel.replaceChildren(...estado.apelidos.map((a) => {
        const o = doc.createElement("option");
        o.value = a;
        o.textContent = a;
        return o;
      }));
      if (estado.apelidos.includes(escolhido)) sel.value = escolhido;
      $("integ-ssh-ajuda").textContent = instrucaoDeHosts(estado.apelidos, estado.arquivo);
      reavaliarExecutar();
    }

    function esconderCartao() {
      clearTimeout(estado.temporizadorCartao);
      clearTimeout(estado.liberaConfirmar);
      estado.propostaId = null;
      $("integ-ssh-cartao").hidden = true;
    }

    function mostrarCartao(c) {
      if (estado.propostaId && estado.propostaId !== c.proposta_id) d.integracaoSshCancelar(estado.propostaId);   // um cartão por vez
      esconderCartao();
      ocupar(false);
      estado.propostaId = c.proposta_id;
      $("integ-cartao-servidor").textContent = c.servidor;
      $("integ-cartao-comando").textContent = c.comando;
      $("integ-cartao-risco").textContent = "ALTO";
      $("integ-cartao-muda").textContent = c.o_que_muda;
      $("integ-cartao-desfazer").textContent = c.como_desfazer;
      $("integ-cartao-validade").textContent = validadeDoCartao(c.valida_min, Date.now());
      const confirmar = $("integ-cartao-confirmar");
      confirmar.disabled = true;
      estado.liberaConfirmar = setTimeout(() => { confirmar.disabled = false; }, ESPERA_CONFIRMAR_MS);
      estado.temporizadorCartao = setTimeout(() => {
        esconderCartao();
        mensagem("O cartão venceu e nada foi feito. Envie o comando de novo se ainda quiser.", false);
      }, c.valida_min * 60000);
      $("integ-ssh-cartao").hidden = false;
      $("integ-ssh-saida").hidden = true;
      mensagem("");
      $("integ-cartao-titulo").scrollIntoView({ block: "center" });
      $("integ-cartao-titulo").focus();
    }

    function mostrarResultadoSsh(r) {
      ocupar(false);
      esconderCartao();
      mensagem(tituloDoResultado(r), r.ok);
      const saida = $("integ-ssh-saida");
      saida.textContent = textoDaSaida(r);
      saida.setAttribute("data-ok", r.ok ? "1" : "0");
      saida.hidden = !r.ok;
    }

    function executar() {
      const apelido = $("integ-ssh-apelido").value;
      const comando = $("integ-ssh-comando").value;
      if (!podeExecutar(apelido, comando, estado.ocupado)) return;
      esconderCartao();
      $("integ-ssh-saida").hidden = true;
      mensagem("Falando com o servidor...");
      ocupar(true);
      d.integracaoSshRodar(apelido, comando);
    }

    // ---- ligações
    function abrir() {
      if (!dialogo.open) dialogo.showModal();
      $("integ-titulo").focus();
      d.integracaoPedir();
    }

    $("p-abrir-integracao").addEventListener("click", abrir);
    $("integ-fechar").addEventListener("click", () => dialogo.close());
    // fechar a janela com um cartão aberto descarta o cartão: ele não fica esperando escondido
    dialogo.addEventListener("close", () => {
      if (estado.propostaId) d.integracaoSshCancelar(estado.propostaId);
      esconderCartao();
    });
    $("integ-ssh-form").addEventListener("submit", (e) => { e.preventDefault(); executar(); });
    $("integ-ssh-comando").addEventListener("input", reavaliarExecutar);
    $("integ-ssh-apelido").addEventListener("change", reavaliarExecutar);
    $("integ-cartao-confirmar").addEventListener("click", () => {
      const id = estado.propostaId;
      if (!id || $("integ-cartao-confirmar").disabled) return;   // botão ainda "apagado" não age
      $("integ-cartao-confirmar").disabled = true;
      clearTimeout(estado.temporizadorCartao);
      estado.propostaId = null;      // vale um clique só
      ocupar(true);
      mensagem("Rodando no servidor...");
      d.integracaoSshConfirmar(id);
    });
    $("integ-cartao-cancelar").addEventListener("click", () => {
      const id = estado.propostaId;
      esconderCartao();
      if (id) d.integracaoSshCancelar(id);
      mensagem("Cancelado. Nada foi feito no servidor.", true);
    });

    d.aoIntegracao((m) => {
      if (!m || typeof m.parte !== "string") return;
      switch (m.parte) {
        case "cerebros": desenharCerebros(m); break;
        case "web": desenharWeb(m); break;
        case "fila": desenharFila(m); break;
        case "avisos": desenharAvisos(m); break;
        case "ssh": desenharSsh(m); break;
        case "ssh_cartao": mostrarCartao(m); break;
        case "ssh_resultado": mostrarResultadoSsh(m); break;
        case "ssh_cancelado": break;
        case "mensagem": mensagem(m.texto, m.ok); break;
        default: break;
      }
    });
  }

  return { rotuloDoTipo, botaoDoCerebro, comandoValido, podeExecutar, instrucaoDeHosts, validadeDoCartao,
    tituloDoResultado, textoDaSaida, chipDaPonte, iniciarTela };
});
