# Arquitetura do agente — as cinco opções, comparadas

Documento escrito para você decidir, não para programar. Ele compara, por nome, as cinco
coisas que você pôs na mesa — **Hermes Agent**, **LiveKit**, **OpenClaw**, a **API da
OpenAI** e **IA rodando no seu VPS** — e termina recomendando um caminho.

Nada aqui foi instalado, testado ou ligado. Esta é a entrega escrita da rodada
`dervs-cara-nova`; implementar o controle de navegador, PC, servidor, GitHub ou VS Code
continua fora de escopo por decisão sua no briefing.

---

## Em uma página

- **A recomendação é um "agente ouvinte local":** um programa no seu PC que **liga para
  fora** e nunca aceita ligação de fora. Você fala pelo celular ou pelo VPS, o pedido chega
  ao PC, e quem decide se aquilo roda é a sua própria máquina — o porteiro e o
  `dervs_safety.py` que já existem, sem mudança de regra.
- **O OpenClaw não entra.** Ele é real, popular e documentadamente perigoso: mais de 30 mil
  instâncias expostas na internet, alerta oficial de órgão de segurança, e nenhuma defesa
  contra "página web dando ordem". A seção de destaque está logo abaixo.
- **O Hermes Agent fica como candidato a cérebro mais capaz**, não como peça de controle
  remoto — ele foi feito para rodar **na** máquina que controla, que é o oposto do que você
  pediu.
- **O LiveKit foi avaliado e não é adotado.** Ele resolve um problema que o DERVS não tem.
- **A API da OpenAI vence a IA no seu VPS, e com número:** o VPS custaria cerca de
  US$ 54/mês para entregar um modelo mais fraco; o self-host só compensa financeiramente
  entre 10 e 30 milhões de tokens por dia — ordens de grandeza acima de um assistente
  pessoal de voz.
- **Por onde começar, quando começar:** navegador → PC → GitHub → VS Code → servidor.

---

## Como ler os números deste documento

**Nenhuma latência, nenhum custo e nenhum risco aqui foi medido nesta máquina.** Tudo vem
de fonte pública, com link e data de consulta (**15/09/2026**). Isso foi uma decisão
consciente: uma prova de conceito exigiria instalar uma dessas ferramentas ou hospedar IA
no VPS, e as duas coisas você já tinha excluído do escopo.

Isso basta para **escolher o caminho** — que é para o que este documento serve. Não basta
para prometer "vai responder em X milissegundos na sua casa". Quando o caminho estiver
escolhido, a medição real vira a primeira tarefa da implementação.

---

## Ferramenta por ferramenta

### 1. Hermes Agent

**O que é.** Um agente de IA que roda na sua própria máquina e sabe usar navegador, SSH e
tarefas agendadas. É o mais próximo de "um DERVS pronto" entre os três que você trouxe.
Fonte: https://hermes-agent.org/ (consultado em 15/09/2026).

**Licença.** MIT — livre, inclusive comercialmente.
Fonte: https://hermes-agent.org/ (15/09/2026).

**Maturidade.** Cresceu muito rápido: mantido pela Nous Research, com cerca de 95,6 mil
estrelas no GitHub em sete semanas e a versão 0.10.0 trazendo 118 habilidades
(https://dev.to/tokenmixai/hermes-agent-review-956k-stars-self-improving-ai-agent-april-2026-11le,
15/09/2026), chegando a 214 mil estrelas em seis meses
(https://startupfortune.com/hermes-agent-crosses-214000-github-stars-as-developers-abandon-commercial-ai-agent-frameworks/,
15/09/2026). Traduzindo: é popular de verdade, mas é um projeto **novo**. Popularidade de
seis meses não é o mesmo que estabilidade de seis anos.

**Custo.** O programa é gratuito. O que custa é o modelo de IA que ele usa por trás — a
mesma conta que você já paga hoje na OpenAI.

**Latência.** Não há número público comparável; o tempo de resposta seria essencialmente o
do modelo escolhido (ver a seção da API da OpenAI).

