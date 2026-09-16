# Lente do Arquiteto — Dervs cara nova (PyQt6 → Electron)

Investigação só de dentro do repositório. Fonte do índice: grafo de código já
pronto e no commit atual (`index_status` → `head_sha` bate com o `HEAD` do
repo, não precisou reindexar).

## 1. Como a interface PyQt6 está estruturada hoje

Tudo mora num arquivo só: `dervs.py` (raiz do repo).

- **Selo flutuante (o ícone redondo sempre no topo, embaixo da tela):**
  classe `Launcher(QtWidgets.QWidget)`, `dervs.py:1504-1602` (aprox., a classe
  começa em 1504). Desenha o selo com `_selo()` (`dervs.py:202-238`, um
  `QPainter` fazendo losango + faceta dourada + ponto aceso quando gravando).
  `Launcher._pos_canto()` (`dervs.py:1524`) fixa a posição embaixo, centralizado;
  `_dentro_da_tela()` (`dervs.py:1528-1540`) é a trava que impede o selo de sair
  da tela ao arrastar — corrigida em 02/09 depois do selo "sumir" de vez (ver
  seção 4).
- **Janela principal (o pop-up com a conversa):** classe `PopUp(QtWidgets.QWidget)`,
  `dervs.py:402` em diante (é a maior classe do arquivo, vai até perto da
  linha 1490). `PopUp.abrir()` está em `dervs.py:647`. Arrasto pelo cabeçalho:
  `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` em `dervs.py:1478-1489`
  (limitado à faixa `y() < 46`, sem checagem de borda de tela — diferente do
  selo). `closeEvent` (`dervs.py:1487-1488`) ignora o fechamento e só esconde
  (`e.ignore(); self.hide()`), coerente com "sempre um DERVS só" — fechar a
  janela nunca mata o processo.
- **Ícone de bandeja:** função solta `_montar_bandeja(app, launcher)`,
  `dervs.py:1640-1663`. Monta o `QSystemTrayIcon`, com menu "Abrir DERVS",
  "Trazer o selo de volta", "Recolher janela", "Sair do DERVS" (`app.quit`).
  Guarda de plataforma: se `QSystemTrayIcon.isSystemTrayAvailable()` for falso,
  devolve `None` sem quebrar.
- **Trava de instância única:** arquivo próprio, `dervs_instancia.py` (283
  linhas no total, cabeçalho em `dervs_instancia.py:1-29`). Não é lock de
  arquivo nem mutex do SO — é um servidor de socket TCP em `127.0.0.1` (nunca
  `0.0.0.0`), com porta e senha sorteadas gravadas em
  `%APPDATA%\dervs\instancia.json` junto do PID de quem abriu primeiro.
  Protocolo: quem abre depois manda `MOSTRAR <senha>` e espera exatamente
  `DERVS-OK` (`RESPOSTA_SIM`, `dervs_instancia.py:44`) — texto exato de
  propósito, porque "OK" solto combina com qualquer servidor HTTP que tenha
  herdado a porta. `_processo_vivo(pid)` (`dervs_instancia.py:51-77`) confere
  o PID antes de confiar no registro. A ponte entre a thread do socket (que
  recebe `MOSTRAR`) e a thread da tela (que precisa mostrar a janela) é a
  classe `Ponte(QtCore.QObject)` com sinal `chegou` (`dervs.py:1491-1501`) —
  o comentário no código documenta que `QTimer.singleShot` chamado de fora da
  thread do Qt **nunca dispara**, e que só um sinal do Qt atravessa a
  fronteira de thread de forma confiável. Isso é diretamente relevante para
  qualquer ponte nova Electron↔Python: o mesmo problema de thread existe em
  qualquer app com processo de fundo + UI de evento único.

**Sinal de volume de áudio já disponível hoje?** Não há sinal Qt exposto à UI
com o volume/nível do áudio. O que existe são duas funções puras de análise de
amplitude em `dervs_listen.py`:

- `rms(frame: bytes) -> float` (`dervs_listen.py:32-40`) — energia média de um
  quadro de 16 bits (`math.sqrt(sum(x*x...)/len(a))`).
- `pico(pcm: bytes) -> int` (`dervs_listen.py:291-302`) — amostra mais alta em
  módulo, 0 = silêncio absoluto.

