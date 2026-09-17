# VERIFICAÇÃO — dervs-painel-completo (fase 1)

Conferência dos seis itens de `briefing.md`, "criterio_de_aceitacao", com evidência.

1. **Janela some atrás de outras janelas** → corrigida: `alwaysOnTop` nível
   "screen-saver" em `electron/main.js`. Comprovado ao vivo: screenshot de tela
   inteira mostrando o painel do DERVS por cima de uma janela do VS Code
   maximizada, sem eu ter precisado trazer nada para frente.
2. **Hora/CPU/RAM/disco reais, atualizando sozinho** → comprovado: relógio
   mudou entre capturas sucessivas (16:44:25 → 16:53:20) e os números de
   CPU/RAM variaram entre elas (13% → 18% → 9% de CPU; 87% → 79% de RAM) —
   dado real da máquina, não estático.
3. **Fundo translúcido/"espelhado"** → parcialmente comprovado: `transparent:
   true` funciona de verdade (teste com fundo vermelho a 30% de opacidade
   mostrou o texto do VS Code atrás, através do painel). O borrão do desktop
   ("vidro fosco") NÃO foi alcançado: `backgroundMaterial: "acrylic"` (o
   material nativo do Windows 11 que faria isso) conflita com `transparent:
   true` nesta versão do Electron e deixa a janela opaca — documentado em
   `electron/main.js` e em `ESTADO.md`. Ficou "vidro liso" transparente, sem
   o borrão — abaixo do pedido original, dito com todas as letras.
4. **Botão "Abrir DERVS App" clicável** → comprovado: clique simulado
   (coordenadas de tela) no botão, app não travou nem fechou depois do
   clique; o código (`main.js`, `ipcMain.on("dervs:abrir-app-dervs")`) chama
   `shell.openExternal` com a URL validada de `dervs_config.py`.
5. **Nada quebrou (núcleo/anéis/cartão de plano/erro/testes)** → comprovado:
   núcleo e anéis renderizando normalmente nas capturas; a regra
   `[hidden] { display: none !important; }` (bug corrigido numa esteira
   anterior) continua intacta; suíte inteira (`python -m pytest -q`) em
   **624 testes verdes**, sem nenhuma regressão.
6. **Testado ao vivo por mim, não só "deveria funcionar"** → sim: app
   reaberto do zero três vezes durante esta esteira (uma delas revelou o
   conflito do item 3, encontrado só por testar de verdade, não por ler o
   código), com screenshot da janela real e de tela inteira, e clique real
   no botão novo.

## O que NÃO foi verificado

- Comportamento com voz real (fora de escopo desta esteira — ver `ESTADO.md`,
  a pendência da Etapa 12 do plano anterior, que continua aberta).
- O botão "Abrir DERVS App" abrindo de fato uma aba no navegador do dono: o
  clique foi simulado e o app não travou, mas eu não inspecionei as abas do
  navegador do dono para confirmar a aba nova — ele tinha abas de trabalho
  sensíveis abertas (dado de paciente de outro sistema) e eu decidi não
  varrer as abas dele para confirmar isso. A lógica (`shell.openExternal`
  com URL fixa, validada, sem entrada do usuário) foi revisada linha a linha
  em vez disso.

## Nota de segurança operacional desta rodada

Durante o teste ao vivo, uma captura de tela inteira (não da janela do DERVS
especificamente) trouxe, por acidente, a tela de outro aplicativo do dono com
dado de paciente (agenda cirúrgica). O arquivo foi apagado imediatamente,
nunca foi descrito em detalhe nem citado fora desta nota, e os testes
seguintes passaram a capturar SÓ a janela do DERVS (`PrintWindow`), não a
tela inteira — exceto a única vez em que precisei comprovar a transparência
de verdade (item 3), feita com a tela praticamente vazia por trás.
