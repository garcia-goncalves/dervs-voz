# PLANO DE EXECUÇÃO — dervs-cara-nova

Fase 4 da esteira. Escrito pelo `neguin-planner` em 15/09/2026, contra
`docs/esteira/dervs-cara-nova/{briefing,spec,design,textos,assets}.md` e
`assets/CREDITOS.md`, com o código do repositório conferido arquivo por arquivo.

Índice do grafo de código: `ready`, `head_sha` `26cbdec` — **bate com o HEAD do
repositório**, então o que está mapeado aqui é o código de agora, não o de ontem.

---

## Contexto verificado

Fatos conferidos no disco (não no que a esteira supôs):

- **543 testes coletados** hoje no ambiente do projeto
  (`./dervs-venv/Scripts/python.exe -m pytest --collect-only -q` → `543 tests collected`).
  Esse é o piso que não pode regredir.
- **`rms()` existe e é pura**: `dervs_listen.py:32-40`. `pico()`: `dervs_listen.py:291-302`.
  Nenhuma das duas depende de Qt — teste novo sobre elas roda também no Python do sistema.
- **`Escuta` é onde nasce o nível**: `dervs.py:330-399`; a leitura quadro a quadro está em
  `dervs.py:362` (`frame = self._mic.ler()`), a decisão de pausa em `dervs.py:370-378`, e os
  únicos dois sinais existentes são `fala` e `mudo` (`dervs.py:335-338`).
- **C9 do spec está RESOLVIDO, e o plano B não é necessário.** A varredura dedicada achou o
  playback que o Arquiteto não encontrara: `Voz._tocar(wav)` em **`dervs_tts.py:604-610`**,
  que chama `criar_reprodutor(wav)` (`dervs_tts.py:205-223`) e depois `play.wait()`. Os
  reprodutores são `_ReprodutorSD` (sounddevice, `dervs_tts.py:139-170`) e `_ReprodutorWinsound`
  (reserva, `:173-202`), os dois com o contrato `poll()/terminate()/wait()` do `Popen`.
  **Consequência prática:** existe um ponto único e síncrono onde a reprodução começa e
  termina — é ali que o nível da voz do DERVS entra, sem inventar chamador nenhum.
- **`dervs_instancia.py` não tem uma linha de Qt**: `Posse` (`:120-208`), `tomar_posse`
  (`:229`), `chamar_quem_ja_esta_aberto` (`:101-117`), `RESPOSTA_SIM = DERVS-OK` (`:44`).
  O callback `ao_ser_chamado` roda **numa thread de fundo** (docstring em `:237-239`) — é
  exatamente por isso que hoje existe a `Ponte(QtCore.QObject)` (`dervs.py:1491-1501`).
- **A trava de instância é usada só no `__main__`** de `dervs.py:1687-1711` — nada dentro de
  `PopUp`/`Launcher` depende dela. Reusar num ponto de entrada novo é copiar ~10 linhas.
- **`escuta_ao_abrir` já liga o microfone sozinho** ao abrir (`dervs.py:632-635`, padrão
  `True` em `dervs_config.py:82`). A janela nova não precisa de botão de microfone para o
  app funcionar no primeiro segundo — ver "Decisões em aberto", item D.
- **A bandeja de hoje tem 4 itens** (`_montar_bandeja`, `dervs.py:1640-1663`); o item que
  sai é "Trazer o selo de volta", como o C8 do spec decidiu.
- **`closeEvent` só esconde**: `dervs.py:1487-1488` (`e.ignore(); self.hide()`).
- **O atalho aponta para `dervs.py` com `pythonw.exe`**: `scripts/instalar_atalho.py:105-110`
  (`ATALHOS`), e o `.ico` é montado por `gerar_icone()` (`:48-76`) a partir de `_png_de(px)`
  (`:37-45`), que hoje desenha `dervs._selo(px)`. O segundo atalho
  (`DERVS - Transcrever audio` → `dervs_transcrever.py`) **não muda**.
- **Node está instalado nesta máquina**: `node v20.19.5`, `npm 10.8.2`. Electron **não** está
  — `npm install` vai precisar de internet e baixa ~150-300 MB em `electron/node_modules/`.
- **Convenções de teste**: `pytest.ini` (`--import-mode=importlib`), `conftest.py:30-49`
  (exclui `.claude/`), testes na raiz com nome `test_<frase em português>`. Testes que puxam
  Qt usam `pytest.importorskip("PyQt6", ...)` — modelo em
  `test_dervs_aviso_de_silencio.py:24-27` e `test_dervs_encerrar.py:24-29`.

### Premissas do pedido que NÃO se confirmaram

1. **"O Arquiteto não achou o playback" (C9 do spec) — a premissa caiu.** Achou-se: é
   `Voz._tocar`, `dervs_tts.py:604-610`. O "plano B" (calcular `rms()` por trecho do `.wav`)
   continua sendo o **cálculo** certo, mas agora tem um chamador natural e síncrono, em vez
   de precisar ser sincronizado "por fora" ao início da reprodução. A Etapa 4 usa isso.
