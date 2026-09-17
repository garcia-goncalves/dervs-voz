# BRIEFING — dervs-painel-completo

## pedido_original

Mensagem 1 (17/09/2026): "O DERVS Está bugado/quebrado/parado. Corrija tudo e garanta que
esteja 100% impecável... ele não faz nada. Não tem botão... nada... precisa deixar ele completo
e funcionando. Veja no print como eu gostaria que ele fosse (como se fosse um painel
transparentado... como se fosse meio espelhado, transparente.... bem revolucionário mesmo...
bem futurista... igual ao JARVIS em anexo (original)... mais ou menos isso (aceito suas
melhores ideias)... quero que o DERVS seja incrível e super inteligente! abra ele e Teste tudo
e clique em tudo..." — com duas imagens de referência (widgets estilo Rainmeter/"Stark
Industries EXPO" e um HUD circular JARVIS com relógio, capacidade de disco, comunicação, clima).

Mensagem 2 (resposta à pergunta de escopo): "Quero a opção 2 - Painel de desktop completo,
estilo Rainmeter. Quero que seja bem completo. Não precisa inventar moda. Sem firula. Mas quero
bem completo e bonito/revolucionário. Quero que inclusive esteja integrado ao meu projeto DERVS
(aplicação para gerenciar e desenvolver minhas aplicações
https://github.com/garcia-goncalves/dervs quero que tenha botão no DERVS VOZ para ele trabalhar
no DERVS aplicação... etc... quero que meu Agente DERVS seja bem inteligente e faça tudo."

Mensagem 3 (resposta à pergunta de ordem): confirmou a sequência em duas fases — primeiro o
painel visual completo com botão simples para abrir o DERVS App, depois (etapa separada) a
integração funcional profunda.

## entendimento

O dono achou o DERVS Voz "quebrado" porque (a) a janela existe e o backend está vivo, mas fica
atrás de outras janelas sem nenhum jeito óbvio de saber que está viva — nenhum estado visível
sem ele mesmo procurar — e (b) a tela de hoje é muito mais pobre do que a imagem mental dele:
só um título e um círculo com anéis, sem nenhum painel de informação, sem nenhum botão. As
imagens de referência não são "decoração" — são o pedido: um HUD de desktop tipo Rainmeter,
sempre visível, translúcido/espelhado, com dados reais da própria máquina, na linguagem visual
JARVIS que ESTE MESMO projeto já tinha aprovado antes (ciano elétrico, anéis segmentados,
tipografia de painel de nave — ver `docs/esteira/dervs-cara-nova/design.md`).

Depois de eu explicar que "painel de desktop completo" é um salto bem maior que "consertar a
tela" — e que ligar de verdade a outro projeto (`garcia-goncalves/dervs`, um painel de
segurança com login/cofre) é uma decisão à parte — o dono confirmou querer o caminho maior, mas
concordou em fazer em duas fases. **Esta esteira cobre só a fase 1**: o painel visual completo,
translúcido, com dados reais da máquina, mantendo tudo que já funciona (voz, plano, cartão de
erro), e um botão que só ABRE o DERVS App no navegador (sem login, sem comando, sem cofre).

## usuario_alvo

Um usuário só: o dono desta máquina Windows, leigo em terminal, que abre o DERVS pelo atalho da
Área de Trabalho e não vai ler nenhum log — a prova para ele é sempre visual, ao vivo, na tela.

## criterio_de_aceitacao

1. Com o DERVS aberto e outra janela (ex.: o navegador) em primeiro plano, a janela do DERVS
   continua visível por cima — não fica mais "escondida" sem o dono saber que está viva.
2. A janela mostra, sem precisar de voz nem clique: hora atual ao vivo, uso real de CPU, uso
   real de memória e espaço livre em disco desta máquina — atualizando sozinho.
3. O fundo é translúcido/"espelhado" (efeito vidro fosco), não mais um retângulo opaco quase
   preto — comprovado com uma foto de tela mostrando o desktop por trás do painel.
4. Existe um botão visível, clicável, rotulado para abrir o DERVS App — clicar nele abre
   `http://localhost:4777` no navegador padrão.
5. Nada do que já funcionava quebra: o núcleo com anéis continua reagindo a ouvindo/pensando/
   falando/erro, o cartão de plano com Confirmar/Cancelar continua funcionando, a suíte de
   testes (`python -m pytest -q`, hoje 606 verdes) continua 100% verde.
6. Eu mesmo testei tudo isso ao vivo (screenshot da janela real, clique simulado nos elementos
   novos) antes de dizer que terminei — não só "deveria funcionar".

## fora_de_escopo

- Integração funcional com o DERVS App (login, comandos, cofre, o agente "operando dentro" do
  outro projeto) — fica para a fase 2, combinada e não desta esteira.
- Previsão do tempo — dependeria de serviço externo com chave de API; não foi pedido de forma
  explícita e contraria o "sem firula" dito pelo dono.
- Ícones de atalho para abrir outros programas genéricos (Explorer, editor, jogos, como nas
  imagens de referência) além do botão do DERVS App — pode entrar depois, se ele pedir.
- Qualquer funcionalidade que dependa de internet.
- Mudar o motor de voz, o reconhecimento de fala ou a lógica de risco/confirmação — não foi
  tocado nem relatado como quebrado.

## riscos

- Nova dependência Python (`psutil`, para ler CPU/RAM/disco de verdade) — é biblioteca madura e
  amplamente usada, mas precisa entrar em `requirements.txt` e na venv da máquina do dono.
- Janela "sempre por cima" pode incomodar se cobrir área de trabalho demais — mitigado
  mantendo o painel pequeno e ancorado numa borda da tela, como um widget, não uma janela
  central.
- Fundo transparente em Electron no Windows depende do compositor do sistema (DWM) — Windows 11
  (a versão desta máquina) suporta bem; testar ao vivo antes de declarar pronto.

## plano_de_voo

1. **Janela e vidro**: `main.js` — janela `transparent: true`, sempre visível por cima
   (`alwaysOnTop`), ancorada numa borda da tela, com área de arraste própria (sem moldura do
   Windows). CSS com `backdrop-filter` para o efeito de vidro fosco, seguindo os tokens de cor
   já aprovados (`docs/esteira/dervs-cara-nova/design.md`) — consultar a skill
   `modern-web-guidance` antes de escrever o CSS novo, por causa do `backdrop-filter`.
2. **Dados reais da máquina**: módulo Python novo que lê CPU/RAM/disco com `psutil` e manda pela
   ponte já existente (mesmo soquete local, verbo novo `sistema`); o relógio é só JavaScript no
   navegador embutido, não precisa do Python.
3. **Botão para o DERVS App**: um botão na tela que, ao clicar, manda uma mensagem pelo canal
   seguro existente (`preload.js`/`ipcMain`) para o processo principal abrir
   `http://localhost:4777` no navegador do dono — sem tocar em login nem em dado do outro
   projeto.
4. **Sem regressão**: rodar a suíte completa (`python -m pytest -q`) antes de considerar pronto,
   e testar ao vivo cada estado (ocioso/ouvindo/pensando/falando/erro) e os dois botões novos
   com uma automação de tela (não só leitura de código).
5. **Documentação e memória**: atualizar `ESTADO.md`/`DERVS-EXECUTAR.md`/README com a tela nova
   e o `requirements.txt`, registrar em memória o que ficou combinado para a fase 2.
