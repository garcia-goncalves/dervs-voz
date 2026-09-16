# Lente do Pesquisador — Hermes Agent, LiveKit, Open Claw e arquitetura de IA

Consultas feitas em 15/09/2026, via busca web. Cada afirmação carrega URL e data de
consulta — a data de consulta é sempre 15/09/2026 salvo indicação contrária.

---

## 1. Hermes Agent

**Existem pelo menos dois usos do nome "Hermes" no espaço de IA.** O relevante para o
Dervs é o projeto lançado pela Nous Research em 25/02/2026, não modelos de linguagem
antigos chamados "Hermes" (fine-tunes da própria Nous Research sobre Llama/Mistral, que
são outra coisa — pesos de modelo, não um agente).

- **O que é:** "The AI agent that grows with you" — um agente autônomo que roda no
  computador ou servidor do próprio usuário, com memória de três camadas, cria "skills"
  reutilizáveis a partir da experiência (loop de aprendizado fechado), e se conecta a
  Telegram, Discord, Slack, WhatsApp, Signal e CLI.
  Fonte: https://hermes-agent.org/ (consultado 15/09/2026).
- **Mantenedor:** Nous Research. Fonte:
  https://dev.to/tokenmixai/hermes-agent-review-956k-stars-self-improving-ai-agent-april-2026-11le
  (consultado 15/09/2026).
- **Licença:** MIT — código aberto sem versão paga.
  Fonte: https://hermes-agent.org/ (consultado 15/09/2026).
- **Roda local ou precisa de nuvem:** Roda localmente em Linux, macOS e WSL2 (Windows
  precisa do WSL2, não é nativo), instalação por um único comando, dados armazenados em
  `~/.hermes/` — não depende de nuvem para funcionar, embora ele mesmo chame LLMs (locais
  ou via API, a decisão é do usuário) para "pensar".
  Fonte: https://hermes-agent.org/ (consultado 15/09/2026).
- **Funcionalidades relevantes ao briefing:** controle de navegador (automação, busca,
  extração de página, captura de tela), controle de máquina/servidor (comandos locais,
  Docker, SSH remoto), transcrição de áudio e texto-em-fala, automação agendada (cron).
  Fonte: https://hermes-agent.org/ (consultado 15/09/2026).
- **Maturidade e tração:** lançado 25/02/2026; em sete semanas atingiu ~95,6 mil
  estrelas no GitHub; a versão v0.10.0 (16/04/2026) trazia 118 skills; em seis meses
  passou de 214 mil estrelas, virando o framework de agente open source de crescimento
  mais rápido de 2026.
  Fontes: https://dev.to/tokenmixai/hermes-agent-review-956k-stars-self-improving-ai-agent-april-2026-11le
  e https://startupfortune.com/hermes-agent-crosses-214000-github-stars-as-developers-abandon-commercial-ai-agent-frameworks/
  (ambas consultadas 15/09/2026).
- **Resolveria algo do briefing?** Resolve parte do controle (navegador, comandos,
  SSH, agendamento) e tem voz embutida, mas **não** endereça a onda visual reagindo ao
  áudio (isso é problema de interface, não de agente de backend) e **não** é desenhado
  para o cenário "agente no VPS mexendo num PC diferente" — ele assume que roda na
  própria máquina que ele controla. Ele é candidato a "cérebro" mais capaz que o
  gpt-4.1-mini de hoje, mas trocar o cérebro é decisão maior que abrir mão da API paga
  já validada, e adicionaria uma dependência nova de projeto com 7 meses de idade.
  **Risco:** por ser recente e por dar a si mesmo acesso a shell, SSH e navegador,
  herda a mesma classe de risco de prompt injection descrita para o Open Claw (seção
  3) — nenhuma fonte encontrada nesta pesquisa audita especificamente o Hermes Agent
  quanto a isso, o que por si é um sinal de cautela (menos escrutínio público que o
  Open Claw).

---

## 2. LiveKit