2. **"`dervs.py` fica intocado"** (formulação do despacho) **é incompatível com o item 2 do
   próprio spec** ("`Escuta` ganha um terceiro sinal... `dervs.py:346-392` é o lugar exato
   onde nasce um sinal novo de nível"). O corte #8 do spec diz outra coisa, mais fraca:
   `dervs.py` e seus testes **ficam no disco** e o que sai de circulação é **o caminho de
   entrada**. Este plano segue o spec: `dervs.py` recebe **uma** edição cirúrgica (um sinal
   novo + uma linha de `emit`), em uma etapa só, e nenhuma outra etapa toca nesse arquivo.
3. **`textos.md` traz cores da Direção C** (`--rosa`, `--limao`, `--bg-elevado`, "faixa da
   onda"), que o `design.md` final substituiu. **As palavras de `textos.md` valem; as cores
   dele, não.** Onde houver conflito, cor e tipografia vêm do `design.md` (`--acento` para
   os três rótulos, Orbitron caixa alta; `--painel` para o cartão; `--erro` só no erro).

---

## Contrato compartilhado — a ponte (leia antes de qualquer etapa)

Esta seção é **normativa**: as Etapas 2, 7, 8 e 9 são escritas por pessoas diferentes, em
paralelo, e só não colidem porque todas obedecem a este contrato ao pé da letra.

**Transporte.** O Python sobe o Electron como **processo filho**. Uma mensagem = uma linha de
JSON UTF-8 terminada em quebra de linha. Python para Electron pelo `stdin` do filho; Electron
para Python pelo `stdout` do filho. O `stderr` do filho é lido pelo Python e reescrito no
`sys.stderr` dele (padrão da casa: `dervs.py:355-357` — falha nunca é engolida). É o mesmo
espírito de protocolo de linha dos daemons (`dervs_stt_daemon.py:25-30`,
`dervs_kokoro_daemon.py:92-117`), e nada além disso: sem versionamento, sem WebSocket, sem
plugin (corte #3 do spec).

**Verbos Python para Electron** (os cinco do spec, e só eles):

- `estado` — campos `valor` (um de: ocioso, ouvindo, pensando, falando, erro), `texto` e
  `apoio`. Os dois últimos só são usados quando `valor` é `erro` (frase e linha de apoio de
  `textos.md`). Enviado só quando o estado muda.
- `volume` — campo `valor`, número de 0.0 a 1.0, já normalizado.
- `fala` — campos `papel` (um de: dono, dervs, resultado, erro) e `texto`. Uma linha nova de
  conversa.
- `plano` — campos `passos` (lista de objetos com `rotulo` e `nivel`, sendo `nivel` um de:
  reversivel, cuidado, destrutivo), `nivel` (o pior do plano) e `pergunta`. Lista vazia em
  `passos` limpa o cartão.
- `mostrar` — sem campos. Traz a janela para frente; substitui o `Ponte.chegou` do Qt.

**Verbos Electron para Python** (o mínimo que o comportamento de hoje exige; não é escopo
novo, é o que a bandeja e a confirmação de risco já fazem no Qt):

- `pronto` — a janela carregou. Equivale ao `READY` dos daemons: o Python só empurra `estado`
  e `volume` depois disto (antes, guarda o último de cada e despacha quando o `pronto` chega).
- `sair` — o item "Sair do DERVS" da bandeja foi clicado.
- `plano` com campo `resposta` (`confirmar` ou `cancelar`) — botão do cartão de plano.

"Abrir DERVS" e "Recolher janela" resolvem-se **dentro** do Electron (mostrar/esconder a
janela), sem mensagem nenhuma para o Python.

**Regras duras da ponte (valem para os dois lados):**

- Linha que não é JSON válido, verbo desconhecido ou campo faltando: **ignora e escreve uma
  linha no stderr**. Nunca derruba o processo, nunca faz `except` mudo.
- Linha maior que 64 KiB é descartada (mesmo espírito do `_LIMITE_LINHA` de
  `dervs_instancia.py`). Texto de conversa é cortado em 4000 caracteres antes de ser enviado.
- **Nada de credencial atravessa a ponte.** Só os campos listados acima.
- `volume` é **estrangulado no lado Python**: no máximo 20 mensagens por segundo (50 ms),
  valor arredondado em 2 casas, e valor repetido não é reenviado. A `Escuta` produz ~33
  quadros por segundo (30 ms, `dervs_listen.py:26-29`) — sem estrangular, a régua de CPU do
  C10 é queimada só com JSON.
- O método de envio da ponte é **thread-safe** (`threading.Lock` em volta da escrita): quem
  escreve são a thread da tela (estado e fala), a thread do Qt vinda da `Escuta` e a thread de
  fala do `dervs_tts` — três donos do mesmo `stdin`.
- Se o `stdin` do Electron fechar (o pai morreu), o Electron **encerra sozinho** — a lição do
  "neto órfão" (`test_dervs_arvore_de_processos.py`).
- O filho sobe com `creationflags=subprocess.CREATE_NO_WINDOW` no Windows. Sem isso volta a
  "janela preta" já corrigida (`ESTADO.md`, item 3.2).

**API que o `preload.js` expõe ao renderer** (`contextBridge`, contexto isolado):
`window.dervs` com `aoEstado(cb)`, `aoVolume(cb)`, `aoFala(cb)`, `aoPlano(cb)` e
`responderPlano(resposta)`. O `cb` de estado recebe um objeto com `valor`, `texto` e `apoio`;
o de volume recebe um número de 0 a 1; o de fala recebe `papel` e `texto`; o de plano recebe
`passos`, `nivel` e `pergunta`; `responderPlano` recebe a palavra `confirmar` ou `cancelar`.
O renderer **não** tem `require`, `nodeIntegration` nem acesso a rede.

---

## Riscos

1. **`npm install` precisa de internet e baixa centenas de MB.** Se falhar, as etapas de
   Electron ficam sem verificação de execução. Registre a falha exata, não finja verde, e
   siga as etapas de Python — elas são independentes.
2. **As fontes (Orbitron, Share Tech Mono) vêm do Google Fonts e precisam de rede.** Se não
   baixarem, o CSS cai no fallback declarado e a etapa é entregue com a pendência escrita. O
   app **não pode** buscar fonte na rede em tempo de execução (`design.md`; `CREDITOS.md`).
3. **Regressão silenciosa nos 543 testes.** Duas etapas mexem em arquivo coberto por teste
   (`dervs.py` e `dervs_tts.py`). Quem toca esses dois roda a **suíte inteira**, não só o
   teste novo.
4. **Régua de CPU do C10.** A onda nova não pode custar mais que o `QTimer` de 500 ms do selo
   atual (`dervs.py:1521-1522`) a ponto de atrapalhar o uso o dia inteiro. Mitigação já
   embutida: estrangulamento do volume, um único `requestAnimationFrame`, nenhuma segunda
   camada animada (`assets.md`, item 4). Medição na Etapa 12.
5. **Duas interfaces ao mesmo tempo.** O briefing exige "não sobra duas interfaces
   concorrentes". O motor Python continua sendo a `PopUp` do Qt **nunca mostrada** (Decisão
   A) — a Etapa 9 tem teste provando que nenhuma janela Qt aparece.
6. **Texto de fora renderizado como HTML.** Transcrição, resposta do cérebro e saída de
   comando são conteúdo hostil por definição (`ESTADO.md:130-135` registra uma página que já
   tentou dar ordem ao cérebro). No renderer: **`textContent`, nunca `innerHTML`**, e CSP
   fechada no `index.html`.
7. **O microfone continua tendo um dono só** (C4). Nenhuma etapa pode chamar `getUserMedia`,
   `AnalyserNode` de captura ou qualquer API de áudio no Electron.

---

## Decisões em aberto — leia antes de despachar

**A) Quem orquestra do lado Python (duas leituras; recomendo a primeira).**
O spec diz "a janela Electron substitui as três peças PyQt6", mas **a orquestração inteira
mora dentro da `PopUp`** (`dervs.py:402-1489`: fila de fala, porteiro, janela de desperto, STT
via `QProcess`, cérebro, plano, confirmação, execução, registro de queda — cerca de 1000
linhas corrigidas a duras penas).

- *Leitura 1 (recomendada):* o ponto de entrada novo instancia a `PopUp` como **motor
  invisível** (subclasse `Motor(dervs.PopUp)` que nunca se mostra) e liga os ganchos dela na
  ponte. Custo: zero reescrita, 543 testes intactos, comportamento preservado. É o que este
  plano executa.
- *Leitura 2:* reescrever a orquestração sem Qt. Custo: reescrita grande, fora do que o spec
  decidiu, e joga fora justamente as correções que o `ESTADO.md` documenta. **Não recomendo.**

**B) O que "ouvindo" quer dizer.** O `design.md` diz "o dono está falando"; o dado disponível
é o nível por quadro. Recomendo: `ouvindo` = **a escuta está ligada e o DERVS não está
pensando nem falando** (a onda mostra sozinha, pelo nível, quando ele fala de verdade). Casa
com o tooltip de `textos.md` ("DERVS — ouvindo você"). `ocioso` = escuta desligada.

