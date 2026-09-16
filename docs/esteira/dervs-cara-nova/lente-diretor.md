# Lente do Diretor — o que **não** entra na primeira entrega

Trabalho: `dervs-cara-nova`. Base: `docs/esteira/dervs-cara-nova/briefing.md` e `ESTADO.md`
(02/09/2026, 543 testes verdes).

Meu sucesso se mede pelo que deixei de ser feito. O tamanho real do projeto manda: um app
pessoal, um usuário, um mantenedor com ajuda de IA, sem CI, sem equipe, sem prazo de
cliente. Tudo que for construído "para o dia em que" custa manutenção para sempre e não
tem quem pague por ela.

A pergunta que apliquei em cada item: **se isto não existir na primeira entrega, o que
quebra?** Resposta "nada, só ficaria melhor" ⇒ vai para depois.

---

## O que eu não posso cortar, e não cortei

Pedido explícito do dono, fora do meu alcance de tesoura:

1. A migração da interface para Electron.
2. A onda de voz reagindo ao **volume real** do áudio — dele falando e do Dervs
   respondendo.
3. O documento de arquitetura comparando Hermes Agent, LiveKit, Open Claw, API da OpenAI
   e IA open source no VPS.

Também não corto o que é segurança: nenhuma credencial na tela/log (critério do
briefing), os trilhos de risco do `dervs_safety.py`, a cerca contra página que dá ordem, o
porteiro decidindo na máquina. Regressão em qualquer um deles não é "ficaria melhor
depois": é o app ficando perigoso.

O que eu tenho ressalva, mandei para `duvidas_para_o_dono` no fim, não cortei sozinho.

---

## Balde 1 — o que faz a coisa existir

Sem qualquer um destes, não há entrega. Ordenados pelo que **destrava o resto**.

| # | Item | Por que é balde 1 |
|---|---|---|
| 1 | **A ponte Electron↔Python, no formato mínimo** — o Python de hoje continua sendo o dono do processo e sobe o Electron como filho; conversa por uma linha de JSON por vez (`stdout`/`stdin`) | Sem ela, nada da tela nova enxerga o backend. É o pré-requisito de todo o resto |
| 2 | **Um número de volume saindo do áudio e chegando na tela** | É o coração do pedido e o critério de aceitação testável. Já existe pronto: `dervs_listen.py:32` (`rms`) e `dervs_listen.py:291` (`pico`) — não há DSP novo a escrever, só empurrar o número pela ponte |
| 3 | **Uma direção visual escolhida pelo dono** (fase 3) | O julgamento estético é dele; implementar antes da escolha é jogar fora o trabalho |
| 4 | **A janela nova com a onda, em uma direção só** | É a entrega |
| 5 | **Paridade funcional da janela de hoje**: gravar, escuta contínua, conversa da sessão, os botões copiar/enviar/executar, confirmação de plano com os dois níveis de risco, aviso de silêncio, recado de queda | Critério do briefing: "sem regressão". Cada um destes nasceu de um defeito real e caro |
| 6 | **Instância única — reusando `dervs_instancia.py` como está** | Critério do briefing. Ver o corte C1: aqui o trabalho é quase zero |
| 7 | **Bandeja com "Abrir DERVS" e "Sair do DERVS"** | Sem "Sair", o dono não tem como fechar o app (ele não usa o Gerenciador de Tarefas). Ver corte C2 |
| 8 | **Os atalhos de hoje (Área de Trabalho e menu Iniciar) apontando para o app novo, e a interface PyQt6 saindo de circulação** | Critério do briefing: "não sobra duas interfaces concorrentes" |
| 9 | **`docs/esteira/dervs-cara-nova/arquitetura-agente.md`, só análise escrita** | Critério do briefing. Ver corte C3 |
| 10 | **Os 543 testes continuando verdes + o teste novo de amplitude→onda** | É como se prova que a paridade existe |

---

## Balde 2 — o que faz ficar bom (espera a v2)

Nada aqui quebra a entrega. Cada um entra quando houver um motivo, e o motivo está escrito.