- **O que é:** infraestrutura de tempo real para áudio, vídeo e agentes de IA. Inclui
  o servidor de mídia (`livekit/livekit`, WebRTC) e o framework **LiveKit Agents**
  (Python/Node) para construir agentes de voz — ele entra numa "room" do LiveKit como
  participante, cuida do pipeline de áudio e de detecção de turno de fala ("quem está
  falando agora"), e se conecta a provedores de STT/LLM/TTS por plugins.
  Fontes: https://docs.livekit.io/agents/ e
  https://github.com/livekit/agents (ambas consultadas 15/09/2026).
- **Licença:** Apache 2.0 para o ecossistema inteiro — servidor de mídia e framework
  de agentes. Sem custo de licenciamento para self-host.
  Fonte: https://voice.oss.codes/open-source/livekit-agents/ (consultado 15/09/2026).
- **Detecção de volume/amplitude em tempo real (relevante para a onda visual):** o
  SDK cliente JS expõe `createAudioAnalyser`, que cria um nó `AnalyserNode` da Web
  Audio API anexado à faixa de áudio e devolve um método de conveniência
  `calculateVolume` para leitura instantânea de volume. O pacote
  `@livekit/components-react` já embrulha isso em hooks prontos que dividem o
  espectro de frequência em "bandas" para visualização.
  Fontes: https://docs.livekit.io/client-sdk-js/functions/createAudioAnalyser.html e
  https://deepwiki.com/livekit/components-js/5.4-audio-visualization
  (ambas consultadas 15/09/2026). Ou seja: por baixo do capô é a mesma Web Audio API
  padrão do navegador (ver seção 6) — o LiveKit só empacota o acesso a ela quando o
  áudio já está trafegando pela room dele.
- **Self-host no VPS do dono:** sim, tecnicamente possível — é o mesmo binário que
  roda na nuvem deles. Mas a própria documentação avisa para orçar **3 a 4 semanas de
  trabalho de infraestrutura** só para chegar perto da paridade operacional do LiveKit
  Cloud (TURN/STUN, escala, observabilidade) rodando em Kubernetes próprio.
  Fonte: https://www.cekura.ai/blogs/livekit-agents (consultado 15/09/2026). Isso é
  desproporcional para um VPS que já hospeda outros dois projetos do dono e não deve
  competir por recursos com eles.
- **Custo aproximado:** LiveKit Cloud tem 4 planos — Build (grátis: 5.000 minutos
  WebRTC, 50 GB de saída, 1.000 minutos de agente de IA e US$ 2,50 em créditos de
  inferência por mês), Ship (US$ 50/mês), Scale (US$ 500/mês) e Enterprise (sob
  consulta). Acima da cota grátis, cobra por minuto de sessão de agente
  (~US$ 0,01/min), minuto de mídia WebRTC (~US$ 0,0004–0,0005/min) e tráfego de dados
  (US$ 0,10–0,12/GB). O self-host é grátis de licença, mas exige a própria infra (CPU,
  rede, TURN) do dono.
  Fonte: https://trtc.io/blog/details/livekit-pricing-2026 (consultado 15/09/2026).
- **Já resolve parte do que o Dervs faz manualmente?** Sim — streaming de voz em
  tempo real e "turn-taking" (detectar quando a pessoa parou de falar e o agente pode
  responder) são exatamente o problema central que o LiveKit Agents resolve pronto,
  hoje implementado de forma manual e local no Dervs. Adotar LiveKit trocaria a
  arquitetura de "processo local que grava, transcreve e fala" por "cliente que entra
  numa room e troca mídia com um agente", o que é uma mudança grande de arquitetura —
  não cabe nesta rodada (o briefing já marca fora de escopo qualquer implementação de
  controle remoto; adotar LiveKit é decisão do mesmo porte).

---

## 3. Open Claw

O dono provavelmente ouviu falar de **OpenClaw** (com ou sem espaço/maiúscula — grafias
"Open Claw", "OpenClaw" e "Openclaw" aparecem intercambiáveis nas fontes). Não foi
encontrado nenhum projeto real e relevante com o nome exato "Open Claw" separado de
OpenClaw — as buscas por variações ("OpenHands", forks de Claude Code, "open-interpreter")
não trouxeram nada mais próximo do nome ouvido pelo dono do que OpenClaw.

- **O que é:** assistente de IA pessoal open source que roda localmente e tem acesso
  amplo ao sistema: lê e escreve arquivos, roda comandos de shell, envia e-mails,
  navega na web, gerencia calendário, conecta com WhatsApp/Telegram/Discord/Slack/
  iMessage (29 canais ao todo) e é extensível por mais de 100 "AgentSkills"
  pré-configuradas.
  Fonte: https://openclaw.ai/ (consultado 15/09/2026).
- **Histórico do nome:** criado por Peter Steinberger (fundador da PSPDFKit) como
  projeto de fim de semana; nasceu como **Clawdbot** (referência a "Claude"), foi
  renomeado para **Moltbot** depois de reclamação de marca da Anthropic, e por fim
  virou **OpenClaw** — hoje mantido por uma fundação independente sem fins lucrativos
  (OpenClaw Foundation, 501(c)(3)) depois que Steinberger anunciou, em fevereiro de
  2026, que ia liderar a divisão de agentes pessoais da OpenAI.
  Fonte: https://www.digitalocean.com/resources/articles/what-is-openclaw e
  https://milvus.io/blog/openclaw-formerly-clawdbot-moltbot-explained-a-complete-guide-to-the-autonomous-ai-agent.md
  (ambas consultadas 15/09/2026).
- **Licença:** MIT, sem versão enterprise nem paga.
  Fonte: https://openclaw.ai/ (consultado 15/09/2026).
- **Roda local ou nuvem:** totalmente local — macOS, Windows ou Linux, sem
  dependência de nuvem para operar; o dono escolhe o modelo (Claude, GPT etc.) por
  trás.
  Fonte: https://openclaw.ai/ (consultado 15/09/2026).
- **Risco de segurança — e este é o ponto mais importante da seção:** OpenClaw
  anuncia explicitamente "acesso total ao sistema" (ler/escrever arquivo, rodar
  shell, executar script), e **não tem forma de distinguir um comando legítimo de um
  prompt malicioso embutido em conteúdo que ele processa** (ex.: uma página web, um
  e-mail, uma mensagem recebida) — é o cenário clássico de prompt injection indireta,
  agravado porque o produto normalmente processa muito conteúdo de fontes não
  confiáveis. A empresa de segurança Bitsight encontrou mais de 30 mil instâncias
  expostas na internet, e observou que as primeiras tentativas de invasão contra uma
  instância-isca (honeypot) chegaram minutos depois dela ficar no ar. O órgão chinês
  CNCERT emitiu alerta oficial sobre os riscos do produto, citando configuração de
  segurança fraca por padrão somada ao acesso privilegiado ao sistema. Se comprometido,
  pode instalar malware, alterar configuração do sistema, desligar proteções de
  segurança ou acessar arquivo sensível.
  Fontes: https://www.bitsight.com/blog/openclaw-ai-security-risks-exposed-instances,
  https://thehackernews.com/2026/03/openclaw-ai-agent-flaws-could-enable.html e
  https://www.giskard.ai/knowledge/openclaw-security-vulnerabilities-include-data-leakage-and-prompt-injection-risks
  (todas consultadas 15/09/2026).
- **Resolveria algo do briefing?** Como o Hermes Agent, resolve parte do "controlar
  navegador/PC/arquivos", mas não a onda visual. E o próprio risco documentado
  (acesso total sem filtro contra instrução maliciosa embutida) é exatamente o tipo
  de risco que o briefing pede para tratar com cautela ("caminho seguro... sem
  liberar controle irrestrito") — adotar o OpenClaw como está, sem um mediador que
  valide comandos, contraria diretamente esse critério.

---

## 4. OpenAI API (créditos já pagos) vs IA open source hospedada no VPS

- **Custo de API hoje:** GPT-4.1 (linha usada hoje pelo Dervs, `gpt-4.1-mini`) fica na
  faixa de US$ 2,00 por milhão de tokens de entrada e US$ 8,00 por milhão de saída
  para o modelo cheio — o "mini" já em uso é sensivelmente mais barato que isso, e o
  dono já tem crédito pago, ou seja, custo marginal zero até esgotar o saldo.
  Fonte: https://www.spheron.network/blog/gpt-6-vs-self-hosted-llm-2026/ (consultado
  15/09/2026, dado referente a GPT-4.1).
- **Custo de hospedar modelo aberto:** um VPS dedicado a isso (ex.: 4 vCPU / 8 GB,
  categoria "Business") rodando Ollama com um modelo pequeno tipo Llama 3.1 8B em CPU
  fica em torno de US$ 54/mês só de servidor — sem contar o tempo de engenharia para
  manter no ar. Modelos "competentes" (na casa de 70B de parâmetros) exigem GPU; em
  CPU pura, mesmo modelos de 8B rodam perceptivelmente mais devagar que uma API.
  Fonte: https://cloudzy.com/blog/self-hosting-open-weight-llm-gpu-vps-cost/
  (consultado 15/09/2026).
- **Ponto de equilíbrio:** para a maioria dos casos abaixo de 50 milhões de tokens por
  dia, a API sai mais barata considerando custo total (servidor + manutenção +
  engenharia); o self-host só começa a compensar financeiramente entre 10 e 30
  milhões de tokens/dia, dependendo do modelo — um volume muito acima do que um
  assistente pessoal de voz gera.
  Fonte: https://cloudzy.com/blog/self-hosting-open-weight-llm-gpu-vps-cost/
  (consultado 15/09/2026).
- **Latência:** para modelos de fronteira via API, o tempo até o primeiro token
  (TTFT) fica em 200–600 ms em carga normal, podendo piorar bastante em pico. Um
  modelo rodando na própria região do usuário pode entregar o primeiro token em menos
  de 100 ms — mas isso pressupõe hardware adequado (GPU), o que não é o caso do VPS
  descrito pelo dono (que já hospeda dois outros projetos e não deve competir por
  recursos).
  Fonte: https://cloudzy.com/blog/self-hosting-open-weight-llm-gpu-vps-cost/
  (consultado 15/09/2026).
- **O que é fácil vs difícil hoje, no caso concreto do Dervs:** usar a API da OpenAI
  é o caminho fácil — já está integrado, o dono já pagou crédito, e a qualidade do
  gpt-4.1-mini já é conhecida e testada no projeto. Hospedar um LLM open source
  competente **sem GPU dedicada**, no mesmo VPS que já serve outros dois projetos, é o
  caminho difícil: exige memória e CPU que competem com os outros serviços, entrega
  modelo mais fraco que o gpt-4.1-mini para o mesmo custo mensal, e ainda soma
  trabalho de manutenção (atualização de modelo, monitoramento, isolamento de
  recursos). **Recomendação de pesquisa (não é decisão, é insumo para o Diretor/
  Sintetizador):** não há caso econômico nem técnico, hoje, para tirar o cérebro da
  API da OpenAI e colocar no VPS descrito.

---

## 5. Controle remoto de PC local a partir de um agente no VPS

O padrão que projetos open source sérios usam para isto é o oposto do que soa
intuitivo: **o servidor não teria acesso de entrada (inbound) à máquina do dono; é a
máquina do dono que se conecta para fora (outbound) e só executa o que ela mesma valida.**

- **Exemplo consolidado, fora do universo de IA, mas do mesmo formato de problema:**
  os "self-hosted runners" do GitHub Actions só precisam de acesso de saída em HTTPS
  (porta 443); é o runner (rodando na máquina do dono) que abre a conexão para o
  GitHub e fica perguntando ("long poll") se há trabalho para fazer — nenhuma porta de
  entrada precisa ser aberta na máquina que executa o comando.
  Fonte: https://docs.github.com/en/actions/reference/runners/self-hosted-runners
  (consultado 15/09/2026).
- **Exemplo específico de agente de IA controlando estação de trabalho remota
  (MCP):** o projeto `remote-workstation-mcp` implementa exatamente o padrão "agente
  ouvinte local": o transporte HTTP fica vinculado só a `127.0.0.1` (não escuta a
  internet), e há um "MCP Tunnel seguro" que é **só de saída**, sem abrir porta pública
  na máquina de trabalho. Funcionalidades de controle total exigem uma "concessão
  local" (lease) explícita e com prazo, mais permissões específicas ligadas
  manualmente para qualquer recurso perigoso — e ferramentas HTTP autenticadas exigem
  escopo registrado, falhando fechado (nega por padrão) para qualquer ferramenta não
  classificada.
  Fonte: https://github.com/Tunglam0605/remote-workstation-mcp (consultado
  15/09/2026).
