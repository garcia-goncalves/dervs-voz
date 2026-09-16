## pedido_original
"continue de onde vc parou... quero que refatore a CARA do Dervs... vi sobre o HERMES AGENTE
e sobre o LIVEKIT... gostaria de saber se podemos usar eles. Eles são opensource... estou até
pensando em ter eles no meu computador e no meu servidor para me ajudar... quais são suas
ideias? Eu deveria hospedar no meu servidor VPS e consigo fazer o agente mexer no meu pc mesmo
ele estando hospedado no servidor vps? Gostaria ou de usar a api da openai CHATGPT que tenho
créditos ou podemos verificar a possibilidade de instalar uma IA no meu VPS (ia opensource)...
o que vc acha? analise tudo e me diga... quero que o Dervs seja revolucionário... quero que
quando falamos, balance as ondas da voz, sabe? Bem futurista... não sei se estou sabendo me
expressar... mas quero algo surreal e bonito... muito louco! Quero suas ideias da melhor coisa
a se fazer... também vi sobre o Open claw... se pudermos fazer uma fusão de várias aplicações
opensource, seria perfeito. Vc poderia inclusive sugerir quais ferramentas e programas
opensource podemos usar para deixar o DERVS super foda! Quero que ele controle tudo. Meu
navegador, meu PC, meu servidor, meu github, meu vscode, tudo... quero que ele acesse
plataformas e ferramentas e manusei tudo. Quero que ele faça tudo o que eu pedir pra ele..."

## entendimento
Duas entregas nesta rodada. Primeira: migrar a interface do Dervs (hoje janela + selo
flutuante em PyQt6) para uma janela Electron/web nova, futurista, com uma onda visual que
reage ao volume real do áudio — tanto quando o dono fala quanto quando o Dervs responde —
mantendo tudo que já funciona hoje (atalho, porteiro, transcrição, cérebro, execução de
comando com trilhos de segurança). Segunda: um documento de arquitetura comparando Hermes
Agent, LiveKit e Open Claw (as três ferramentas open source que o dono viu) contra usar a API
da OpenAI (ele já tem créditos) ou hospedar uma IA open source no VPS dele, incluindo um
caminho seguro para o Dervs eventualmente controlar navegador, PC, servidor, GitHub e VS Code.
Esta rodada não implementa esse controle — só entrega a recomendação por escrito.

## usuario_alvo
O próprio dono: decide o produto, não opera terminal, interage com o Dervs por voz e no dia a
dia. Quer uma experiência visual "surreal, bonita, futurista" — o julgamento estético final é
dele, por isso a fase de design (painel de direções visuais) é obrigatória aqui.

## criterio_de_aceitacao
- A janela nova abre pelos mesmos atalhos de hoje (Área de Trabalho e menu Iniciar) e
  substitui a janela/selo PyQt6 atual — não sobra duas interfaces concorrentes.
- Só um Dervs roda por vez: abrir de novo traz a janela existente para frente, em vez de abrir
  outra (mesmo comportamento que já existe hoje, recriado no Electron).
- A onda visual muda de forma visivelmente ligada ao volume real do áudio — provável com um
  teste automatizado que injeta um trecho de áudio de amplitude conhecida e confere que o
  valor lido pela interface mudou de acordo, mais uma checagem visual do dono.
- As funcionalidades de hoje continuam funcionando sem regressão: porteiro, transcrição,
  cérebro, execução de comando com os trilhos de risco, atalho de transcrever arquivo,
  registro de queda. Os testes atuais (543 verdes) continuam verdes, mais os testes novos da
  interface.
- Nenhuma credencial (chave da OpenAI, senha do VPS, token do GitHub) aparece na interface
  nova, em log ou em qualquer arquivo do repositório.
- Existe `docs/esteira/dervs-cara-nova/arquitetura-agente.md` comparando Hermes Agent, LiveKit,
  Open Claw e OpenAI API vs IA open source no VPS — com custo, latência, e uma recomendação
  clara de caminho seguro para controle futuro de navegador/PC/servidor/GitHub/VS Code, sem
  liberar controle irrestrito.
- O dono consegue ver a onda reagindo à própria voz numa demonstração ao vivo antes de a
  entrega ser dada como pronta.

## fora_de_escopo
Implementar de fato o controle de navegador, PC, servidor, GitHub ou VS Code por um agente
remoto (fica para depois da leitura do documento de arquitetura). Hospedar qualquer IA no VPS
nesta rodada. Trocar a voz Kokoro pela da nuvem (decisão de dinheiro já registrada em memória,
ainda sem resposta do dono). Resolver o microfone físico desconectado. Instalar CI. Montar o
instalador do navegador autônomo (Playwright) no Windows.

## riscos
Dar a um agente hospedado fora da máquina do dono (VPS exposto na internet) capacidade de
mexer no PC pessoal, no navegador logado e nos outros projetos do servidor é uma decisão de
segurança de alto impacto — tratada aqui só como documento de recomendação, não como código
que já libera esse controle. Migrar a interface inteira para Electron reimplementa
comportamentos que já existem e foram corrigidos a duras penas no PyQt6 (instância única,
bandeja com "Sair", selo que não sai da tela, terminal escondido, aviso de silêncio) — risco
real de regressão se a fase de execução não recriar cada um deles.

## plano_de_voo
Fases 1 a 7, com a fase 3 (design) ligada — há interface nova e a estética importa de verdade
para o dono. Modo **completo** na descoberta (fase 2): o escopo mistura reescrita de interface
com uma decisão de arquitetura real, então as quatro lentes (Analista, Arquiteto, Pesquisador,
Diretor) rodam em despachos paralelos, não fundidas — o Arquiteto precisa mapear a fundo o que
existe hoje em PyQt6 antes de desenhar a ponte para o Electron, e o Pesquisador precisa
investigar Hermes Agent, LiveKit e Open Claw de verdade (com fonte e data), o que não cabe num
despacho só.

Modelos: Interrogador `opus` (esta fase). Descoberta: Analista, Arquiteto e Pesquisador em
`sonnet`; Diretor em `opus` (corte de escopo real: reescrita completa é grande). Sintetizador
em `opus` (decide as contradições entre "já existe e funciona" vs "trocar tudo"). Design:
Diretor de arte, Redator, Estrategista e Diretor de mídia em `sonnet`, com o painel final
revisado em `opus`. Plano (fase 4): `neguin-planner` em `opus` dado o tamanho da reescrita.
Execução (fase 5): `neguin-executor` em `sonnet`, em worktrees paralelas por etapa
independente. Revisão (fase 6): revisores por arquivo tocado (typescript-reviewer ou
react-reviewer para o Electron, python-reviewer para a ponte com o backend, security-reviewer
pelo risco de controle remoto, design-reviewer pela tela nova) mais o Verificador técnico e o
Verificador de tela. Cronista (fase 7): `sonnet`.

Despachos previstos: ~19 (4 lentes + 1 síntese na fase 2; ~2 na fase 3; 1 no plano; de 4 a 6
executores na fase 5; até 5 revisores na fase 6; 1 cronista). É uma reescrita de interface
inteira mais um documento de pesquisa — por isso o número é da ordem de "criar um site", não
de um ajuste pontual.
