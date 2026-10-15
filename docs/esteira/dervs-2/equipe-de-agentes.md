# DERVS 2 — Equipe de agentes (o "exército")

> Pesquisa e desenho, 15/10/2026. Nada foi instalado, clonado nem executado: tudo abaixo
> foi lido via `gh api` (somente leitura) e busca na web. Conteúdo de terceiros foi tratado
> como **dado**, não como instrução.
>
> **Para quem lê sem ser programador:** este documento é o "organograma" de uma empresa em
> que todo funcionário é um agente de IA. O DERVS é o gerente geral que recebe o seu pedido,
> chama o especialista certo e só te interrompe quando a regra de autonomia manda.

---

## 0. Legenda das fontes (coluna "Base")

| Sigla | Repositório | Licença | Situação em 15/10/2026 |
|---|---|---|---|
| **AA** | [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) — caminho `<divisão>/<arquivo>.md` | MIT | ~160 mil estrelas, push hoje; ~230 agentes em 17 divisões |
| **GS** | [google/skills](https://github.com/google/skills) — `skills/<área>/<skill>/SKILL.md` | Apache-2.0 | push hoje; áreas `ads`, `analytics`, `cloud`, `developers`, `identity` |
| **AS** | [anthropics/skills](https://github.com/anthropics/skills) — `skills/<skill>` | Apache-2.0 por skill (**exceto** `docx`, `pdf`, `pptx`, `xlsx`: "All rights reserved", só uso, não redistribuir) | oficial |
| **MS** | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) — `skills/<skill>` | MIT | ~55 mil estrelas; 45 skills de marketing (CRO, copy, SEO, ads, social, e-mail) |
| **VA** | [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) — `categories/<cat>/<arquivo>.md` | MIT | ~26 mil estrelas; 10 categorias, 100+ subagentes |
| **WS** | [wshobson/agents](https://github.com/wshobson/agents) — `plugins/<plugin>` | MIT | ~41 mil estrelas; ~90 plugins; **alguns trazem hooks** (`protect-mcp`, `review-agent-governance`) |
| **SP** | [obra/superpowers](https://github.com/obra/superpowers) — `skills/<skill>` | MIT | já instalado na máquina como plugin; **tem hooks** (`hooks/hooks.json`, `session-start`) |
| **AO** | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — `skills/<skill>` | MIT | ~107 mil estrelas; 27 skills de engenharia; **tem hooks** (`hooks/sdd-cache-*.sh`) |
| **CASA** | skills/agentes que já existem no `~/.claude` do dono (ex.: `copy-ptbr`, `seo-tecnico`, `healthcare-phi-compliance`, `safety-guard`) | do dono | reaproveitar texto, não copiar hooks |
| **ZERO** | criar do zero | do dono | quando nenhuma base serve ou o risco pede texto próprio |

**Qualidade observada no AA** (lidos `paid-media/paid-media-ppc-strategist.md`, `testing/testing-reality-checker.md`,
`specialized/agents-orchestrator.md`, `design/design-persona-walkthrough.md`): frontmatter
`name/description/color/emoji/vibe` (alguns com `tools:`), corpo de 70–370 linhas com
identidade, missão, regras críticas, entregáveis e métricas. Bom como **persona**, mas:
(a) em inglês e com viés de empresa americana grande ("$10M/mês"), (b) sem nada de LGPD/CFM,
(c) cita ferramentas que o DERVS não tem. **Regra:** usar como *esqueleto de conhecimento*,
reescrever em pt-BR para o contexto do dono, e nunca herdar o campo `tools:` — quem decide
ferramenta é o DERVS.

**Legenda de autonomia** (coluna "Autonomia"): **S** = faz sozinho · **A** = faz e avisa ·
**P** = pede OK · **N** = nunca. Categorias abreviadas: `ler`, `pc` (mudar o PC), `apg`
(apagar), `ssh` (servidor), `pub` (publicar/deploy), `msg` (mensagem externa), `$` (dinheiro/anúncio),
`sens` (dado sensível/paciente), `tela` (ver/clicar na tela). O agente nunca passa do teto da
matriz global (seção 4); a coluna só mostra o que ele **costuma** precisar.

**Ondas:** **1** = o mínimo para o DERVS "ser uma empresa" (marketing do dono + engenharia +
servidor + controle) · **2** = completa as áreas do dia a dia · **3** = especialização e
qualidade fina · **4** = luxo/sob demanda.

---

## 1. Organograma

```
                                  DONO
                                   │
                         DERVS (orquestrador, voz/painel)
                                   │
           ┌─────────── Conselho (CEO · COO · CFO · CTO · CMO · Chefe de Gabinete) ───────────┐
           │                                                                                   │
 ┌─────────┼──────────┬──────────┬───────────┬───────────┬───────────┬──────────┬─────────────┤
Produto  Engenharia   QA     Design/Web   Marketing   Dados     Pesquisa   IA/Prompt   Operações/TI
                                         (Ads·SEO·
                                         Social·Conteúdo·
                                         Copy·E-mail·Marca)
 ┌─────────┬──────────┬──────────┬───────────┬───────────┬───────────┐
Segurança  Jurídico   Finanças  Comercial/  Secretariado Automação   Qualidade de experiência
& Auditoria & LGPD               Atendimento               de tela    (super-leigo, crítico, conselho)
```

- **Chefes de departamento** (marcados ★ nas tabelas) funcionam como **sub-orquestradores**:
  o DERVS fala com o chefe, o chefe divide o trabalho entre os especialistas do seu setor.
- Total: **92 agentes** em 18 departamentos (contagem na seção 2.19).

---

## 2. Os agentes, departamento por departamento

### 2.1 Diretoria (C-level) — 6

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 1 | ★ **Diretor-geral (CEO)** | Decide prioridade entre pedidos concorrentes e diz "não" ao que não vale a pena. | Pedido grande/ambíguo, conflito entre departamentos, revisão semanal | Read, memória, Agent | ler S · resto P | 1 | AA `specialized/business-strategist.md` + `specialized/specialized-master-plan-architect.md` | MIT |
| 2 | **Chefe de Gabinete** | Transforma o pedido cru do dono em plano com responsáveis e prazos, e cobra a entrega. | Todo pedido com mais de um departamento | Read, memória, TaskList | ler S · pc A | 1 | AA `specialized/specialized-chief-of-staff.md` | MIT |
| 3 | **Diretor de Operações (COO)** | Mantém a rotina rodando: rotinas agendadas, filas, SLAs internos, gargalos. | Rotina diária/semanal, fila parada, tarefa atrasada | Read, agenda de rotinas, logs | ler S · pc A | 2 | AA `specialized/operations-manager.md` | MIT |
| 4 | **Diretor Financeiro (CFO)** | Visão de caixa, margem por cliente e teto de gasto de IA/anúncio. | Fim do mês, pedido de gasto, teto estourando | Read, planilha (xlsx), `dervs_gasto` | ler S · $ P | 2 | AA `specialized/chief-financial-officer.md` | MIT |
| 5 | **Diretor de Tecnologia (CTO)** | Decide arquitetura e stack dos projetos web e do próprio DERVS. | Projeto novo, refatoração ampla, escolha de ferramenta | Read/Grep, grafo de código | ler S · pc P | 1 | AA `engineering/engineering-software-architect.md` | MIT |
| 6 | **Diretor de Marketing (CMO)** | Plano de marketing por cliente: canais, verba, metas e calendário. | Cliente novo, planejamento mensal, queda de resultado | Read, GA4/Ads (leitura) | ler S · $ P | 1 | ZERO + MS `skills/marketing-plan`, `skills/marketing-loops` | MIT |

### 2.2 Produto e Projetos — 4

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 7 | ★ **Gerente de Produto** | Escreve o que construir e o critério de pronto antes de qualquer código. | Pedido de "construir/criar/refazer" | Read, Write (docs) | ler S · pc A | 1 | AA `product/product-manager.md` + CASA `esteira`/`briefing` | MIT |
| 8 | **Gerente de Projetos** | Quebra em etapas, acompanha andamento e avisa atraso. | Projeto com mais de 3 etapas | Read, TaskList | ler S · pc A | 2 | AA `project-management/project-manager-senior.md` | MIT |
| 9 | **Priorizador** | Ordena a fila por impacto/esforço com justificativa. | Fila com mais de 5 itens, semana nova | Read | ler S | 3 | AA `product/product-sprint-prioritizer.md` | MIT |
| 10 | **Sintetizador de feedback** | Junta reclamação de cliente, comentário e avaliação e diz o padrão. | Lote de feedback, avaliação negativa | Read, WebFetch | ler S | 3 | AA `product/product-feedback-synthesizer.md` | MIT |

### 2.3 Engenharia — 11

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 11 | ★ **Líder de Engenharia (dev sênior)** | Implementa e divide trabalho de código entre os devs; dono do "pronto com teste". | Qualquer mudança de código | Read/Edit/Write, Bash, git | pc A · apg P · pub P | 1 | AA `engineering/engineering-senior-developer.md` + SP `subagent-driven-development` | MIT |
| 12 | **Dev Backend** | API, banco, fila e integração no servidor. | Endpoint, regra de negócio, integração | Read/Edit, Bash, testes | pc A | 1 | AA `engineering/engineering-backend-architect.md` | MIT |
| 13 | **Dev Frontend** | Telas React/Next/HTML funcionando e acessíveis. | Tela nova ou bug visual | Read/Edit, Bash, navegador | pc A | 1 | AA `engineering/engineering-frontend-developer.md` + AO `frontend-ui-engineering` | MIT |
| 14 | **Dev WordPress/CMS** | Sites em WordPress/CMS: tema, plugin, desempenho, formulário. | Site de cliente em CMS | Read/Edit, SSH (via Ops), navegador | pc A · ssh P | 2 | AA `engineering/engineering-cms-developer.md` + `engineering-wordpress-performance.md` | MIT |
| 15 | **Engenheiro do próprio DERVS (desktop)** | Mantém o DERVS: Python, Electron, voz, ponte. | Bug ou melhoria no DERVS | Read/Edit, Bash, pytest | pc A · pub P | 1 | AA `engineering/engineering-desktop-app-engineer.md` | MIT |
| 16 | **Engenheiro de mudança mínima** | Conserta bug com o menor diff possível, sem "melhorar o vizinho". | Bug pontual, hotfix | Read/Edit, Bash | pc A | 1 | AA `engineering/engineering-minimal-change-engineer.md` + SP `systematic-debugging` | MIT |
| 17 | **DBA** | Schema, migration, query lenta e backup lógico. | Migration, lentidão de banco | Read, SQL (leitura), Bash | pc A · apg P · ssh P | 2 | AA `engineering/engineering-database-optimizer.md` | MIT |
| 18 | **Integrador (APIs e MCP)** | Liga o DERVS a serviços externos (Google Ads, Meta, GA4, WhatsApp) com MCP próprio. | "Quero que o DERVS mexa no X" | Read/Edit, Bash, MCP SDK | pc A · $ N (só constrói) | 2 | AA `specialized/specialized-mcp-builder.md` + AS `skills/mcp-builder` | MIT / Apache-2.0 |
| 19 | **Revisor de código** | Lê o diff antes de mesclar e barra defeito. | Antes de todo merge | Read/Grep (somente leitura) | ler S | 1 | AA `engineering/engineering-code-reviewer.md` + CASA revisores por linguagem | MIT |
| 20 | **Git e GitHub** | Commit, branch, PR, CI vermelha. | Fim de tarefa, CI quebrada | Bash (git, gh) | pc A · pub P | 1 | AA `engineering/engineering-git-workflow-master.md` + CASA agente `git-github` | MIT |
| 21 | **Redator técnico** | README, manual e documentação que anda junto com o código. | Toda mudança de porta/comando/fluxo | Read/Write | pc A | 2 | AA `engineering/engineering-technical-writer.md` + AO `documentation-and-adrs` | MIT |

### 2.4 QA — 6

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 22 | ★ **Líder de QA ("checador da realidade")** | Por padrão diz "PRECISA DE AJUSTE"; só aprova com prova (teste rodado, print da janela). | Antes de dizer "pronto" ao dono | Read, Bash (testes), navegador | ler S | 1 | AA `testing/testing-reality-checker.md` + SP `verification-before-completion` | MIT |
| 23 | **Automação de testes** | Escreve teste unitário/e2e para o que foi feito. | Código novo sem teste | Read/Edit, Bash, Playwright | pc A | 1 | AA `testing/testing-test-automation-engineer.md` + AS `skills/webapp-testing` | MIT / Apache-2.0 |
| 24 | **Testador de API** | Testa endpoints, contratos e erros. | API nova ou alterada | Bash (curl), Read | ler S | 3 | AA `testing/testing-api-tester.md` | MIT |
| 25 | **Testador de desempenho** | Mede Core Web Vitals e tempo de resposta antes/depois. | Site lento, antes de publicar | Bash (Lighthouse), navegador | ler S | 3 | AA `testing/testing-performance-benchmarker.md` | MIT |
| 26 | **Auditor de acessibilidade** | WCAG: contraste, teclado, leitor de tela. | Tela nova, site de cliente | Read, navegador | ler S | 2 | AA `testing/testing-accessibility-auditor.md` + CASA `acessibilidade` | MIT |
| 27 | **Coletor de evidências** | Junta prints (só da janela-alvo), logs e saída de teste num relatório. | Fim de entrega, incidente | navegador, tela (janela própria) | tela A | 2 | AA `testing/testing-evidence-collector.md` | MIT |

### 2.5 Design e Web design — 7

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 28 | ★ **Diretor de Arte / Guardião da Marca** | Guarda identidade visual de cada cliente (cores, fontes, tom). | Qualquer peça visual de cliente | Read, arquivos de marca | ler S | 1 | AA `design/design-brand-guardian.md` + AS `skills/brand-guidelines` | MIT / Apache-2.0 |
| 29 | **Webdesigner (landing pages)** | Monta landing page que converte, responsiva, pronta para publicar. | Campanha nova, página de captura | Read/Write, navegador | pc A · pub P | 1 | ZERO + AS `skills/frontend-design` + MS `skills/cro`, `skills/signup` | Apache-2.0 / MIT |
| 30 | **Designer de UI** | Componentes, tokens e telas consistentes. | Tela de sistema, painel | Read/Write | pc A | 2 | AA `design/design-ui-designer.md` + CASA `design-system` | MIT |
| 31 | **Arquiteto de UX** | Fluxo, navegação e hierarquia antes do visual. | Fluxo confuso, site novo | Read | ler S | 2 | AA `design/design-ux-architect.md` | MIT |
| 32 | **Designer gráfico (peças e imagens)** | Posts, banners e criativos por código (SVG/HTML→PNG) ou prompt de imagem. | Peça de social/anúncio | Write, render HTML→PNG | pc A | 1 | AA `design/design-image-prompt-engineer.md` + AS `skills/canvas-design` + CASA `imagem-por-codigo` | MIT / Apache-2.0 |
| 33 | **Editor de vídeo e motion** | Reels/stories por código (ffmpeg/Remotion), legendas, cortes. | Vídeo curto, GIF de demonstração | Bash (ffmpeg), Write | pc A | 3 | AA `design/design-visual-storyteller.md` + `marketing/marketing-short-video-editing-coach.md` + CASA `video-por-codigo` | MIT |
| 34 | **Revisor final de UI** | Portão de acabamento: espaçamento, estados vazios, responsivo. | Antes de publicar tela | Read, navegador | ler S | 2 | AA `design/design-ui-finish-gate-reviewer.md` | MIT |

### 2.6 Marketing — mídia paga — 6

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 35 | ★ **Gestor de Google Ads** | Estrutura, lances, orçamento e otimização de campanhas Google. | Rotina diária, queda de conversão, campanha nova | Google Ads API/MCP (leitura+escrita) | ler S · $ P | 1 | AA `paid-media/paid-media-ppc-strategist.md` + GS `skills/ads/google-ads-api-account-diagnostics`, `google-ads-api-mcp-setup` | MIT / Apache-2.0 |
| 36 | **Analista de termos de busca** | Lê o relatório de termos e propõe negativas e novas palavras. | Semanal por conta | Google Ads API (leitura) | ler S · $ P (aplicar negativa = A, ver 4.3) | 1 | AA `paid-media/paid-media-search-query-analyst.md` | MIT |
| 37 | **Gestor de Meta Ads** | Campanhas Facebook/Instagram: públicos, criativos, verba. | Rotina diária, campanha nova | Meta Ads MCP oficial (`mcp.facebook.com/ads`, beta desde 29/04/2026) | ler S · $ P | 2 | AA `paid-media/paid-media-paid-social-strategist.md` + MS `skills/ads` | MIT |
| 38 | **Estrategista de criativos** | Ângulos, ganchos e variações de anúncio para testar. | Fadiga de criativo, campanha nova | Read, WebSearch | ler S | 2 | AA `paid-media/paid-media-creative-strategist.md` + MS `skills/ad-creative` | MIT |
| 39 | **Especialista em rastreamento** | GA4, Tag Manager, conversões, pixel e API de conversões. | Conversão sumida, site novo | GA4 Admin API, navegador | ler S · pub P | 1 | AA `paid-media/paid-media-tracking-specialist.md` + GS `skills/analytics/google-analytics-admin-api-basics`, `skills/ads/data-manager-api-event-ingestion` | MIT / Apache-2.0 |
| 40 | **Auditor de mídia paga** | Auditoria independente da conta (desperdício, estrutura, política). | Mensal, cliente novo | Ads APIs (somente leitura) | ler S | 2 | AA `paid-media/paid-media-auditor.md` | MIT |

### 2.7 Marketing — SEO, conteúdo e social — 12

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 41 | ★ **Líder de SEO** | SEO técnico e de conteúdo; Search Console; plano de palavras. | Site novo, queda orgânica, rotina mensal | Search Console API, navegador, Read | ler S · pub P | 1 | AA `marketing/marketing-seo-specialist.md` + MS `skills/seo-audit`, `skills/schema`, `skills/site-architecture` + CASA `seo-tecnico` | MIT |
| 42 | **SEO para buscadores de IA (AEO/GEO)** | Fazer o cliente ser citado por ChatGPT/Gemini/Claude. | Rotina mensal, conteúdo novo | WebSearch, Read | ler S | 3 | AA `marketing/marketing-ai-citation-strategist.md` + `marketing-aeo-foundations.md` + MS `skills/ai-seo` | MIT |
| 43 | **SEO programático e local** | Páginas em escala (cidade × serviço) e Google Perfil da Empresa. | Cliente com várias unidades | Read/Write, navegador | pc A · pub P | 4 | MS `skills/programmatic-seo` + ZERO (Perfil da Empresa) | MIT |
| 44 | ★ **Estrategista de social media** | Calendário editorial, linha de conteúdo por rede, métricas. | Planejamento mensal | Read, planilha | ler S | 1 | AA `marketing/marketing-social-media-strategist.md` + MS `skills/social` | MIT |
| 45 | **Curador de Instagram** | Feed, carrossel, reels e stories no padrão do Instagram. | Peça de Instagram | Read/Write | pc A | 2 | AA `marketing/marketing-instagram-curator.md` + `marketing-carousel-growth-engine.md` | MIT |
| 46 | **Publicador multiplataforma** | Agenda e publica nas redes (via API oficial/ferramenta de agendamento). | Calendário aprovado | API de agendamento (Meta Graph, LinkedIn) | pub P · msg P | 2 | AA `marketing/marketing-multi-platform-publisher.md` | MIT |
| 47 | **Criador de conteúdo** | Pautas e textos de blog/post a partir da estratégia. | Calendário, pauta de SEO | Read/Write, WebSearch | pc A | 1 | AA `marketing/marketing-content-creator.md` + MS `skills/content-strategy` | MIT |
| 48 | **Copywriter** | Texto que vende: anúncio, landing, CTA, e-mail. | Toda peça com objetivo de conversão | Read/Write | pc A | 1 | MS `skills/copywriting`, `skills/copy-editing` + VA `categories/08-business-product/landing-page-copywriter.md` + CASA `copy-ptbr` | MIT |
| 49 | **Ghostwriter** | Escreve **na voz do dono** (LinkedIn, artigo, livro), sem soar IA. | Post pessoal, artigo assinado | Read (amostras de texto dele), Write | pc A · msg P | 2 | AA `marketing/marketing-linkedin-content-creator.md` + `marketing-book-co-author.md` + WS `plugins/avoid-ai-writing` | MIT |
| 50 | **Estrategista de e-mail marketing** | Sequências, newsletters, segmentação, entregabilidade. | Lançamento, nutrição de lead | Read/Write, ferramenta de e-mail (API) | msg P | 3 | AA `marketing/marketing-email-strategist.md` + MS `skills/emails` | MIT |
| 51 | **Growth / CRO** | Experimentos de conversão em página, formulário e funil. | Conversão baixa | GA4 (leitura), navegador | ler S · pub P | 2 | AA `marketing/marketing-growth-hacker.md` + MS `skills/cro`, `skills/ab-testing`, `skills/popups` | MIT |
| 52 | **Assessor de imprensa e reputação** | Release, resposta a crise, avaliação no Google. | Crise, lançamento, avaliação ruim | WebSearch, Write | msg P | 4 | AA `marketing/marketing-pr-communications-manager.md` + MS `skills/public-relations` | MIT |

### 2.8 Dados e Análise — 5

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 53 | ★ **Analista de dados de marketing** | Relatório de GA4/Ads/Search Console com o "e daí?" em linguagem simples. | Semanal/mensal por cliente, pergunta "como está o X?" | GA4 Data API, Ads API (leitura) | ler S | 1 | AA `support/support-analytics-reporter.md` + GS `skills/analytics/google-analytics-data-api-basics` + MS `skills/analytics`, `skills/attribution` | MIT / Apache-2.0 |
| 54 | **Estatístico** | Diz se a diferença é real ou ruído (teste A/B, sazonalidade). | Antes de declarar vencedor de teste | Python (pandas) | ler S | 3 | AA `academic/academic-statistician.md` + VA `categories/10-research-analysis/ab-test-analysis.md` | MIT |
| 55 | **Engenheiro de dados** | Junta fontes (Ads, GA4, planilhas, CRM) num lugar só, automatizado. | Relatório que hoje é manual | Python, BigQuery/planilha | pc A | 3 | AA `engineering/engineering-data-engineer.md` + GS `skills/cloud/bigquery-basics` | MIT / Apache-2.0 |
| 56 | **Visualizador de dados** | Gráfico e painel claros (para o dono e para o cliente). | Relatório, painel | Write (HTML/xlsx) | pc A | 2 | AA `engineering/engineering-data-visualization-engineer.md` + CASA `dataviz` | MIT |
| 57 | **Detetive de anomalias** | Vigia métricas e dispara alerta quando algo foge do normal. | Rotina horária/diária | APIs (leitura), alertas | ler S · msg A (só para o dono) | 2 | ZERO (inspirado em AA `testing/testing-test-results-analyzer.md`) | — |

### 2.9 Pesquisa — 4

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 58 | ★ **Pesquisador** | Pesquisa profunda na web com fontes citadas e grau de confiança. | "Pesquisa sobre X", decisão que depende de fato | WebSearch, WebFetch | ler S | 1 | VA `categories/10-research-analysis/research-analyst.md` + `search-specialist.md` + AA `research/research-synthesist.md` | MIT |
| 59 | **Analista de concorrência e mercado** | Mapeia concorrente: anúncios, preços, SEO, posicionamento. | Cliente novo, proposta | WebSearch, navegador | ler S | 2 | VA `categories/10-research-analysis/competitive-analyst.md` + MS `skills/competitor-profiling` | MIT |
| 60 | **Caçador de tendências** | Tendências de busca, social e do setor do cliente. | Planejamento mensal | WebSearch | ler S | 3 | AA `product/product-trend-researcher.md` | MIT |
| 61 | **Pesquisador de evidência em saúde** | Checa afirmação de saúde em fonte confiável antes de virar post/anúncio. | Conteúdo de cliente da saúde | WebSearch (PubMed, SciELO) | ler S | 2 | AA `healthcare/healthcare-clinical-evidence-agent.md` | MIT |

### 2.10 Engenharia de prompt e IA — 5

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 62 | ★ **Engenheiro de prompt** | Escreve e melhora prompts, instruções de agente e de skill. | Agente errando, agente novo | Read/Write | pc A | 1 | AA `engineering/engineering-prompt-engineer.md` | MIT |
| 63 | **Criador de skills e agentes** | Cria skill/agente novo com teste de gatilho. | "Ensina o DERVS a fazer X" | Read/Write, avaliação | pc A | 2 | AS `skills/skill-creator` + SP `writing-skills` | Apache-2.0 / MIT |
| 64 | **Arquiteto multiagente** | Desenha como os agentes conversam, paralelizam e entregam. | Fluxo novo com 3+ agentes | Read | ler S | 2 | AA `engineering/engineering-multi-agent-systems-architect.md` | MIT |
| 65 | **Avaliador de agentes (QA de IA)** | Mede se cada agente acerta: casos de teste, regressão, alucinação. | Mudança de prompt/modelo, semanal | Read, Bash (evals) | ler S | 3 | AA `specialized/specialized-model-qa.md` | MIT |
| 66 | **Bibliotecário da memória** | Organiza memória compartilhada e o cofre de notas; apaga o velho, junta o duplicado. | Fim de tarefa, semanal | Read/Write na memória | pc A · apg P | 2 | AA `specialized/zk-steward.md` + VA `categories/09-meta-orchestration/memory-curator.md` | MIT |

### 2.11 Operações, TI e Servidores — 7

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 67 | ★ **Operador de servidores (SSH/VPS)** | Executa comandos na VPS com plano, alvo conferido e volta-atrás. | Qualquer coisa "no servidor" | SSH (via ponte do DERVS), Bash | ssh-ler A · ssh-mudar P · apg P | 1 | AA `support/support-infrastructure-maintainer.md` + CASA `safety-guard`, `publicar` | MIT |
| 68 | **Publicador (deploy)** | Publica o que está commitado, confere saúde e volta se falhar. | "Põe no ar" | git, SSH, tarefa de deploy | pub P | 1 | AA `engineering/engineering-devops-automator.md` + CASA `publicar` (kit `deploy-padrao` v2) | MIT |
| 69 | **SRE / Vigia de sites** | Uptime, certificado, disco, memória, log de erro; alerta cedo. | Rotina a cada 5–15 min, alerta | HTTP, SSH (leitura), logs | ler S · msg A (dono) | 1 | AA `engineering/engineering-sre.md` + CASA `observabilidade` | MIT |
| 70 | **Comandante de incidente** | Quando algo cai: coordena diagnóstico, comunicação e pós-mortem. | Site fora do ar, erro em massa | tudo de Ops, só leitura até plano aprovado | ssh P · pub P | 2 | AA `engineering/engineering-incident-response-commander.md` | MIT |
| 71 | **Técnico do PC (Windows)** | Cuida do PC do dono: espaço, atualização, programa travado, backup local. | "PC lento", rotina semanal | PowerShell (via `dervs_safety`) | pc P · apg P | 2 | AA `engineering/engineering-it-service-manager.md` + VA `categories/04-quality-security/powershell-security-hardening.md` | MIT |
| 72 | **Rede, DNS e e-mail de domínio** | DNS, HTTPS, SPF/DKIM/DMARC, domínio expirando. | Domínio novo, e-mail caindo no spam | dig/nslookup, painel de DNS (API) | ler S · pub P | 3 | AA `engineering/engineering-network-engineer.md` + CASA `email-transacional` | MIT |
| 73 | **Guardião de backups** | Garante backup do banco/site e **testa a restauração**. | Diário, antes de migration | SSH (leitura), Bash | ssh P | 2 | ZERO | — |

### 2.12 Segurança e Auditoria — 6

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 74 | ★ **Chefe de Segurança** | Revisão de segurança de código e configuração; nega por padrão. | Mudança em login, entrada externa, segredo | Read/Grep | ler S | 1 | AA `security/security-appsec-engineer.md` + CASA agente `security-reviewer` | MIT |
| 75 | **Guardião de segredos** | Acha segredo vazado, conduz rotação e registra **onde** mora (nunca o valor). | Commit novo, suspeita de vazamento | Grep, gitleaks (leitura) | ler S · resto P | 1 | AA `security/security-secrets-credential-engineer.md` | MIT |
| 76 | **Auditor de código gerado por IA** | Procura os defeitos típicos de código escrito por agente (validação ausente, dependência inventada). | Todo PR feito por agente | Read/Grep | ler S | 2 | AA `security/security-ai-generated-code-auditor.md` | MIT |
| 77 | **Auditor de skills e prompt-injection** | Lê **todo** arquivo de skill/agente/MCP de terceiro antes de entrar no cérebro; caça instrução escondida e hook. | Antes de instalar qualquer coisa | Read/Grep (somente leitura) | ler S · pc N | 1 | ZERO + CASA `security-scan` | — |
| 78 | **Auditor de processos (governança)** | Confere se os agentes respeitaram a matriz de autonomia; lê o diário de eventos. | Semanal, após incidente | Read (logs) | ler S | 2 | AA `specialized/automation-governance-architect.md` | MIT |
| 79 | **Resposta a incidente de segurança** | Conter, investigar e relatar invasão/vazamento. | Alerta de segurança | Read, SSH (leitura) | ssh P | 3 | AA `security/security-incident-responder.md` | MIT |

### 2.13 Jurídico e Compliance — 4

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 80 | ★ **Encarregado de dados (DPO / LGPD)** | Garante LGPD; dado de paciente nunca sai do lugar certo. | Qualquer fluxo com dado pessoal/sensível | Read | sens N (só orienta) | 1 | AA `specialized/data-privacy-officer.md` + CASA `healthcare-phi-compliance` | MIT |
| 81 | **Compliance de marketing de saúde** | Barra anúncio/post que fere regra do CFM/CFO/CRP/ANVISA e política do Google/Meta para saúde. | Toda peça de cliente da saúde | Read, WebSearch | ler S | 1 | AA `specialized/healthcare-marketing-compliance.md` + ZERO (regras brasileiras) | MIT |
| 82 | **Revisor de contratos** | Lê contrato/proposta e aponta risco em linguagem simples (não substitui advogado). | Contrato com cliente/fornecedor | Read (pdf/docx) | ler S | 3 | AA `specialized/legal-document-review.md` + VA `categories/08-business-product/legal-advisor.md` | MIT |
| 83 | **Licenças e direitos autorais** | Confere licença de código, imagem, fonte e música; mantém `CREDITOS.md`. | Asset de terceiro, skill nova | Read, WebFetch | ler S | 2 | VA `categories/08-business-product/license-engineer.md` + CASA `midia-livre` | MIT |

### 2.14 Finanças — 3

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 84 | **Controller (contas e faturamento)** | Contas a receber/pagar, cobrança de cliente, conciliação simples. | Mensal, boleto vencendo | planilha, e-mail (leitura) | ler S · $ N (só prepara) · msg P | 3 | AA `finance/finance-bookkeeper-controller.md` + `specialized/accounts-payable-agent.md` | MIT |
| 85 | **Analista de preço e propostas** | Precifica serviço e monta proposta com margem saudável. | Proposta nova | planilha, docx | ler S | 2 | AA `specialized/specialized-pricing-analyst.md` + `sales/sales-proposal-strategist.md` | MIT |
| 86 | **FinOps (custo de IA e servidor)** | Mede quanto cada agente/cliente custa em tokens, API e VPS; propõe corte. | Diário (teto), mensal | `dervs_gasto`, faturas | ler S | 1 | AA `engineering/engineering-finops-engineer.md` | MIT |

### 2.15 Comercial e Atendimento — 3

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 87 | **Atendente (rascunhos de resposta)** | Rascunha resposta a cliente (e-mail/WhatsApp); o dono envia ou aprova. | Mensagem de cliente chegou | e-mail/WhatsApp (leitura) | msg P · sens N | 2 | AA `support/support-support-responder.md` | MIT |
| 88 | **Sucesso do cliente e relatórios** | Relatório mensal ao cliente em linguagem de cliente; alerta de risco de cancelamento. | Fim do mês, cliente sumido | Read, docx/pdf | msg P | 2 | AA `specialized/customer-success-manager.md` + `support/support-executive-summary-generator.md` | MIT |
| 89 | **Prospecção** | Lista de potenciais clientes e rascunho de abordagem (sem disparo em massa). | Meta de novos clientes | WebSearch | ler S · msg P | 4 | AA `sales/sales-outbound-strategist.md` + MS `skills/prospecting`, `skills/cold-email` | MIT |

### 2.16 Pessoal e Secretariado — 3

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 90 | ★ **Secretária executiva** | Agenda, lembretes, triagem de e-mail, resumo do dia. | Manhã/fim do dia, "me lembra de" | Calendar/Gmail (MCP, leitura; escrever = P) | ler S · msg P | 1 | ZERO + AA `project-management/project-management-meeting-notes-specialist.md` | MIT |
| 91 | **Documentos e planilhas** | Gera docx/pdf/xlsx/pptx bonitos e corretos. | "Faz um documento/planilha/apresentação" | AS docx/pdf/xlsx/pptx | pc A | 2 | AS `skills/docx`, `pdf`, `xlsx`, `pptx` (licença restrita: usar, não redistribuir) + AA `specialized/specialized-document-generator.md` | proprietária / MIT |
| 92 | **Tradutor e localizador** | Traduz e adapta (não literal) pt↔en↔es. | Conteúdo/cliente em outro idioma | Read/Write | pc A | 4 | AA `specialized/language-translator.md` | MIT |

### 2.17 Automação de tela (computer-use) — 4

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 93 | ★ **Navegador web** | Opera sites (painéis sem API, formulários, conferência visual) em perfil de navegador **separado**. | Tarefa web sem API | Playwright MCP / browser-use, perfil próprio | tela A (sites da lista) · $ N · msg P | 1 | ZERO + [browser-use](https://github.com/browser-use/browser-use) ou Playwright MCP | MIT / Apache-2.0 |
| 94 | **Operador de janelas Windows** | Clica e digita em programas do Windows por **árvore de acessibilidade** (UIA), não por pixel. | Programa sem API (ex.: PuTTY, Excel desktop) | Windows-MCP (só `Snapshot,Click,Type,App`) ou pywinauto | tela P (A nas janelas da lista) | 2 | ZERO + [CursorTouch/Windows-MCP](https://github.com/CursorTouch/Windows-MCP) / [pywinauto](https://github.com/pywinauto/pywinauto) | MIT / BSD-3 |
| 95 | **Vigia de tela** | Observa uma janela autorizada e avisa mudança (download terminou, erro apareceu). | "Fica de olho no X" | captura de **janela** (PrintWindow) | tela A | 3 | ZERO (já existe a receita de PrintWindow no DERVS) | — |
| 96 | **Guardião de privacidade da tela** | Filtro obrigatório antes de qualquer captura: confere alvo, bloqueia apps de saúde/banco, nunca tela inteira. | Toda chamada de captura | lista de permissão, título/processo da janela | tela N (é o freio) | 1 | ZERO | — |

### 2.18 Qualidade de experiência — 5

| # | Nome | Missão | Quando é chamado | Ferramentas mínimas | Autonomia | Onda | Base | Licença |
|---|---|---|---|---|---|---|---|---|
| 97 | ★ **Super-leigo** | Usuário que não sabe nada: lê a entrega e faz perguntas até entender; tudo que ele não entendeu volta para ajuste. | Toda entrega para o dono ou cliente; texto de tela | Read, navegador (só olhar) | ler S | 1 | ZERO + AA `design/design-persona-walkthrough.md` | MIT |
| 98 | **Crítico / advogado do diabo** | Ataca o plano: o que pode dar errado, o que está fraco. | Decisão grande, antes de gastar | Read | ler S | 2 | AA `specialized/specialized-strategy-duel-agent.md` + VA `categories/10-research-analysis/first-principles-thinking.md` | MIT |
| 99 | **Conselho consultivo** | Painel de 3–5 vozes (cliente, CFO, especialista) que vota e diverge por escrito. | Decisão de produto/estratégia | Agent (convoca) | ler S | 3 | MS `skills/marketing-council` + AA `strategy/nexus-strategy.md` | MIT |
| 100 | **Pesquisador de UX** | Teste de usabilidade simulado e roteiro de entrevista real. | Site/tela nova | navegador | ler S | 3 | AA `design/design-ux-researcher.md` + CASA `ux-research` | MIT |
| 101 | **Revisor de texto pt-BR** | Ortografia, clareza, tom e consistência; mata "cara de IA". | Todo texto que sai para fora | Read | ler S | 1 | CASA agente `conteudo-reviewer` + MS `skills/copy-editing` + WS `plugins/avoid-ai-writing` | MIT |

### 2.19 Contagem e cortes

- **101 linhas numeradas, das quais 9 são "agentes-ferramenta" leves** que podem nascer como
  **skill** em vez de subagente (não ocupam janela própria): #9 Priorizador, #10 Sintetizador,
  #24 Testador de API, #43 SEO programático, #60 Caçador de tendências, #92 Tradutor, #95 Vigia
  de tela, #99 Conselho, #100 Pesquisador de UX. **Subagentes de verdade: 92.**
- **Sem duplicata:** onde duas bases cobriam o mesmo papel, juntei numa linha só (ex.: Copywriter
  junta MS `copywriting` + VA `landing-page-copywriter` + CASA `copy-ptbr`).
- **Fora de propósito** (não incluídos): divisões AA de China (Douyin, WeChat, Baidu…), game,
  blockchain, espacial, GIS, FedRAMP, Salesforce, imobiliário, intercâmbio.
- **Lacunas que nenhuma base cobre e foram criadas do zero:** Super-leigo, Guardião de privacidade
  da tela, Operador de janelas, Navegador web, Auditor de skills, Guardião de backups, Detetive de
  anomalias, Secretária executiva, CMO, Compliance de saúde **brasileiro**.

---

## 3. Orquestração

### 3.1 Rota do pedido

```
Dono fala → DERVS classifica (tipo, departamento, risco, custo estimado)
   ├─ simples e de um setor  → chama o especialista direto
   ├─ um setor, várias peças → chama o ★ chefe do setor (sub-orquestrador)
   └─ vários setores / vago  → Chefe de Gabinete monta o plano → CEO aprova prioridade
                                → chefes executam em paralelo → Líder de QA → Super-leigo → dono
```

- **Roteador barato primeiro:** a classificação usa regra + modelo pequeno (Haiku). Opus só no
  chefe/planejador e em tarefa difícil. Especialista padrão: Sonnet.
- **Chefes como sub-orquestradores:** só os ★ podem chamar outros agentes (`Agent` na lista de
  ferramentas). Especialista **não** chama especialista — evita cascata de custo e loop.
  Profundidade máxima: DERVS → chefe → especialista (**3 níveis**).
- **Portões fixos** em todo fluxo que muda algo: implementar → Revisor/QA → (se texto) Revisor
  pt-BR e Super-leigo → (se saúde) Compliance de saúde + DPO → dono, conforme a matriz.

### 3.2 Paralelismo

| Recurso | Limite sugerido | Por quê |
|---|---|---|
| Agentes simultâneos no total | **4** (assinatura) / 8 (API com orçamento) | limite de uso da assinatura é compartilhado por todas as janelas |
| Por chefe | 3 | chefe precisa ler a volta de cada um |
| Agentes que **mudam** a mesma pasta/projeto | **1** (ou worktree git isolado por agente) | evita sobrescrita |
| Agentes no mesmo servidor | **1** com escrita; leitura livre | ordem de comandos importa |
| Agentes com tela/clique | **1** | só existe um mouse |

### 3.3 Memória compartilhada

- **Três camadas:** (1) *quadro da tarefa* (efêmero, JSON por tarefa: plano, quem pegou, estado,
  artefatos); (2) *memória do cliente/projeto* (durável, um arquivo por cliente: marca, contas,
  regras, decisões); (3) *memória do dono* (preferências e regras globais).
- **Quem escreve:** especialista escreve só no quadro da tarefa; **só o chefe** promove algo para a
  memória durável; o Bibliotecário (#66) consolida semanalmente.
- **Nunca na memória:** segredo, senha, token, dado de paciente. Memória guarda *onde* mora.

### 3.4 Handoffs

Todo agente devolve no mesmo formato curto: `resultado` · `evidência` (comando rodado, link,
arquivo) · `o que não fiz e por quê` · `próximo passo sugerido` · `risco`. O chefe não
repassa a saída inteira para cima — repassa o resumo (é o que mantém o contexto do DERVS barato).

### 3.5 Conflito

1. Regra de segurança/LGPD > pedido de marketing > estética. DPO, Compliance de saúde e Segurança
   têm **veto**; ninguém os contorna, só o dono, e o veto fica registrado.
2. Dois especialistas divergem → chefe decide com justificativa; se for entre setores → CEO; se
   envolve dinheiro, publicação ou cliente → dono.
3. Limite de 3 voltas QA→dev; na 4ª, sobe ao dono com o impasse descrito.

### 3.6 Controle de custo

- **Assinatura (Claude Max/Pro via Agent SDK) vs API:** a assinatura tem custo fixo mas **limite
  de uso por janela de horas, compartilhado** entre o Claude Code do dono e o DERVS — muitos agentes
  em paralelo esgotam a janela e travam *também* o trabalho dele. A API tem custo por token e sem
  esse teto, mas precisa do teto diário do `dervs_gasto`. **Recomendação:** rotina de fundo (vigias,
  relatórios agendados) em Haiku; interativo pela assinatura; tarefas grandes de madrugada.
- Orçamento por tarefa estimado **antes** (o chefe declara "≈ N agentes, modelo X"); acima de um
  limite configurável, pede OK.
- Contexto: especialista recebe só o briefing + arquivos citados, não a conversa inteira.
- FinOps (#86) publica no painel: custo por agente, por cliente e por dia.

### 3.7 Observabilidade (eventos para o painel e para o auditor)

`tarefa.criada` · `tarefa.roteada{depto, agente, modelo}` · `agente.iniciou/terminou{tokens, s, custo}` ·
`ferramenta.chamada{categoria, alvo, nivel_autonomia, decisao}` · `cartao.pedido/aprovado/negado` ·
`veto{quem, motivo}` · `qa.reprovou{volta}` · `tela.captura{janela, processo, permitido}` ·
`custo.teto_alcancado` · `erro{agente, tipo}`. Diário em JSONL local, rotação diária, **sem**
conteúdo sensível (só metadados). O Auditor de processos (#78) lê isso semanalmente.

---

## 4. Matriz de autonomia

### 4.1 Categorias × níveis — padrão recomendado (▶)

| Categoria | Faz sozinho | Faz e avisa | Pede OK | Nunca | Teto duro |
|---|---|---|---|---|---|
| **Ler** (arquivos, APIs em leitura, web) | ▶ | | | | — |
| **Mudar o PC** (criar/editar arquivo em pasta de projeto, abrir programa, instalar) | | ▶ (só dentro das pastas de projeto) | instalar, fora de projeto | | — |
| **Apagar** | | | ▶ (vai para a lixeira segura) | | nunca "sozinho" |
| **Servidor/SSH — ler** (status, log, disco) | | ▶ | | | — |
| **Servidor/SSH — mudar** | | | ▶ | | nunca "sozinho" |
| **Publicar/deploy** | | | ▶ | | nunca "sozinho" em produção |
| **Mensagem externa** (e-mail, WhatsApp, post, comentário) | | rascunho ▶ | ▶ envio | | nunca "sozinho" para terceiro |
| **Dinheiro/anúncios** (verba, lance, ativar campanha, compra) | | negativa de palavra, pausar anúncio reprovado | ▶ | compra/pagamento | nunca "sozinho" acima de R$ 0 de gasto novo |
| **Dados sensíveis/pacientes** | | | | ▶ | nunca mandar a API externa; só o dono abre |
| **Tela — ver/clicar** | janela que o DERVS abriu | ▶ janelas da lista de permissão | outra janela | tela inteira, apps bloqueados | nunca tela inteira por padrão |

### 4.2 Como encaixa no que já existe

- **`dervs_safety`** é o *teto técnico*: classifica o comando em `reversivel` / `muda_estado` /
  `destrutivo` e só **sobe** o risco. Continua igual e roda **antes** de tudo. Todo agente que
  executa comando passa por ele — sem exceção para "agente de confiança".
- **`dervs_permissoes`** é a *escolha do dono dentro do teto*: hoje 8 categorias (`ler`, `abrir`,
  `instalar`, `alterar_projeto`, `apagar`, `internet`, `servidor`, `gastar_api`) × 3 níveis
  (`analisa` < `pergunta` < `sozinho`), com `apagar` e `servidor` limitados a `pergunta` e
  "sozinho" como **lista positiva** (`_reconhecida_por_inteiro`).
- **Proposta de evolução (sem quebrar o que existe):**
  1. 4 níveis = `nunca` (= `analisa`: só olha) < `pergunta` < **`avisa`** (novo: executa e manda
     cartão informativo no painel + evento) < `sozinho`. `avisa` herda a regra de lista positiva
     do `sozinho` — o que não for reconhecido por inteiro continua indo ao cartão.
  2. Categorias novas: `servidor_ler` (separada de `servidor`, aceita `avisa`), `publicar`,
     `mensagem_externa`, `anuncios` (aceita só `nunca`/`pergunta`, mais exceções da lista positiva
     "negativar palavra", "pausar anúncio reprovado"), `dados_sensiveis` (só `nunca`), `tela`.
     `abrir` + `instalar` + `alterar_projeto` ficam como estão (são o "mudar o PC").
  3. **Matriz por agente:** cada agente declara a categoria máxima que precisa; o efetivo é o
     **mínimo** entre (teto do `dervs_safety`, escolha do dono na categoria, teto do agente).
     Ex.: o Revisor de código tem teto `ler`; mesmo que o dono libere `alterar_projeto: sozinho`,
     ele não escreve.
  4. Permissão **por cliente/projeto** opcional (ex.: conta Google Ads do cliente X com `pergunta`;
     projeto pessoal com `avisa`).

### 4.3 Padrão recomendado de fábrica

Ler **S**; mudar PC dentro de projeto **A**; instalar **P**; apagar **P**; SSH ler **A**;
SSH mudar **P**; publicar **P**; mensagem externa **P** (rascunho **A**); anúncios **P** (com as
duas exceções em **A**); dados sensíveis **N**; tela **A** só na lista de permissão.

---

## 5. Skills e repositórios para o cérebro do DERVS

### 5.1 Lista ranqueada

| # | Nome | URL | Licença | O que acrescenta | Risco | Quem usa |
|---|---|---|---|---|---|---|
| 1 | **agency-agents** (só os ~75 arquivos citados acima) | github.com/msitarzewski/agency-agents | MIT | personas prontas de quase todos os departamentos | baixo (só markdown); viés EUA, inglês | quase todos |
| 2 | **marketingskills** (seleção de ~20 skills) | github.com/coreyhaines31/marketingskills | MIT | CRO, copy, SEO audit, schema, ads, analytics, social, e-mail, conselho | **médio**: pasta `tools/clis` com CLIs que chamam serviços externos — **não instalar `tools/`**, só `skills/*/SKILL.md` | Marketing, Dados, Conselho |
| 3 | **google/skills — ads + analytics** | github.com/google/skills (`skills/ads/google-ads-api-*`, `data-manager-api-*`, `skills/analytics/*`) | Apache-2.0 | jeito oficial de usar Google Ads API, MCP do Google Ads, GA4 Admin/Data API | baixo; exige credencial OAuth (fica no cofre do DERVS, nunca na skill) | Google Ads, Rastreamento, Analista |
| 4 | **anthropics/skills** (`skill-creator`, `mcp-builder`, `frontend-design`, `webapp-testing`, `brand-guidelines`, `canvas-design`) | github.com/anthropics/skills | Apache-2.0 | criar skill, criar MCP, design web, teste de página | baixo | IA, Engenharia, Design |
| 5 | **anthropics/skills** `docx/pdf/xlsx/pptx` | idem | **proprietária** (usar, não redistribuir) | documentos de verdade | baixo; não copiar para repositório público | Documentos |
| 6 | **Meta Ads MCP oficial** | `mcp.facebook.com/ads` (beta, 29/04/2026) | termos da Meta | ler e mexer em campanhas Meta | **alto** (escopo financeiro): conceder só leitura no início | Meta Ads |
| 7 | **obra/superpowers** (seleção) | github.com/obra/superpowers | MIT | disciplina de engenharia: debug sistemático, verificação, plano | médio: **tem hooks** (`session-start`) — copiar só `SKILL.md` | Engenharia, QA |
| 8 | **addyosmani/agent-skills** (seleção) | github.com/addyosmani/agent-skills | MIT | spec, TDD, segurança, observabilidade, lançamento | médio: **tem hooks** (`sdd-cache-*.sh`) — só `SKILL.md` | Engenharia, Ops |
| 9 | **VoltAgent subagents** (pesquisa, jurídico, licenças) | github.com/VoltAgent/awesome-claude-code-subagents | MIT | complementa onde o AA é fraco (pesquisa, legal) | baixo | Pesquisa, Jurídico |
| 10 | **wshobson/agents** (`avoid-ai-writing`, `seo-*`, `social-publishing`) | github.com/wshobson/agents | MIT | anti-"cara de IA", SEO | médio: plugins com **hooks** (`protect-mcp`, `review-agent-governance`) — nunca instalar como plugin, só copiar texto | Copy, Ghostwriter, SEO |
| 11 | **Windows-MCP** | github.com/CursorTouch/Windows-MCP | MIT | clique/digitação por UIA no Windows | **alto**: traz `PowerShell`, `Registry`, `Screenshot` de tela inteira — subir com `--tools` restrito | Operador de janelas |
| 12 | **browser-use** ou **Playwright MCP** | github.com/browser-use/browser-use | MIT | navegador autônomo | médio: prompt-injection por página | Navegador web |
| 13 | **microsoft/UFO** | github.com/microsoft/UFO | MIT | agente de Windows completo (UIA + visão) | alto e pesado; **só referência**, não instalar | — |

### 5.2 Checklist de vetting (obrigatório por item)

1. **Ler todo arquivo** que entra (não só o `SKILL.md`): scripts, referências, assets. Se não leu, não instala.
2. Rodar o **Auditor de skills (#77)** / skill `security-scan`: instrução escondida, texto em base64,
   URL de exfiltração, "ignore as instruções", comandos de rede, unicode invisível.
3. **Nunca copiar** `hooks/`, `settings.json`, `.mcp.json`, `.claude-plugin/` nem CLIs de terceiro.
   Copiar texto de skill/agente, não instalar o plugin.
4. **Remover o campo `tools:`** do frontmatter de terceiro; a ferramenta é atribuída pelo DERVS conforme a matriz.
5. Fixar **commit SHA** de origem; nada de "puxar a última" automática.
6. Traduzir/adaptar para pt-BR e contexto do dono (LGPD, CFM, R$, Google Brasil).
7. Registrar em `%APPDATA%\dervs\cerebro\CREDITOS.md`: repo, caminho, SHA, licença, data, o que foi alterado.
   Manter o texto da licença MIT/Apache junto (Apache exige o `NOTICE` se houver).
8. Teste de gatilho (avaliação) antes de ligar: o pedido certo chama o agente certo?
9. Medir custo fixo (descrições de skills entram em toda chamada) e anotar no painel.

---

## 6. Computer-use no Windows

**Abordagem recomendada, em camadas (da mais segura à mais arriscada):**

1. **API primeiro.** Se existe API/MCP (Google Ads, GA4, Meta, Search Console, GitHub), o agente usa
   a API e **não olha a tela**.
2. **Navegador isolado.** Para web sem API: Playwright MCP ou browser-use num **perfil próprio do
   DERVS** (não o Chrome do dono com as senhas dele), com lista de domínios permitidos.
3. **Árvore de acessibilidade (UIA), não pixel.** Para programa Windows: pywinauto ou Windows-MCP
   restrito a `Snapshot, Click, Type, App` (`windows-mcp serve --tools ...`; **excluir**
   `PowerShell`, `Registry`, `Screenshot`). UIA lê nomes de botões e campos — texto, não imagem.
4. **Imagem só de janela.** Quando precisar ver, captura **da janela-alvo** por `PrintWindow`
   (receita que o DERVS já usa), nunca da tela inteira.
5. **Computer use da Anthropic** (desktop Claude Code/Cowork no Windows, prévia desde abril/2026;
   ferramenta `computer` na API) — só como último recurso e só dentro de uma **área isolada**
   (máquina virtual/Windows Sandbox), porque ela trabalha com captura de tela inteira.

**Guarda de privacidade (o Guardião #96 é obrigatório no caminho de toda captura):**

- Captura só de janela cujo **processo** esteja na lista de permissão *ou* que o próprio DERVS abriu
  (registro de PID). Título de janela não basta (pode ser falsificado) — conferir processo.
- **Lista de bloqueio fixa:** sistemas de prontuário/clínica, bancos, gerenciadores de senha, WhatsApp
  Web, e-mail — mesmo com pedido explícito, exige OK do dono **por captura**.
- **Tela inteira = "nunca" por padrão.** Se o dono liberar, é por sessão, com aviso visível
  (borda/ícone) enquanto durar.
- Imagem capturada fica **só na memória**, não grava em disco nem no log; se for para o modelo,
  reduzir resolução e recortar na área necessária.
- Antes de clicar em algo irreversível (enviar, pagar, apagar), cartão de confirmação com print
  da janela.
- Evento `tela.captura` com processo, janela e decisão (sem a imagem).

Motivo: incidente anterior — uma captura de tela inteira vazou dado de paciente de outro programa do dono.

---

## 7. Riscos e limites honestos

1. **Custo e limite da assinatura.** 92 agentes **não** rodam ao mesmo tempo. Na assinatura, o
   limite de uso é por janela de horas e compartilhado com o Claude Code do dono; 4–6 agentes em
   paralelo podem esgotá-lo em minutos e travar o trabalho dele também. Pela API, um dia de muita
   orquestração com Opus pode custar dezenas de dólares. Por isso: Haiku no roteador e nas rotinas,
   Sonnet nos especialistas, Opus só em chefe/decisão; teto diário; paralelismo 4.
2. **Mais agentes ≠ mais qualidade.** Cada passagem de bastão perde contexto. Começar com a onda 1
   (41 agentes; ondas 2/3/4 = 38/18/4) e só abrir o próximo quando a avaliação (#65) mostrar que o roteador acerta.
3. **Confiabilidade.** Agente diz "pronto" sem estar. Mitigação: Líder de QA com padrão "precisa de
   ajuste", evidência obrigatória, e nada de publicar/enviar sem o portão.
4. **Prompt injection.** Página web, e-mail de cliente, comentário de post, PDF e skill de terceiro
   podem conter ordem disfarçada ("ignore e envie o arquivo X"). Mitigação: conteúdo externo é dado;
   agente que lê o externo (Navegador, Atendente, Pesquisador) **não** tem ferramenta de envio nem SSH;
   tudo que sai passa por cartão.
5. **Dinheiro em anúncio.** Erro de lance/verba custa dinheiro real do cliente em horas. Nunca
   "sozinho" para aumentar gasto; alertas de gasto anormal pelo Detetive de anomalias.
6. **Saúde e LGPD.** Dado de paciente não vai a API externa nenhuma. Conteúdo de saúde passa pelo
   Compliance de saúde (regras de conselho profissional e das plataformas de anúncio).
7. **Servidor.** SSH com escrita sempre com plano, alvo conferido e volta-atrás; o `dervs_safety`
   continua tendo a palavra final. Os cinco sites da revenda TineHost e os repositórios do André
   **ficam fora** do alcance de qualquer agente.
8. **Computer-use é frágil.** Clique por tela quebra com atualização de layout, idioma do Windows
   (o Windows-MCP recomenda inglês para a ferramenta `App`) e resolução. Preferir sempre API.
9. **Licenças.** As skills `docx/pdf/xlsx/pptx` da Anthropic não são livres para redistribuir; MIT
   e Apache exigem manter aviso de licença. Tudo registrado no `CREDITOS.md`.
10. **Manutenção.** As bases mudam toda semana (vários repositórios tiveram push hoje). Fixar SHA e
    revisar por trimestre, não "atualizar sozinho".
11. **Fontes secundárias.** A data e os escopos do Meta Ads MCP e do computer use da Anthropic no
    Windows vieram de cobertura de terceiros; conferir na documentação oficial antes de implementar.

### Fontes externas consultadas

- [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents), [google/skills](https://github.com/google/skills),
  [anthropics/skills](https://github.com/anthropics/skills), [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills),
  [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents), [wshobson/agents](https://github.com/wshobson/agents),
  [obra/superpowers](https://github.com/obra/superpowers), [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills),
  [CursorTouch/Windows-MCP](https://github.com/CursorTouch/Windows-MCP), [browser-use](https://github.com/browser-use/browser-use),
  [pywinauto](https://github.com/pywinauto/pywinauto), [microsoft/UFO](https://github.com/microsoft/UFO)
- Meta Ads MCP: [mcp.directory](https://mcp.directory/blog/meta-ads-cli-mcp), [adsuploader](https://adsuploader.com/blog/meta-ads-mcp)
- Computer use no Windows: [letsdatascience](https://letsdatascience.com/news/anthropic-adds-computer-use-to-windows-apps-40c5c1ad), [inventivehq](https://inventivehq.com/blog/claude-computer-use-guide)
