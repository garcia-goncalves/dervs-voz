# SPEC — dervs-cara-nova

Síntese das quatro lentes (Analista, Arquiteto, Pesquisador, Diretor) contra o
`briefing.md` aprovado. Escrito pelo Sintetizador em 15/09/2026.

## problema

O DERVS funciona, mas a cara dele é de três peças herdadas do PyQt6 — selo flutuante
(`Launcher`, `dervs.py:1504`), janela de conversa (`PopUp`, `dervs.py:402`) e ícone de
bandeja (`_montar_bandeja`, `dervs.py:1640`) — e nenhuma delas mostra a coisa que o dono
mais quer ver: a própria voz virando imagem. Hoje o dado de amplitude do microfone é
calculado quadro a quadro dentro do loop de escuta e **jogado fora** depois da decisão
binária de "acabou de falar?" (`Escuta.run`, `dervs.py:346-392`, usando `rms()` de
`dervs_listen.py:32-40`). O dono fala com uma tela que não responde visualmente.

Há uma segunda dor, e é de decisão, não de tela: o dono viu três ferramentas open source
(Hermes Agent, LiveKit, Open Claw), tem crédito pago na API da OpenAI e um VPS, e quer que
o DERVS "controle tudo" — navegador, PC, servidor, GitHub, VS Code. Ele não tem como
decidir entre esses caminhos porque não existe, hoje, nenhum documento que compare custo,
latência, maturidade e **risco** dessas opções. E o risco aqui não é teórico: este próprio
repositório já registra uma página web que conseguiu dar ordem disfarçada de dono ao
cérebro do DERVS (`ESTADO.md`, linhas 130-135). Ampliar o raio de ação desse mesmo
adversário de "o próprio DERVS" para "PC, navegador logado, servidor e GitHub" sem cerca é
a dor de segurança central desta rodada.

## solucao

Duas entregas, ambas já delimitadas pelo briefing aprovado.

**1. A cara nova.** Uma janela Electron única substitui as três peças PyQt6. O processo
Python continua sendo o dono do app: ele sobe o Electron como filho e conversa por uma
linha de JSON por vez em `stdin`/`stdout` — a mesma forma de protocolo de linha que o
projeto já usa com todos os daemons (`dervs_stt_daemon.py:25-30`,
`dervs_kokoro_daemon.py:92-117`), e não um transporte novo. A ponte é sob medida, com um
punhado de verbos (`volume`, `estado`, `fala`, `plano`, `mostrar`), sem versionamento nem
camada trocável.

**A amplitude é calculada no Python, não no navegador** — esta é a decisão de arquitetura
mais consequente do spec, e o motivo está em `contradicoes_resolvidas` (C4): dar ao
Electron acesso ao microfone criaria um segundo dono do mesmo stream de áudio, que é
exatamente a corrida de threads que já derrubou o DERVS com `0xc0000374`
(memória `dervs-voz-morte-por-corrida-de-microfone.md`). `Escuta` ganha um terceiro sinal
com o nível por quadro, reusando o `rms()` que já roda ali; a onda no Canvas 2D só desenha
o número que chega pela ponte. A Web Audio API entra como referência de desenho, não como
captura.

**2. O documento `arquitetura-agente.md`.** Análise escrita, sem protótipo. Compara Hermes
Agent, LiveKit, Open Claw e API da OpenAI vs IA open source no VPS, com custo, latência e
fonte datada. A recomendação central é o **agente ouvinte local**: um processo no PC do
dono que abre conexão de saída para o VPS, recebe pedidos e decide **localmente** se
executa, reusando os trilhos de risco que o `dervs_safety.py` já aplica. O VPS nunca tem
acesso de entrada ao PC. E o documento carrega, em destaque, a ressalva de segurança sobre
o OpenClaw: mais de 30 mil instâncias expostas encontradas pela Bitsight, alerta oficial do
CNCERT chinês, e nenhuma defesa contra prompt injection indireta — ele **não** é
recomendado como peça de controle, e dizer isso é parte da entrega, não uma nota de rodapé.

## o_que_ja_existe

Tudo abaixo veio da lente do Arquiteto, com caminho conferido no repositório.

**Reaproveitado sem alteração:**

