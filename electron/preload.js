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
});