**C) O cartão de plano não foi desenhado no `design.md` — mas sem ele há regressão de
segurança.** Hoje, passo de risco só roda com **clique** do dono (`_confirmar_plano`,
`dervs.py:1218`; `confirmar_passo`, `dervs.py:1388`). Sem um cartão com dois botões na janela
nova, o dono perde o único jeito de autorizar — e o briefing exige "execução de comando com
os trilhos de risco sem regressão". Por isso o verbo `plano` está no spec e este plano inclui
um cartão mínimo, na linguagem do HUD (Etapa 8). **Não é escopo novo; é o que já existe, com
cara nova.**

**D) O microfone perde o liga/desliga na tela.** O `design.md` não prevê controle nenhum e o
C8 fixou três itens de bandeja. Consequência honesta: nesta rodada o dono só desliga o
microfone saindo do DERVS ou editando `%APPDATA%\dervs\config.json` (`escuta_ao_abrir`).
**Não incluí controle novo** (seria escopo não decidido) — mas isto precisa ser dito ao dono
antes da entrega, porque é algo que ele podia fazer hoje e não poderá amanhã.

---

## Etapas

### Etapa 1 — `dervs_nivel.py`: o número que a onda desenha

**Objetivo:** existe uma função pura que transforma áudio em nível de 0.0 a 1.0, testada, sem
Qt e sem Electron — o dado que a onda consome, em um lugar só.

**Arquivos:** `dervs_nivel.py` (novo), `test_dervs_nivel.py` (novo).

**Contexto:** reusa `rms()` (`dervs_listen.py:32-40`), **não reimplementa**. Quadro tem 30 ms,
480 amostras, 960 bytes (`dervs_listen.py:26-29`). Docstring em português contando o porquê,
como manda a casa.

**Fazer:**
- `TETO_NIVEL = 6000.0` — rms de fala normal bate perto do teto; constante num lugar só, com
  docstring explicando que é o parafuso de ajuste da onda.
- `nivel_do_frame(frame: bytes) -> float`, igual a `min(1.0, rms(frame) / TETO_NIVEL)`, 0.0
  para quadro vazio, nunca negativo, nunca acima de 1.0.
- `envelope_do_wav(caminho: str, passo_ms: int = 30) -> list[float]` — abre o `.wav` com o
  módulo `wave`, lê em blocos de `passo_ms` e devolve o `nivel_do_frame` de cada bloco. Se o
  arquivo não for PCM de 16 bits (`getsampwidth() != 2`) ou não abrir: devolve lista vazia e
  escreve o motivo em `sys.stderr` (nunca `except` mudo).
- Testes, com nome em português no estilo da casa: silêncio absoluto dá 0.0; áudio alto dá
  perto de 1.0 e nunca acima; quadro vazio ou de tamanho ímpar não explode; áudio mais alto
  nunca dá nível menor que áudio mais baixo (**monotonicidade — é isto que o critério de
  aceitação do briefing pede**, não o valor da constante); `envelope_do_wav` de um `.wav`
  sintetizado alto tem média maior que a de um `.wav` de silêncio; arquivo inexistente devolve
  lista vazia.

**Verificação:** `./dervs-venv/Scripts/python.exe -m pytest test_dervs_nivel.py -q` passa; e
`python -m pytest test_dervs_nivel.py -q` no Python do sistema também passa (prova que o
módulo não puxou Qt).

**Depende de:** nenhuma.

### Etapa 2 — `dervs_ponte_electron.py`: o lado Python da ponte

**Objetivo:** o Python sabe subir o Electron como filho, mandar os cinco verbos e receber os
três de volta, com tudo testado sem precisar do Electron instalado.

**Arquivos:** `dervs_ponte_electron.py` (novo), `test_dervs_ponte_electron.py` (novo).

**Contexto:** o contrato normativo está na seção "Contrato compartilhado" deste plano — siga-o
ao pé da letra. Modelo de estilo: `dervs_stt_daemon.py:25-30` (protocolo documentado no
cabeçalho do arquivo) e as três escutas do `QProcess` do STT (`dervs.py:477-490`: saída, erro
e morte). Sem as três, volta o "DERVS surdo e calado".

**Fazer:**
- Classe `PonteElectron(ao_sair, ao_plano, ao_pronto)`:
  - `abrir(caminho_app, executavel=None)` — sobe o filho com `subprocess.Popen`, com
    `stdin`/`stdout`/`stderr` em `PIPE` e `CREATE_NO_WINDOW` no Windows; executável padrão é
    `electron/node_modules/electron/dist/electron.exe` na raiz do repositório. Se não existir,
    levanta `FileNotFoundError` com mensagem em português dizendo que falta rodar
    `npm install` dentro de `electron/`.
  - Uma thread lendo o `stdout` linha a linha (verbos de volta) e **outra** lendo o `stderr` e
    reescrevendo em `sys.stderr` com prefixo `electron:`. As duas com `daemon=True`. Se o
    `stdout` fechar, chama `ao_sair` — o filho morreu, e o DERVS não pode ficar sem cara em
    silêncio.
  - `enviar_estado(valor, texto="", apoio="")`, `enviar_volume(x)`, `enviar_fala(papel,
    texto)`, `enviar_plano(passos, nivel, pergunta)`, `enviar_mostrar()`.
  - `enviar_volume` aplica o estrangulamento (50 ms, 2 casas, sem repetido).
  - Antes do `pronto` do filho, `estado` e `volume` ficam **guardados** (só o último de cada) e
    são despachados quando o `pronto` chegar.
  - `fechar(espera=3.0)` — fecha o `stdin`, espera, `terminate()`, espera de novo, `kill()`.
  - Escrita sob `threading.Lock`; `BrokenPipeError` e `OSError` viram linha no stderr, nunca
    exceção que sobe para a tela.