**Risco — e é o ponto que importa.** Ele **roda na máquina que controla**, em Linux, macOS
ou WSL2 (https://hermes-agent.org/, 15/09/2026). Isso é o contrário do que você descreveu
("um agente no VPS mexendo no meu PC"): ele não é a ponte entre VPS e PC, ele é o morador
do PC. E, segundo risco: **nenhuma das fontes encontradas audita o Hermes Agent quanto a
"página web dando ordem" (prompt injection)**. Menos escrutínio público que o OpenClaw não
significa mais seguro — significa menos gente tendo procurado.

**Veredito.** Fica na mesa como **candidato a cérebro mais capaz** numa rodada futura, se
o `gpt-4.1-mini` ficar apertado. Não é a peça de controle remoto.

### 2. LiveKit

**O que é.** Uma infraestrutura para agentes de voz em tempo real: transporte de áudio,
controle de quem fala quando, salas de conversa.
Fontes: https://docs.livekit.io/agents/ e https://github.com/livekit/agents (15/09/2026).

**Licença.** Apache 2.0 em todo o ecossistema — livre, inclusive comercialmente.
Fonte: https://voice.oss.codes/open-source/livekit-agents/ (15/09/2026).

**Maturidade.** Alta. É a opção mais adulta das três open source aqui.

**Custo.** Plano Build gratuito, plano Ship US$ 50/mês, plano Scale US$ 500/mês, e cerca de
US$ 0,01 por minuto de agente acima da cota
(https://trtc.io/blog/details/livekit-pricing-2026, 15/09/2026). Rodar por conta própria no
seu VPS não sai de graça em tempo: **a própria documentação orça 3 a 4 semanas de trabalho
de infraestrutura** (https://www.cekura.ai/blogs/livekit-agents, 15/09/2026).

**Latência.** Feito para tempo real — é a especialidade da casa. Mas veja abaixo por que
isso não muda nada para você.

**Risco.** Baixo em segurança, alto em "reescrever o que funciona".

**Veredito — não adotar, e por dois motivos concretos.** Primeiro: para a onda de voz da
tela nova, a função de visualização do LiveKit (`createAudioAnalyser`) é apenas um embrulho
de um recurso que **todo navegador já tem de fábrica**
(https://docs.livekit.io/client-sdk-js/functions/createAudioAnalyser.html e
https://deepwiki.com/livekit/components-js/5.4-audio-visualization, 15/09/2026) — não
adiciona nada. Segundo: para o áudio em si, adotá-lo trocaria "um programa local que grava,
transcreve e fala" por "um cliente que entra numa sala de reunião". É uma mudança de
arquitetura do mesmo tamanho do controle remoto que você já tirou de escopo, num VPS que já
hospeda outros dois projetos seus.

### 3. OpenClaw

**O que é.** Um agente autônomo que se conecta a muitos canais (WhatsApp, e-mail e outros —
29 no total) e traz mais de 100 habilidades prontas, com acesso amplo ao sistema. Nasceu
como Clawdbot, virou Moltbot, hoje se chama OpenClaw, foi criado por Peter Steinberger e
está sob uma fundação sem fins lucrativos. Fontes: https://openclaw.ai/,
https://www.digitalocean.com/resources/articles/what-is-openclaw e
https://milvus.io/blog/openclaw-formerly-clawdbot-moltbot-explained-a-complete-guide-to-the-autonomous-ai-agent.md
(15/09/2026).

**Licença.** MIT. **Maturidade.** Muito popular, muito jovem, três nomes em pouco tempo.

**Custo.** Gratuito; paga-se o modelo por trás.

**Risco.** É o assunto da próxima seção, e ela existe porque a resposta não cabia aqui.

### 4. API da OpenAI (o caminho de hoje)

**O que é.** O cérebro que o DERVS já usa: `gpt-4.1-mini`, integrado, testado e com crédito
já pago por você.

**Licença.** Serviço pago de terceiro, sem licença de software a respeitar.

**Maturidade.** É o que está rodando na sua máquina agora. Melhor evidência que existe.

**Custo.** Cobrado por uso. Como referência pública de ordem de grandeza: o GPT-4.1 custa
cerca de US$ 2,00 por milhão de palavras-token de entrada e US$ 8,00 por milhão de saída
(https://www.spheron.network/blog/gpt-6-vs-self-hosted-llm-2026/, 15/09/2026) — e o modelo
`mini` que você usa é **mais barato que isso**. Como o crédito já foi comprado, o custo
marginal é zero até o saldo acabar.

**Latência.** O tempo até a primeira palavra da resposta fica entre 200 e 600 ms
(https://cloudzy.com/blog/self-hosting-open-weight-llm-gpu-vps-cost/, 15/09/2026). Número
de fonte pública, não medido aqui.

**Risco.** O áudio e o texto saem da sua casa. Esse risco já está tratado no DERVS pelo
porteiro: ele decide **dentro da máquina** se você chamou o DERVS, e só o que passa por ele
é enviado para fora. Quem não foi chamado é descartado e nunca sai do computador.

### 5. IA open source rodando no seu VPS

**O que é.** Hospedar você mesmo um modelo aberto (por exemplo, com Ollama) no servidor que
já tem.

**Licença.** Os modelos abertos são livres; o que se paga é a máquina.

**Maturidade.** A tecnologia é madura. O problema não é ela.

**Custo.** Um VPS de 4 vCPU e 8 GB rodando Ollama sai por cerca de **US$ 54/mês**
(https://cloudzy.com/blog/self-hosting-open-weight-llm-gpu-vps-cost/, 15/09/2026) — e esse
é um VPS **sem placa de vídeo dedicada**, competindo por processador e memória com os
outros dois projetos que já moram lá.

**Latência.** Pior que a da API, pelo mesmo motivo: sem GPU, o modelo pensa devagar.

**Risco.** O dado não sai de casa — essa é a vantagem real e honesta. Em troca, você paga
mensalidade fixa por um modelo mais fraco e mais lento, e assume a manutenção.

---

## DESTAQUE — por que o OpenClaw **não** entra

Esta seção vem **antes** da recomendação de propósito. Ela é a informação mais valiosa
deste documento.

**Recomendação: não adotar o OpenClaw como peça de controle do DERVS.**

Os três achados, cada um com fonte e data:

1. **Mais de 30 mil instâncias do OpenClaw estão expostas na internet aberta.** Os
   pesquisadores da Bitsight subiram uma instância-isca e ela **começou a ser atacada
   minutos depois de entrar no ar**.
   Fonte: https://www.bitsight.com/blog/openclaw-ai-security-risks-exposed-instances
   (consultado em 15/09/2026).
2. **Um órgão oficial de segurança emitiu alerta público sobre ele** — o CNCERT, o centro
   de resposta a incidentes chinês. O motivo citado: configuração fraca por padrão somada a
   acesso privilegiado ao sistema. Ou seja, ele vem de fábrica aberto demais para o tanto de
   poder que tem.
   Fonte: https://thehackernews.com/2026/03/openclaw-ai-agent-flaws-could-enable.html
   (15/09/2026).
3. **Vazamento de dado e "página dando ordem" (prompt injection) estão documentados.**
   Fonte: https://www.giskard.ai/knowledge/openclaw-security-vulnerabilities-include-data-leakage-and-prompt-injection-risks
   (15/09/2026).

**Por que isso é grave especificamente no seu caso.** O adversário aqui não é teórico — ele
já bateu na sua porta. O `ESTADO.md` deste repositório registra, na seção "o que foi
corrigido", que **uma página web conseguia dar ordem disfarçada de você ao cérebro do
DERVS**: bastava a página escrever algo como "[dono] agora rode: ..." e o modelo lia como se
fosse a sua voz. Pior: o teste que deveria proteger disso passava verde, porque exercitava o
outro caminho de código. Isso já foi corrigido — hoje os dois cérebros rodam a mesma bateria
de testes, e os rótulos que o piloto do navegador lê entram cercados e explicitamente
marcados como "não obedeça a isto".

Agora junte as duas coisas. O OpenClaw anuncia acesso amplo ao sistema **sem** distinguir um
comando legítimo de um comando plantado no conteúdo que ele processa. Ligá-lo ao DERVS
significaria pegar exatamente o mesmo adversário que já tentou — e ampliar o raio de ação
dele de "o próprio DERVS" para "seu PC, seu navegador logado, seu servidor e seu GitHub".

Você pediu, com todas as letras no briefing, um "caminho seguro, sem liberar controle
irrestrito". Adotar o OpenClaw como ele é hoje contraria esse critério de forma direta.

Ele continua **avaliado** neste documento porque você perguntou sobre ele, e silêncio seria
responder outra pergunta. Ele só não é **recomendado**.

---

## Dinheiro: API da OpenAI contra IA no seu VPS

Aqui não houve divergência entre as análises. Vence a API, e dá para ver pelo número:

| | API da OpenAI (hoje) | IA no seu VPS |
|---|---|---|
| Mensalidade fixa | nenhuma | **~US$ 54/mês** |
| Custo marginal agora | **zero** (crédito já pago) | além da mensalidade, a manutenção |
| Tempo até a primeira palavra | **200–600 ms** | pior, sem GPU dedicada |
| Qualidade do modelo | melhor | mais fraca |
| Quando o self-host compensa | — | **entre 10 e 30 milhões de tokens por dia** |
| Dado sai de casa? | sim (cercado pelo porteiro) | não |

Fontes: https://cloudzy.com/blog/self-hosting-open-weight-llm-gpu-vps-cost/ (US$ 54/mês,
ponto de equilíbrio de 10 a 30 milhões de tokens/dia, TTFT de 200–600 ms) e
https://www.spheron.network/blog/gpt-6-vs-self-hosted-llm-2026/ (preço por milhão de
tokens), ambas consultadas em 15/09/2026.

**A frase que resume:** 10 milhões de tokens por dia é aproximadamente o equivalente a
milhões de palavras faladas **por dia**. Um assistente pessoal de voz, usado o dia inteiro
por uma pessoa, fica ordens de grandeza abaixo disso. Você estaria pagando US$ 54 por mês
para receber respostas piores e mais lentas.

**A única razão legítima para inverter essa conta** é privacidade: querer que absolutamente
nada saia de casa. Se um dia esse for o critério, a conversa muda — mas aí o problema a
resolver é "privacidade", não "custo", e a resposta honesta seria uma máquina com placa de
vídeo, não o VPS atual.

---

## A recomendação: o agente ouvinte local

Nenhuma das três ferramentas open source é a resposta para "um agente no VPS mexendo no meu
PC". A resposta é um **padrão de arquitetura**, e ele é mais simples do que parece.

### Como funciona, em linguagem de porta de casa

Existem duas formas de alguém de fora falar com o seu computador:

- **Abrir uma porta de entrada.** Seu PC fica ouvindo a internet, esperando quem chegar. É o
  caminho fácil — e é exatamente por isso que existem 30 mil instâncias de OpenClaw expostas
  sendo atacadas. Porta aberta é porta que qualquer um bate.
- **Ligar para fora.** Seu PC é quem inicia a conversa: ele conecta ao seu VPS, como um
  navegador conecta a um site, e mantém essa linha aberta. Pelos pedidos chegam por essa
  linha que **ele mesmo abriu**.

**A recomendação é a segunda: o seu PC nunca abre porta de entrada.** Quem quiser mandar um
pedido deixa recado no VPS; o PC busca o recado pela linha de saída. Do lado de fora, o seu
computador simplesmente não existe como endereço acessível — não há o que atacar.

### Quem decide continua sendo a sua máquina

Isso é o segundo pilar, e é o que separa esta proposta do OpenClaw.

Chegar um pedido **não** é o mesmo que executá-lo. O pedido entra pelo mesmo funil que já
existe hoje no DERVS:

- **O porteiro** (`dervs_porteiro.py`) decide, sem nada sair da máquina, se aquilo era mesmo
  com o DERVS.
- **A rede de segurança** (`dervs_safety.py`) dá a palavra final sobre o risco. Ela é
  deliberadamente desconfiada: o cérebro sugere um nível de risco, e a máquina pode **subir**
  esse nível, nunca baixar — porque a resposta do modelo também vem "de fora". Os três
  trilhos continuam iguais: reversível (uma confirmação), muda estado (confirma com o comando
  à vista), destrutivo (dupla confirmação, e autorização à parte se toca alvo de rede).

O VPS, nesse desenho, é só um mural de recados. Ele nunca ganha poder sobre o seu PC.

### Isso não é invenção nossa — dois precedentes

1. **Os runners self-hosted do GitHub Actions.** Milhões de empresas rodam código do GitHub
   dentro das próprias máquinas assim: o runner só precisa de **saída** HTTPS, e **nenhuma
   porta de entrada é aberta** na máquina que executa.
   Fonte: https://docs.github.com/en/actions/reference/runners/self-hosted-runners
   (15/09/2026).
2. **O `remote-workstation-mcp`,** um projeto que faz exatamente o que você descreveu:
   transporte preso a `127.0.0.1` (só a própria máquina enxerga), túnel apenas de saída,
   concessão de permissão local com prazo de validade, e **nega por padrão**.
   Fonte: https://github.com/Tunglam0605/remote-workstation-mcp (15/09/2026).

Para quando houver identidade e autorização por chamada, o padrão de referência é token com
escopo por chamada e validação automática
(https://www.scalekit.com/blog/agent-workflows-remote-mcp-servers, 15/09/2026).

---

## Por onde começar: a ordem dos cinco alvos

Você citou cinco coisas para o DERVS controlar. Elas não têm o mesmo custo nem o mesmo
risco, e esta é a ordem recomendada:

**1º — Navegador.** É o único que **já tem código e teste no repositório**
(`dervs_browser.py`, `test_dervs_browser.py`). O DERVS já sabe receber um objetivo em
português e dirigir o Chrome com os seus logins. Começar aqui é terminar algo que existe pela
metade, não começar do zero. E a cerca contra "página dando ordem" já foi construída
justamente neste caminho.

**2º — PC (abrir programas, mexer em arquivos).** Segundo porque a rede de segurança
(`dervs_safety.py`) e os três trilhos de risco já foram feitos exatamente para isto — a
parte difícil, que é decidir o que é perigoso, está pronta e testada.

**3º — GitHub.** Terceiro porque tem fronteira nítida e um caminho oficial de acesso com
permissões limitadas por escopo. O estrago possível é sério mas reversível: quase tudo no
Git dá para voltar atrás.

**4º — VS Code.** Quarto porque é conveniência, não capacidade nova: quase tudo que se pede
ao editor também se consegue pelos alvos 2 e 3, com menos peça móvel.

**5º — Servidor (VPS).** **Por último, e de propósito.** É o único alvo onde um erro é
visível para outras pessoas e não tem "desfazer": lá moram projetos que estão no ar. Se o
servidor entrar, entra com o mesmo rigor da publicação — ação explícita, nunca automática.

---

## Limites honestos

O que este documento **não** entrega, dito antes que você descubra sozinho:

- **Nenhuma latência foi medida aqui.** Os 200–600 ms são de fonte pública datada
  (15/09/2026), medidos por outra pessoa, em outra máquina, com outra internet. Servem para
  comparar caminhos, não para prometer desempenho na sua casa.
- **Nenhuma das cinco opções foi instalada ou testada.** Isso foi decidido de propósito: uma
  prova de conceito exigiria hospedar IA no VPS ou implementar o controle, e as duas coisas
  estão fora do escopo que você aprovou.
- **Os números de custo mudam.** Preço de API e de VPS muda por conta de quem vende. Antes
  de assinar qualquer coisa, os valores devem ser reconferidos na fonte.
- **A popularidade do Hermes Agent e do OpenClaw é recente.** Estrela no GitHub mede
  entusiasmo, não estabilidade nem segurança. Nenhum dos dois tem histórico longo o bastante
  para se saber como envelhece.
- **"Nenhuma fonte auditou" não é atestado de saúde.** O Hermes Agent não tem auditoria
  pública de prompt injection encontrada. Isso significa que ninguém procurou com afinco,
  não que não haja o que achar.
- **A recomendação do agente ouvinte local ainda não tem uma linha de código escrita.** Ela é
  um desenho com dois precedentes sólidos. O tamanho real do trabalho só aparece quando
  virar etapa de implementação — e esta rodada não vai até lá.
- **Segurança não termina em arquitetura.** Porta fechada e a rede de segurança decidindo
  localmente reduzem muito o risco; não o zeram. Todo alvo novo de controle precisa da sua
  própria cerca e do seu próprio teste, do mesmo jeito que o navegador precisou.
