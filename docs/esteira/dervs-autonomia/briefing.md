# Briefing — DERVS com autonomia configurável (02/10/2026)

Aprovado em: 2026-10-06

## pedido_original
"Preciso que o DERVS VOZ funcione incrivelmente. Se estiver tudo conectado e conversando/integrado (Claude/hermes/JEV/etc...) e caso ache que não precise ter informações deles (cérebro), e consiga deixar tudo automático e automatizado, podemos tirar as informações de 'claude, hermes, jev, etc'... não sei o que faz sentido. Quero suas melhores ideias. Preciso que o DERVS seja inteligente e revolucionário... e faça tudo (consiga fazer tudo)... autonomia total. Mas eu preciso configurar o que eu vou liberar ele fazer ou não. Ele precisa analisar e corrigir qualquer tipo de problema... e desenvolver qualquer tipo de coisas tbm."

## entendimento
Um DERVS com **uma porta só**: o dono fala o que quer e o DERVS escolhe sozinho quem resolve (JEV na triagem, Claude Code para código e máquina, OpenAI/Hermes na VPS quando fizer sentido); os nomes dos cérebros saem da tela principal e ficam num painel "Avançado". O dono liga e desliga, categoria por categoria, o que o DERVS pode fazer sozinho, com três níveis (só analisa · pergunta antes · faz sozinho). O DERVS vigia a si mesmo (erros, queda, atualização) e consegue consertar e desenvolver, sempre dentro desses limites e com tudo reversível.

## usuario_alvo
O dono (decide produto, não opera terminal, fala português, usa por voz e painel) e, depois, sócios e funcionários com o DERVS instalado (Onda F). Não é desenvolvedor.

## criterio_de_aceitacao

- [ ] Painel "O que o DERVS pode fazer" lista as categorias (ler arquivos, abrir programas, instalar, alterar arquivos do projeto, apagar, usar a internet, mexer em servidor, gastar dinheiro com API) e cada uma tem os três níveis; a escolha persiste após reiniciar (…ver detalhe)
- [ ] Padrão de fábrica: tudo em "pergunta antes", exceto leitura em "faz sozinho". Provado por teste sobre a configuração padrão.
- [ ] Os limites duros NÃO aparecem como opção e não podem ser religados pelo painel: nunca `bypassPermissions`, nada em produção/servidor sem "sim" na hora, segredo nunca em chat/commit, apagar só por quarentena reversível. Teste que tenta configurar o contrário e falha.
- [ ] Toda ação respeita o nível: teste com nível "só analisa" em que a ação de escrita é recusada com mensagem em português, e com "pergunta antes" em que aparece o cartão de confirmação existente.
- [ ] Roteador único: um pedido de voz de código, um de máquina e uma conversa vão para o executor certo sem o dono escolher; o motivo da escolha aparece em "Avançado" (log). Teste com executores falsos.
- [ ] Piloto automático: ao achar `ultimo_erro.txt` ou queda, o DERVS diagnostica e mostra causa e correção em português; só aplica sozinho se a categoria "alterar arquivos do projeto" estiver em "faz sozinho", sempre em branch com testes verdes e nunca na `main` (…ver detalhe)
- [ ] Modo desenvolvedor: pedido de "crie/conserte X" abre uma sessão do Claude Code (assinatura do dono, no PC dele) em worktree isolada, roda os testes e devolve o resultado resumido; nada vai para a `main` sem o "sim" dele.
- [ ] Teto de gasto configurável para qualquer API paga (OpenAI); ao estourar, o DERVS para e avisa. Teste com contador falso.
- [ ] Suíte completa continua verde e `README`/`COMO-USAR` atualizados no mesmo commit.

## fora_de_escopo
- Qualquer coisa na VPS/produção (depende da `dervs-2a` e de deploy do dono).
- Cliente do porteiro `/agente/voz/triagem` (a rota ainda dá 404).
- Instalar Hermes e Bolt.diy na VPS (precisa de chave de API com teto, decisão dele).
- Instalador para outros PCs (Onda F do `dervs-central-do-pc`).
- Usar a assinatura Claude Max dentro de Bolt.diy/Hermes ou dividi-la com outra pessoa (proibido pelas regras da Anthropic).
- Geração de foto/vídeo realista.

## riscos
Alto, mas contido: o DERVS age na máquina inteira por voz (prompt injection, ação destrutiva). Mitigação: os limites duros acima, quarentena reversível, revisor de segurança antes de mesclar, e o painel de permissões só **reduz** poder em relação ao teto fixo do `dervs_safety`. Dado de paciente: o DERVS não pode abrir programas listados em `caminhos_protegidos.json`. Sem migration, sem deploy, sem produção.

## plano_de_voo
Modo **enxuto**. Fases: 1 briefing (este) → 2 descoberta (um despacho `sonnet` com as quatro lentes, focado em reaproveitar `dervs_safety`, `dervs_aprovacao`, `dervs_cerebros`, `dervs_porteiro`, `dervs_central`) → 3 design só do painel de permissões (um despacho `sonnet`) → 4 plano (`neguin-planner`, `opus`) → 5 execução em ondas (2 a 3 executores `sonnet` em worktree) → 6 revisão (`security-reviewer` e `python-reviewer`, mais `design-reviewer` no painel) → 7 cronista. **Despachos previstos: cerca de 12.**

## detalhe_dos_criterios

Texto completo dos critérios encurtados acima (a lista tem teto de 300 caracteres por linha):

1. Painel "O que o DERVS pode fazer" lista as categorias (ler arquivos, abrir programas, instalar, alterar arquivos do projeto, apagar, usar a internet, mexer em servidor, gastar dinheiro com API) e cada uma tem os três níveis; a escolha persiste após reiniciar (teste automático que grava (…ver detalhe)