- Testes com **dublê de processo** (um objeto com `stdin`/`stdout` de pipe ou `io.BytesIO`; não
  precisa de Electron): cada verbo vira exatamente uma linha de JSON com os campos certos;
  volume repetido não reenvia; rajada de 100 volumes em 100 ms entrega poucas linhas; verbo
  desconhecido vindo do filho não derruba nada e escreve no stderr; linha gigante é descartada;
  `sair` chama `ao_sair`; resposta de plano chama `ao_plano("confirmar")`; **só os campos do
  contrato saem na linha** (teste com um texto contendo algo parecido com chave, provando que
  nenhum campo extra vaza); `fechar()` é seguro de chamar duas vezes.

**Verificação:** `./dervs-venv/Scripts/python.exe -m pytest test_dervs_ponte_electron.py -q`
verde, e a suíte inteira continua sem falha.

**Depende de:** nenhuma.

### Etapa 3 — a `Escuta` ganha o sinal de nível

**Objetivo:** o nível do microfone, que hoje é calculado e jogado fora, passa a sair da
`Escuta` como um terceiro sinal — sem tocar a lógica de decisão de silêncio.

**Arquivos:** `dervs.py` (edição cirúrgica; **único arquivo desta etapa, e nenhuma outra etapa
o toca**), `test_dervs_escuta_nivel.py` (novo).

**Contexto:** `Escuta` em `dervs.py:330-399`. Já existem os sinais `fala` (`:335`) e `mudo`
(`:338`). O laço está em `:361-384`; a pausa (enquanto o DERVS fala) em `:370-377`. C4 do
spec: o microfone tem um dono só, o Python — nada de captura no Electron.

**Fazer:**
- Importar `dervs_nivel` no topo do arquivo.
- Em `Escuta`, acrescentar `nivel = QtCore.pyqtSignal(float)` com um comentário de uma linha
  dizendo para que serve (a onda do HUD).
- **Uma** linha de emissão, no caminho **não pausado**, logo depois de `estava_pausado = False`
  (`dervs.py:378`): `self.nivel.emit(dervs_nivel.nivel_do_frame(frame))`. Durante a pausa não
  se emite — quem manda o nível enquanto o DERVS fala é a Etapa 4.
- **Nada mais muda:** `ep.processar`, `vigia.ver`, `aquecer`, `reset` e a religada do
  microfone ficam idênticos.
- Teste com `pytest.importorskip("PyQt6", ...)` (modelo:
  `test_dervs_aviso_de_silencio.py:24-27`), com microfone dublê entregando quadros de
  amplitude conhecida: a `Escuta` emite `nivel` para quadro alto e para quadro baixo, com o
  alto maior que o baixo; **não** emite enquanto `pausado` é `True`; os sinais `fala` e `mudo`
  continuam se comportando como antes.

**Verificação:** `./dervs-venv/Scripts/python.exe -m pytest test_dervs_escuta_nivel.py -q`
verde **e** `./dervs-venv/Scripts/python.exe -m pytest -q` com 544 ou mais passando e zero
falhas (os 16 testes de Qt continuam verdes — é o C7 do spec).

**Depende de:** Etapa 1.

### Etapa 4 — a onda também reage quando o DERVS fala (C9)

**Objetivo:** enquanto o DERVS responde, a onda reage ao áudio dele — que é metade do pedido
do briefing.

**Arquivos:** `dervs_tts.py` (edição cirúrgica), `test_dervs_nivel_da_fala.py` (novo).

**Contexto:** **o playback existe** — `Voz._tocar(wav)` em `dervs_tts.py:604-610`, que cria o
reprodutor (`criar_reprodutor`, `:205-223`) e chama `play.wait()`. `Voz.calar()` (`:306-323`)
derruba a reprodução no meio (barge-in): o nível tem de parar junto. `Voz.falando()`
(`:296-304`) já diz se está tocando — **não crie sinal novo para o estado, ele já existe**.

**Fazer:**
- Em `Voz.__init__`, `self.ao_nivel = None` — um chamável opcional que recebe um float,
  documentado como "quem quiser ver a onda enquanto o DERVS fala liga isto aqui".
- Em `_tocar`, depois de criar o reprodutor e antes do `play.wait()`: se `self.ao_nivel` está
  ligado, sobe uma thread `daemon=True` que percorre
  `dervs_nivel.envelope_do_wav(wav, passo_ms=30)` chamando `self.ao_nivel(valor)` a cada 30 ms
  de relógio (`time.monotonic`, sem deriva acumulada), parando assim que `play.poll()` deixar
  de ser `None` (fim ou barge-in), e chamando `self.ao_nivel(0.0)` ao terminar — sempre,
  inclusive quando é cortado no meio.
- Envelope vazio (wav estranho) não sobe thread nenhuma e o comportamento de hoje segue
  idêntico. Exceção dentro da thread vira linha no stderr, nunca mata a fala.
- Testes: com um `.wav` sintetizado e um reprodutor dublê, `ao_nivel` recebe valores maiores
  que zero e termina em 0.0; quando o dublê "termina" no meio, as chamadas param; sem
  `ao_nivel` ligado, `_tocar` se comporta exatamente como antes; envelope vazio não quebra a
  fala.

**Verificação:** `./dervs-venv/Scripts/python.exe -m pytest test_dervs_nivel_da_fala.py
test_dervs_tts.py -q` verde, e a suíte inteira sem regressão.

**Depende de:** Etapa 1.

### Etapa 5 — os ícones do HUD

**Objetivo:** existem o ícone do app, o da bandeja e o de erro na linguagem HUD/JARVIS, e um
jeito repetível de gerar os PNGs.

**Arquivos:** `assets/icone-app.svg`, `assets/icone-bandeja.svg`, `assets/icone-erro.svg`
(novos), `scripts/icone_hud.py` (novo), `scripts/gerar_icones.py` (novo),
`electron/assets/bandeja-16.png` e `electron/assets/bandeja-32.png` (gerados).

**Contexto:** os três SVGs estão **escritos linha a linha** em
`docs/esteira/dervs-cara-nova/assets.md` (seções 1, 2 e 3) — copie de lá, não redesenhe.
Cores: `#050810`, `#00E5FF`, `#0A6E82`, `#FFFFFF`, `#FF3B3B`. **Não toque em
`scripts/instalar_atalho.py` nem em `dervs.ico`** — são da Etapa 10.

