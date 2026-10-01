# Arquitetura da plataforma DERVS — proposta para revisão

Estado: **rascunho de 01/10/2026, já revisado pela `dervs-2a` (ver seção 6)**, falta a aprovação do dono. Nada aqui foi implementado nem instalado.
Contrato de mensagens entre as duas pontas: `contrato-ponte.md` (este documento não o substitui).

## 1. Três lugares

| Lugar | Mora lá | Por quê |
|---|---|---|
| **PC de cada pessoa** (instalador `.exe`) | DERVS VOZ, Claude Code, Codex, terminal SSH | usam o **login pessoal** de quem está ali; precisam de microfone, tela e arquivos locais |
| **VPS OVH** (dono: janela DERVS web) | DERVS web (contas, painel, fila), Hermes, estúdio (Bolt.diy), "porteiro" do JEV | ficam ligados 24 h, são compartilhados, guardam as chaves |
| **Serviços de fora** | JEV (TypeSafe), OpenAI, Anthropic API | pagos por uso, só por chave de API |

O VOZ **não** pode ser só web (microfone, atalho global, widget, Claude Code local). O DERVS web
**não** pode ser só local (André e outros precisam de conta e painel compartilhado).

## 2. Regras que valem para as duas janelas

1. **Chave nunca vai dentro do `.exe`.** Quem instala consegue extrair. Chaves (JEV, OpenAI,
   Anthropic API) ficam só na VPS; o VOZ pede ao servidor. Hoje o VOZ lê `TYPESAFE_API_KEY` do PC do
   dono — serve para um, não para vários. Migrar para "porteiro" na VPS antes de distribuir.
2. **Assinatura pessoal não atende terceiros.** Claude Code (Max) e Codex (ChatGPT) usam o login de
   quem está no PC; cada pessoa usa o seu. Um servidor que atendesse outras pessoas com a assinatura
   do dono tende a violar os termos — **conferir nos termos de cada um antes de depender disso.**
   O servidor usa **chave de API** (paga por uso), p.ex. créditos OpenAI do dono.
3. **Todo serviço na VPS fica atrás de login.** Estúdio ou Hermes aberto na internet = qualquer
   um gasta as chaves do dono.
4. **Ponte só de saída** (como já é): o PC fala com o servidor; o servidor nunca abre porta no PC.
5. **Texto de terceiro é dado, nunca instrução** (resumo de alerta, saída de ferramenta). A barreira
   real é o "Pode fazer" do dono.
6. **Cada janela mexe só no próprio repositório.** VOZ → `dervs-voz`; DERVS web → `dervs`. O que
   cruza passa pelo contrato escrito. A VPS só muda pelo deploy do dono, montado pela janela web.
7. **Dado de paciente/pagamento: nenhum serviço novo da VPS toca nele.** Serviços novos em
   contêiner separado, sem acesso ao banco nem ao `.env` de produção.

## 3. Cada componente

- **DERVS VOZ (.exe).** Hoje roda da pasta do projeto (venv + Electron); **instalador não existe**.
  Empacotar é uma etapa própria (assinatura, atualização automática, instalação sem Python
  solto). Embute só o VOZ; **não** embute Hermes, Bolt.diy nem chaves.
- **Pareamento.** Quem instala entra com a conta em dervs.com.br e pareia o PC (crachá por máquina,
  revogável). A conta decide o que o VOZ enxerga: painel, estúdio, Hermes.
- **JEV.** Só triagem (mede urgência); regra fixa decide o que age sozinho. Chave na VPS; o VOZ
  chama o porteiro, não a TypeSafe direto. Provado em 01/10 com a chave do dono: urgência 0,76
  ("disco em 95%") e 0,07 ("tudo ok").
- **Hermes.** (o web não tem permissão por conta para ele: seria funcionalidade nova, ver seção 6.) Pede Linux e fica ligado: encaixa na VPS (Ubuntu/Debian), em contêiner, sem
  acesso a produção. No PC do dono só há o Linux interno do Docker, sem terminal; instalar
  distro WSL foi barrado pelo classificador do Claude Code (não contornado). Só vira cérebro do
  VOZ depois de contrato (comando não interativo, pasta, permissões, saída como dado) e revisão
  de segurança.
- **Estúdio (Bolt.diy).** MIT, ativo; roda com Node/pnpm ou Docker; aceita Claude/OpenAI/Ollama por
  **chave de API** (não aceita o plano Max). Na VPS, em contêiner, atrás de login. Ressalva: o
  motor interno (WebContainers) exige licença comercial para uso com fins lucrativos — checar antes
  de abrir para terceiros. No VOZ entra só como link/abrir.
