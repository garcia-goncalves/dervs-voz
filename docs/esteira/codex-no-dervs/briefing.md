# Briefing — Codex (ChatGPT Plus) como segundo cérebro de código do DERVS

Aprovado em: 2026-10-06

## pedido_original

"Quero também utilizar o CODEX do ChatGPT (OpenAI) pois eu pago mensalmente o ChatGPT PLUS e quero me beneficiar usando o codex no DERVS! Quero o melhor setup do meu Jarvis. Quero que seja ultra inteligente e rápido."

## entendimento

O DERVS passa a poder entregar trabalho de código e análise ao **Codex** (o `codex.exe` que já vem com o app Codex instalado neste PC, CLI 0.160.0, já logado "using ChatGPT"), por voz ("pede pro Codex analisar o projeto X"). Roda localmente com a assinatura pessoal do dono, no PC dele, em modo somente leitura por padrão; para escrever, só numa cópia isolada (git worktree) e depois do "confirma". A resposta final vira fala curta e texto na conversa; tudo que o Codex devolve é dado, nunca ordem.

## usuario_alvo

O dono (não programador, fala em português, PC Windows com ChatGPT Plus). Futuramente outras pessoas, cada uma com a própria assinatura no próprio PC; nunca a do dono atendendo terceiros.

## criterio_de_aceitacao

- [ ] `dervs_codex.localizar()` acha o `codex.exe` (config `codex_caminho` > `...\WindowsApps\OpenAI.Codex_*\app\resources\codex.exe` da versão mais nova > `codex` no PATH), só aceita arquivo chamado `codex.exe`/`codex.cmd` que exista, e devolve `None` com motivo legível se não achar (…ver detalhe)
- [ ] `dervs_codex.status()` roda `codex login status` e distingue "logado com ChatGPT", "logado com chave de API" (avisa: gasta dinheiro, não a assinatura), "não logado" e "falhou"; provado por teste com executor falso.
- [ ] `dervs_codex.perguntar(texto, pasta, modo)` monta SEMPRE `exec -s read-only --ephemeral --skip-git-repo-check -C <pasta> --output-last-message <arquivo temporário> -` (prompt por stdin, nunca na linha de comando), nunca usa `--dangerously-bypass-approvals-and-sandbox` (…ver detalhe)
- [ ] Modo escrita ("no projeto X pede pro Codex fazer Y") só depois do "confirma", numa cópia git worktree em branch `dervs/codex-…`, com `-s workspace-write`, sem permissão de `git push` (variável de ambiente que remove credenciais do git e `-c` que o impeça) (…ver detalhe)
- [ ] Por voz: "pergunta pro Codex …", "pede pro Codex …", "manda o Codex …", "usa o Codex para …", "no projeto X pede pro Codex …"; frase que não casa inteira segue como sempre; "para" interrompe o Codex em andamento; só um Codex por vez (…ver detalhe)
- [ ] Saída do Codex é DADO: passa por filtro de segredo (`dervs_cofre.parece_segredo`, linha a linha), é cercada como saída de comando se alimentar outro cérebro, vira no máximo 2 frases faladas e o texto completo vai para a conversa do painel (…ver detalhe)
- [ ] Config `codex_ligado` (padrão `true`), `codex_caminho` (padrão vazio), `codex_esforco` (`low|medium|high`, padrão `medium`, passado por `-c model_reasoning_effort=`), com validação de valor torto; chip/linha de estado no painel dizendo "Codex: pronto (…ver detalhe)
- [ ] Um teste real, **pulado por padrão** (liga com `DERVS_TESTE_CODEX_REAL=1`), roda `perguntar("responda pong")` de verdade em somente leitura; e o implementador o roda uma vez e relata o tempo.
- [ ] Documentação: `COMO-USAR.md` seção "Codex", `ESTADO.md`, e a memória descreve onde o `codex.exe` mora e a armadilha da pasta versionada do WindowsApps.

## fora_de_escopo

- Codex em nuvem, servidor (VPS) ou para terceiros usando a assinatura do dono.
- Substituir o cérebro de conversa (OpenAI por API) ou o Claude Code; o Codex é **mais um** executor.
- Roteamento automático Claude↔Codex por custo ou qualidade (onda seguinte; hoje só se o dono citar o Codex).
- Mexer em `~/.codex/config.toml` ou na autenticação do Codex.

## riscos

Sem paciente, pagamento, migration ou deploy. Riscos de segurança: (a) Codex escrevendo fora da pasta ou subindo código (`git push`) sem o dono; (b) prompt injection pelo conteúdo que o Codex lê e devolve; (c) segredo na resposta lida em voz alta (a voz pode ser de nuvem); (d) gasto escondido se o login for por chave de API em vez de ChatGPT (item 2 avisa); (e) pasta do pacote do WindowsApps muda a cada atualização do app (item 1 a procura de novo a cada uso, não grava o caminho).

## plano_de_voo

Fases: 1 briefing (esta, aprovada pelo dono em 06/10: "faça tudo sem parar") → 2 descoberta (já feita: `codex.exe` achado, `exec --help` lido, teste real pong em 9 s) → 4 plano e 5 execução por um agente em worktree isolada → 6 revisão (security-reviewer + python-reviewer) → 7 cronista. Sem design novo (uma linha de estado no painel).
Modelos: execução em Opus (segurança), revisão em Opus, mecânico em Haiku. Despachos previstos: 1 executor, 2 revisores (4 com a busca semântica em paralelo).

## detalhe_dos_criterios

Texto completo dos critérios encurtados acima (a lista tem teto de 300 caracteres por linha):

7. Config `codex_ligado` (padrão `true`), `codex_caminho` (padrão vazio), `codex_esforco` (`low|medium|high`, padrão `medium`, passado por `-c model_reasoning_effort=`), com validação de valor torto; chip/linha de estado no painel dizendo "Codex: pronto (ChatGPT)" ou o motivo de não estar (…ver detalhe)