**Fazer:**
- Salvar os três SVGs mestres exatamente como especificados.
- `scripts/icone_hud.py`: `pixmap(px)` desenha a composição do `icone-app.svg` com `QPainter`
  (PyQt6 já é dependência e já é usado assim em `instalar_atalho.py:37-45`) — anel de 4 arcos,
  4 ticks nos eixos, núcleo ciano com centro branco; e `pixmap_bandeja(px)` com a versão
  simplificada (anel fechado e núcleo, sem ticks).
- `scripts/gerar_icones.py`: usa `icone_hud` para gravar `electron/assets/bandeja-16.png` e
  `bandeja-32.png`. **Não** grava o `.ico` (é da Etapa 10).
- Docstring em português explicando por que a bandeja é simplificada (em 16px, arco mais tick
  vira borrão — `assets.md`, seção 2).

**Verificação:** `./dervs-venv/Scripts/python.exe scripts/gerar_icones.py` roda sem erro e os
dois PNGs existem, com os tamanhos certos no cabeçalho do arquivo. Critério visual: em 32px o
anel e o núcleo são distinguíveis; em 16px não viram mancha.

**Depende de:** nenhuma.

### Etapa 6 — as fontes, empacotadas localmente

**Objetivo:** Orbitron e Share Tech Mono abrem sem internet, com a licença registrada.

**Arquivos:** `electron/renderer/fontes/orbitron-700.woff2`,
`electron/renderer/fontes/share-tech-mono-400.woff2`,
`electron/renderer/fontes/OFL-Orbitron.txt`, `electron/renderer/fontes/OFL-ShareTechMono.txt`,
`electron/renderer/fontes/LEIA-ME.md` (todos novos).

**Contexto:** `design.md` (tipografia) e `assets/CREDITOS.md` — SIL OFL 1.1, as duas do Google
Fonts, **empacotadas localmente porque o app precisa abrir sem internet**.

**Fazer:** baixar os `.woff2` (peso 700 da Orbitron, 400 da Share Tech Mono) e o `OFL.txt` de
cada família; escrever o `LEIA-ME.md` de uma tela dizendo de onde vieram, a licença e a data.
Se o download falhar, **não invente arquivo**: entregue a etapa com a pendência escrita e
avise — a Etapa 8 tem fallback declarado.

**Verificação:** os quatro arquivos existem e não estão vazios; cada `.woff2` começa com os
bytes `wOF2`; o `LEIA-ME.md` cita as duas licenças.

**Depende de:** nenhuma.

### Etapa 7 — a casca Electron (processo principal, janela e bandeja)

**Objetivo:** existe uma janela Electron que sobe, entende as linhas do Python, tem os três
itens de bandeja e nunca morre ao ser fechada.

**Arquivos:** `electron/package.json`, `electron/main.js`, `electron/preload.js` (novos), e
uma linha em `.gitignore` (`electron/node_modules/`).

**Contexto:** contrato normativo acima. Comportamentos que **têm de ser copiados de
propósito**, cada um com comentário dizendo o porquê (não são o padrão do framework):
- fechar a janela só esconde — `win.on("close", e => { e.preventDefault(); win.hide(); })`,
  espelho de `dervs.py:1487-1488`;
- `app.on("window-all-closed")` **não** encerra o app;
- bandeja com exatamente três itens, nas palavras de `textos.md`: **Abrir DERVS**, **Recolher
  janela**, **Sair do DERVS** (C8 do spec; "Trazer o selo de volta" não existe mais). "Sair do
  DERVS" manda o verbo `sair` ao Python e só se autoencerra se o pai não fechar em 3 s;
- tooltip da bandeja muda com o estado, na tabela de `textos.md`: `DERVS`, `DERVS — ouvindo
  você`, `DERVS — pensando`, `DERVS — respondendo`, `DERVS — precisa de atenção`;
- `stdin` fechado significa que o pai morreu: `app.quit()`.

**Fazer:**
- `package.json` com `"main": "main.js"`, nome `dervs`, sem script que use rede, e a versão do
  Electron **travada em versão exata** (sem acento circunflexo), no espírito do
  `requirements.txt`.
- `main.js`: `BrowserWindow` de 420x560, `minWidth` 360, `frame: false`, `backgroundColor`
  `#050810`, ícone do app; `webPreferences` com `preload`, `contextIsolation: true`,
  `nodeIntegration: false` e `sandbox: true`; `setWindowOpenHandler` negando tudo e
  `will-navigate` bloqueado (o conteúdo é local e hostil por definição); leitura do `stdin`
  com `readline`; repasse de cada verbo ao renderer por `webContents.send`; envio de `pronto`,
  `sair` e resposta de plano pelo `stdout`. **Nada além dos verbos do contrato pode ir para o
  `stdout`** — `console.log` é proibido neste processo (sujaria o canal); diagnóstico vai para
  `console.error`.
- `preload.js`: expõe exatamente a API `window.dervs` do contrato, e nada mais.
- A bandeja usa `electron/assets/bandeja-16.png` e `bandeja-32.png` (Etapa 5).

**Verificação:** `cd electron && npm install` conclui; `node --check main.js` e `node --check
preload.js` sem erro; rodar o binário do Electron apontando para a pasta sobe a janela (aceita-
se tela preta com os cantos, o HUD é da Etapa 8); a bandeja aparece com os três itens; clicar
no X esconde a janela e o processo continua vivo; "Sair do DERVS" escreve o verbo `sair` no
stdout (rodar com o stdout redirecionado para arquivo e conferir); matar o processo pai fecha
a janela sozinha.

**Depende de:** Etapa 5 (PNG da bandeja).

### Etapa 8 — a janela: HUD, cinco estados e a onda

**Objetivo:** o dono abre e vê o núcleo com os anéis girando, reagindo à própria voz, com os
textos certos em cada um dos cinco estados.

**Arquivos:** `electron/renderer/index.html`, `electron/renderer/estilo.css`,
`electron/renderer/hud.js` (novos).

**Contexto:** o `design.md` é a fonte da verdade de cor, forma e tipografia; o `textos.md` é a
fonte da verdade das **palavras**. Onde o `textos.md` cita cor da Direção C (`--rosa`,
`--limao`, `--bg-elevado`), vale o `design.md`. Tokens exatos, sem inventar nenhum: `--bg`
`#050810`, `--painel` `#0A1220`, `--acento` `#00E5FF`, `--acento-fraco` `#0A6E82`,
`--nucleo-quente` `#FFFFFF`, `--texto-primario` `#D9F6FF`, `--texto-secundario` `#5C8A99`,
`--erro` `#FF3B3B`. Uma cor de marca só; vermelho **apenas** no erro.