- `dervs_instancia.py` (arquivo inteiro) — a trava de instância única não tem uma linha de
  PyQt6: é `%APPDATA%\dervs\instancia.json` + porta sorteada em `127.0.0.1` + senha +
  verificação de PID vivo (`_processo_vivo`, `dervs_instancia.py:51-77`), com protocolo
  `MOSTRAR <senha>` → `DERVS-OK` (`RESPOSTA_SIM`, `dervs_instancia.py:44`). Como o Python
  continua subindo o app, ela segue funcionando intacta. O único fio novo é trocar o sinal
  `Ponte.chegou` do Qt (`dervs.py:1491-1501`) por um "mostrar" empurrado pela ponte nova.
- `test_dervs_instancia.py` (ex.: `test_o_primeiro_toma_posse`, linhas 36-40) — continua
  cobrindo a trava sem reescrita.

**Reaproveitado com um fio novo:**

- `rms(frame)` em `dervs_listen.py:32-40` e `pico(pcm)` em `dervs_listen.py:291-302` — são
  as únicas funções de amplitude do projeto e já entregam exatamente o número que a onda
  precisa. Já testadas em `test_dervs_listen.py:127-129` e `test_dervs_silencio.py:38-87`.
- `Escuta.run()` em `dervs.py:346-392`, com a leitura quadro a quadro em `dervs.py:362` —
  é o lugar exato onde nasce um sinal novo de nível, sem tocar a lógica de decisão que já
  existe (`fala` e `mudo`, `dervs.py:335-338`).

**Reaproveitado como padrão a copiar:**

- O protocolo de linha dos daemons: `READY` / `PORTEIRO <wav>` / `TRANSCREVER <wav>` →
  `RESULT <json>` (`dervs_stt_daemon.py:25-30`) e `READY` / `WAV <caminho>` / `FIM` /
  `ERRO <motivo>` (`dervs_kokoro_daemon.py:92-117`). A ponte Electron fala no mesmo
  espírito: uma linha, um verbo, resposta previsível.
- As três escutas do `QProcess` do STT (`finished`, `errorOccurred`,
  `readyReadStandardError`, a partir de `dervs.py:477`) — o `child_process` do lado Node
  precisa das mesmas três, ou volta o "DERVS surdo e calado".
- `closeEvent` em `dervs.py:1487-1488` (`e.ignore(); self.hide()`) — em Electron é
  `preventDefault()` no `close` da `BrowserWindow`. Não é o padrão do framework: tem de ser
  copiado de propósito.
- Convenções da casa: `pytest.ini:2-11` (`--import-mode=importlib`) e `conftest.py:30-49`
  (exclusão de `.claude/worktrees` da coleta) — qualquer config de teste JS nova precisa do
  equivalente, ou o mesmo problema volta quando agentes trabalharem em paralelo.
- `scripts/instalar_atalho.py` — continua sendo quem cria os atalhos e desenha o `dervs.ico`
  (`README.md:52-57`); só o ponto de entrada muda.

**Descartado por falta de caminho:** a lente do Arquiteto declarou explicitamente que
**não encontrou código de reprodução/playback** do `.wav` gerado pelos daemons de voz.
Sem caminho, não entra como achado. Fica como primeira tarefa da fase 4 uma varredura
dedicada (candidato provável: `dervs_tts.py`, que o Arquiteto não abriu linha a linha).
Plano B, caso não exista módulo isolado: calcular `rms()` por trecho do `.wav` já pronto e
empurrar pela ponte sincronizado ao início da reprodução — a função existe, falta só o
chamador.

## fontes_externas

Todas consultadas em 15/09/2026, pela lente do Pesquisador.

**Hermes Agent** — https://hermes-agent.org/ (o que é, licença MIT, roda local em Linux/
macOS/WSL2, funcionalidades de navegador/SSH/cron) · https://dev.to/tokenmixai/hermes-agent-review-956k-stars-self-improving-ai-agent-april-2026-11le
(mantenedor Nous Research, ~95,6 mil estrelas em sete semanas, v0.10.0 com 118 skills) ·
https://startupfortune.com/hermes-agent-crosses-214000-github-stars-as-developers-abandon-commercial-ai-agent-frameworks/
(214 mil estrelas em seis meses).

