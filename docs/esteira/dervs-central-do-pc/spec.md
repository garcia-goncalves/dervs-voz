# SPEC — dervs-central-do-pc

Fase 2 (descoberta, modo enxuto), 29/09/2026. Fonte da verdade do escopo:
`docs/esteira/dervs-central-do-pc/briefing.md` (aprovado). Este documento responde
às quatro lentes (DX, Claude Code real, motor de aprovação + Central do PC, harness +
instalador) e decide; o que depende de dinheiro ou de produto está em
`duvidas_para_o_dono`, sempre com recomendação.

## problema

Hoje o DERVS tem **duas janelas** (widget 420×700 sempre por cima + painel grande
1280×800) e o dono quer uma só. O cérebro que roda o `claude` é um **planejador
isolado** (`--setting-sources ""`, sem MCP, sem ferramentas) — não é "o mesmo Claude
do VS Code"; e, no Windows, a sessão contínua dele **nunca funciona**: `select.select`
num cano (pipe) levanta `OSError [WinError 10093]` (provado nesta fase com o Python do
`dervs-venv`), então todo turno cai silenciosamente no modo antigo de um processo por
frase (~10 s). Não existe caixa de texto no painel, nem streaming, nem MCP (Playwright),
nem Central do PC, nem um motor que obrigue "analisar → explicar item a item → aprovar
→ executar → registrar → desfazer". A trava atual (`dervs_safety.py`) classifica **um
comando de texto**; ela não sabe o que é o arquivo, quanto pesa, nem guarda prova de
aprovação. Por fim, o DERVS só roda nesta máquina: não há harness versionado (depende
do `~/.claude` pessoal do dono) nem instalador para sócios e funcionários.

## solucao

Seis ondas (A–F), cada uma testada e enviada ao GitHub antes da próxima. A ideia
central de segurança: **o Claude analisa e propõe; quem executa ação destrutiva é
código do DERVS, e só com aprovação registrada item a item, feita por clique.** O
Claude Code ganha leitura ampla da máquina, mas não ganha a mão que apaga.

### Onda A — painel único com bandeja (lente Analista/DX)

**O que existe hoje** (`electron/main.js`):
- `criarJanela()` (widget, `index.html` + `hud.js`, `alwaysOnTop` nível
  "screen-saver", minimizar é desfeito na hora) e `criarPainel()` (painel,
  `painel.html` + `painel.js`, criado sob demanda, fechar esconde, minimizar também é
  desfeito).
- Atalhos: `ATALHO_GLOBAL = "Control+Alt+D"` → `alternarPainel`;
  `ATALHO_WIDGET = "Control+Alt+Shift+D"` → `alternarJanela`.
- Bandeja `montarBandeja()`: menu "Abrir painel grande / Abrir DERVS (widget) /
  Recolher janela / Sair do DERVS"; clique no ícone abre o **widget**.
- O verbo `mostrar` (Python → Electron) chama `mostrarJanela()` (widget), e o verbo
  `plano` traz o **widget** de volta porque o cartão de confirmação só existe nele.
- `painel.js` **não** usa `aoPlano`, `responderPlano`, `alternarReuniao`,
  `abrirAppDervs` (contagem de `window.dervs.*` feita nesta fase); o widget usa. Ou
  seja: tirar o widget sem portar esses quatro quebra a confirmação de planos.

**Menor caminho (decidido):**
1. Portar para o painel o **cartão de plano** (passos, nível, comando, caixa
   "tenho autorização", dupla confirmação, `cartaoId`), o botão **reunião 1h** e o
   **Abrir DERVS App**. O cartão vira um diálogo modal dentro do painel (`<dialog>`),
   com texto só por `textContent` (regra já provada em §3.9 do `ESTADO.md`).
2. `main.js`: `app.whenReady` cria o **painel** (não o widget); `mostrar` e `plano`
   passam a chamar `mostrarPainel()`; apagar `criarJanela`, `alternarJanela`,
   `recolherJanela`, `ATALHO_WIDGET`, `widgetEstavaVisivel` e o ramo do plano que
   reexibe o widget. `Ctrl+Alt+D` alterna o painel. Bandeja: menu "Abrir DERVS /
   Sair do DERVS"; clique simples alterna o painel.
3. Botões da barra: **minimizar** (minimiza de verdade, vai para a barra de tarefas —
   remover o `restore()` automático do painel, que só fazia sentido no widget sem
   moldura), **diminuir/restaurar** (o `ampliarPainel` que já existe, renomeado no
   texto da tela) e **fechar** (esconde na bandeja; `app.isQuitting` continua sendo o
   único caminho de sair). Novo verbo IPC `dervs:painel-minimizar`.
4. Extrair a lógica de abrir/esconder/minimizar para `electron/janela-estado.js`
   (função pura: estado + evento → ação), testada em Node como já se faz com
   `painel-formato.test.js`. É o "teste da lógica de abrir/esconder" do critério 1.
5. Apagar `electron/renderer/index.html` e `hud.js`. **Manter** `estilo.css`
   (o `painel.html` o importa na linha 10).
6. Mover o `userData` do Electron para `%APPDATA%\dervs\electron`
   (`app.setPath("userData", …)` antes do `ready`): hoje o cache do Chromium está
   misturado com `config.json` e `lembretes.json` em `%APPDATA%\dervs`, o que
   atrapalha a desinstalação "manter meus dados" da onda F.

