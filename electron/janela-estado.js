// Lógica pura de abrir/esconder/minimizar do painel único: estado + evento -> ação.
// Sem Electron aqui de propósito (testável em Node): main.js lê o estado real da
// janela, chama decidirJanela e executa a ação devolvida.
//
// estado: { existe, visivel, minimizada, saindo }
// evento: "alternar" | "mostrar" | "esconder" | "minimizar" | "fechar"
// ação:   "criar-e-mostrar" | "mostrar" | "esconder" | "minimizar" | "deixar-fechar" | "nada"

function decidirJanela(estado, evento) {
  if (!estado) return "nada";
  const { existe, visivel, minimizada, saindo } = estado;
  switch (evento) {
    case "alternar":
      if (!existe) return "criar-e-mostrar";
      return visivel && !minimizada ? "esconder" : "mostrar";
    case "mostrar":
      return existe ? "mostrar" : "criar-e-mostrar";
    case "esconder":
      return existe ? "esconder" : "nada";
    case "minimizar":
      return existe && visivel && !minimizada ? "minimizar" : "nada";
    case "fechar":
      if (!existe) return "nada";
      return saindo ? "deixar-fechar" : "esconder";
    default:
      return "nada";
  }
}

module.exports = { decidirJanela };