**Fazer:**
- `index.html` com CSP fechada no `meta`: `default-src 'none'`, `img-src 'self' data:`,
  `style-src 'self'`, `script-src 'self'`, `font-src 'self'`. Estrutura: nome `DERVS`
  (Orbitron 700, caixa alta, ancorado no topo), `canvas` quadrado central, rótulo de estado
  acima do núcleo, leitura técnica `AMP 0.xx` (Share Tech Mono, 9-10px) ao lado do núcleo,
  área de conversa (só a última troca), cartão de aviso e cartão de plano.
- `estilo.css`: `@font-face` apontando para `fontes/` (Etapa 6) com fallback declarado; grade
  de fundo em `linear-gradient` repetido, linhas de 1px em `rgba(0,229,255,.025)` a cada 26px;
  marcas em L nos quatro cantos (2px em `--acento`, 22px de comprimento); raio de borda de 0 a
  2px em tudo; nenhuma sombra de UI (o único brilho é o do núcleo, no canvas).
- `hud.js`, Canvas 2D, com **um** `requestAnimationFrame`:
  - núcleo com gradiente radial (branco no centro para `--acento`) e `shadowBlur` proporcional
    ao volume; anéis segmentados girando; ticks radiais tipo dial;
  - **ocioso**: o núcleo pulsa devagar por conta própria e os anéis giram devagar — nunca
    parado ("o sistema nunca aparenta estar desligado");
  - **ouvindo**: rotação e brilho proporcionais ao volume; `AMP 0.xx` atualizando; rótulo
    `ouvindo` em Orbitron 700/22px, caixa alta por CSS, cor `--acento`;
  - **pensando**: rótulo `pensando`, rotação constante e moderada, sem reagir a volume;
  - **falando**: rótulo `falando`, mesmo motor do ouvindo, alimentado pelo volume que chega
    (que nessa hora vem do `.wav` do DERVS);
  - **erro**: os anéis desaceleram e mudam para `--erro`; cartão em `--painel` com borda
    `--erro`, o ícone de erro **inline** (SVG da seção 3 do `assets.md`), a frase exata de
    `textos.md` e, quando o Python mandar `apoio`, a linha de apoio em 13px
    `--texto-secundario`;
  - suavização do volume (média móvel curta), para a onda não tremer por causa do
    estrangulamento de 50 ms;
  - quando a janela está escondida, **pare o `requestAnimationFrame`**
    (`visibilitychange`/`document.hidden`) — régua de CPU do C10.
- Conversa: só a última troca; `papel` decide o rótulo ("você" / "DERVS"); **sempre
  `textContent`, nunca `innerHTML`**.
- Cartão de plano (ver Decisão C): lista dos passos com o rótulo que o Python mandou, a
  pergunta, e dois botões — "Confirmar" e "Cancelar" — chamando `window.dervs.responderPlano`.
  Passo de nível `destrutivo` marcado em `--erro`.
- Em 360px de largura tudo continua legível: o canvas encolhe proporcionalmente e rótulo e
  leitura técnica ficam ancorados nas bordas.

**Verificação:** com a Etapa 7 no lugar, subir o Electron alimentando o `stdin` com um roteiro
de linhas (arquivo com `estado`, `volume`, `fala`, `plano` e `mostrar`) e conferir um a um os
cinco estados na tela; `node --check hud.js`; procurar `innerHTML` no renderer **não pode
achar nada**. Critério visual do dono fica para a Etapa 12.

**Depende de:** Etapas 6 e 7.

### Etapa 9 — `dervs_electron.py`: o novo ponto de entrada

**Objetivo:** o processo Python continua dono de tudo — trava de instância, daemons, cérebro,
trilhos de risco — e agora a cara dele é o Electron.

**Arquivos:** `dervs_electron.py` (novo), `test_dervs_electron_entrada.py` (novo).

**Contexto:** copie o miolo de `dervs.py:1666-1713`: `registro.colher_anterior()`,
`registro.instalar()`, `faxina_de_audio(TMP)`, `instancia.tomar_posse(...)`, `QApplication`,
`app.setQuitOnLastWindowClosed(False)`, e `encerrar_tudo(pop)` mais `posse.soltar()` no
`aboutToQuit`. **`Launcher` e `_montar_bandeja` não são usados.** A `Ponte` do Qt
(`dervs.py:1491-1501`) é substituída por `ponte.enviar_mostrar()` chamado direto da thread do
socket — pode, porque a ponte é thread-safe e **não toca em widget nenhum**; a armadilha do
`QTimer.singleShot` fora da thread do Qt (documentada em `dervs.py:1494-1499`) não se aplica
aqui, e isso merece um comentário no código para ninguém "consertar" depois.

**Fazer:**
- `class Motor(dervs.PopUp)`, criada mas **nunca mostrada**:
  - `abrir()` e `show()` sobrescritos para chamar `self.ponte.enviar_mostrar()` — a janela Qt
    jamais aparece;
  - `_diz(papel, texto, cor=None)` chama `super()` e manda `fala`;
  - `_ocupado(on, msg)` chama `super()` e empurra o estado `pensando` quando `on` é verdadeiro;
  - `_recado_do_ouvido(texto, cor)` chama `super()` e empurra `estado` `erro` com a frase de
    `textos.md` correspondente (sem som / microfone desconectado / um ajudante caiu / sem
    internet) e a linha de apoio nos casos 2, 3 e 4;
  - `_confirmar_plano()` chama `super()` e manda `plano` com os passos, o nível e a pergunta;
    `cancelar_plano()` e o fim do plano mandam `plano` com lista vazia;
  - `atualizar()` — o relógio de 500 ms que já existe (`dervs.py:619-620`) — chama `super()` e,
    **só quando mudou**, empurra `estado`: `erro` se há recado do ouvido ou de queda; `falando`
    se `self.voz.falando()`; `pensando` se `self._tarefa` não é `None` ou `self._transcrevendo`;
    `ouvindo` se `self.escuta` não é `None`; senão `ocioso` (Decisão B). **Sem timer novo** —
    régua do C10.
- Ligações de volume: o sinal `nivel` da `Escuta` vai para `ponte.enviar_volume` (ligado logo
  depois de `alternar_conversa` criar a escuta), e `self.voz.ao_nivel = ponte.enviar_volume`.
- Vindo do Electron: `sair` chama `app.quit()` (o `aboutToQuit` já faz `encerrar_tudo` e
  `posse.soltar`); resposta de plano `confirmar` chama `confirmar_plano_ok()` ou
  `confirmar_passo()` conforme o estado (`dervs.py:1249` e `:1388`); `cancelar` chama
  `cancelar_plano()`; `pronto` despeja o estado guardado.
- Se o Electron não subir (`FileNotFoundError` da ponte): escreve o motivo em português no
  `sys.stderr`, solta a posse e sai com código 1 — nunca fica um DERVS invisível rodando.