Essas duas são usadas hoje só para decisão (fim de fala, detecção de mudo,
`VigiaDeSilencio`), nunca para desenhar nada. A classe `Escuta(QtCore.QThread)`
(`dervs.py:330-399`) lê quadro a quadro do microfone em loop (`self._mic.ler()`,
`dervs.py:362`) e só emite dois sinais: `fala` (caminho do `.wav` pronto) e
`mudo` (`dervs.py:335-338`) — nenhum sinal de nível contínuo. Ou seja: **o dado
de amplitude por quadro já é calculado a cada iteração do loop de escuta, mas
descartado depois da decisão binária.** É o ponto de menor esforço para
alimentar uma onda visual: bastaria emitir `rms(frame)`/`pico(frame)` como um
sinal novo do `Escuta`, em vez de calcular de novo.

## 2. Como o backend hoje se comunica entre processos

Não há RPC nem arquivo compartilhado — é **protocolo de linha por
stdin/stdout**, com o processo Qt (`dervs.py`) segurando um `QtCore.QProcess`
por daemon (`dervs.py:477-478`: `self.stt = QtCore.QProcess(self)`, canais
separados por `SeparateChannels`).

- **STT (`dervs_stt_daemon.py`)** — protocolo documentado no próprio cabeçalho
  do arquivo, `dervs_stt_daemon.py:25-30`:
  - ao subir, imprime `READY`;
  - app manda `PORTEIRO <caminho.wav>` → recebe
    `PORTEIRO {"acordou": true|false, "texto": "..."}`;
  - app manda `TRANSCREVER <caminho.wav>` → recebe `RESULT <json-do-texto>`.
- **Voz (Kokoro/Piper, `dervs_kokoro_daemon.py` / `dervs_piper_daemon.py`)** —
  mesmo estilo de protocolo, comentado como "IGUAL ao do Piper"
  (`dervs_kokoro_daemon.py:13`): `READY` ao carregar o modelo
  (`dervs_kokoro_daemon.py:92-93`), depois por frase falada devolve
  `WAV <caminho>\n` (`dervs_kokoro_daemon.py:111`, mandado **imediatamente**,
  frase por frase) e ao fim `FIM\n` (`dervs_kokoro_daemon.py:113`), ou
  `ERRO <motivo>` em caso de falha (`dervs_kokoro_daemon.py:117`).
- **Cérebro (`dervs_brain.py`)** não é um daemon próprio — é chamado
  diretamente em processo, via chamada HTTP para a API (OpenAI ou Claude CLI
  como reserva), dentro de uma `Tarefa(QtCore.QThread)` genérica
  (`dervs.py:241-255`) que roda qualquer função pesada fora da tela e emite
  `pronto`/`erro`.
- **Executor de comando (`dervs_exec.py`)** roda no mesmo processo Qt, também
  disparado dentro de uma `Tarefa`.
- **Instância única (`dervs_instancia.py`)** é o único canal que já é
  *socket* de verdade (ver seção 1) — e é o candidato natural a virar a base
  da ponte Electron↔Python, em vez de reinventar transporte: já resolve
  autenticação leve (senha sorteada), endereço restrito a loopback, e
  descoberta de "quem está vivo".

**Implicação direta para a ponte Electron:** a nova interface não fala com
STT/TTS diretamente — hoje só o processo Qt fala esse protocolo de linha via
`QProcess`. Duas rotas ficam abertas para o Electron: (a) manter um processo
Python de fundo (sem UI) que continua orquestrando os `QProcess`/daemons via
stdin/stdout como hoje, e expor um canal novo (socket local, nos mesmos moldes
de `dervs_instancia.py`) para o Electron mandar/receber eventos; ou (b) o
processo Node reimplementar a orquestração dos daemons em `child_process`,
falando o mesmo protocolo de linha diretamente. A opção (a) reaproveita mais
código testado (543 testes cobrem o lado Python hoje) e evita duplicar em
JS a lógica de religar daemon, vigiar timeout etc., já corrigida a duras penas.

## 3. O que já existe reaproveitável para a onda reagindo a volume real

- `rms()` e `pico()` em `dervs_listen.py:32-40` e `:291-302` — únicas funções
  de amplitude do projeto. Já testadas (`test_dervs_listen.py:127-129` para
  `rms`; `test_dervs_silencio.py:38-87` para `pico`, cobrindo silêncio
  absoluto, PCM vazio, byte solto no fim).