- **Padrão de autorização por token com escopo, não acesso irrestrito:** em MCP
  remoto, o padrão recomendado é o servidor local validar tokens OAuth 2.1 emitidos
  por um serviço de autorização, checando chaves (JWKS) e aplicando escopos por
  chamada — ou seja, cada comando carrega prova de quem pediu e o que está autorizado
  a fazer, e o "ouvinte" recusa qualquer coisa fora do escopo daquele token.
  Fonte: https://www.scalekit.com/blog/agent-workflows-remote-mcp-servers (consultado
  15/09/2026).
- **Leitura para o Dervs:** o caminho seguro sugerido pela pesquisa é: um "agente
  ouvinte" instalado no PC do dono (não no VPS) que se conecta ao VPS por conexão de
  saída, recebe pedidos de ação, e **decide localmente** se executa — usando os
  mesmos trilhos de confirmação por voz/clique que o Dervs já tem hoje para comando
  de risco — em vez do VPS ter acesso direto (SSH, RDP, VNC) à máquina pessoal. O
  MCP (Model Context Protocol) aparece em múltiplas fontes como o padrão emergente
  para expor "ferramentas" de um lado da ponte ao agente do outro lado, com
  autenticação e escopo por chamada.

---

## 6. Onda de voz reagindo ao áudio em Electron/web

