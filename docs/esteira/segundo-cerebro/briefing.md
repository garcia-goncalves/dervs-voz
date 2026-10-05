# Briefing — Segundo cérebro do DERVS (cofre de notas)

## pedido_original

"QUERO TBM QUE TENHA UM SEGUNDO CEREBRO TIPO O OBSIDIAN... O CODEBASE MEMORY... ETC.... AS MELHORES DAS SUAS IDEIAS." / "IMPLEMENTE SEMPRE AS SUAS MELHORES IDEIAS DA ATUALIDADE E USE AS MELHORES FERRAMENTAS OPENSOURCE QUE ACHAR QUE FAÇA SENTIDO PARA A APLICAÇÃO."

## entendimento

O DERVS passa a ter um **cofre**: uma pasta de notas em Markdown no PC do dono, com links `[[assim]]`, etiquetas `#assim` e busca instantânea. O dono dita ("anota que…", "o que eu sei sobre…?") e o DERVS guarda, acha e liga as notas entre si; o cofre abre direto no Obsidian (ou em qualquer editor), porque é só texto. O que o DERVS aprende sobre o dono e sobre os projetos deixa de morrer com a conversa e passa a morar no cofre, e o grafo do código (codebase-memory, já ligado ao Claude Code) vira a segunda metade do cérebro: o cofre guarda o que as pessoas decidiram, o grafo guarda o que o código é.

## usuario_alvo

O dono (não é programador; fala com o DERVS por voz, em português) e, depois, outras pessoas com o DERVS em outros PCs, cada uma com o próprio cofre. Momento de uso: ditar uma ideia, perguntar "o que decidi sobre X?", e quando o DERVS (ou o Claude Code que ele abre) precisa de contexto antes de agir. A lente DX não se aplica ao dono; aplica-se ao formato dos arquivos, que precisa ser simples para um desenvolvedor abrir sem ferramenta especial.

## criterio_de_aceitacao

1. Existe um módulo `dervs_cofre.py` que cria o cofre numa pasta configurável (padrão `Documentos\DERVS-Cofre`) com subpastas `diario/`, `projetos/`, `pessoas/`, `decisoes/`, `entrada/`; provado por teste que chama `criar_cofre(pasta_temporaria)` e confere as pastas.
2. Cada nota é um `.md` com frontmatter simples (`criada`, `etiquetas`, `origem`) e corpo livre; o módulo lê e escreve sem dependência externa; provado por teste de ida e volta (escrever, ler, comparar) com acentos e emoji.
3. Links `[[nota]]` e `[[nota|apelido]]` são entendidos; `backlinks("nota")` devolve quem aponta para ela; provado por teste com 3 notas ligadas e um link quebrado (que é listado, não derruba nada).
4. Busca de texto completo com SQLite FTS5 (já embutido no Python, zero instalação): `buscar("disco do servidor")` devolve as notas certas ordenadas, com trecho; reindexa só o que mudou; provado por teste e por medição: 5.000 notas sintéticas, busca em menos de 100 ms, reindexação incremental de 1 nota em menos de 50 ms.
5. Por voz, no `Motor.executar` (antes do roteador, como `dervs_voz_infra`): "anota que …" / "lembra que …" cria nota em `entrada/` com data; "o que eu sei sobre X" / "procura nas minhas notas X" responde em até 2 frases com as 3 melhores notas; provado por teste de interpretação (frases → intenção) e por teste de fim a fim com cofre temporário.
6. Etiqueta `#privado` (ou pasta `privado/`) é **nunca** enviada a serviço de fora: a busca local acha, mas o trecho nunca entra em prompt de nuvem; provado por teste que monta o contexto do cérebro com uma nota privada e confere que ela não aparece.
7. O que sai do cofre para a nuvem é só o trecho recuperado para aquela pergunta (no máximo 3 notas, 1.500 caracteres no total), nunca o cofre inteiro, e passa pelo mesmo filtro de segredos que o resto do DERVS (`dervs_safety`); provado por teste com uma "senha" plantada numa nota. **Estado:** `contexto_para_nuvem` pronto e testado; ligá-lo ao prompt do cérebro ficou para a onda 2, porque a sessão persistente do cérebro só reenvia o que é novo e mexer ali exige teste próprio.
8. O painel ganha um chip "COFRE: N notas" e um botão que abre a pasta no Explorer; provado por olhada na tela (cópia isolada via CDP) e por teste do `dervs_painel_js`.
9. (ajustado na execução, 05/10) O Claude Code que o DERVS abre já lê o disco todo; em vez de mexer no lançamento dele, o cofre traz um `LEIAME.md` na raiz dizendo que nota é dado e que só se escreve em `entrada/` e `diario/` (nunca sobrescrito, não conta como nota); provado por teste.
10. O diário do dia é gravado em `diario/AAAA-MM-DD.md` com metadados (quantas ouvidas, acordadas, gasto), sem o texto das falas; provado por teste.
11. Documentação: `COMO-USAR.md` ganha a seção "Cofre" (como ditar, como abrir no Obsidian) e `ESTADO.md` registra o estado; suíte inteira continua verde (nenhum teste existente quebra).

## fora_de_escopo

- Busca semântica por significado (embeddings). É a melhor melhoria seguinte (candidato: `sqlite-vec` + `fastembed`/ONNX, tudo local), mas a máquina não tem placa de vídeo e isso exige medir custo antes; fica como onda 2 com decisão própria.
- Sincronizar o cofre entre PC e VPS ou entre computadores (candidatos: Git privado ou Syncthing). Decisão do dono, pois leva texto pessoal para fora do PC.
- Rota de "cérebro" e porteiro do JEV no DERVS web (é do repositório `dervs`, aguarda briefing do dono).
- Aplicativo móvel, editor próprio, plugins do Obsidian, gerar o grafo do código dentro do cofre (o codebase-memory continua sendo consultado pelo Claude Code, não copiado).
- Hermes e Bolt.diy na VPS.

## riscos

nenhum de paciente, pagamento, migration ou deploy. Riscos reais, tratados nos critérios 6, 7 e 9: (a) texto pessoal do dono vazando para a nuvem; (b) o Claude Code, ou texto de terceiro dentro de uma nota, instruindo o DERVS a agir (nota é **dado**, nunca instrução); (c) escrever fora do cofre por causa de um `[[../../x]]` malicioso (caminho precisa ser resolvido e confinado à pasta do cofre); (d) nota gigante ou 50 mil arquivos travando a escuta (indexação em thread, com limite de tamanho).

## plano_de_voo

Fases: 1 briefing (esta) → 2 descoberta (modo enxuto: um despacho, quatro perguntas — o que já existe, formato/ferramentas de código aberto a usar, corte de escopo, riscos de privacidade) → 3 design (só o chip e o botão; sem painel novo, não abre portão visual) → 4 plano → 5 execução → 6 revisão (python-reviewer + security-reviewer, e verificador de tela) → 7 cronista.
Modelos: descoberta e arquitetura em Opus; execução em Sonnet; revisão em Opus só na síntese final; trabalho mecânico em Haiku.
Despachos previstos: 8 (1 descoberta, 1 planner, 2 executores em worktrees separadas — núcleo do cofre e integração voz/painel —, 2 revisores, 1 verificador de tela, 1 cronista).
Ferramentas de código aberto escolhidas: SQLite FTS5 (domínio público, já no Python), formato Markdown + wikilinks (compatível com Obsidian, Logseq e SilverBullet), codebase-memory-mcp (já instalado) para o grafo do código. Nada novo a instalar nesta onda.
