# DERVS — companheiro de voz (Windows)

> **Origem:** este projeto é o irmão Windows do
> [`thi-garcia/grimoire-voz`](https://github.com/thi-garcia/grimoire-voz), que roda
> no Parrot OS (Linux). O original continua onde está.
>
> **Para quem só quer usar:** leia **[COMO-USAR.md](COMO-USAR.md)**, escrito sem
> jargão. Este README é para quem vai mexer no código.

Selo flutuante na bandeja. Você fala → transcreve → o cérebro entende e propõe um
plano → você confirma → ele executa (abre apps, sites, roda comandos). Fala de
volta com voz humana.

Detalhe completo em **[DERVS-EXECUTAR.md](DERVS-EXECUTAR.md)**.

## A espinha (2026-09-01)

O desenho é um **funil**: cada estágio custa mais que o anterior e só roda se o
anterior deixar passar. É isso que permite deixar ligado o dia inteiro.

| # | Estágio | Onde | Custo |
|---|---|---|---|
| 1 | Fim de fala (`Endpointer`, energia + histerese) | local | zero |
| 2 | **Porteiro** — "foi comigo?" (`dervs_porteiro.py`, Whisper `tiny` com aviso de vocabulário) | **local** | **zero** |
| 3 | Transcrição precisa — OpenAI `gpt-transcribe`. Reserva: Whisper local | nuvem | US$ 0,0045/min |
| 4 | Cérebro — OpenAI `gpt-4.1-nano`. Reserva: Claude CLI | nuvem | barato |
| 5 | Voz — Kokoro, velocidade 1,2. Reserva: Piper | local | zero |

**Nada sai da máquina antes do estágio 2 abrir**, e isso é travado por teste
(`test_dervs_porteiro.py::test_porteiro_nao_manda_audio_para_a_nuvem`). A
gravação de cada frase é apagada depois de usada, inclusive a que o porteiro
recusa (`test_dervs_privacidade.py`).

Custo estimado de uso pesado (~300 interações/dia): **~US$ 5–6/mês**. Sem o
funil, ligado 8 h/dia, só a transcrição daria ~US$ 43/mês.

O porteiro é peça trocável (`criar_porteiro`). Hoje só existe o local; o encaixe
para o Picovoice Porcupine está documentado em `dervs_porteiro.py`.

## Rodar e gerenciar

No Windows, do diretório do projeto:

```
dervs-venv\Scripts\python.exe dervs.py            # abre o DERVS
dervs-venv\Scripts\python.exe -m pytest -q        # testes (284 verdes)
dervs-venv\Scripts\python.exe amostras_de_voz.py  # gera amostras das 3 vozes
```

Ainda **não** há serviço que suba sozinho no boot — está fora do escopo desta
rodada, de propósito, até o comportamento estabilizar.

No Linux (repositório irmão) o serviço continua sendo `systemctl --user`.

## Configuração

No Windows fica em `%APPDATA%\dervs\config.json`; no Linux, em
`~/.config/dervs/config.json`. Criado sozinho no 1º boot. Para descobrir o
caminho: `python -c "import dervs_config as c; print(c.CONFIG_PATH)"`.

Chaves: `stt`, `stt_openai_modelo`, `porteiro`, `porteiro_modelo`, `cerebro`,
`cerebro_openai_modelo`, `motor`, `voz_kokoro`, `voz`, `voz_velocidade`,
`janela_desperto_seg`, `atalhos_ligados`, e as do navegador. Valor inválido cai
no padrão em vez de derrubar o app (`_validar`). Mudou → reinicie.

## Segredo

`OPENAI_API_KEY` é procurado por `dervs_config.segredo()`, nesta ordem:
variável de ambiente → arquivo de segredos ao lado da configuração → o caminho
antigo da máquina irmã. Nunca é registrado em log nem commitado.

Ver o caminho certo:
`python -c "import dervs_config as c; print(c.caminhos_do_segredo()[0])"`.

## O que fica fora do git

Ambientes Python (`*-venv/`, `dervs-venv/`), modelos, o arquivo de segredos,
`.wav`, `.log`, `amostras_voz/` e `.claude/worktrees/`. Ver `.gitignore`.

## O estado da portabilidade (01/09/2026)

**Feito:** captura e reprodução de áudio por `sounddevice` (sem `arecord`,
`pw-play` nem `pw-record`); porteiro local invertendo a ordem nuvem/portão;
atalhos, execução, rede de segurança e prompt do cérebro com vocabulário do
Windows; configuração e segredo nos caminhos do Windows; colar por
`keybd_event` no lugar do `ydotool`; gravações apagadas depois de usadas.
**284 testes passam, zero falham** (antes: 112 passavam e 4 falhavam).

**Falta:**

| Peça | Situação |
|---|---|
| Chave da OpenAI nesta máquina | **bloqueia** a transcrição precisa e o cérebro. Depende do dono |
| Medir o tempo de resposta ponta a ponta | depende da chave |
| Reconhecer a voz do dono no ruído real dele | o porteiro foi medido com voz sintetizada |
| Serviço que sobe sozinho no boot | fora de escopo desta rodada, de propósito |
| `dervs_enrich.py` (OSINT com `bbot`) | `bbot` não roda em Windows. Fica desligado |
| `dervs_painel.py` | legado, ninguém importa. Fica como está |
| `falar.sh`, `ligar-voz-com-senha.sh` | scripts do Linux, ainda não traduzidos |
| Navegador autônomo ponta a ponta | caminho do perfil do Chrome corrigido, mas não validado |

Detalhe e medições: `docs/esteira/windows-tempo-real/`.
