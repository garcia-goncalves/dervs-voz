// Ponte de contexto isolado entre o processo principal e o renderer.
//
// Expõe SÓ a API do contrato (window.dervs) — nada de require, nodeIntegration
// ou acesso a rede no renderer. O renderer é conteúdo local e hostil por
// definição (transcrição, resposta do cérebro): quanto menos ele puder fazer
// além de desenhar o HUD, melhor. Ver docs/superpowers/plans/dervs-cara-nova.md,
// seção "Contrato compartilhado".

const { contextBridge, ipcRenderer } = require("electron");

function aoCanal(canal) {
  return (callback) => {
    ipcRenderer.on(canal, (_evento, dado) => callback(dado));
  };
}

contextBridge.exposeInMainWorld("dervs", {
  aoEstado: aoCanal("dervs:estado"),
  aoVolume: aoCanal("dervs:volume"),
  aoFala: aoCanal("dervs:fala"),
  aoPlano: aoCanal("dervs:plano"),
  // Extensão do protocolo (fase 1 da esteira dervs-painel-completo): CPU/RAM/
  // disco reais, mandados a cada ~2s — ver dervs_sistema.py.
  aoSistema: aoCanal("dervs:sistema"),
  // Botão liga/desliga do microfone: `alternarMicrofone(ligar)` só pede ao
  // Python; `aoMicrofone` recebe `{ ligado }` quando a escuta de fato mudou.
  aoMicrofone: aoCanal("dervs:microfone"),
  alternarMicrofone: (ligar) => {
    ipcRenderer.send("dervs:alternar-microfone", Boolean(ligar));
  },
  // Modos de escuta: `definirModoEscuta("desligado"|"atalho"|"voz")` só pede ao
  // Python; `aoModoEscuta` recebe `{ modo, fechaEmMin }` (minutos ou null).
  aoModoEscuta: aoCanal("dervs:modo-escuta"),
  definirModoEscuta: (modo) => {
    ipcRenderer.send("dervs:definir-modo-escuta", String(modo));
  },
  // Modo reunião: `alternarReuniao(ligar)` só pede ao Python (booleano
  // estrito); `aoReuniao` recebe `{ restanteS }` — inteiro ou null.
  aoReuniao: (callback) => {
    ipcRenderer.on("dervs:reuniao", (_evento, dado) => {
      const r = dado && dado.restanteS;
      if (r === null || (Number.isInteger(r) && r >= 0)) callback({ restanteS: r });
    });
  },
  alternarReuniao: (ligar) => {
    ipcRenderer.send("dervs:alternar-reuniao", Boolean(ligar));
  },
  // Cartão do diário do porteiro: `{ ouvidas, acordou }`, inteiros de HOJE.
  aoDiario: (callback) => {
    ipcRenderer.on("dervs:diario", (_evento, dado) => {
      if (dado && Number.isInteger(dado.ouvidas) && Number.isInteger(dado.acordou)) {
        callback({ ouvidas: dado.ouvidas, acordou: dado.acordou });
      }
    });
  },
  // Painel grande (JARVIS): dados extras que o widget compacto não usa.
  aoAgenda: aoCanal("dervs:agenda"),
  aoDiarioEntradas: aoCanal("dervs:diario-entradas"),
  aoGasto: aoCanal("dervs:gasto"),
  aoVoz: aoCanal("dervs:voz"),
  aoCofre: aoCanal("dervs:cofre"),
  aoCodex: aoCanal("dervs:codex"),
  abrirCofre: () => {
    ipcRenderer.send("dervs:abrir-cofre");
  },
  aoAcao: aoCanal("dervs:acao"),
  // Controles da janela grande — só PEDEM; quem mexe na janela é o main.js.
  painelEsconder: () => { ipcRenderer.send("dervs:painel-esconder"); },
  painelMinimizar: () => { ipcRenderer.send("dervs:painel-minimizar"); },
  painelAmpliar: () => { ipcRenderer.send("dervs:painel-ampliar"); },
  painelRedimensionar: (fase, x, y) => {
    if ((fase === "inicio" || fase === "mover") && Number.isFinite(x) && Number.isFinite(y)) {
      ipcRenderer.send("dervs:painel-redimensionar", { fase, x, y });
    }
  },
  // Botão "Abrir DERVS App": só manda o pedido para o processo principal
  // abrir a URL no navegador — o renderer não tem `shell` nem rede.
  abrirAppDervs: () => {
    ipcRenderer.send("dervs:abrir-app-dervs");
  },
  // `autorizado` é extensão do protocolo (ver dervs_ponte_electron.py,
  // cabeçalho): reflete a caixa "Tenho autorização" do cartão de passo.
  // Omitido, vira `false` — nunca destrava um passo que pede autorização
  // sem ela ter sido marcada de verdade.
  // `cartaoId` é extensão do protocolo (correção de concorrência): o id do
  // cartão que o HUD estava mostrando quando o clique saiu — sem ele, o
  // Python não tem como descartar uma resposta duplicada/atrasada e rodar
  // o passo errado (ver relato desta etapa, dervs_electron.py).
  responderPlano: (resposta, autorizado = false, cartaoId = null) => {
    ipcRenderer.send("dervs:responder-plano",
      { resposta, autorizado: Boolean(autorizado), cartaoId });
  },

  // ---- Claude Code no painel (onda B) — lista ESTREITA, de propósito --------
  // Python -> tela: pedaços da resposta, uso de ferramenta, pedido de permissão
  // e fim do turno. Tudo texto de fonte hostil: o painel só usa textContent.
  aoClaudeDelta: aoCanal("dervs:claude-delta"),
  aoClaudeFerramenta: aoCanal("dervs:claude-ferramenta"),
  aoClaudePedido: aoCanal("dervs:claude-pedido"),
  aoClaudeFim: aoCanal("dervs:claude-fim"),
  // Tela -> Python: só estes quatro pedidos, cada um com o formato conferido
  // aqui E de novo no main.js E de novo no Python (dervs_ponte_electron.py).
  claudePerguntar: (texto) => {
    if (typeof texto === "string" && texto.trim() && texto.length <= 8000) {
      ipcRenderer.send("dervs:claude-perguntar", texto);
    }
  },
  claudeParar: () => { ipcRenderer.send("dervs:claude-parar"); },
  // `permitir` só é true se for o booleano true de verdade.
  claudeResponder: (id, permitir, cartaoId = null) => {
    if (typeof id === "string" && id) {
      ipcRenderer.send("dervs:claude-responder", {
        id, permitir: permitir === true,
        cartaoId: typeof cartaoId === "string" ? cartaoId : null });
    }
  },
  claudeNovaConversa: () => { ipcRenderer.send("dervs:claude-nova-conversa"); },
  // Sem parâmetro: o processo principal sabe sozinho qual script abrir.
  claudeEntrar: () => { ipcRenderer.send("dervs:claude-entrar"); },

  // ---- Central do PC (onda D) — lista ESTREITA, de propósito ------------------
  // Python -> tela: a visão da análise, o andamento, o relatório de limpeza (com o
  // cartão do clique) e o resultado. Tudo texto de fonte hostil: só textContent.
  aoCentral: aoCanal("dervs:central"),
  aoCentralProgresso: aoCanal("dervs:central-progresso"),
  aoCentralRelatorio: aoCanal("dervs:central-relatorio"),
  aoCentralResultado: aoCanal("dervs:central-resultado"),
  // Tela -> Python: só estes seis pedidos; formato conferido aqui, no main.js e no Python.
  centralPedir: () => { ipcRenderer.send("dervs:central-pedir"); },
  centralAnalisar: () => { ipcRenderer.send("dervs:central-analisar"); },
  centralProporLimpeza: () => { ipcRenderer.send("dervs:central-propor-limpeza"); },
  centralAprovar: ({ relatorioId, ids, cartao, dupla } = {}) => {
    if (typeof relatorioId === "string" && typeof cartao === "string" && Array.isArray(ids) && ids.length) {
      ipcRenderer.send("dervs:central-aprovar", {
        relatorioId, cartao, ids: ids.map(String), dupla: Array.isArray(dupla) ? dupla.map(String) : [] });
    }
  },
  centralDesfazer: (desfazerId) => {
    if (typeof desfazerId === "string" && desfazerId) ipcRenderer.send("dervs:central-desfazer", desfazerId);
  },
  centralExplicar: (codigo) => {
    if (typeof codigo === "string" && codigo) ipcRenderer.send("dervs:central-explicar", codigo);
  },

  // ---- Integração (cérebro, painel web, terminal SSH) — lista ESTREITA ---------
  // Python -> tela: um canal só; cada mensagem traz `parte`. Tudo texto de terceiro
  // (pedido do painel web, saída do servidor): só textContent.
  aoIntegracao: aoCanal("dervs:integracao"),
  // Tela -> Python: só estes sete pedidos; formato conferido aqui, no main.js e no Python.
  // `integracaoSshConfirmar` só é chamado pelo botão do cartão (a segunda confirmação).
  integracaoPedir: () => { ipcRenderer.send("dervs:integracao-pedir"); },
  integracaoEscolherCerebro: (nome) => {
    if (typeof nome === "string" && nome) ipcRenderer.send("dervs:integracao-cerebro", nome);
  },
  integracaoDispensar: (id) => {
    if (typeof id === "string" && id) ipcRenderer.send("dervs:integracao-dispensar", id);
  },
  integracaoPedirConserto: (avisoId) => {
    if (typeof avisoId === "string" && avisoId) ipcRenderer.send("dervs:integracao-conserto", avisoId);
  },
  integracaoSshRodar: (apelido, comando) => {
    if (typeof apelido === "string" && typeof comando === "string" && comando.trim() && comando.length <= 400) {
      ipcRenderer.send("dervs:integracao-ssh-rodar", { apelido, comando });
    }
  },
  integracaoSshConfirmar: (propostaId) => {
    // Só vale com um gesto REAL do usuário (clique/tecla). Script no renderer não fabrica
    // ativação: `element.click()` e eventos sintéticos não contam.
    if (!(navigator.userActivation && navigator.userActivation.isActive)) return;
    if (typeof propostaId === "string" && propostaId) ipcRenderer.send("dervs:integracao-ssh-confirmar", propostaId);
  },
  integracaoSshCancelar: (propostaId) => {
    if (typeof propostaId === "string" && propostaId) ipcRenderer.send("dervs:integracao-ssh-cancelar", propostaId);
  },

  // ---- Permissões ("O que o DERVS pode fazer") — lista ESTREITA ----------------
  // Python -> tela: `parte` = estado | mensagem. Tela -> Python: só estes três pedidos;
  // categoria/nível/teto são conferidos de novo no main.js e no Python.
  aoPermissoes: aoCanal("dervs:permissoes"),
  permissoesPedir: () => { ipcRenderer.send("dervs:permissoes-pedir"); },
  permissoesDefinir: (categoria, nivel) => {
    if (typeof categoria === "string" && typeof nivel === "string") {
      ipcRenderer.send("dervs:permissoes-definir", { categoria, nivel });
    }
  },
  permissoesTeto: (valor) => {
    if (typeof valor === "number" && Number.isFinite(valor)) ipcRenderer.send("dervs:permissoes-teto", valor);
  },

  // ---- Vozes (perfis de voz da conversa natural) — lista ESTREITA --------------
  // Python -> tela: {lista?, estado?, gravando?, resultado?}. Tela -> Python: só estes quatro
  // pedidos; nome/papel/ativo são conferidos de novo no main.js e no Python.
  aoVozes: aoCanal("dervs:vozes"),
  vozesPedir: () => { ipcRenderer.send("dervs:vozes-pedir"); },
  vozesGravar: (nome, papel) => {
    if (typeof nome === "string" && nome.trim() && nome.length <= 40 && (papel === "dono" || papel === "convidado")) {
      ipcRenderer.send("dervs:vozes-gravar", { nome, papel });
    }
  },
  vozesAtivar: (nome, ativo) => {
    if (typeof nome === "string" && nome && typeof ativo === "boolean") {
      ipcRenderer.send("dervs:vozes-ativar", { nome, ativo });
    }
  },
  vozesApagar: (nome) => {
    if (typeof nome === "string" && nome) ipcRenderer.send("dervs:vozes-apagar", nome);
  },
});