- Testes com `importorskip("PyQt6")` e dublagem no estilo de `test_dervs_encerrar.py`, com
  ponte dublê e sem subir Electron de verdade: depois de `Motor().abrir()`, **`isVisible()` é
  `False`** e a ponte recebeu `mostrar` (prova de que não sobram duas interfaces); `_diz` manda
  `fala`; `_ocupado(True)` manda `estado pensando`; `_recado_do_ouvido` manda `estado erro` com
  a frase de `textos.md`; o callback de instância única (que roda em outra thread) empurra
  `mostrar` sem tocar em Qt; `sair` leva a `encerrar_tudo` e `posse.soltar()`; e a trava de
  instância continua sendo a de `dervs_instancia.py` (o teste monta uma `Posse` e confirma que
  um segundo chamador é recusado — **reuso, não recriação**).

**Verificação:** `./dervs-venv/Scripts/python.exe -m pytest test_dervs_electron_entrada.py
test_dervs_instancia.py -q` verde, e a suíte inteira sem regressão.

**Depende de:** Etapas 2, 3 e 4 (a Etapa 7 é necessária só para rodar de ponta a ponta, o que
acontece na Etapa 12; aqui a verificação é com dublê).

### Etapa 10 — o atalho passa a abrir a cara nova

**Objetivo:** o mesmo atalho de sempre, com o ícone novo, abre a janela nova. Nada muda para o
dono no "como abrir".

**Arquivos:** `scripts/instalar_atalho.py`, `dervs.ico` (regerado).