| Item | Entra quando |
|---|---|
| Selo flutuante permanente na tela (o de hoje) | O dono disser que sente falta depois de uma semana com a bandeja |
| `prefers-reduced-motion` / botão "acalmar a onda" | Se a animação incomodar em uso longo. Barato, mas não é v1 |
| Suavização/física bonita da onda (mola, decaimento, easing) | Depois de o dono ver a onda crua reagindo — aí ele diz o que quer diferente |
| Empacotar como instalador (`.exe`, NSIS, auto-update) | Quando o Dervs for para uma segunda máquina. Hoje é uma máquina só, e o atalho já resolve |
| Testes automatizados da tela (Playwright/Spectron) | Quando a tela parar de mudar toda semana. Testar tela em movimento é retrabalho puro |
| Teste próprio dos três daemons de voz (`ESTADO.md` 4.6) | Já era pendência antes desta esteira; não piora com o Electron |

---

## Balde 3 — o que alguém achou legal (some)

Nada disto foi pedido pelo dono e nada disto tem usuário. Não volta a menos que alguém
nomeie a pessoa que sofre com a ausência.

- Tema claro/escuro.
- Redimensionamento livre da janela e memória de posição/tamanho.
- Histórico visual de conversas persistido em disco.
- Tela de configurações dentro do app (hoje é `%APPDATA%\dervs\config.json`, e funciona).
- Onda em 3D/WebGL/three.js, partículas, shader, espectro FFT multibanda.
- Protocolo de ponte genérico, versionado, com registro de mensagens e plugins.
- Onda reagindo ao áudio do sistema (música, outros programas).
- Atalhos globais novos, multi-janela, modo "sempre visível em cima de jogo".
- Internacionalização da tela nova.

---

## Os cortes, um a um, com o custo dito por inteiro

### C1 — instância única **não** é recriada no Electron; reusamos a de hoje

`dervs_instancia.py` (245 linhas) não tem uma linha de PyQt6: é arquivo em
`%APPDATA%\dervs\instancia.json` + porta em `127.0.0.1` + senha sorteada + verificação de
PID (`dervs_instancia.py:51`). Como o Python continua sendo quem sobe o app (item 1 do
balde 1), a trava continua funcionando **sem alteração**, e os testes de
`test_dervs_instancia.py` continuam cobrindo. O único fio novo é trocar o `Ponte.chegou`
do Qt (`dervs.py:1491`) por "mandar `mostrar` pela ponte".

*Custo do corte:* nenhum — é paridade total por menos trabalho; a alternativa (o
`app.requestSingleInstanceLock()` do Electron) jogaria fora uma trava que já foi
depurada a duras penas e duplicaria a responsabilidade em dois lugares.

### C2 — bandeja simplificada: dois itens, não cinco

Hoje o menu tem cinco (`dervs.py:1640`): Abrir, Trazer o selo de volta, Recolher janela,
Sair. Os dois do meio existem **por causa do selo flutuante**. Se o selo não está na v1
(C3 abaixo), eles não têm o que fazer.

*Custo do corte:* o dono perde dois itens de menu que só faziam sentido com o selo — e
ganha um menu que não mente sobre o que existe.

### C3 — o selo flutuante não volta na v1; uma janela só

O critério de aceitação do briefing não pede o selo; pede que a janela nova "substitua a
janela/selo PyQt6 atual" sem sobrar duas interfaces. Recriar o selo é uma segunda janela
Electron sem moldura, sempre no topo, arrastável, com seu próprio ciclo de vida — e o
"selo que não sai da tela" já está listado no briefing como risco de regressão.

*Custo do corte:* o dono perde o lembrete visual permanente no canto da tela e passa a
chamar o Dervs pela bandeja ou pelo atalho — um clique a mais, no mesmo lugar de sempre.

### C4 — a ponte é feita sob medida para esta tela, não é framework

Uma linha de JSON por mensagem, um punhado de verbos (`volume`, `estado`, `fala`,
`plano`, `mostrar`), tipagem conferida na borda, e ponto. Sem servidor WebSocket, sem
versionamento de protocolo, sem camada de transporte trocável, sem "e se um dia outro
cliente se conectar".

*Custo do corte:* se algum dia existir um segundo cliente (um app de celular, por
exemplo), a ponte terá de ser generalizada — trabalho que hoje seria abstração de uso
único, e o CLAUDE.md deste computador proíbe exatamente isso.

### C5 — três direções visuais, estáticas; não seis, não animadas

Três é o número em que o dono consegue escolher sem cansar, e uma tela parada por direção
já mostra cor, tipografia, forma da onda e densidade. Animar as três antes da escolha é
pagar três vezes por duas que vão para o lixo.

