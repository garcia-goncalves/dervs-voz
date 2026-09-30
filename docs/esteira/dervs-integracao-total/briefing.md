# BRIEFING — dervs-integracao-total (Fatia B, lado do DERVS-VOZ)

## pedido_original

"Continue de onde você parou e faça tudo. Preciso da aplicação 100% funcionando e sem erros. Preciso que o DERVS-VOZ (você) esteja conectado e integrado a aplicação web DERVS. O Dervs já está aberto em outro terminal/VSCODE. Vocês podem interagir... e quero que vcs mesmo façam tudo o que for necessário para funcionar. Preciso que a aplicação DERVS e o Dervs voz analisem todos os projetos e monitore eles 24h por dia. Faça manutenção e ajustes em tudo. Desenvolva e programe/crie. Preciso que o DERVS-VOZ / DERVS possa utilizar tanto o Claude Code como modelo de IA, mas tbm quero que tenha opção de usar o HERMES AGENT e o JEV. Quero que tenhamos nosso proprio terminal SSH para comandos e desenvolvimento. Precisa ser tudo bem inteligente e integrado." Depois: "segue com a onda 1 (sempre esteja conversando com o DERVS) e vice versa. Estejam no mesmo contexto e trabalhe em equipe."

## entendimento

O DERVS-VOZ passa a conversar com o DERVS web por uma ponte só de saída, usando o mesmo token de computador pareado que o DERVS já emite: manda o estado e a vigília, busca recados do painel e devolve o resultado. A onda 1 entrega essa ponte, testada de ponta a ponta contra o servidor do DERVS. As ondas seguintes (cérebros Claude Code/Hermes/JEV, vigia 24h, terminal SSH, estúdio de criação) usam essa ponte. O contrato combinado com a sessão do DERVS web está em `contrato-ponte.md`.

## usuario_alvo

O dono, leigo em terminal, que fala com o DERVS-VOZ e olha o painel web de manhã. O trabalho toca código que desenvolvedores mantêm depois, então a lente DX vale.

## criterio_de_aceitacao

1. Existe `dervs_ponte_web.py`, que só faz conexão de saída (não abre porta), lê o token de `~/.dervs/agente.json` (ou de `DERVS_AGENTE_ARQUIVO`), nunca o escreve em log nem o mostra. Provado por teste que examina log e representação do objeto, e por teste de que o módulo não importa `socket.bind`/servidor.
2. A ponte manda `POST /agente/voz/estado` com o formato de `contrato-ponte.md` e busca `GET /agente/voz/recados`; devolve `POST /agente/voz/resultado`. Provado por teste contra servidor HTTP de mentira em thread.
3. Recado de nível `leitura` é executado sozinho; nível `muda_estado` vira proposta no painel do DERVS-VOZ e só anda com clique local; o que o porteiro e os caminhos protegidos recusam volta com `estado=recusado`. Id repetido é ignorado. Provado por testes.
4. Sem token, sem rede ou com o painel web fora do ar, a ponte diz o motivo em português e o DERVS-VOZ segue funcionando (nunca derruba a voz). Provado por teste.
5. Prova ponta a ponta: o servidor real do DERVS (`servir.py`, local) e o DERVS-VOZ trocam estado, recado e resultado. Feito em conjunto com a sessão do DERVS web quando a rota dela existir.
6. A suíte inteira continua verde (`python -m pytest -q` no `dervs-venv`), sem abrir microfone real.

## fora_de_escopo

Seletor de cérebro, JEV, Hermes, vigia 24h, terminal SSH e estúdio de criação (ondas 2 a 5, cada uma com critério próprio). Qualquer edição no repositório `dervs`. Publicar em servidor. Dado de paciente, chave ou caminho protegido indo para a ponte.

## riscos

Média-alta: a ponte cria um caminho novo de entrada de comando (painel web -> computador do dono). Mitigação: só saída, token por arquivo, recado tratado como dado, ação que muda estado exige clique local, revisão security-reviewer antes de mesclar. Sem migration, sem pagamento, sem dado de paciente.

## plano_de_voo

Modo enxuto. Fases 1, 4, 5 e 6 (sem interface nova nesta onda, então sem fase 3). Fase 5 feita por mim direto, porque o escopo é um módulo novo; fase 6 com revisores python e security. Despachos previstos: 2 (python-reviewer e security-reviewer).