- **Abordagem padrão:** a própria **Web Audio API** do navegador (disponível em
  Electron, que roda Chromium) — criar um `AnalyserNode`, conectá-lo à fonte de áudio
  (microfone via `getUserMedia`, ou o áudio de saída do TTS), e ler os dados em tempo
  real com `getByteTimeDomainData` (forma de onda) ou `getByteFrequencyData` (espectro
  de frequência), desenhando o resultado a cada quadro com `requestAnimationFrame`
  num `<canvas>` (2D) ou WebGL para efeitos mais elaborados.
  Fonte: https://developer.mozilla.org/en-US/docs/Web/API/AnalyserNode (consultado
  15/09/2026).
- **Tutoriais de referência com código completo** confirmam o mesmo padrão:
  criar o `AnalyserNode` com FFT de 2048, ler o buffer de domínio do tempo ou
  frequência, normalizar valores de decibel para uma faixa 0–1, e desenhar via
  `requestAnimationFrame`.
  Fontes: https://css-tricks.com/making-an-audio-waveform-visualizer-with-vanilla-javascript/
  e https://developer.mozilla.org/en-US/docs/Web/API/AnalyserNode (ambas consultadas
  15/09/2026).
- **Relação com o LiveKit (seção 2):** se o Dervs eventualmente adotar LiveKit para o
  áudio, o pacote `@livekit/components-react` já embrulha esse mesmo `AnalyserNode`
  em hooks prontos (`createAudioAnalyser` + `calculateVolume`) — mas isso não é
  necessário para a onda visual: a Web Audio API sozinha, sem LiveKit, já é o padrão
  usado pela indústria e resolve o critério de aceitação do briefing (onda reagindo ao
  volume real do áudio, testável injetando um trecho de amplitude conhecida).
  Fonte: https://docs.livekit.io/client-sdk-js/functions/createAudioAnalyser.html
  (consultado 15/09/2026).