*Custo do corte:* o dono escolhe sem ver a onda em movimento — a primeira vez que ele vê
o movimento é na demonstração ao vivo, e aí ainda dá para ajustar (balde 2).

### C6 — o documento de arquitetura é análise escrita, sem protótipo de código

Comparação, custo em dólar, latência medida ou citada com fonte e data, risco de
segurança, e uma recomendação clara. **Não** entra: subir LiveKit local, criar conta,
rodar Hermes Agent, escrever POC, instalar IA no VPS (isso já está em `fora_de_escopo`).

*Custo do corte:* os números de latência do documento serão de fonte pública, não medidos
nesta máquina — o que basta para **decidir o caminho**, que é para o que o documento serve;
medir de verdade é trabalho da rodada em que algo for implementado.

### C7 — a onda é uma forma só, em Canvas 2D

Uma onda, ligada ao valor de amplitude que já existe. Sem espectro por bandas, sem
WebGL, sem partículas.

*Custo do corte:* o "surreal" vem de cor, forma e movimento bem feitos, não de polígonos;
se depois de ver pronto o dono achar pouco, subir para WebGL é v2 e não joga nada fora.

### C8 — nada de instalador empacotado nesta rodada

O atalho continua chamando o mesmo ponto de entrada em Python de hoje
(`scripts/instalar_atalho.py` segue valendo), que agora sobe o Electron.

*Custo do corte:* o Dervs continua preso a esta máquina e ao `dervs-venv` dela — que é
exatamente onde ele já está desde sempre.

### C9 — os testes de Qt não são reescritos, e o PyQt6 não é arrancado do repositório

O que sai de circulação é o **caminho de entrada**: o atalho passa a abrir a tela nova.
`dervs.py` e seus testes ficam no disco por uma rodada.

*Custo do corte:* sobra código não usado no repositório por algumas semanas — o mesmo
tratamento já dado ao `dervs_painel.py` (`ESTADO.md` 4.7), e é o que dá um caminho de
volta se o Electron decepcionar na primeira semana.

---

## Ordem em que o que ficou entra

1. Ponte mínima Python↔Electron, com uma janela feia que só imprime o que chega. *Prova:*
   o Python manda, a janela mostra.
2. Volume real atravessando a ponte, ainda em número cru na tela. *Prova:* o teste de
   amplitude conhecida do critério de aceitação já passa aqui.
3. Fase de design: três direções, o dono escolhe uma.
4. A onda, na direção escolhida, ligada ao número do passo 2.
5. Paridade funcional (gravar, escuta, conversa, plano, confirmação, avisos) + bandeja.
6. Troca do atalho e aposentadoria do caminho PyQt6.
7. `arquitetura-agente.md` — independente dos seis anteriores, pode rodar em paralelo a
   qualquer momento.

Os passos 1 e 2 vêm antes do design de propósito: se o número do volume não atravessar
com folga de tempo, a direção visual escolhida pode ser impossível de animar, e é melhor
descobrir isso antes de desenhar.

---

## Dúvidas para o dono (para o Sintetizador registrar — não são cortes meus)

1. **O selo flutuante sai na primeira entrega?** (a) Sai, a bandeja cobre — **recomendo
   esta**; (b) fica, recriado no Electron como segunda janela. O selo é um comportamento
   que deu trabalho para acertar no Qt e refazê-lo é o maior risco isolado de regressão
   desta migração.
2. **Aceita o custo do Electron?** Ele pediu Electron e eu não corto o que ele pediu — mas
   o custo honesto é: ~150 MB a mais no disco, um processo de navegador permanentemente
   aberto numa máquina sem placa de vídeo dedicada (memória do projeto:
   `maquina-sem-placa-de-video.md`), e a paridade descrita acima para refazer. **Recomendo
   seguir com Electron**, porque a onda que ele quer é genuinamente mais fácil e mais
   bonita em Canvas/web do que em Qt — só quero que o número esteja dito antes, não depois.
3. **O documento de arquitetura fica só escrito nesta rodada?** (a) Sim, análise e
   recomendação — **recomendo esta**, é o que o `fora_de_escopo` do briefing já implica;
   (b) inclui uma prova de conceito rodando. A (b) dobra o tamanho da rodada e a decisão
   que o documento existe para tomar ainda não foi tomada.
