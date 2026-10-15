# Contrato da ponte DERVS-VOZ <-> DERVS web (versão 1)

Combinado em 30/09/2026 entre a sessão do DERVS-VOZ e a do DERVS web. Cada lado
edita só o próprio repositório. Implementação deste lado: `dervs_ponte_web.py`.

**Autenticação.** `Authorization: Token <token de computador pareado>`, o mesmo de
`agente/enviar.py` (arquivo `~/.dervs/agente.json`). O VOZ só faz conexão de saída
e recusa redirecionamento. Acesso `maquina` nas três rotas. Teto de 64 KB.

| Rota | Quem chama | Corpo |
|---|---|---|
| `POST /agente/voz/estado` | VOZ, a cada ~60 s | `versao`, `enviado_em`, `cerebro_ativo`, `cerebros{nome:{disponivel,motivo}}`, `gasto_dia_usd` (EXATAMENTE estas cinco chaves: o servidor responde 400 a qualquer outra, NaN ou Infinity). **Não é sinal de vida**: a vigília é julgada só pelo `visto_em` de `/agente/relatorio`. Sem `/estado` há mais de 2x `intervalo_s`, o painel mostra "sem informação" naquele campo. |
| `GET /agente/voz/recados` | VOZ | resposta `{"recados":[{id,criado_em,tipo,alvo,texto,nivel,cerebro_pedido}]}` |
| `POST /agente/voz/resultado` | VOZ | `id`, `cerebro`, `estado`, `resumo`(<=1000), `custo_usd`, `duracao_s`, `terminado_em` |

Valores: `tipo` = analisar, status, propor, avisar (novo em 30/09: o painel gera sozinho quando um computador fica 20 min sem medir ou surge alerta grave; `nivel` sempre `leitura`, `alvo` = `vigilia` ou nome de projeto; o VOZ só MOSTRA o texto ao dono e responde `feito`; `avisar` com `muda_estado` é recusado). `nivel` = leitura, muda_estado.
`cerebro_pedido` = auto, claude_code, hermes. `estado` = feito, recusado, falhou,
aguardando_clique. `texto` <= 500 caracteres e é sempre DADO. `alvo` é nome de projeto
(uma palavra, sem barra). `id` é gerado pelo painel; repetido é ignorado.

**Segurança (não negociável).** Só `status`/`analisar` em `leitura` rodam sozinhos.
Todo o resto vira proposta no painel do VOZ e só anda com clique do dono lá; aprovar
no painel web não substitui. O que o porteiro e os caminhos protegidos recusam volta
`recusado`. Nenhuma rota abre terminal, shell ou SSH no servidor.

## Pedido do VOZ ao painel (novo em 30/09)

`POST /agente/voz/pedido` (acesso `maquina`). Corpo EXATO: `{"tipo":"enfileirar_conserto","alerta_id":"<=200","resumo":"<=300"}`
(chave extra = 400). Resposta 200: `{"ok":true,"tarefa_id":"regra:usuario:alerta","pedido":true|false,"aviso":""}`;
`pedido:false` = já existia. A tarefa nasce PENDENTE do "Pode fazer" do dono no painel e nunca roda sozinha.
404 = alerta inexistente ou de outra conta; 403 = regra que a IA não conserta por aqui (desde 15/10, PR #42 do dervs, nenhum projeto é bloqueado);
429 = 10 pedidos por 15 min. Cliente: `PonteWeb.pedir_conserto`. Hoje só `memoria_crlf` e `env_drift` passam.

## Recusa da máquina (painel desde 09/10, PRs #38/#39)

Nas quatro rotas `/agente/voz/*`, o painel recusa por causa da MÁQUINA antes de qualquer outra regra:
403 `{"erro":"este servidor so olha"}` (`tipo=servidor`) e 403 `{"erro":"este computador so mede"}`
(computador ligado pelo `conectar-dervs.cmd`). O VOZ casa pelo texto exato (`RECUSA_DA_MAQUINA` em
`dervs_ponte_web.py`) e diz ao dono o que fazer. Outro texto de 403 cai na frase genérica de token.