- **Terminal SSH (VOZ).** Chave de quem está no PC, lista de hosts fixa, clique para o que muda
  estado, log. Já existe. Não é caminho para terceiros chegarem à VPS do dono.

## 4. Perguntas em aberto (para o dono e para a `dervs-2a`)

1. **Tamanho da VPS** (RAM, CPU, disco) e o que já roda: aguenta Hermes + estúdio sem prejudicar
   o DERVS web e o grimoire? (a `dervs-2a` sabe; o VOZ não tem acesso.)
2. **Quem usa o quê:** o André usa as mesmas contas/serviços ou tem os dele? Outros públicos?
3. **Quem paga as chaves de API** quando terceiros usarem; limite por usuário (o gasto do dia já
   aparece no painel do VOZ).
4. **Onde mora o porteiro do JEV:** rota nova no DERVS web (ex.: `/agente/voz/triagem`) ou
   serviço próprio? Proposta do VOZ: rota no DERVS web, com cota por conta.
5. **Ordem:** (a) porteiro do JEV; (b) estúdio na VPS; (c) Hermes na VPS; (d) instalador do VOZ.
   O VOZ sugere esta ordem porque (d) depende de (a) para não carregar chave.

## 5. O que o VOZ NÃO fará sem alinhamento

Instalar nada na VPS, conectar nela, alterar rota ou esquema do painel, ou usar o token de
produção (vazou em 30/09; precisa ser removido e pareado de novo pelo dono).

## 6. Revisão da `dervs-2a` (DERVS web, 01/10) — correções e decisões

**Correções ao texto acima**
- O web **não tem** conceito de estúdio nem permissão por conta para Hermes: "a conta decide o que o
  VOZ enxerga" é funcionalidade **nova**, não algo que já existe.
- Deploy é pela tarefa "Deploy para a VPS" do VS Code (sem GitHub Actions desde 25/09). Existe um
  **Claude Code dentro da VPS**, não mencionado acima.
- Rotas de máquina do VOZ: **4** (estado, recados, resultado, pedido); do dono: **2** (`GET /api/voz`,
  `POST /api/voz/recado`).
- A medição da VPS é de **26/08** (8 vCPU, 24 GB RAM, 193 GB disco, 26 contêineres de 8 sistemas,
  disco a 67%). **Não há medição de hoje**: não dá para afirmar que aguenta Hermes e estúdio.

**Porteiro do JEV — `POST /agente/voz/triagem` (cabe como rota nova)**
- Pedido: `{"versao":1,"pergunta":"urgente","texto":"<=500 caracteres","tipo":"score"}`; `pergunta`
  em lista fechada; campo extra = 400.
- Resposta 200: `{"ok":true,"versao":1,"urgencia":0.76,"rotulo":"alta"}`. Erros: 400, 401, 429,
  503 `{"erro":"triagem indisponivel"}`. Falha fechada: se a TypeSafe falhar, "indisponível", nunca "ok";
  nunca repete erro cru da TypeSafe.
- Segurança: token de máquina pareada; balcão próprio (não empresta o teto de outra rota); URL da
  TypeSafe fixa no código; a chave só no servidor, com nome `DERVS_TYPESAFE_KEY` (a guarda
  `test_publicar` só enxerga `DERVS_*`), linha no compose e no `.env` do servidor, gravado à mão
  pelo administrador.
- Limite: o balcão é por janela de 15 min e **em memória** (zera ao reiniciar); **não é cota de
  gasto**. Cota diária por conta exige tabela nova: **decisão do dono**.
- Dependência: o porteiro só funciona **depois de um deploy que leve a ponte junto**.

**Ordem e atrito.** A ordem proposta não conflita. A Fase 2 da `dervs-2a` está só local, em ramo; os
dois mexem em `servir.py` e no `Dockerfile`, então o porteiro vem **depois do merge da Fase 2** (ou
em ramo próprio).

**Estúdio e Hermes na VPS (condições)**: antes, o dono mede RAM/CPU/disco hoje
(`docker stats`, `free -m`, `df -h`); `mem_limit` e `pids_limit` nos dois, como no compose do DERVS;
rede própria; **sem `docker.sock`** (o usuário do dono na VPS tem grupo docker, na prática root);
chave de API com **teto de gasto no provedor**.

**Pré-requisito de segurança:** revogar o token de produção que vazou em 30/09 e parear a máquina de
novo (a rota de revogar existe) — antes de abrir o porteiro.

**Esclarecido (dervs-2a, 01/10):** as rotas `/agente/voz/*` **estão em produção** (publicadas em 01/10;
401 sem credencial, rota inventada 404). Parear o token de novo **não exige deploy**; o deploy só
é necessário para o porteiro `/agente/voz/triagem`, depois da Fase 2 dela.