- O loop de leitura em `Escuta.run()` (`dervs.py:346-392`) já lê quadro a
  quadro (`frame = self._mic.ler()`, linha 362) num ritmo constante — é o
  lugar exato para acrescentar um terceiro sinal Qt (`nivel = pyqtSignal(float)`
  ou similar) sem tocar a lógica de decisão existente.
- Não achei nenhum uso de amplitude para o **porteiro** nem para o lado da
  fala do próprio Dervs (saída de voz) — os dois motores de voz
  (`dervs_kokoro_daemon.py`, `dervs_piper_daemon.py`) só devolvem o caminho de
  um `.wav` pronto (`WAV <caminho>`), nunca amplitude quadro a quadro. Para a
  onda reagir também **quando o Dervs fala** (pedido explícito no briefing),
  será preciso ler o `.wav` já gerado e calcular `rms`/`pico` por trecho do
  próprio arquivo (a função já existe e serve para isso, só falta o chamador),
  ou instrumentar a reprodução para emitir nível durante o playback — não
  achei código de playback/reprodução de áudio no repo (a busca por
  reprodução de voz não trouxe nada além dos daemons gerando o `.wav`; quem
  toca o áudio não apareceu nas buscas feitas, vale confirmar com mais uma
  varredura dedicada antes do plano).

## 4. O que quebra com a migração PyQt6 → Electron

Comportamentos corrigidos "a duras penas" e documentados em `ESTADO.md`, cada
um com o arquivo que hoje garante a correção:

| Comportamento | Onde vive hoje | Risco se recriado sem cuidado |
|---|---|---|
| Instância única + "traz para frente" | `dervs_instancia.py` inteiro + `Ponte` (`dervs.py:1491-1501`) | reimplementar do zero em Electron sem a trava de PID vivo (`_processo_vivo`, `dervs_instancia.py:51-77`) reintroduz o bug original ("cada clique abre mais um DERVS") |
| Bandeja com "Sair" | `_montar_bandeja` (`dervs.py:1640-1663`) | Electron/`Tray` API tem comportamento próprio; falta o item de sair = usuário preso de novo no Gerenciador de Tarefas |
| Selo não sai da tela ao arrastar | `Launcher._dentro_da_tela` (`dervs.py:1528-1540`) | é lógica por-monitor (`QApplication.screenAt`), não só "trava na tela principal" — precisa ser recriada com a mesma regra (não travar ao monitor primário) |
| Morte do daemon de STT escutada | ligações `finished`/`errorOccurred`/`readyReadStandardError` no `QProcess` do STT (linha ~477 em diante em `dervs.py`) | Electron falando com daemon via `child_process` precisa das mesmas 3 escutas — se só ligar `stdout`, volta o "DERVS surdo e calado" |
| Fechamento correto do microfone (corrida de threads) | `dervs.py`, `Microfone.fechar` (mora em `dervs_listen.py`, ver comentário em `dervs.py:258-262`) | é um bug de corrida específico do PortAudio/`sounddevice`; se a captura de áudio migrar para o lado Node (Web Audio / navegador), o risco muda de natureza mas a lição (uma única thread/dono pode fechar o stream) vale igual |
| `closeEvent` nunca mata o processo, só esconde | `dervs.py:1487-1488` | em Electron isso é `event.preventDefault()` no `close` da `BrowserWindow` — comportamento análogo, precisa ser copiado de propósito, não é o padrão do framework |

**Testes que cobrem isso hoje** (ver `ESTADO.md`, "543 testes verdes"):
`test_dervs_instancia.py` (9 testes citados no README, ex.
`test_o_primeiro_toma_posse`, `test_dervs_instancia.py:36-40`),
`test_dervs_listen.py`, `test_dervs_silencio.py`, `test_dervs_microfone.py`.
Note que 16 testes hoje só rodam no ambiente do projeto porque dependem do
PyQt6 (`ESTADO.md`, topo) — esses são exatamente os que cobrem `Launcher`,
`PopUp`, `Escuta`, `GravacaoManual`; uma migração para Electron torna esse
conjunto **obsoleto por definição** (não há mais PyQt6 para testar) e exige
equivalentes novos do lado Node/Playwright ou de contrato Python↔ponte.

**Quem depende da janela atual:** só o atalho e o menu Iniciar
(`scripts/instalar_atalho.py`, que também desenha `dervs.ico` a partir do
selo — `README.md:52-57`). Não há outro processo do repo que abra ou dependa
da janela Qt diretamente.

## 5. Convenções da casa