**LiveKit** — https://docs.livekit.io/agents/ e https://github.com/livekit/agents
(framework de agentes de voz, pipeline de áudio e turn-taking) ·
https://voice.oss.codes/open-source/livekit-agents/ (licença Apache 2.0 no ecossistema
inteiro) · https://docs.livekit.io/client-sdk-js/functions/createAudioAnalyser.html e
https://deepwiki.com/livekit/components-js/5.4-audio-visualization (o `createAudioAnalyser`
é um embrulho do `AnalyserNode` padrão) · https://www.cekura.ai/blogs/livekit-agents (a
própria documentação orça 3 a 4 semanas de infraestrutura para self-host) ·
https://trtc.io/blog/details/livekit-pricing-2026 (planos Build grátis / Ship US$ 50 /
Scale US$ 500; ~US$ 0,01 por minuto de agente acima da cota).

**OpenClaw ("Open Claw")** — https://openclaw.ai/ (o que é, licença MIT, roda local, 29
canais, 100+ AgentSkills) · https://www.digitalocean.com/resources/articles/what-is-openclaw
e https://milvus.io/blog/openclaw-formerly-clawdbot-moltbot-explained-a-complete-guide-to-the-autonomous-ai-agent.md
(histórico Clawdbot → Moltbot → OpenClaw, criado por Peter Steinberger, hoje sob uma
fundação 501(c)(3)) · **segurança:**
https://www.bitsight.com/blog/openclaw-ai-security-risks-exposed-instances (mais de 30 mil
instâncias expostas; honeypot atacado minutos depois de subir),
https://thehackernews.com/2026/03/openclaw-ai-agent-flaws-could-enable.html (alerta do
CNCERT; configuração fraca por padrão somada a acesso privilegiado) e
https://www.giskard.ai/knowledge/openclaw-security-vulnerabilities-include-data-leakage-and-prompt-injection-risks
(vazamento de dado e prompt injection).

**OpenAI API vs IA no VPS** — https://www.spheron.network/blog/gpt-6-vs-self-hosted-llm-2026/
(GPT-4.1 em ~US$ 2,00/milhão de entrada e US$ 8,00/milhão de saída; o `mini` em uso é mais
barato) · https://cloudzy.com/blog/self-hosting-open-weight-llm-gpu-vps-cost/ (VPS 4 vCPU/
8 GB com Ollama ≈ US$ 54/mês; ponto de equilíbrio do self-host entre 10 e 30 milhões de
tokens/dia; TTFT de 200–600 ms via API).

**Controle remoto seguro** — https://docs.github.com/en/actions/reference/runners/self-hosted-runners
(o runner só precisa de saída HTTPS; nenhuma porta de entrada aberta na máquina que
executa) · https://github.com/Tunglam0605/remote-workstation-mcp (transporte preso a
`127.0.0.1`, túnel só de saída, concessão local com prazo, nega por padrão) ·
https://www.scalekit.com/blog/agent-workflows-remote-mcp-servers (token OAuth 2.1 com
escopo por chamada, validação por JWKS).

**Onda de voz na web** — https://developer.mozilla.org/en-US/docs/Web/API/AnalyserNode
(`getByteTimeDomainData` / `getByteFrequencyData` + `requestAnimationFrame` em `<canvas>`) ·
https://css-tricks.com/making-an-audio-waveform-visualizer-with-vanilla-javascript/ (código
completo do mesmo padrão).

## fora_de_escopo

O corte do Diretor, já decidido, mais o que o briefing aprovado já tinha excluído.

**Não entra nesta rodada, e o motivo está escrito:**

1. **Selo flutuante permanente** — não é recriado no Electron nesta entrega. Seria uma
   segunda janela sem moldura, sempre no topo, arrastável, com ciclo de vida próprio, e a
   regra "não sai da tela" é lógica por-monitor (`Launcher._dentro_da_tela`,
   `dervs.py:1528-1540`), não um simples limite da tela primária. **Confirmado pelo dono em
   15/09/2026:** some nesta entrega; volta na v2 se fizer falta.
2. **Recriar a instância única em Electron** (`app.requestSingleInstanceLock()`) —
   `dervs_instancia.py` é reusado como está.
3. **Ponte genérica, versionada, com plugins ou WebSocket** — abstração de uso único.
4. **Mais de três direções visuais, ou direções animadas** — três telas paradas mostram cor,
   tipografia, forma e densidade. Animar antes da escolha é pagar três vezes por duas que
   vão para o lixo.
5. **Onda em WebGL/three.js, partículas, shader, espectro FFT multibanda** — uma forma só,
   em Canvas 2D, ligada ao valor de amplitude que já existe.
