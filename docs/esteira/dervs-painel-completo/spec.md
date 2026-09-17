# SPEC — dervs-painel-completo

## problema

A tela do DERVS (HUD Electron) hoje mostra só o título e um núcleo com anéis, sem nenhum dado
da máquina, sem efeito de vidro/transparência, e some atrás de outras janelas sem aviso — o
dono não consegue confirmar visualmente que o app está vivo nem tem como abrir o outro projeto
(DERVS App) a partir dali. O resultado é a sensação de "está quebrado", mesmo com o backend de
voz funcionando.

## solucao

Um widget de desktop sempre visível: janela Electron com fundo de vidro fosco (transparent +
backdrop-filter), sempre por cima das outras janelas mas pequena e ancorada numa borda da tela
para não atrapalhar. Três blocos de informação real, sem inventar dado: relógio (JS local),
CPU/RAM/disco desta máquina (Python + `psutil`, entregue pela ponte já existente com um verbo
novo `sistema`), e o núcleo/anéis que já existe (ocioso/ouvindo/pensando/falando/erro,
inalterado). Um botão novo, "Abrir DERVS App", que dispara `shell.openExternal` para
`http://localhost:4777` — nenhuma outra integração com o outro projeto nesta entrega.

## o_que_ja_existe

- Identidade visual já aprovada pelo dono em esteira anterior: ciano `#00E5FF`, tipografia
  Orbitron/Share Tech Mono, cantos técnicos em L, núcleo com anéis, 5 estados — ver
  `docs/esteira/dervs-cara-nova/design.md`. Esta entrega ESTENDE esses tokens, não escolhe uma
  direção nova (por isso não reabre o portão de design/painel adversarial).
- Ponte Python↔Electron por soquete TCP local já funcionando (`dervs_ponte_electron.py` +
  `electron/main.js`), com um protocolo de verbos (`estado`, `volume`, `fala`, `plano`,
  `mostrar`) documentado em `docs/superpowers/plans/dervs-cara-nova.md`, seção "Contrato
  compartilhado" — o verbo novo `sistema` segue o mesmo padrão (JSON, uma linha, `\n`).
- `preload.js`/`ipcMain` já expõe um canal seguro do renderer para o processo principal
  (`dervs:responder-plano`) — o botão do DERVS App usa o mesmo mecanismo, canal novo
  `dervs:abrir-app-dervs`.
- `dervs_config.py` já é o padrão de configuração editável em `%APPDATA%\dervs\config.json` —
  a URL do DERVS App entra como chave nova (`dervs_app_url`, padrão
  `http://localhost:4777`) em vez de ficar fixa no código.

## fontes_externas

- Documentação oficial do Electron sobre `BrowserWindow` (`transparent`, `alwaysOnTop`,
  `-webkit-app-region: drag`) — necessária para a janela de vidro sem moldura do Windows.
- `psutil` (PyPI) para CPU/RAM/disco reais — biblioteca madura, usada largamente, licença BSD.
- Skill `modern-web-guidance` (consultada antes do CSS novo) para o padrão atual de
  `backdrop-filter`/glassmorphism, por ser explicitamente um dos gatilhos da skill.

## fora_de_escopo

Igual ao `briefing.md`: integração funcional com o DERVS App (login/cofre/comando), previsão do
tempo, atalhos genéricos para abrir outros programas, qualquer dependência de internet, e
qualquer mudança na lógica de voz/risco já existente.

## contradicoes_resolvidas

- **"Sempre visível por cima" vs. "não atrapalhar quem está trabalhando":** resolvido mantendo
  o painel pequeno (mesmo tamanho de hoje, ~420×560) e ancorado numa borda da tela, não
  centralizado nem maximizado — o modelo mental é "widget de canto", igual às referências que o
  dono mandou, não uma janela que disputa o centro da tela.
- **"Sem firula" vs. "bem completo e revolucionário":** resolvido interpretando "firula" como
  decoração sem função (cores extras, animação gratuita, dado inventado) e "completo" como
  dado real e útil (relógio, uso de CPU/RAM/disco, estado de voz, atalho para o outro projeto).
  Por isso previsão do tempo (dado externo, exige API paga/gratuita e chave) fica de fora nesta
  entrega, mas dados que já existem de graça na própria máquina entram todos.

## duvidas_para_o_dono

nenhuma — as duas perguntas de escopo já foram feitas e respondidas nesta conversa (opção 2,
"painel de desktop completo", em duas fases; fase 1 é este documento).
