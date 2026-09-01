# DERVS — companheiro de voz (Windows)

> **Origem:** este projeto é o irmão Windows do
> [`thi-garcia/grimoire-voz`](https://github.com/thi-garcia/grimoire-voz), que roda
> no Parrot OS (Linux). O código é o mesmo, com o agente renomeado de *Grimoire*
> para *DERVS*. O original continua onde está e segue sendo o de Linux.
>
> **A portabilidade para Windows ainda NÃO foi feita.** O que já está adaptado é
> só o nome — incluindo a palavra de acordar, que foi recalibrada para "dervs"
> (ver `dervs_listen.py`). O que ainda é de Linux está listado em
> *[O que falta para rodar no Windows](#o-que-falta-para-rodar-no-windows)*.

Selo flutuante na bandeja. Você fala → transcreve → o cérebro entende e propõe um
plano → você confirma → ele executa (abre apps, sites, roda comandos). Fala de
volta com voz humana.

Detalhe completo em **[DERVS-EXECUTAR.md](DERVS-EXECUTAR.md)**.

## A espinha (2026-08-30)

- **Ouvido:** OpenAI `gpt-4o-mini-transcribe` (~2,6s, preciso). Reserva: Whisper local.
- **Cérebro:** OpenAI `gpt-4.1-nano` (~1,5–3s, barato). Reserva: Claude CLI local.
- **Voz:** Kokoro `pm_santa` (humana, offline, grátis, ~0,6s). Reserva: Piper.
- **Comportamento:** confirma antes de executar (entende → pede OK → faz).

Custo estimado de uso pesado (~300 interações/dia): **~US$ 5–6/mês** (voz é grátis).

## Rodar e gerenciar

```bash
systemctl --user restart dervs     # reinicia (aplica mudança de código/config)
systemctl --user status dervs      # estado
journalctl --user -u dervs -n 50   # log
python -m pytest -q                    # testes (só `python -m pytest` nesta máquina)
```

## Configuração

Arquivo editável: `~/.config/dervs/config.json` (criado sozinho no 1º boot).
Chaves: `stt`, `stt_openai_modelo`, `cerebro`, `cerebro_openai_modelo`, `motor`,
`voz_kokoro`, `voz`, `janela_desperto_seg`, `atalhos_ligados`. Mudou → reinicie.

## Segredo

`OPENAI_API_KEY` mora em `~/voice/.env` (chmod 600, fora do git). Nunca é logada
nem commitada.

## O que fica fora do git

Ambientes Python (`*-venv/`), modelos (`kokoro-model/`, `vosk-*`, `piper-voices/`),
`.env`, `.wav`, `.log`. Ver `.gitignore`. Ainda **sem remoto no GitHub** (local).

## O que falta para rodar no Windows

Levantado em 01/09/2026, com `python -m pytest` rodando nesta máquina:
**112 testes passam, 4 falham** — todos os 4 em `test_dervs_atalhos.py`, e todos
pelo mesmo motivo: os atalhos abrem programas que só existem no Linux.

| Peça | Hoje (Linux) | Precisa virar |
|---|---|---|
| Atalhos de app (`dervs_atalhos.py`) | `firefox`, `konsole`, `kcalc` | equivalentes do Windows |
| Ligar/desligar o serviço | `systemctl --user` | Tarefa Agendada ou atalho na Inicialização |
| Scripts `falar.sh`, `ligar-voz-com-senha.sh` | shell do Linux | `.ps1` (PowerShell) |
| Painel (`dervs_painel.py`) | `ydotool`, `pgrep`, XWayland/KDE | envio de tecla e bandeja do Windows |
| Aviso na tela | `notify-send` | notificação do Windows |
| Caminho da configuração | `~/.config/dervs/config.json` | `%APPDATA%\dervs\config.json` |
| Voz (Kokoro/Piper) e ouvido | binários Linux | conferir build para Windows |

O que **não** depende do sistema e já deve funcionar: cérebro, transcrição pela
OpenAI, detecção de fim de fala e a palavra de acordar.