6. **Protótipo, POC ou instalação de qualquer das ferramentas pesquisadas** — o documento de
   arquitetura é análise escrita. Nada de subir LiveKit, rodar Hermes Agent ou instalar IA
   no VPS.
7. **Instalador empacotado** (`.exe`, NSIS, auto-update) — o atalho continua chamando o
   ponto de entrada Python, que agora sobe o Electron.
8. **Arrancar o PyQt6 do repositório** — `dervs.py` e seus testes ficam no disco por uma
   rodada. O que sai de circulação é o caminho de entrada. É o caminho de volta se o
   Electron decepcionar na primeira semana, e é o mesmo tratamento já dado ao
   `dervs_painel.py`.
9. **Testes automatizados de tela (Playwright/Spectron)** — entram quando a tela parar de
   mudar toda semana.
10. **Balde 3 inteiro, sem dono nomeado:** tema claro/escuro, redimensionamento e memória de
    posição, histórico de conversas em disco, tela de configurações no app, onda reagindo ao
    áudio do sistema, atalhos globais novos, multi-janela, internacionalização.
11. **Do briefing, e continua valendo:** implementar de fato o controle de navegador, PC,
    servidor, GitHub ou VS Code; hospedar qualquer IA no VPS; trocar a voz Kokoro pela da
    nuvem; resolver o microfone físico desconectado; instalar CI; montar o instalador do
    Playwright no Windows.

**O que não foi cortado, e não podia ser:** a migração para Electron, a onda ligada ao
volume real (da voz do dono e da voz do DERVS), o documento comparando as cinco opções por
nome, e tudo que é segurança — nenhuma credencial em tela/log/arquivo, os trilhos de
`dervs_safety.py`, a cerca contra página que dá ordem, o porteiro decidindo na máquina.

## contradicoes_resolvidas

**C1 — "controlar tudo" e "Open Claw" saem de foco (Analista, Diretor) vs o pedido original
nomeia os dois (dono).** Vence uma divisão, não um lado. Como **código**, o controle
continua fora de escopo — isso o briefing aprovado já decidiu, e o Analista confirmou pela
lente de usuário: nenhum dos cinco alvos (navegador, PC, servidor, GitHub, VS Code) tem
momento de uso concreto e frequente nomeado pelo dono, só o desejo genérico. Como
**documento**, porém, o Analista e o Diretor não podem tirar de foco o que o
`criterio_de_aceitacao` do briefing exige por nome: `arquitetura-agente.md` **avalia Hermes
Agent, LiveKit e Open Claw nominalmente**, cada um com custo, licença, maturidade e risco. O
Analista sugeriu que o Open Claw "é candidato natural a ficar de fora da recomendação
principal" — isso é aceito com uma correção importante: ele fica fora da **recomendação**,
mas dentro da **avaliação**, e justamente a razão pela qual ele é recusado é a informação
mais valiosa que o documento entrega (ver C2). Motivo: o dono pediu para saber sobre essas
ferramentas; entregar silêncio sobre uma delas seria responder outra pergunta. E o documento
deve propor uma **ordem de prioridade** entre os cinco alvos de controle, como o Analista
pediu, começando pelo navegador — é o único que já tem código parcial e teste no repositório
(`dervs_browser.py`).

**C2 — "Open Claw talvez nem tenha papel próprio" (Analista) vs "OpenClaw é real, popular e
documentadamente perigoso" (Pesquisador).** Vence o Pesquisador, com fonte datada: o
projeto existe (MIT, fundação 501(c)(3), 100+ AgentSkills, 29 canais), e é exatamente por
existir e ser popular que o achado importa. A Bitsight encontrou mais de 30 mil instâncias
expostas na internet, com honeypot atacado minutos depois de subir; o CNCERT emitiu alerta
oficial citando configuração fraca por padrão somada a acesso privilegiado ao sistema; e o
produto anuncia "acesso total ao sistema" sem qualquer forma de distinguir um comando
legítimo de um prompt malicioso embutido no conteúdo que ele processa. **Decisão: o
documento de arquitetura recomenda CONTRA adotar o OpenClaw como peça de controle do DERVS,
e essa ressalva vai em destaque visível, não em nota de rodapé.** Motivo: o briefing pede
"caminho seguro, sem liberar controle irrestrito", e adotar o OpenClaw como está contraria
esse critério diretamente. Some-se a isso o que o Analista já documentou: este repositório
**já sofreu** uma tentativa de ordem disfarçada de dono vinda de uma página web
(`ESTADO.md:130-135`) e só se salvou porque havia teste. O adversário é o mesmo; só o raio
de ação mudaria.