**Arquivos afetados:** `electron/main.js`, `electron/preload.js` (sai
`alternarPainel` do widget; entra `painelMinimizar`), `electron/renderer/painel.html`,
`painel.js`, `painel.css`, novos `janela-estado.js` + `janela-estado.test.js`;
`dervs_ponte_electron.py` (cabeçalho: `mostrar` agora significa painel);
docs `README.md` (linhas 20 e 138–140), `COMO-USAR.md` (225–227, 287–288), `ESTADO.md`.
**Testes afetados:** `test_dervs_electron_entrada.py` (os asserts de `mostrar`
continuam válidos; só muda quem obedece), `test_dervs_ponte_electron.py`,
`test_dervs_painel_js.py` (passa a rodar também `janela-estado.test.js`). Nenhum teste
Python referencia `index.html`/`hud.js` (varrido nesta fase).

### Onda B — o Claude Code de verdade dentro do DERVS (lente Arquiteto 1)

**O que o CLI instalado aceita** (`claude --help`, versão 2.1.284, lido nesta fase):
`-p`, `--input-format stream-json`, `--output-format stream-json`,
`--include-partial-messages`, `--permission-mode`
(`acceptEdits|auto|bypassPermissions|manual|dontAsk|plan`),
`--permission-prompts host|none`, `--allowedTools`, `--disallowedTools`, `--tools`,
`--mcp-config`, `--strict-mcp-config`, `--settings`, `--setting-sources`,
`--add-dir`, `--agents`, `--plugin-dir`, `--resume`, `--session-id`,
`--max-budget-usd`, `--include-hook-events`, `--restricted`, `--bare` (atenção: o
`--bare` **não lê OAuth** — exige chave de API, então é proibido aqui).

**Duas peças distintas, de propósito:**
1. **Planejador de voz** (`dervs_brain.py`, `cerebro: "claude"`) — continua isolado
   (`--setting-sources ""`), porque isso foi medido: com o `~/.claude` inteiro eram
   ~40 mil tokens por frase e o JSON quebrava. Correção obrigatória: trocar o
   `select.select` de `_Sessao._ler_resultado` por uma **thread leitora + `queue.Queue`
   com `get(timeout=)`**, que funciona em cano no Windows. Teste novo que roda sem
   `claude` real (processo falso que cospe stream-json) e prova que o segundo turno
   **não** reinicia o processo. Também remover o fallback de caminho Linux
   `~/.local/bin/claude` e resolver `claude.cmd`/`claude.exe` por `shutil.which`.
2. **Sessão Claude Code** (módulo novo `dervs_claude_code.py`) — é "o mesmo Claude":
   carrega `~/.claude` (CLAUDE.md, skills, agentes, MCPs, plugins), pela **assinatura
   do dono** (OAuth já logado no CLI; nenhuma chave de API). Usa o SDK oficial em
   Python, **`claude-agent-sdk`** (versão travada no `requirements.txt`, `cli_path`
   apontando para o `claude` instalado), com `ClaudeSDKClient` numa thread própria com
   laço asyncio. Motivo de usar o SDK e não escrever o protocolo à mão: ele já fala o
   protocolo de controle do stream-json (pedido de permissão `can_use_tool`,
   `interrupt`, `set_permission_mode`, ganchos em processo), que é justamente a parte
   perigosa de errar.

**Configuração da sessão (decidida):**
- `permission_mode="default"` e **nunca** `bypassPermissions`, `acceptEdits` ou
  `auto` — constante no código, com teste que falha se alguém trocar.
  `--permission-prompts host`: todo pedido que não for resolvido por regra chega ao
  DERVS.
- `setting_sources=["user", "project", "local"]` no **perfil dono**;
  `["project"]` no **perfil equipe** (onda E) — assim as regras do harness valem
  iguais em qualquer PC.
- `cwd` = pasta do harness do DERVS (onda E) — é ela que traz o `CLAUDE.md` e o
  `.claude/settings.json` do DERVS como "projeto".
