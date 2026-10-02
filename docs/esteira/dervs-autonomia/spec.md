# Spec — DERVS com autonomia configurável (02/10/2026)

## problema
O dono quer um DERVS que faça muito mais sozinho, mas hoje só existe o "pergunta sempre" fixo do motor de aprovação: não há como ele liberar ou travar categorias, não há teto de gasto em API paga, a escolha de cérebro é uma cascata fixa e um erro do app só vira texto em `ultimo_erro.txt` que ninguém lê.

## solucao
Uma camada **de política** que só pode reduzir poder, nunca ampliar o teto fixo de segurança:
1. `dervs_permissoes.py` (novo, puro): 8 categorias × 3 níveis (`analisa` < `pergunta` < `sozinho`), padrão e normalização (valor inválido cai no padrão; corrompido cai no padrão inteiro). Mapeia ferramenta → categoria e decide `negar | perguntar | permitir`.
2. Ligação no gancho existente `decisao_do_gancho` e no `_can_use_tool`, **depois** de `motivo_de_bloqueio` (que continua sendo o teto). `sozinho` só vale para ação não destrutiva, sem rede, sem caminho protegido, sem segredo.
3. Teto de gasto diário (`teto_gasto_dia_usd`) em `dervs_gasto.estourou()`, contando só API paga (nunca `tipo="claude"`); `_pensar_openai` recusa ao estourar e a cascata cai para o Claude da assinatura.
4. Roteador (`dervs_roteador.py`, novo): escolhe o executor por intenção (código/máquina → Claude Code; conversa → OpenAI se houver chave e teto; senão Claude) e grava o motivo em `roteamento.jsonl`. É heurística transparente, não modelo.
5. Painel "O que o DERVS pode fazer" (chip + dialog, molde do Central/Integração) com IPC nas 4 camadas, mais uma seção "Avançado" com o roteamento recente.
6. Piloto automático (`dervs_piloto.py`, novo): lê a queda anterior **antes** de o registro apagá-la, escreve diagnóstico em português; só prepara/aplica conserto se "alterar arquivos do projeto" estiver em `sozinho`, sempre em worktree/branch, com testes verdes, nunca na `main`.
**Por que assim:** reaproveita o gancho, o cartão e a quarentena que já foram revisados; a política é uma peça pura e testável; e o "revolucionário" fica na orquestração, não em abrir mão de segurança.

## o_que_ja_existe
- `dervs_safety.py:302,363` `classificar_local`/`decidir_risco` — teto fixo, só sobe. Não editar.
- `dervs_claude_code.py:310` `classificar`, `:386` `motivo_de_bloqueio`, `:434` `decisao_do_gancho`, `:451` `criar_gancho`, `:1152` `_can_use_tool`, `:66-67` `PERMISSION_MODE`/`MODOS_PROIBIDOS`, `:80-84` conjuntos de ferramentas.
- `dervs_aprovacao.py:476` `Motor.aprovar` (só `origem=="clique"`), `:64-70` categorias de ação.
- `dervs_config.py:66` `PADRAO`, `:224` `_validar`, `:313` `carregar`, `:329` `gravar`.
- `dervs_gasto.py:93` `registrar`, `:115` `total_do_dia`; `dervs_brain.py:712` `_pensar_openai`, `:734` `pensar`.
- `dervs_cerebros.py:204` `Seletor`, `:35` `CEREBROS_ESCOLHIVEIS`.
- `dervs_registro.py:45,93` `anotar`/`colher_anterior`, `QUEDA_ANTERIOR`.
- Painel: `electron/renderer/painel.html` (chips/dialogs), `electron/preload.js`, `electron/main.js`, `dervs_ponte_electron.py:191,506`, `dervs_integracao_painel.py:151`; testes `test_dervs_painel_js.py`, `test_dervs_integracao_painel.py`.

## fontes_externas
nenhuma (decisão apoiada no código local e nas regras da Anthropic já consultadas em 02/10/2026: https://code.claude.com/docs/en/legal-and-compliance).

## fora_de_escopo
VPS/produção, cliente do porteiro `/agente/voz/triagem`, Hermes/Bolt.diy na VPS, instalador (Onda F), roteamento por modelo de linguagem (só heurística nesta rodada), apagar sem quarentena, qualquer coisa que use a assinatura Max fora do Claude Code do próprio dono.

## contradicoes_resolvidas
- "Autonomia total" × travas: vence a trava. Cinco limites ficam fixos e fora do painel (sem `bypassPermissions`, nada em servidor sem "sim", segredo nunca exposto, apagar só por quarentena, teto de gasto). Motivo: o painel só reduz poder; um erro de entendimento por voz não pode virar dano.
- Esconder os cérebros × transparência: saem da tela principal, ficam em "Avançado" com o motivo de cada escolha. Motivo: o dono não precisa decidir, mas precisa poder auditar.
- Piloto automático × `Motor.aprovar` só por clique: o piloto **nunca** chama `aprovar`; ele age só em worktree própria com permissão `sozinho` já dada no painel. Motivo: preservar a regra de que aprovação é humana.
- Falha aberta do gasto × teto: o teto falha **fechado** só para API paga; leitura do gasto com erro conta como estourado. Motivo: erro no medidor não pode liberar gasto ilimitado.

## duvidas_para_o_dono
nenhuma. Defaults escolhidos e ajustáveis depois no painel: teto diário US$ 3,00 (igual ao teto de sessão já usado no DERVS web); leitura e "usar a internet de leitura" em `sozinho`; instalar, alterar projeto, apagar, servidor e gastar em `pergunta`.

## plano de ondas
- **W1 (eu, TDD):** chave `permissoes` + `teto_gasto_dia_usd` no config; `dervs_permissoes.py`; `dervs_gasto.estourou`.
- **W2 (eu, TDD):** integração no gancho/`_can_use_tool`; teto no `_pensar_openai`; `dervs_roteador.py` ligado ao `pensar`.
- **W3 (executor sonnet, worktree) e W4 (executor sonnet, worktree), em paralelo:** W3 painel + IPC + testes; W4 piloto automático + testes.
- **Revisão:** `security-reviewer`, `python-reviewer`, `design-reviewer`; depois suíte completa, prova na tela real, doc, PR.