**C3 — o dono quer "agente no VPS mexendo no meu PC" vs Hermes Agent assume rodar na própria
máquina que controla (Pesquisador).** Vence o Pesquisador, e a solução não é nenhuma das
três ferramentas: é o padrão do **agente ouvinte local com conexão de saída**. O PC do dono
nunca abre porta de entrada; ele conecta para fora, recebe pedidos e decide localmente se
executa, aplicando os trilhos de risco que o DERVS já tem. Motivo: é o padrão real de
projetos sérios, com dois exemplos independentes e datados — os self-hosted runners do
GitHub Actions (só saída em HTTPS) e o `remote-workstation-mcp` (transporte preso a
`127.0.0.1`, túnel só de saída, concessão local com prazo, nega por padrão). O Hermes Agent
segue no documento como candidato a **cérebro mais capaz**, avaliado por nome, com a
ressalva de que nenhuma fonte encontrada o audita quanto a prompt injection — menos
escrutínio público que o OpenClaw não é sinal de que é mais seguro.

**C4 — onde a amplitude é calculada: `rms()`/`pico()` no Python (Arquiteto) vs
`AnalyserNode` da Web Audio API no Electron (Pesquisador).** Vence o Arquiteto, e por uma
razão mais forte que "o que já existe no repositório ganha". Se o Electron capturar o
microfone com `getUserMedia`, passam a existir **dois donos do mesmo stream de áudio** — e
esse é, literalmente, o defeito que já derrubou o DERVS com `0xc0000374`, duas threads
fechando o mesmo stream (memória do projeto,
`dervs-voz-morte-por-corrida-de-microfone.md`; o Arquiteto também aponta o risco na sua
tabela, linha do fechamento do microfone). **Decisão: o microfone continua tendo um dono só,
o Python.** `Escuta` ganha um sinal novo de nível por quadro reusando o `rms()` que já roda
no loop (`dervs.py:362`), e o número atravessa a ponte. A Web Audio API entra apenas como
referência de **desenho** (`requestAnimationFrame` + `<canvas>` 2D), não de captura. Bônus:
o teste de amplitude exigido pelo `criterio_de_aceitacao` fica sendo um teste Python sobre
uma função pura já coberta, em vez de um teste de navegador.

**C5 — "LiveKit resolve streaming de voz" (Pesquisador) vs "a onda não precisa de LiveKit"
(Pesquisador e Diretor).** Não há adoção de LiveKit nesta rodada, e a razão é dupla: para a
onda, o `createAudioAnalyser` do LiveKit é apenas um embrulho do `AnalyserNode` padrão — não
adiciona nada que o navegador já não faça; e para o áudio em si, adotá-lo trocaria "processo
local que grava, transcreve e fala" por "cliente que entra numa room", uma mudança de
arquitetura do mesmo porte que o controle remoto que o briefing já pôs fora de escopo, com
self-host orçado pela própria documentação em 3 a 4 semanas num VPS que já hospeda outros
dois projetos do dono. Ele permanece **avaliado por nome no documento**, com custo e licença,
como manda o critério de aceitação.

**C6 — API da OpenAI vs IA open source no VPS.** Não houve contradição entre as lentes:
vence a API, e com número. O `gpt-4.1-mini` já está integrado, testado, e o crédito já foi
pago (custo marginal zero até esgotar o saldo); o VPS sem GPU dedicada custaria ~US$ 54/mês
para entregar um modelo mais fraco e mais lento, competindo por CPU e memória com os outros
dois projetos hospedados, e o ponto de equilíbrio financeiro do self-host só chega entre 10
e 30 milhões de tokens por dia — ordens de grandeza acima do que um assistente pessoal de
voz gera. O documento traz esses números com fonte, porque o Analista observou corretamente
que o dono decide dinheiro quando vê o número, não quando lê "depende".