- **Nomes de arquivo:** `dervs_<assunto>.py` em português (`dervs_listen.py`,
  `dervs_brain.py`, `dervs_safety.py`, `dervs_instancia.py`, `dervs_registro.py`
  etc.), sempre minúsculo com underscore, um daemon por arquivo
  (`dervs_stt_daemon.py`, `dervs_kokoro_daemon.py`, `dervs_piper_daemon.py`,
  `dervs_tts_daemon.py`). Teste é `test_<mesmo nome>.py` na raiz — não há
  pasta `tests/`, tudo fica junto do código-fonte.
- **Framework de teste:** `pytest` puro (ver `pytest.ini`), com
  `--import-mode=importlib` — decisão explícita para não quebrar quando há
  cópias de trabalho paralelas em `.claude/worktrees/` (comentário longo em
  `pytest.ini:2-11`). `conftest.py` na raiz filtra qualquer coisa dentro de
  `.claude/` da coleta, inclusive quando o caminho é passado explicitamente na
  linha de comando (`pytest_ignore_collect` + `pytest_collection_modifyitems`,
  `conftest.py:30-49`). Código JS/Electron novo precisará de um equivalente —
  se usar Vitest/Jest, replicar a mesma exclusão de `.claude/worktrees` nas
  configs de teste novas, para não repetir o mesmo problema quando agentes
  trabalharem em paralelo.
- **Nomes de teste:** funções `test_<frase em português descrevendo o
  comportamento>`, nunca `test_case_1`. Exemplos:
  `test_o_primeiro_toma_posse`, `test_pico_de_silencio_absoluto_e_zero`,
  `test_qualquer_outra_coisa_nao_vaza_audio`. O nome do teste é a
  documentação do comportamento — convenção a manter em qualquer teste JS
  novo (nome descritivo em português, não `it("works")`).
- **Docstrings:** todo módulo e toda classe/função não-trivial tem docstring
  em português, muitas vezes contando o "porquê" e a data do incidente que
  motivou o código (ex. `dervs_instancia.py:1-29`, `Ponte` em
  `dervs.py:1491-1501`, `_montar_bandeja` em `dervs.py:1640-1663`). Não é só
  comentário de API — é registro de incidente. Vale manter esse padrão no
  código novo (Electron/ponte), especialmente em qualquer lógica que
  reproduza comportamento corrigido (citar o porquê evita alguém "limpar" a
  trava sem entender por que ela existe).
- **Tratamento de erro:** falha nunca é silenciosa por padrão — em vários
  lugares há comentário explícito sobre isso (`ESTADO.md`: "foi o
  `except Exception: pass` de bloco inteiro que manteve o `kill()`
  escondido"). Padrão observado: `try/except Exception as e` com
  `sys.stderr.write(...)` + `sys.stderr.flush()` explicando o que falhou (ver
  `GravacaoManual.run`, `dervs.py:303-305`; `Escuta.run`, `dervs.py:355-357`),
  nunca um `except` mudo. Falha de rede cai para reserva local em vez de
  travar (STT cai para Whisper local; cérebro cai para Claude CLI). Valor
  inválido de configuração cai no padrão em vez de derrubar o app
  (`dervs_config._validar`, citado no `README.md:73`). Esse é o padrão a
  copiar do lado Python da ponte nova: nunca engolir exceção sem log, e ter
  um caminho de reserva quando o canal de rede/IPC falha.

## Achados de "já existe, não precisa reconstruir"

- A trava de instância única já é, na prática, um protótipo funcional de
  "servidor local + segredo + comando por texto" (`dervs_instancia.py`) — é
  a peça mais reaproveitável para qualquer ponte Electron↔Python, mais do que
  escrever transporte novo.
- `rms()`/`pico()` já calculam exatamente o dado bruto que a onda visual
  precisa; falta só expô-los como sinal, não recalcular.

## O que não encontrei (e por isso não afirmei)

- Não encontrei nenhum código de **reprodução/playback** de áudio no
  repositório (quem toca o `.wav` que os daemons de voz geram) — as buscas no
  grafo e por `Popen`/`subprocess` em `dervs.py` não trouxeram um player.
  Isso importa para "a onda reage também quando o Dervs fala": vale uma
  varredura dedicada antes do plano de execução, porque pode estar em um
  daemon que não abri neste levantamento, ou pode não existir ainda como
  módulo isolado (pode estar embutido em `dervs_tts.py`, que não abri linha a
  linha).