- `add_dirs=[unidade C:\ inteira]` para **leitura** (o critério "acesso à máquina
  inteira"); escrita e exclusão fora do harness passam pelo motor da onda C.
- `include_partial_messages=True` → streaming palavra a palavra na tela.
- Gancho **`PreToolUse` em processo** (callback Python do SDK) que chama
  `dervs_safety.decidir_risco` + a lista de caminhos protegidos (onda C) em todo
  `Bash`/`PowerShell`/`Edit`/`Write`. Ganchos rodam **antes** de qualquer regra e o
  "negar" deles vale até em `bypassPermissions` (documentação oficial, fontes).
  Destrutivo → nega com a mensagem "use a ferramenta `dervs__propor_acao`".
- Servidor MCP **em processo** `dervs` (via `create_sdk_mcp_server`) com as
  ferramentas: `central_coletar(<coletor>)` (só leitura), `propor_acao(itens)`
  (cria um relatório da onda C e mostra no painel; **não executa**),
  `status_aprovacao(relatorio_id)`. Não existe ferramenta "executar": executar é
  clique do dono no painel.
- Sessão contínua: guarda o `session_id` em `%LOCALAPPDATA%\dervs\claude_sessao.json`;
  botão "Nova conversa" zera; ao reabrir o app, `resume`.
- Cancelar: botão "Parar" e a palavra "para" por voz → `client.interrupt()`; se não
  obedecer em 5 s, `dervs_processos.encerrar_arvore` (padrão já provado na §3.3).
- Custo/limite: o `ResultMessage` traz custo equivalente e uso; grava em
  `dervs_gasto.py` com a etiqueta "assinatura (equivalente)" — não é cobrança, é
  medida. Eventos de limite de uso da assinatura viram aviso no painel e em voz
  ("atingi o limite do plano, volta às HH:MM").

**Aprovações do Claude → motor do DERVS:** o callback `can_use_tool(nome, entrada,
contexto)` monta um pedido `{id, ferramenta, resumo, entrada_cortada, nivel}` (nível
vindo de `dervs_safety`), manda ao painel pelo verbo novo `claude_pedido`, e espera a
resposta `claude_resposta {id, permitir, cartaoId}` (mesmo padrão anti-duplicação do
`cartao_id` atual). Sem resposta em 5 min → nega. Voz **nunca** aprova pedido de
nível `muda_estado` ou `destrutivo` (coerente com `test_dervs_voz_nao_e_senha.py`).

**Verbos novos da ponte** (`dervs_ponte_electron.py` + `main.js` + `preload.js`):
Python → Electron: `claude_delta {texto}`, `claude_ferramenta {nome, resumo}`,
`claude_pedido {…}`, `claude_fim {ok, custo, erro}`. Electron → Python:
`claude_perguntar {texto}` (caixa de texto nova no painel, limite 8 000 caracteres),
`claude_parar`, `claude_resposta`, `claude_nova_conversa`. Todo texto vindo do Claude
entra na tela só por `textContent`; Markdown renderizado por formatador próprio e
mínimo (negrito, código, lista), sem `innerHTML`.

**Voz:** o planejador continua respondendo comando curto; frase que pede trabalho
("pede pro Claude…", "analisa…", "verifica meu PC") vira `claude_perguntar` e a
resposta final é resumida em até 2 frases para a fala (o texto inteiro fica no painel).

**Playwright (MCP):** o dono já tem `playwright` no `~/.claude.json`
(`npx --prefer-offline @playwright/mcp@0.0.80`) — no perfil dono ele entra sozinho.
Regras no `settings.json` do harness: `browser_navigate`, `browser_snapshot`,
`browser_tabs`, `browser_take_screenshot` liberados; `browser_click`, `browser_type`,
`browser_fill_form`, `browser_select_option`, `browser_press_key` pedem aprovação
**por domínio, uma vez por tarefa**; `browser_evaluate`, `browser_run_code_unsafe` e
`browser_file_upload` negados. O Playwright MCP usa perfil próprio (não o Chrome
logado do dono) — manter assim; conteúdo de página é dado, nunca ordem (regra já
existente no `CLAUDE.md` e no piloto de `dervs_browser.py`).

### Onda C — motor de aprovação (lente Arquiteto 2a)

Módulo novo `dervs_aprovacao.py` (funções puras + armazenamento), mais
`dervs_protegidos.py` (lista de caminhos) e `dervs_executor_seguro.py` (o único que
toca o disco). `dervs_safety.py` continua valendo por cima: ele classifica comando; o
motor classifica **item**.

**Fluxo:**
1. **Analisar** — um coletor ou o Claude (via `propor_acao`) gera itens
   `Item{id, acao ∈ {lixeira, quarentena, desinstalar, desativar_inicializacao,
   atualizar, alterar_config}, alvo, o_que_e, onde, tamanho_bytes, por_que_seguro,
   risco ∈ {baixo, medio, alto}, o_que_muda, como_desfazer, reversivel: bool,
   impressao}`. `impressao` = hash de (caminho normalizado + tamanho + mtime) — ou
   (id do pacote + versão) para programas.
2. **Relatório** — gravado em `%LOCALAPPDATA%\dervs\relatorios\<id>.json`, exibido no
   painel item a item, com o total e o texto em português leigo. Item sem `o_que_e`
   ou sem `por_que_seguro` é **recusado na criação** (o motor não aceita relatório raso).
3. **Aprovação** — um clique por item (e "aprovar todos os de risco baixo" só para
   itens `reversivel` + `baixo`; risco alto é sempre individual com dupla
   confirmação). Registro `{relatorio_id, item_id, impressao, quando, origem:"clique",
   cartaoId}`. `origem:"voz"` é rejeitado pelo motor para qualquer ação desta lista.
4. **Executar** — `executor_seguro.executar(item, registro)` **recusa** se: não há
   registro; a impressão mudou (o arquivo mudou depois da análise); passou de 15 min;
   o alvo cai num caminho protegido; o alvo é ponto de junção/atalho simbólico
   (resolver com `os.path.realpath` e checar `FILE_ATTRIBUTE_REPARSE_POINT`).
   Esse "recusa sem aprovação registrada" é o teste automatizado do critério 4.
5. **Apagar = Lixeira ou quarentena, nunca exclusão direta.** Lixeira via
   `IFileOperation`/`SHFileOperationW` com `FOF_ALLOWUNDO` (ctypes, sem dependência);
   quarentena = mover para `%LOCALAPPDATA%\dervs\quarentena\<data>\<id>\` com
   `manifesto.json` (origem, hash) para **Desfazer** com um clique. Quarentena é o
   padrão para itens fora do perfil (ex.: `C:\Windows\Temp`) e quando a Lixeira não
   aceita. Esvaziar Lixeira/quarentena é ação `irreversivel` separada, com dupla
   confirmação, e a quarentena se oferece para esvaziar só depois de 30 dias.
6. **Log** — `%LOCALAPPDATA%\dervs\acoes.jsonl`, só acrescenta, cada linha com o hash
   da anterior (adulteração fica visível). Registra analisar, propor, aprovar,
   executar, desfazer, recusar. Passa por um redator que reusa os padrões de
   `_SEGREDOS` de `dervs_safety.py` e corta valores de variáveis de ambiente. Aba
   "Registro" no painel lê o arquivo (critério 7).
7. **Programas e sistema** (desinstalar, `winget upgrade`, desativar inicialização,
   firewall): não vão para a Lixeira; o relatório diz "como desfazer" (reinstalar a
   versão X; reativar na lista) e, quando houver administrador, oferece criar ponto
   de restauração (`Checkpoint-Computer`) antes. Desativar inicialização é feito pelo
   mesmo registro que o Gerenciador de Tarefas usa (`StartupApproved`), portanto
   reversível.

**Caminhos protegidos (nunca se apagam, nem aprovados):** `C:\Windows`,
`C:\Program Files`, `C:\Program Files (x86)`, `C:\ProgramData\Microsoft`, raiz de
cada perfil (`C:\Users\<nome>` em si), as pastas-raiz Documentos, Área de Trabalho,
Imagens, Vídeos, Música, OneDrive (a pasta inteira; itens dentro só com risco alto),
qualquer `.git`, `~\.claude`, `~\.ssh`, `~\source\repos\*` (o repositório inteiro),
`%APPDATA%\dervs`, `%LOCALAPPDATA%\dervs` (exceto quarentena expirada),
`pagefile.sys`, `hiberfil.sys`, `swapfile.sys`, `System Volume Information`,
`$Recycle.Bin`, e a lista `caminhos_protegidos_extra` do `config.json` (onde entram
as pastas dos programas com dados de paciente — ver dúvidas). Comparação
insensível a maiúsculas, após normalizar `\\?\`, nomes curtos 8.3 e barras.

### Onda D — Central do PC: coletores (lente Arquiteto 2b)

Pacote `dervs_central/` com um coletor por arquivo; cada coletor recebe um
`rodar(comando) -> str` injetável (teste com saída gravada em
`tests/fixtures/central/*.json`), roda PowerShell com
`-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "<consulta> |
ConvertTo-Json -Depth 4 -Compress"` sem janela (`dervs_processos.sem_janela()`),
timeout próprio, e devolve `{ok, itens, precisa_admin, erro}`. **Tudo só leitura.**
Sem admin, o coletor diz "precisa de administrador" em vez de falhar.

| Coletor | Consulta | Permissão |
|---|---|---|
| Espaço em disco | `psutil.disk_usage` por volume + `Get-Volume \| Select DriveLetter,FileSystemLabel,Size,SizeRemaining,HealthStatus` | usuário |
| Saúde do disco (SMART) | `Get-PhysicalDisk \| Select FriendlyName,MediaType,HealthStatus,OperationalStatus,Size`; detalhe `Get-PhysicalDisk \| Get-StorageReliabilityCounter \| Select Temperature,Wear,ReadErrorsTotal,PowerOnHours` | usuário (o 2º precisa admin) |
| Erros do Visualizador de Eventos | `Get-WinEvent -FilterHashtable @{LogName='System','Application';Level=1,2;StartTime=(Get-Date).AddDays(-7)} -MaxEvents 300 \| Select TimeCreated,Id,ProviderName,LevelDisplayName,Message`, agrupado por (fonte, id); marca conhecidos: Kernel-Power 41, BugCheck 1001, WHEA-Logger, Service Control Manager 7031/7034, Application Error 1000 | usuário |
| Windows Update | COM `(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher().Search("IsInstalled=0 and IsHidden=0").Updates \| Select Title,MsrcSeverity,IsDownloaded`; último instalado `Get-CimInstance Win32_QuickFixEngineering`; reinício pendente = existe `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired` | usuário (busca lenta: 30–120 s, roda em segundo plano) |
| winget | módulo `Microsoft.WinGet.Client`: `Get-WinGetPackage \| ? IsUpdateAvailable \| Select Name,Id,InstalledVersion,AvailableVersions`; sem o módulo, `winget upgrade --include-unknown --disable-interactivity` com parser de texto testado por fixture | usuário |
| Inicialização | `Get-CimInstance Win32_StartupCommand \| Select Name,Command,Location,User` + estado em `HKCU/HKLM:\...\Explorer\StartupApproved\Run`; tarefas no logon `Get-ScheduledTask \| ? {$_.Triggers.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger'}` | usuário |
| Processos pesados | `psutil` (já dependência): duas amostras de CPU a 1 s + RSS, top 10; assinatura só desses 10 via `Get-AuthenticodeSignature` | usuário |
| Defender | `Get-MpComputerStatus \| Select AMServiceEnabled,AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureLastUpdated,QuickScanEndTime`; ameaças `Get-MpThreatDetection`; antivírus de terceiros `Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct` | usuário (ameaças pode pedir admin) |
| Firewall | `Get-NetFirewallProfile \| Select Name,Enabled,DefaultInboundAction` | usuário |
| Temporários | Python `os.scandir` em `%TEMP%`, `C:\Windows\Temp` (se legível), cache de miniaturas, `Windows.old` e Lixeira (tamanho); só arquivos com mais de 7 dias e não travados | usuário |
| Repositórios sem push | varre raízes do `config` (padrão `~\source\repos`) atrás de `.git`; `git -C <repo> status --porcelain=v2 --branch` (ahead, sujo); **sem `fetch`**, nada de rede | usuário |
| Drivers | `Get-CimInstance Win32_PnPEntity \| ? ConfigManagerErrorCode -ne 0 \| Select Name,DeviceID,ConfigManagerErrorCode` | usuário |
| Energia | `Get-CimInstance Win32_Battery` (ausente = "não se aplica", caso desta máquina), `powercfg /getactivescheme`, `(Get-CimInstance Win32_OperatingSystem).LastBootUpTime` | usuário |

Resultado vai para `%LOCALAPPDATA%\dervs\central\ultima.json` e uma linha resumida em
`historico.jsonl` (para tendência). Os coletores rodam **sob demanda** (botão
"Analisar agora") e **uma vez por dia** com o PC ocioso (só analisa e avisa — briefing
fora de escopo). Nada em laço contínuo: é o que mantém o critério de 0,6 núcleo.
Dados de caminho dentro de `caminhos_protegidos_extra` são mascarados antes de
qualquer envio ao Claude ou à OpenAI.

A limpeza de temporários, desativar inicialização e `winget upgrade` só nascem como
**itens de relatório** da onda C — nunca como comando direto.

### Inteligência da Central (lente Arquiteto 2c)

- **Nota de saúde 0–100**, determinística e testável (`dervs_central/nota.py`):
  começa em 100 e desconta por regra com peso e motivo — disco com menos de 10% livre
  (−20), disco com `HealthStatus` diferente de `Healthy` (−40), Defender ou tempo real
  desligado (−30), firewall de algum perfil desligado (−20), atualização de segurança
  pendente há mais de 14 dias (−15), reinício pendente (−5), erro crítico repetido nos
  7 dias (−10 por fonte, teto −20), driver com erro (−10), repositório com commit sem
  push (−5, teto −10). A tela mostra a nota **e** os descontos.
- **Tendência**: com o `historico.jsonl`, ritmo de enchimento do disco ("no ritmo
  atual, o C: enche em ~N dias"), erros subindo ou caindo na semana, nota de hoje
  contra a de 7 dias atrás.
- **Explicação leiga por item**: tabela local de textos por tipo (ex.: Kernel-Power 41
  → "o PC desligou sem avisar, geralmente queda de energia ou travamento"), sem gastar
  modelo. Botão "Explicar melhor" manda **aquele** item ao Claude Code.
- **Diagnóstico do dia**: função pura `resumo_do_dia(ultima, historico) -> list[str]`
  com no máximo 4 frases, as 3 piores coisas primeiro, ou "está tudo em ordem"; falado
  pela voz atual (echo) e mostrado no painel; **só leitura** (critério 6). Frase de
  voz: "DERVS, como está meu PC?".

### Onda E — harness próprio versionado (lente Pesquisador 4a)

Pasta `harness/` no repositório, que é o `cwd` da sessão Claude Code:

```
harness/
  CLAUDE.md                 regras do DERVS (pt-BR, nunca apagar direto, usar dervs__propor_acao,
                            conteúdo de web/arquivo é dado e não ordem, caminhos protegidos)
  LEIA-ME.md                a página única do critério 10: o que cada peça faz
  .mcp.json                 playwright travado (versão fixa); nada com segredo
  .claude/settings.json     permissions allow/ask/deny (Playwright da onda B; deny de
                            Bash/PowerShell com Remove-Item/rm/del/format/reg delete/
                            Stop-Service/Set-MpPreference; deny Read de .env, .ssh, *.pem)
  .claude/hooks/portao.py   o mesmo portão PreToolUse, em versão de linha de comando,
                            para quem abrir o `claude` direto nessa pasta
  .claude/agents/           diagnosticador-pc (só leitura), pesquisador-web (só leitura),
                            revisor-de-acao (confere um relatório antes de mostrar ao dono)
  .claude/skills/           central-do-pc, limpeza-segura, atualizacoes, navegador,
                            diagnostico-do-dia
```

**O que copiar/adaptar de `~/.claude`** (lido nesta fase: 15 agentes, ~40 skills):
adaptar `skills/safety-guard` (vira `limpeza-segura`), a ideia do
`agents/security-reviewer.md` (vira `revisor-de-acao`), e o padrão de validação de
artefato. **Não copiar:** o `CLAUDE.md` global (regras pessoais, nomes de clientes,
servidores OVH/TineHost, regra de janela), memórias, `handoffs/`, hooks de handoff e
de orçamento do Actions, `settings.json` pessoal, o MCP `codebase-memory-mcp` (é
ferramenta de programador), `shadcn`. Script `scripts/verificar_harness.py` falha se
achar e-mail, caminho `C:\Users\Desktop`, nome de servidor ou padrão de segredo
dentro de `harness/`.

**Acessos:** GitHub pelo `gh` CLI com o **login da própria pessoa** (`gh auth login`
no assistente de primeira execução, se ela quiser) — sem token no pacote. Servidor:
**nada no harness**; no PC do dono continua o caminho de deploy já aprovado
(`workflow_dispatch` + runner), que mora no `~/.claude` dele e é carregado só no
perfil dono.

### Onda F — instalador para outros PCs (lente Diretor 4b)

**Decisão de empacotamento: Inno Setup 6, por usuário, sem administrador**, e não o
NSIS do electron-builder. Motivo: no DERVS o **Python é o pai** e o Electron é filho
(`dervs_ponte_electron.py`; todo o ciclo de vida de §3 do `ESTADO.md` depende disso).
O electron-builder presume que o `.exe` do Electron é o programa principal e o
auto-update dele também; inverter essa relação agora reabriria os defeitos de "Python
órfão com microfone aberto". O Inno Setup empacota a pasta pronta, faz atalho,
"Aplicativos", desinstalação e atualização por cima sem perder dado.

- **Conteúdo** (`build/dist/DERVS/`, gerado por `scripts/empacotar.py`, um comando):
  `python\` = CPython **embeddable** oficial da mesma versão do `dervs-venv` +
  `site-packages` instalado a partir do `requirements.txt` (sem `pytest`); `app\` = os
  `.py` do projeto vindos de `git archive HEAD` (nunca da pasta de trabalho, que tem
  `config` e `.env` possíveis); `tela\` = Electron empacotado com `@electron/packager`
  (asar ligado) + fusíveis do Electron: `RunAsNode` desligado,
  `EnableNodeOptionsEnvironmentVariable` desligado, `EnableNodeCliInspectArguments`
  desligado, `EnableEmbeddedAsarIntegrityValidation` e `OnlyLoadAppFromAsar` ligados;
  `node\` = `node.exe` portátil oficial só para rodar o MCP do Playwright (não usar o
  Electron como Node, que os fusíveis desligam); `harness\`.
- **Atalho** aponta para `python\pythonw.exe app\dervs_electron.py` com o ícone
  `dervs.ico` (mesmo modelo do `scripts/instalar_atalho.py`).
- **Inno**: `PrivilegesRequired=lowest`, pasta `{localappdata}\Programs\DERVS`,
  assistente em português, página "Privacidade do microfone" antes de instalar,
  desinstalação com caixa "apagar também meus dados (configuração, lembretes,
  registro)" **desmarcada** por padrão.
- **Modelos fora do instalador**: a voz padrão é a de nuvem; Kokoro (~350 MB, hoje em
  `%LOCALAPPDATA%\dervs\modelos`) e o whisper `tiny` do porteiro (~75 MB) são baixados
  na primeira execução, de URL fixa com **SHA-256 travado no código**, com barra de
  progresso; Kokoro só se a pessoa marcar "voz sem internet". Tamanho estimado do
  `Setup.exe`: 250–350 MB (PyQt6, onnxruntime e ctranslate2 são os mais pesados;
  medir no primeiro build).
- **Primeira execução** (assistente no painel): chave da voz (OpenAI) da própria
  pessoa, guardada com **DPAPI do Windows** (`CryptProtectData`, por usuário, via
  ctypes) em vez de `.env` em texto puro; escolha do microfone; microfone **desligado**
  até a pessoa ligar; verificação do Claude Code (`claude --version` e login) — se
  faltar, abre a página oficial de instalação e espera; **não** roda `irm … | iex`
  (o próprio `dervs_safety.py` marca isso como vermelho); `gh auth login` opcional.
- **Perfil equipe** (padrão do instalador): `setting_sources=["project"]`, MCP estrito
  do harness, Playwright com `--browser msedge` (o Edge existe em todo Windows),
  aprovação por voz desligada para tudo que não seja "reversível".
- **Atualização**: v1 sem auto-update — um Setup novo instala por cima e mantém os
  dados. Botão "procurar atualização" lê um `versao.json` público com SHA-256, baixa e
  abre o Setup; nada roda sem o clique.
- **Assinatura de código**: ver dúvida 1. Enquanto não houver certificado, o Setup sai
  com SHA-256 publicado e o passo a passo mostra a tela do SmartScreen ("Mais
  informações → Executar assim mesmo").
- **Segurança do pacote**: `scripts/varrer_pacote.py` roda como portão do build e
  **reprova** se achar `.env`, `config.json`, `*.jsonl`, `instancia.json`, pasta
  `.claude` pessoal, padrões `sk-`, `ghp_`, `github_pat_`, `AKIA`,
  `-----BEGIN .* PRIVATE KEY-----`, o e-mail do dono ou `C:\Users\Desktop` (critério 9:
  zero achados). ASAR não é cofre — nada secreto entra nele. Janela continua com
  `contextIsolation`, `sandbox`, CSP `default-src 'none'`, `will-navigate` bloqueado;
  somar `session.setPermissionRequestHandler` negando tudo (o microfone é do Python,
  não do renderer).
- **LGPD / microfone**: documento `PRIVACIDADE.md` mostrado no instalador e na
  primeira execução: o porteiro roda local; a frase transcrita vai à OpenAI; o que o
  Claude Code lê pode ir à Anthropic; nada vai ao dono. Em PC de funcionário a
  empresa é a controladora — o texto diz isso e o dono decide a política (dúvida 3).
- **Teste de instalação limpa**: **Windows Sandbox** (o Windows desta máquina é Pro)
  com um `DERVS.wsb` que mapeia `build\dist` só leitura e roda
  `DERVS-Setup-<versão>.exe /VERYSILENT /CURRENTUSER`, depois um teste de fumaça que
  confere a pasta, o atalho, a entrada de desinstalação e que o processo sobe; mais
  uma instalação visual com o assistente. Sandbox exige ligar o recurso do Windows uma
  vez (administrador + reinício) — ver dúvida 4.

### Ordem das ondas e testes

| Onda | Depende de | Critério de pronto |
|---|---|---|
| **A** painel único + bandeja | — | Widget apagado; cartão de plano, reunião e "Abrir DERVS App" funcionando no painel; `janela-estado.test.js` cobre abrir/esconder/minimizar/restaurar/fechar-para-bandeja; foto **só da janela** (PrintWindow, regra da memória) com os três botões; `pytest -q` e testes JS verdes; CPU parado < 0,6 núcleo medido. |
| **B** Claude Code real | A (caixa de texto e área de conversa no painel) | Bug do `select` corrigido com teste de sessão falsa; `dervs_claude_code.py` com testes do callback de permissão, do gancho `PreToolUse` e da constante de modo (tudo com cliente falso, sem rede); execução real: pergunta digitada aparece em streaming, "para" interrompe, voz "pede pro Claude…" responde; Playwright abre um site pedido no painel (critérios 2 e 3). |
| **C** motor de aprovação | pode começar junto de B (módulos puros); integra em B | Testes: executor recusa sem registro, com impressão mudada, vencido, em caminho protegido, em junção, com origem voz; Lixeira e quarentena com desfazer provados em pasta temporária; log encadeado e redigido; revisão `security-reviewer` aprovada (critérios 4 e 7). |
| **D** Central do PC | C (limpeza), A (tela) | Cada coletor testado com fixture (inclusive "precisa admin" e saída vazia); nota e `resumo_do_dia` testados; foto do painel com dados reais desta máquina; diagnóstico falado; limpeza de temporários real passando por relatório → clique → Lixeira → desfazer (critérios 5 e 6). |
| **E** harness | B, C | `harness/` versionado; `verificar_harness.py` verde; sessão com perfil equipe numa conta de Windows sem `~/.claude` respeita as mesmas travas (teste com `setting_sources=["project"]`); `LEIA-ME.md` de uma página (critério 10). |
| **F** instalador | E | `python scripts\empacotar.py` gera `DERVS-Setup-<versão>.exe`; `varrer_pacote.py` com zero achados; instalação limpa no Windows Sandbox + desinstalação mantendo/apagando dados conforme a caixa; primeira execução pede chave, microfone e confere o Claude (critério 9). |

Revisores por onda: python-reviewer (todas com `.py`), typescript-reviewer (`main.js`,
`preload.js`, `painel.js`), **security-reviewer obrigatório em B, C, E e F**,
design-reviewer em A e D.

## o_que_ja_existe

- `electron/main.js` — `criarJanela` (widget), `criarPainel`, `alternarPainel`,
  `ampliarPainel`, `redimensionarPainel`, `montarBandeja`, `registrarAtalhoGlobal`
  (`Control+Alt+D` e `Control+Alt+Shift+D`), `sairDoDervs`, `tratarLinhaDoPython`
  (verbos `plano` e `mostrar` apontam para o widget).
- `electron/preload.js` — API `window.dervs` com `contextBridge`; já tem controles do
  painel (`painelEsconder`, `painelAmpliar`, `painelRedimensionar`).
- `electron/renderer/painel.html|css|js`, `painel-formato.js` + `.test.js` — painel
  JARVIS com CSP, sem caixa de texto; `index.html` + `hud.js` — widget;
  `estilo.css` — compartilhado.
- `dervs_ponte_electron.py` — protocolo JSON por linha (Electron→Python por stdout,
  Python→Electron por soquete 127.0.0.1), com `cartao_id` anti-duplicação.
- `dervs_electron.py` — `Motor`, `_confirmar_plano`, `_confirmar_do_electron`,
  chamada a `seg.decidir_risco` (linha 118).
- `dervs_brain.py` — `_cmd_stream` (claude isolado), `_Sessao` (usa `select.select`,
  quebrado no Windows), `_pensar_oneshot`, `_pensar_openai`, `pensar`.
- `dervs_config.py` — `cerebro` aceita `openai|claude` (padrão `openai`),
  `segredo()` lendo `%APPDATA%\dervs\.env`.
- `dervs_safety.py` — `classificar_local`, `decidir_risco`, três trilhos,
  `_SEGREDOS`, `_DESTRUTIVOS`, `_DESTRUTIVOS_COMBO`.
- `dervs_exec.py`, `dervs_processos.py` (`sem_janela`, `encerrar_arvore`,
  `rodar_com_arvore`), `dervs_sistema.py` (psutil), `dervs_gasto.py`,
  `dervs_painel.py`, `dervs_browser.py` (Playwright em Python, não MCP),
  `dervs_kokoro_daemon.py` (modelos em `%LOCALAPPDATA%\dervs\modelos`).
- Testes relevantes: `test_dervs_electron_entrada.py`, `test_dervs_ponte_electron.py`,
  `test_dervs_painel.py`, `test_dervs_painel_js.py`, `test_dervs_safety.py`,
  `test_dervs_safety_powershell.py`, `test_dervs_brain.py`,
  `test_dervs_cerca_nos_dois_cerebros.py`, `test_dervs_voz_nao_e_senha.py`,
  `test_dervs_travas_que_faltavam.py`, `conftest.py` (isola `APPDATA`).
- `scripts/instalar_atalho.py` (atalho com `pythonw.exe`), `requirements.txt`
  (versões travadas; comentário ainda cita Electron 33.2.1), `electron/package.json`
  (Electron 44.4.5).
- Fora do repo, só no PC do dono: `~/.claude.json` com MCP `playwright`
  (`@playwright/mcp@0.0.80`), `codebase-memory-mcp`, `shadcn`; `~/.claude/agents`
  (15) e `~/.claude/skills` (~40); CLI `claude` 2.1.284 em `C:\nvm4w\nodejs\claude`.
- Tamanhos medidos: `dervs-venv` 682 MB, `electron/node_modules` 382 MB.

## fontes_externas

Consultadas em 2026-09-29:
- https://code.claude.com/docs/en/agent-sdk/permissions — ordem de avaliação
  (ganchos → deny → ask → modo → allow → `canUseTool`), gancho nega até em
  `bypassPermissions`, `dontAsk`, aviso de que allow sem escopo pula o callback.
- https://github.com/anthropics/claude-agent-sdk-python/blob/main/examples/tool_permission_callback.py
  — exemplo do callback de permissão no SDK Python.
- https://github.com/anthropics/claude-code/issues/54850 — regressão recente de
  permissão em stream-json (motivo para travar a versão do CLI/SDK e testar).
- https://www.electron.build/docs/nsis/ e
  https://github.com/electron-userland/electron-builder/issues/1104 — NSIS por usuário
  (`perMachine:false`) ignora a escolha de pasta; considerado e preterido.
- https://azure.microsoft.com/en-us/pricing/details/artifact-signing/ e
  https://learn.microsoft.com/en-us/azure/artifact-signing/faq — Artifact Signing
  US$ 9,99/mês, mas pessoa física só nos EUA/Canadá e empresa só EUA/Canadá/UE/Reino
  Unido (fora do alcance de quem está no Brasil).
- https://www.sslmentor.com/certum/certumcodecloud — Certum Code Signing em nuvem a
  partir de ~US$ 116/ano.
- https://ivansingleton.dev/the-cheapest-code-signing-certificate-for-business-central-appsource-in-2026-a-complete-comparison-guide/
  — desde 2024 o EV não dá mais reputação automática no SmartScreen; validade máxima
  de 460 dias desde 01/03/2026.

## fora_de_escopo

Tudo o que o briefing já exclui (correção automática sem aprovação, inclusive
agendada; trocar voz ou motor de fala; publicar em servidor ou Actions; acesso remoto;
projetos de outras janelas; instalar programa sem aprovação item a item). Somam-se,
por decisão desta fase: inverter o pai/filho Python↔Electron; auto-update silencioso;
terminal embutido (xterm.js + node-pty) — o streaming do stream-json na conversa cobre
o pedido sem trazer um shell interativo para dentro da tela; `sfc`/`DISM`/limpeza de
disco do sistema que exigem administrador (a Central só aponta); tirar o PyQt6 do
pacote; publicar na Microsoft Store; qualquer chave de API da Anthropic (só
assinatura via CLI logado).

## contradicoes_resolvidas

1. **"O mesmo Claude, com `~/.claude`" × o cérebro atual isolado com
   `--setting-sources ""`.** Resolvido com duas peças: o planejador de voz continua
   isolado (medido: 40 mil tokens e JSON quebrado sem isolamento); a sessão Claude
   Code nova carrega `~/.claude` no perfil dono.
2. **"Acesso total" × "não pode apagar nada sem analisar e aprovar".** Leitura ampla
   (`add_dirs` C:\) livre; escrita, exclusão, desinstalação e configuração do sistema
   só pelo executor do DERVS com aprovação registrada; o Claude não tem ferramenta de
   executar ação destrutiva.
3. **Sessão contínua do `claude` "existe"** (comentário de `dervs_brain.py`) × na
   prática nunca roda no Windows: `select` em cano falha (provado, WinError 10093).
   Corrigir na onda B com thread leitora.
4. **Padrão de `cerebro`**: `dervs_brain.py` usa `_conf.get("cerebro", "claude")`,
   mas `dervs_config.PADRAO["cerebro"] = "openai"` sempre preenche — o padrão efetivo
   é OpenAI. Mantido (decisão anterior de latência); o Claude Code entra pela conversa
   do painel e pelo encaminhamento de voz. Ver dúvida 2.
5. **Dois atalhos (`Ctrl+Alt+D` e `Ctrl+Alt+Shift+D`) e bandeja abrindo o widget**
   (README/COMO-USAR) × janela única: fica só `Ctrl+Alt+D`, e a bandeja abre o painel.
6. **Painel "minimizar é desfeito na hora"** (herança do widget sem moldura, `main.js`)
   × pedido de minimizar: o painel passa a minimizar de verdade para a barra de tarefas.
7. **Servidor no harness** × "acesso ao servidor não entra no instalador": o harness
   não tem nada de servidor; o deploy do dono continua só no `~/.claude` dele.
8. **`requirements.txt` diz "Electron 33.2.1"** × `package.json` 44.4.5: vale o
   `package.json`; o comentário é corrigido na onda A.
9. **Config e cache do Chromium na mesma pasta `%APPDATA%\dervs`** × desinstalar
   "mantendo os dados": o `userData` do Electron vai para uma subpasta própria.
10. **Artifact Signing (o mais barato) × dono no Brasil**: não é elegível; a
    alternativa real é certificado OV (Certum/SSL.com) ou distribuir sem assinatura
    no círculo interno.

## duvidas_para_o_dono

1. **Assinatura de código (dinheiro).** Sem assinatura, cada pessoa vê o aviso azul
   do Windows e precisa clicar "Mais informações → Executar assim mesmo"; com
   certificado OV em nuvem (Certum, ~US$ 116 por ano, renovação anual) o aviso some
   com o tempo, conforme as pessoas instalam. **Recomendação:** começar sem assinatura
   para sócios e funcionários (passo a passo com foto do aviso + código SHA-256) e
   comprar o Certum no nome da empresa só quando for distribuir para mais gente.
2. **Voz: comandos rápidos continuam pela OpenAI ou tudo vai para o Claude Code?**
   O Claude Code demora mais para responder e usa a cota da sua assinatura.
   **Recomendação:** comandos curtos seguem na OpenAI (1–2 s); pedidos de trabalho
   ("analisa", "verifica", "pede pro Claude") vão para o Claude Code.
3. **Microfone em PC de funcionário (LGPD).** A empresa precisa de uma regra dizendo
   se o microfone pode ficar ligado no expediente. **Recomendação:** no perfil equipe o
   microfone vem desligado e só liga pelo botão; o aviso de privacidade diz o que vai
   para a OpenAI e para a Anthropic; você aprova o texto antes da onda F.
4. **Ligar o Windows Sandbox nesta máquina** (pede administrador e um reinício, uma
   vez). **Recomendação:** sim — é a forma mais barata de provar "instalação limpa sem
   erro" a cada versão, sem outro computador.
5. **Onde estão os dados de paciente dos seus outros programas?** Preciso dos nomes
   (ou pastas) para entrarem em `caminhos_protegidos_extra` e serem mascarados antes de
   qualquer envio ao Claude. **Recomendação:** você só diz os nomes dos programas; eu
   acho as pastas e mostro a lista para você confirmar.