**C7 — "os 543 testes continuam verdes" (briefing) vs "os 16 testes de PyQt6 ficam obsoletos
por definição" (Arquiteto).** Vence o corte C9 do Diretor, e ele dissolve a contradição:
como `dervs.py` e seus testes **ficam no disco** por uma rodada, os 16 testes de Qt continuam
passando sem reescrita, e o critério do briefing é atendido literalmente. O que muda é só o
ponto de entrada do atalho. Motivo: arrancar o PyQt6 na mesma rodada juntaria dois riscos —
o da migração e o da remoção — sem nenhum caminho de volta.

**C8 — bandeja de dois itens (Diretor, corte C2) vs "Recolher janela" é uso frequente
(Analista, momento 4).** Vence o Analista, parcialmente: a bandeja nasce com **três** itens
— "Abrir DERVS", "Recolher janela" e "Sair do DERVS". O Diretor justificou o corte dizendo
que os dois itens do meio existem por causa do selo, mas isso vale só para "Trazer o selo de
volta" (`dervs.py:1654-1656`): "Recolher janela" esconde a `PopUp`, e a `PopUp` tem
sucessora direta na janela Electron. Motivo: o Analista nomeou o usuário que sofre com a
ausência — o dono, que deixa o programa aberto o dia inteiro — e a regra do corte diz que,
nomeado o usuário, o corte não passa. "Sair do DERVS" segue inegociável: é a única saída que
não depende do Gerenciador de Tarefas, e o dono não tem essa habilidade de reserva.

**C9 — o Arquiteto não achou o playback do áudio da voz do DERVS.** Não virou dúvida para o
dono, porque é pergunta sobre o disco, e pergunta sobre o disco não sobe: vira **tarefa
obrigatória da fase 4**, uma varredura dedicada (candidato provável: `dervs_tts.py`, não
aberto linha a linha). Se o módulo não existir isolado, o plano B já está decidido: calcular
`rms()` por trecho do `.wav` que os daemons entregam (`WAV <caminho>`,
`dervs_kokoro_daemon.py:111`) e empurrar pela ponte sincronizado ao início da reprodução. A
função existe; falta o chamador. Motivo para decidir agora: a onda reagindo também quando o
DERVS fala é pedido explícito do briefing, e deixar isso "a confirmar" na fase 4 sem plano B
é como uma rodada perde uma metade da sua entrega.

**C10 — custo do Electron: o Diretor levantou como dúvida, e eu decido aqui.** Seguimos com
Electron, sem perguntar. Motivo: o Electron está nomeado no `entendimento` do briefing **já
aprovado pelo dono**, e o próprio Diretor recomenda seguir — o que ele queria era que o
número fosse dito antes, não depois. Então fica dito, e em destaque: **~150 MB a mais no
disco e um processo de navegador permanentemente aberto numa máquina sem placa de vídeo
dedicada** (memória do projeto, `maquina-sem-placa-de-video.md`). Isso não vai a
`duvidas_para_o_dono` porque não muda o que ele vê entregue: é divulgação de custo, não
decisão de produto, e o Analista já fixou a régua verificável que protege contra o risco
real — a onda nova não pode consumir mais CPU que o `self.timer` de 500 ms do selo atual
(`dervs.py:1521-1522`) ao ponto de atrapalhar o uso o dia inteiro. Essa régua entra como
critério da fase de verificação.

**C11 — o documento de arquitetura fica só escrito? O Diretor perguntou, e eu decido aqui.**
Fica só escrito, sem prova de conceito. Motivo: a resposta já está no briefing aprovado, em
dois lugares — o `fora_de_escopo` exclui hospedar qualquer IA no VPS e implementar o
controle, e uma POC de qualquer das três ferramentas exigiria exatamente uma dessas duas
coisas. Não é decisão nova do dono; é leitura do que ele já aprovou. O custo é honesto e
fica registrado no documento: os números de latência serão de fonte pública datada, não
medidos nesta máquina — o que basta para **escolher o caminho**, que é para o que o documento
serve.

## duvidas_para_o_dono

nenhuma

**Resolvida pelo dono em 15/09/2026: o selo flutuante some nesta entrega.** A bandeja cobre
o lugar dele (Abrir DERVS / Recolher janela / Sair do DERVS). Ele volta, se fizer falta,
como primeira melhoria da versão seguinte, já no visual novo. As outras duas dúvidas que o
Diretor levantou (C10, C11) já tinham sido decididas pelo Sintetizador, porque a resposta já
estava no briefing aprovado.
