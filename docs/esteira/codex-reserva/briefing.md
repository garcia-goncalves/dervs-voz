# Briefing — Codex como reserva automática do Claude

Aprovado em: 2026-10-08

## pedido_original

"Pode apagar e fazer tudo do melhor pra mim." (08/10/2026, retomando a onda seguinte de `docs/esteira/codex-no-dervs`, cujo `fora_de_escopo` deixou para depois o "roteamento automático Claude↔Codex por custo ou qualidade".)

## entendimento

Quando o dono pede uma análise de um projeto dele ("analisa o projeto X", "investiga o bug do login no projeto X") e o Claude Code já está ocupado com outro pedido, o DERVS passa o pedido ao Codex, só para leitura, em vez de responder "ainda estou trabalhando". Ele avisa em voz alta que mandou ao Codex. O Claude continua sendo o programador principal. Pedido de mexer em código nunca vai ao Codex sem o dono citar o Codex, e o dono desliga a troca automática por uma chave no config.

## usuario_alvo

O dono (não programador, fala por voz, PC Windows com assinatura do Claude e ChatGPT Plus), no momento em que faz um segundo pedido enquanto o Claude ainda trabalha no primeiro. Não é desenvolvedor.

## criterio_de_aceitacao

- [ ] `dervs_roteador.reserva_codex(rota, claude_ocupado, codex_pronto, ligado)` devolve a intenção `{"tipo": "codex_leitura", "pedido": …}` só quando a rota é `claude_code` com intenção `trabalho`, o Claude está ocupado, o Codex está pronto e livre e a chave está ligada (…ver detalhe)
- [ ] Pedido que cita o Claude pelo nome ("pede pro Claude…", "Claude, …") nunca é desviado ao Codex: o dono escolheu quem atende. Provado por teste.
- [ ] Pedido de desenvolver (intenção `desenvolver`) com o Claude ocupado não vai ao Codex; a resposta falada passa a dizer "ou diga: no projeto tal, pede pro Codex fazer isso". Provado por teste.
- [ ] Ao desviar, o DERVS fala antes "O Claude está ocupado; passei para o Codex, só para leitura." e a resposta do Codex passa pelo mesmo caminho de `AcoesCodex.executar` (filtro de segredo, `_SENSIVEL`, no máximo 2 frases faladas)
- [ ] Cada desvio vai para `roteamento.jsonl` com `executor: "codex"` e `motivo: "claude ocupado: reserva automática"`. Provado por teste com arquivo temporário.
- [ ] Config `codex_reserva` (padrão `true`), validada como booleano; com `false` ou `codex_ligado=false` o comportamento é idêntico ao de hoje. Provado por teste do `dervs_config`.
- [ ] Suíte inteira verde: `python -m pytest -q` sem falha nova.
- [ ] Documentação: `COMO-USAR.md` (seção "Codex", um parágrafo sobre a reserva e como desligar), `ESTADO.md` e a memória `dervs-codex-integracao` atualizados no mesmo commit.

## detalhe_dos_criterios

1. Só desvia pedido que cita um projeto do dono (extraído por `dervs_codex_voz.interpretar`), e o Codex fica preso à pasta dele; sem projeto ("verifica meu PC") o somente-leitura enxergaria o disco todo, então não desvia (achado da revisão de segurança de 08/10). Projeto inexistente vira "não achei o projeto", nunca a pasta neutra. `reserva_codex` é função pura (sem Qt, sem processo), para ser testada sem o app. O Codex conta como "pronto" quando `codex_ligado` é verdadeiro, o `codex.exe` foi achado e ele não está ocupado. O ponto de chamada é `dervs_electron.py`, no ramo em que `self.claude.perguntar(...)` devolve `False` (Claude ocupado), antes da mensagem "Ainda estou trabalhando…".

## fora_de_escopo

- Codex escrevendo código por desvio automático (só com o dono citando o Codex e dizendo "confirma", como hoje).
- Detectar que a cota ou o limite de uso do Claude acabou e desviar por isso (precisa ler o erro do Claude Code; onda seguinte).
- Escolher Claude ou Codex por custo ou qualidade quando os dois estão livres.
- Codex como cérebro de conversa no lugar do OpenAI por API.
- Tela nova no painel: a chave fica no `config.json`.

## riscos

Nenhum de paciente, pagamento, migration ou deploy. Risco de privacidade: um pedido falado vai a outro fornecedor (OpenAI pelo ChatGPT Plus) sem o dono citar o Codex. Isso é mitigado pelo aviso falado antes de cada desvio, pelo filtro de segredo e `_SENSIVEL` já existentes, pelo modo somente leitura e pela chave `codex_reserva`. O mesmo dono já usa os dois fornecedores.

## plano_de_voo

Fases: 1 briefing (este; o dono autorizou em 08/10: "faça tudo do melhor pra mim") → 2 descoberta já feita na leitura do código (`dervs_roteador.rotear`, `dervs_electron._tentar_codex_voz`, `AcoesCodex._despachar`, `dervs_config.PADRAO`) → sem design (não há tela) → 4 e 5 executados direto nesta sessão com TDD, porque o escopo é pequeno (3 arquivos de código e 3 de teste) → 6 revisão por `python-reviewer` e `security-reviewer` em paralelo → 7 cronista (docs, memória, commit, push).
Modo enxuto. Modelos: execução em Opus (esta sessão), revisores em Sonnet. Despachos previstos: 2.
