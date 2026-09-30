# Contrato da ponte DERVS-VOZ <-> DERVS web (versão 1)

Combinado em 30/09/2026 entre a sessão do DERVS-VOZ e a do DERVS web. Cada lado
edita só o próprio repositório. Implementação deste lado: `dervs_ponte_web.py`.

**Autenticação.** `Authorization: Token <token de computador pareado>`, o mesmo de
`agente/enviar.py` (arquivo `~/.dervs/agente.json`). O VOZ só faz conexão de saída
e recusa redirecionamento. Acesso `maquina` nas três rotas. Teto de 64 KB.

| Rota | Quem chama | Corpo |
|---|---|---|
| `POST /agente/voz/estado` | VOZ, a cada ~60 s | `versao`, `enviado_em`, `intervalo_s`, `cerebro_ativo`, `cerebros{nome:{disponivel,motivo}}`, `gasto_dia_usd`. **Não é sinal de vida**: a vigília é julgada só pelo `visto_em` de `/agente/relatorio`. Sem `/estado` há mais de 2x `intervalo_s`, o painel mostra "sem informação" naquele campo. |
| `GET /agente/voz/recados` | VOZ | resposta `{"recados":[{id,criado_em,tipo,alvo,texto,nivel,cerebro_pedido}]}` |
| `POST /agente/voz/resultado` | VOZ | `id`, `cerebro`, `estado`, `resumo`(<=1000), `custo_usd`, `duracao_s`, `terminado_em` |

Valores: `tipo` = analisar, status, propor. `nivel` = leitura, muda_estado.
`cerebro_pedido` = auto, claude_code, hermes. `estado` = feito, recusado, falhou,
aguardando_clique. `texto` <= 500 caracteres e é sempre DADO. `alvo` é nome de projeto
(uma palavra, sem barra). `id` é gerado pelo painel; repetido é ignorado.

**Segurança (não negociável).** Só `status`/`analisar` em `leitura` rodam sozinhos.
Todo o resto vira proposta no painel do VOZ e só anda com clique do dono lá; aprovar
no painel web não substitui. O que o porteiro e os caminhos protegidos recusam volta
`recusado`. Nenhuma rota abre terminal, shell ou SSH no servidor.