---

## Resumo para quem for sintetizar

| Ferramenta | Resolve a onda visual? | Resolve controle remoto com segurança? | Vale trocar o que já funciona hoje? |
|---|---|---|---|
| Hermes Agent | Não | Parcial — assume que roda na própria máquina que controla | Só se decidirem trocar o cérebro; não é necessário para a onda nem para o controle remoto seguro |
| LiveKit | Sim, mas indiretamente (empacota a Web Audio API padrão) | Não é sobre isso | Só se decidirem migrar toda a arquitetura de áudio para streaming em "rooms" — mudança grande, fora do escopo desta rodada |
| Open Claw (OpenClaw) | Não | Não — documentadamente vulnerável a prompt injection quando exposto, e é isso que aconteceria ao dar acesso de fora | Não recomendado como está para o cenário de controle remoto |
| Web Audio API (`AnalyserNode`) nativa | **Sim — é o caminho direto e padrão da indústria** | N/A | N/A |
| Agente ouvinte local + MCP com escopo/token | N/A | **Sim — é o padrão real usado por projetos sérios** | É a peça que falta para o controle remoto seguro do briefing |
| API OpenAI (créditos já pagos) | N/A | N/A | Continua sendo a opção mais barata e madura para o cérebro, dado o volume de uso de um assistente pessoal |
