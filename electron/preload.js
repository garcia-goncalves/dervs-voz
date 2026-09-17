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
  responderPlano: (resposta) => {
    ipcRenderer.send("dervs:responder-plano", resposta);
  },
});