**Contexto:** `ATALHOS` em `scripts/instalar_atalho.py:105-110`; `_png_de(px)` em `:37-45`;
`gerar_icone()` em `:48-76` — **a estrutura de empacotamento do `.ico` continua igual**
(`assets.md`, seção 1). O segundo atalho (`DERVS - Transcrever audio`) **não muda**. `dervs.py`
continua no disco e continua abrindo se alguém o chamar na mão (corte #8 do spec).

**Fazer:**
- No primeiro item de `ATALHOS`, trocar `dervs.py` por `dervs_electron.py`; continua com
  `pythonw.exe` e a mesma descrição.
- `_png_de(px)` passa a desenhar `scripts/icone_hud.pixmap(px)` em vez de `dervs._selo(px)`, e
  o docstring do módulo (`:9-10`) é corrigido junto, porque ele afirma que o ícone vem do selo
  da janela.
- Regerar `dervs.ico` com os dez tamanhos de `TAMANHOS` (`:34`).

**Verificação:** `./dervs-venv/Scripts/python.exe scripts/instalar_atalho.py` termina sem erro
e imprime os atalhos; `dervs.ico` mudou de tamanho/data; o `.lnk` da Área de Trabalho aponta
para `dervs_electron.py` (conferir lendo o atalho com `WScript.Shell` no PowerShell); o ícone
novo aparece na Área de Trabalho (critério visual).

**Depende de:** Etapas 5 e 9.

### Etapa 11 — `arquitetura-agente.md`

**Objetivo:** o dono tem, por escrito, a comparação das cinco opções e uma recomendação de
caminho seguro — o segundo entregável do briefing. **Nenhum código, nenhuma instalação.**

**Arquivos:** `docs/esteira/dervs-cara-nova/arquitetura-agente.md` (novo).

**Contexto:** todas as fontes já estão levantadas e datadas em `spec.md`, seção
`fontes_externas` (consultadas em 15/09/2026) — **use aquelas, com link e data; não saia
pesquisando de novo**. Decisões já tomadas que o documento precisa refletir: C1 (avalia os três
por nome e propõe uma ordem de prioridade dos cinco alvos, começando pelo navegador, que é o
único com código e teste no repositório — `dervs_browser.py`), C2 (recomenda **contra** o
OpenClaw como peça de controle, **em destaque visível, não em nota de rodapé**), C3 (a
recomendação é o agente ouvinte local com conexão de saída, com os dois precedentes: runner
self-hosted do GitHub Actions e `remote-workstation-mcp`), C5 (LiveKit avaliado por nome, com
custo e licença, sem adoção), C6 (a API da OpenAI vence a IA no VPS, com os números) e C11 (as
latências são de fonte pública datada, **não medidas nesta máquina** — dito no documento).

**Fazer:** documento em português do Brasil, escrito para o dono ler (não para programador),
com: uma seção por ferramenta (o que é, licença, maturidade, custo, latência, risco); a seção
de destaque sobre o OpenClaw (Bitsight: mais de 30 mil instâncias expostas, honeypot atacado
minutos depois de subir; alerta do CNCERT; Giskard: vazamento de dado e prompt injection); API
da OpenAI contra IA no VPS com os números (cerca de US$ 54/mês do VPS, ponto de equilíbrio
entre 10 e 30 milhões de tokens por dia, TTFT de 200 a 600 ms pela API); a recomendação do
agente ouvinte local, explicando em linguagem simples por que o PC **nunca** abre porta de
entrada e por que o porteiro e o `dervs_safety.py` continuam decidindo na máquina; a ordem de
prioridade dos cinco alvos de controle; e uma seção final de limites honestos. Citar
`ESTADO.md:130-135` (a página que já tentou dar ordem ao cérebro) como o adversário real, não
teórico.

**Verificação:** o arquivo existe e cita, por nome, Hermes Agent, LiveKit, OpenClaw, API da
OpenAI e IA no VPS; toda afirmação de custo ou risco tem link com data; a ressalva do OpenClaw
está em seção própria, antes da recomendação; não há um único comando de instalação no
documento. Revisão humana na fase 6.

**Depende de:** nenhuma.

### Etapa 12 — integração, régua de CPU e demonstração ao vivo

**Objetivo:** provar, rodando, que a entrega faz o que o briefing exige — e que nada regrediu.

**Arquivos:** nenhum. É etapa de verificação; se achar defeito, o conserto volta para a etapa
dona do arquivo.

**Fazer e verificar, nesta ordem:**
1. `cd electron && npm install` conclui.
2. `./dervs-venv/Scripts/python.exe -m pytest -q` com **543 mais os novos, zero falhas e zero
   erro de coleta**; e `python -m pytest -q` no Python do sistema sem erro de coleta (os de Qt
   pulados).
3. Abrir pelo atalho da Área de Trabalho: a janela nova abre, os anéis giram, e **não** aparece
   nem selo nem janela Qt.
4. Falar perto do microfone (ou, se o microfone físico continuar desconectado — `ESTADO.md`,
   item 2.1 —, injetar áudio por um dublê): a onda reage, o rótulo `ouvindo` aparece e a
   leitura `AMP` muda.
5. Fazer uma pergunta: `pensando` aparece no intervalo, `falando` aparece na resposta **e a
   onda reage à voz do DERVS** (é o C9, a metade da entrega que estava em risco).
6. Pedir algo que vire plano: o cartão aparece, "Cancelar" cancela e "Confirmar" executa —
   trilho de risco intacto.
7. Clicar de novo no atalho com o DERVS aberto: **traz a janela para frente**, não abre um
   segundo (`dervs_instancia.py` reusada).
8. O X da janela esconde; na bandeja, "Abrir DERVS" traz de volta, "Recolher janela" esconde e
   "Sair do DERVS" encerra tudo — conferir que **não sobra** processo de Python, de Electron,
   do daemon de STT nem do de voz.
9. Desconectar o microfone (ou simular): o estado `erro` aparece com a frase de `textos.md`.
10. **Régua do C10:** com a janela aberta e ociosa por 2 minutos, medir o uso de CPU do
    conjunto (Python mais Electron) e comparar com o DERVS de hoje (`dervs.py`) na mesma
    condição. Anotar os dois números no relatório da etapa. Se o novo for muito pior, o
    conserto é no `requestAnimationFrame` e no estrangulamento — não "aceitar assim".
11. **A demonstração ao vivo para o dono** — critério de aceitação explícito do briefing: ele
    vê a onda reagindo à própria voz antes de a entrega ser dada como pronta.

**Depende de:** Etapas 1 a 10.

### Etapa 13 — documentação andando junto

**Objetivo:** a documentação descreve o software de hoje, não o de ontem.

**Arquivos:** `README.md`, `COMO-USAR.md`, `ESTADO.md`, `DERVS-EXECUTAR.md` e, se for o caso,
um comentário em `requirements.txt`.

**Fazer:** registrar o que mudou de verdade — o ponto de entrada (`dervs_electron.py`), o passo
novo de montagem (`cd electron && npm install`), a pasta `electron/`, a bandeja de três itens,
o fim do selo flutuante nesta rodada (e que ele volta na v2 se fizer falta), que `dervs.py`
continua no disco como caminho de volta (corte #8), o número novo de testes, e a consequência
da Decisão D (como desligar o microfone hoje). No `ESTADO.md`, atualizar a tabela "o que está
funcionando" e a data da última verificação, com os números medidos na Etapa 12.

**Verificação:** ler os quatro arquivos procurando qualquer frase que descreva a interface
antiga como atual; `grep -rn "dervs.py" README.md COMO-USAR.md DERVS-EXECUTAR.md` e conferir
que cada ocorrência ainda é verdadeira.

**Depende de:** Etapa 12.

---

## Paralelização

**Podem rodar juntas (nenhuma interseção de arquivos):**

- **Onda 1 — 5 executores:** Etapas **1, 2, 5, 6 e 11**.
- **Onda 2 — 3 executores:** Etapas **3, 4 e 7**.
- **Onda 3 — 2 executores:** Etapas **8 e 9**.
- **Onda 4:** Etapa **10**.
- **Onda 5:** Etapa **12**.
- **Onda 6:** Etapa **13**.

**Sequencial obrigatório, e por quê:**

- 1 antes de 3 e de 4: as duas importam `dervs_nivel`.
- 2 antes de 7 e de 9: o formato da linha tem de existir antes de quem fala e de quem escuta.
- 5 antes de 7 (PNG da bandeja) e antes de 10 (`icone_hud` antes de o `.ico` ser regerado).
- 6 antes de 8 (a fonte precisa existir para o `@font-face` valer).
- 7 antes de 8: o renderer só é verificável com a casca de pé.
- 3 e 4 antes de 9: o motor liga sinais que precisam existir.
- 9 antes de 10: o atalho não pode apontar para um arquivo que ainda não existe.
- 10 e 8 antes de 12; 12 antes de 13.

**Arquivos com dono único (nunca dois executores no mesmo arquivo):** `dervs.py` só na Etapa 3;
`dervs_tts.py` só na 4; `scripts/instalar_atalho.py` e `dervs.ico` só na 10;
`electron/main.js`, `preload.js`, `package.json` e `.gitignore` só na 7; os três arquivos de
`electron/renderer/` só na 8; `electron/renderer/fontes/` só na 6; `assets/`,
`scripts/icone_hud.py` e `scripts/gerar_icones.py` só na 5.

**Caminho crítico (a sequência mais longa de dependências):** **1 → 3 → 9 → 10 → 12 → 13**,
seis etapas. O ramo visual (2 → 7 → 8 → 12 → 13) tem cinco e cabe dentro dele, desde que a
Onda 1 seja despachada inteira de uma vez.

---

## O que eu não consegui confirmar

- **Se `npm install electron` funciona nesta máquina** (rede, proxy, antivírus). Não instalei
  nada: sou planejador. Se falhar, as Etapas 7, 8 e 12 travam e as de Python seguem.
- **Se a `PopUp` roda 100% bem sem nunca ser mostrada.** Li o suficiente para ter confiança
  (os `show()` internos são de widgets filhos — `chat`, `barra` — dentro de um pai escondido, e
  `QTimer`/`QProcess` não pedem janela), mas isso só vira fato com a Etapa 9 rodando. É o
  principal risco técnico do plano, e está concentrado numa etapa só de propósito.
- **Se o microfone físico do dono já foi ligado** (`ESTADO.md`, item 2.1: as duas entradas rosa
  apareciam DESCONECTADO em 02/09). Se ainda não foi, a demonstração ao vivo da Etapa 12 não
  acontece com a voz dele — e o critério de aceitação do briefing depende disso. **Vale
  perguntar ao dono antes da Onda 1.**
- **Se o `.wav` do Kokoro é sempre PCM de 16 bits.** O `envelope_do_wav` já trata o caso
  contrário devolvendo lista vazia, então o pior caso é a onda ficar parada enquanto ele fala,
  não quebrar. Confirmação real só na Etapa 12, item 5.
- **Quanto de CPU o conjunto Electron mais Python realmente gasta** nesta máquina sem placa de
  vídeo dedicada. O C10 divulgou o custo; a medição é da Etapa 12.

**Uma observação que não virou etapa, como manda a regra de escopo:** `dervs_painel.py`,
`falar.sh` e `ligar-voz-com-senha.sh` continuam sendo peso morto de Linux (`ESTADO.md`, 4.7), e
o `_selo()` e o `Launcher` do Qt ficam sem uso de circulação depois desta rodada. Nada disso é
tocado aqui — some junto com o PyQt6 quando o corte #8 for revisto, numa rodada própria.
