# Grimoire — companheiro de voz

Selo flutuante na bandeja. Você fala → transcreve → o cérebro entende e propõe um
plano → você confirma → ele executa (abre apps, sites, roda comandos). Fala de
volta com voz humana.

Detalhe completo em **[GRIMOIRE-EXECUTAR.md](GRIMOIRE-EXECUTAR.md)**.

## A espinha (2026-08-30)

- **Ouvido:** OpenAI `gpt-4o-mini-transcribe` (~2,6s, preciso). Reserva: Whisper local.
- **Cérebro:** OpenAI `gpt-4.1-nano` (~1,5–3s, barato). Reserva: Claude CLI local.
- **Voz:** Kokoro `pm_santa` (humana, offline, grátis, ~0,6s). Reserva: Piper.
- **Comportamento:** confirma antes de executar (entende → pede OK → faz).

Custo estimado de uso pesado (~300 interações/dia): **~US$ 5–6/mês** (voz é grátis).

## Rodar e gerenciar

```bash
systemctl --user restart grimoire     # reinicia (aplica mudança de código/config)
systemctl --user status grimoire      # estado
journalctl --user -u grimoire -n 50   # log
python -m pytest -q                    # testes (só `python -m pytest` nesta máquina)
```

## Configuração

Arquivo editável: `~/.config/grimoire/config.json` (criado sozinho no 1º boot).
Chaves: `stt`, `stt_openai_modelo`, `cerebro`, `cerebro_openai_modelo`, `motor`,
`voz_kokoro`, `voz`, `janela_desperto_seg`, `atalhos_ligados`. Mudou → reinicie.

## Segredo

`OPENAI_API_KEY` mora em `~/voice/.env` (chmod 600, fora do git). Nunca é logada
nem commitada.

## O que fica fora do git

Ambientes Python (`*-venv/`), modelos (`kokoro-model/`, `vosk-*`, `piper-voices/`),
`.env`, `.wav`, `.log`. Ver `.gitignore`. Ainda **sem remoto no GitHub** (local).
