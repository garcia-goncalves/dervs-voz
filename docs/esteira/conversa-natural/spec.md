# Spec — Conversa natural (camada local + motor trocável)

Briefing: `docs/esteira/conversa-natural/briefing.md` (aprovado 15/10/2026).

## problema

O DERVS leva ~5 s do fim da fala ao primeiro som, soa robótico (frase inteira gerada e depois acelerada por WSOLA no PC), corta o dono em qualquer silêncio de 1,1 s, fica surdo enquanto fala (não dá para interromper) e não distingue o dono de outras pessoas, TV ou da própria voz saindo da caixa. Responde "Entendi: vou…" até para pedido trivial. E o dono não pode gastar muito: uso pesado diário, orçamento perto de zero no começo.

## solucao

Duas camadas, ligadas por um contrato pequeno:

1. **Camada local (no PC, grátis, igual para todo motor)**
   - `dervs_locutor.py` — perfis de voz e "quem fala". Modelo ERes2Net (sherpa-onnx, CPU ~65 ms por segundo de fala, 9/10 no teste de 15/10). Perfil = impressão numérica (`.npy`) + `perfil.json` `{nome, papel: "dono"|"convidado", ativo}` em `%APPDATA%\dervs\vozes\<slug>\`; nunca áudio. API: `Perfis(pasta)`; `.gravar(nome, papel, audio16k) -> Perfil` (exige ≥ 15 s de fala útil, divide em janelas de 3 s e guarda a média normalizada); `.listar()`; `.ativar(nome, bool)`; `.apagar(nome)` (remove a pasta); `.quem_fala(audio16k) -> (Perfil|None, score)` considerando só perfis ativos; limiar `locutor_limiar` (padrão calibrado em teste, ~0,5). Modelo baixado sob demanda para `%LOCALAPPDATA%\dervs\modelos\` com SHA-256 conferido; sem modelo, a trava fica desligada e o painel avisa.
   - `dervs_turno.py` — árbitro de vez. Recebe quadros PCM 16 kHz mono (30 ms). VAD Silero (onnx) marca fala; ao primeiro silêncio ≥ 300 ms roda Smart Turn v3 (pipecat, onnx int8, português; entrada log-mel tipo Whisper de até 8 s, implementada em numpy) sobre o trecho; prob ≥ `turno_prob_fim` (0,5) → `fim_de_vez`; abaixo, espera mais e reavalia a cada 300 ms até `turno_espera_max_s` (3,0 s); retomada de fala cancela. Emite eventos puros: `InicioFala(t)`, `FimDeVez(t, audio)`, `Pausa(t)`. Função pura, testável com WAV, sem Qt nem rede. Sem os modelos: cai no `Endpointer` atual (`dervs_listen.py:43`) com `fim_ms` 1100.
   - Trava de perfil: só áudio cuja janela foi confirmada como perfil ativo segue para o motor; o resto vira silêncio e nunca sai do PC. A confirmação usa a janela móvel dos últimos ~1,5 s de fala.
   - Interrupção (barge-in): durante a fala do DERVS, `InicioFala` abaixa o volume para 30% em ≤ 0,3 s; perfil ativo confirmado (≤ 0,9 s) → `motor.interromper()` e o player para; não confirmado → volume volta. Eco: se o pacote `livekit` (AudioProcessingModule com AEC) instalar no Windows, ele limpa o microfone usando o áudio tocado como referência; sem ele, a própria voz do DERVS não passa na trava de perfil (não é perfil cadastrado) e o abaixar de volume só acontece com VAD acima de um limiar mais alto durante a fala.
   - Player em fluxo: toca PCM conforme chega (sounddevice OutputStream), sem arquivo temporário, sem WSOLA; suporta `abaixar(frac)`, `parar()`.

2. **Motor de conversa trocável** — `dervs_conversa.py`, interface `MotorConversa`:
   - `iniciar(instrucoes, ferramentas)`, `enviar_audio(pcm16k)`, `fim_da_vez()`, `interromper()`, `encerrar()`; callbacks/eventos `AudioSaida(pcm, taxa)`, `TextoSaida(texto)`, `ChamadaFerramenta(id, nome, args)` → `responder_ferramenta(id, resultado)`, `FimResposta`, `Erro(tipo: "limite"|"rede"|"chave"|"outro", msg)`.
   - `MotorGeminiLive` (padrão): WebSocket BidiGenerateContent, `models/gemini-3.8-live`, voz `voz_gemini` (Charon), `languageCode pt-BR`, `automaticActivityDetection.disabled=true` — o árbitro local manda `activityStart`/`activityEnd`, então quem decide a vez é o PC. Ferramentas via `functionDeclarations`. Chave por `dervs_config.segredo("GEMINI_API_KEY")`, nunca impressa (a chave vai na URL: a URL nunca entra em log ou erro).
   - `MotorCascata` (reserva): Groq `whisper-large-v3-turbo` (`language=pt`, `prompt` = `stt_dica_vocabulario`) → cérebro atual (`dervs_brain`, passando a pedir `stream` e falando por frase) → voz em fluxo: `gemini-3.8-flash-lite-tts` (SSE) → `gpt-4o-mini-tts` (`response_format: pcm`, em fluxo, sem WSOLA) → Kokoro.
   - `MotorOpenAIRealtime` (premium, só por config): `gpt-realtime-2.1-mini`, `turn_detection: null` (o árbitro local decide), mesmas ferramentas.
   - Troca automática: `Erro(limite|rede|chave)` ou `dervs_gasto.pode_gastar()` falso → próximo da ordem `conversa_motores` (padrão `["gemini_live", "cascata"]`), com aviso falado curto, preservando as últimas falas como contexto.
   - Gasto: cada motor registra em `dervs_gasto` (`tipo` "conversa", detalhe com motor e segundos/tokens); faixa grátis registra US$ 0.

3. **Política de ação e ferramentas** — as ferramentas oferecidas ao motor são as ações que o DERVS já sabe fazer (`dervs_atalhos.tentar`, planos do `dervs_brain`, `dervs_roteador` → Claude Code/Codex, infra por voz), embrulhadas numa única `fazer(pedido_em_texto, clareza: "clara"|"duvida")` mais as fáceis diretas (abrir app, hora, volume, abrir pasta). Regra no sistema do motor e reforçada em código:
   - fácil + clara + reversível → executa, resposta falada vazia, toca `sinal_feito` (WAV curto) e acende o widget;
   - dúvida/ambígua/incompleta → o motor pergunta antes; nenhuma ação;
   - grave → `plano_pede_confirmacao` (`dervs.py:140`) e travas de hoje, sem atalho;
   - perfil `convidado` → só conversa e ação fácil reversível; o resto recebe recusa falada.

4. **Integração e painel** — nova chave `conversa_natural` (padrão `true` quando houver motor disponível) liga o fluxo novo dentro da janela de desperto (`dervs.py:950`); porteiro "DERVS" e modos Desligado/Atalho/Voz não mudam. Painel Electron ganha a seção "Vozes": gravar perfil (lê um texto de ~30 s com barra de progresso), lista com ativo/inativo, papel, apagar; e mostra o motor ativo ("Google grátis", "Econômico", "Premium").

## o_que_ja_existe

- Escuta e fim de fala por energia: `dervs_listen.py:43-151` (`Endpointer`), thread `Escuta` em `dervs.py:364-430`; microfone pausado enquanto fala em `dervs.py:1293`.
- Porteiro: `dervs_porteiro.py` (`PorteiroLocal`, whisper tiny); janela de desperto `dervs.py:950-967`, `janela_desperto_seg` em `dervs_config.py:72`.
- STT em lote: `dervs_stt_daemon.py:115-145` (OpenAI `gpt-transcribe`), dica `stt_dica_vocabulario` em `dervs_config.py:122`.
- Cérebro: `dervs_brain.py` (`SISTEMA` 143-266, `FICHA_SCHEMA` 724, chamada sem stream 742-761; Claude CLI persistente 402-420).
- Voz: `dervs_tts.py` (`sintetizar_openai` 232, `acelerar_wav` 175, `_falar_openai` 555, `calar` 470, `ACUSES` 147, `INSTRUCOES_VOZ_BR` 131).
- Política: `plano_pede_confirmacao` `dervs.py:140-168`, `confirmar_plano="grave"` `dervs_config.py:193`, `dervs_safety.py`, `dervs_permissoes.py`, `dervs_aprovacao.py`; atalhos locais `dervs_atalhos.py`.
- Roteador: `dervs_roteador.py:51`; Motor do painel `dervs_electron.py:243`.
- Segredos: `dervs_config.segredo` `dervs_config.py:44-65`; `scripts/guardar-chave.ps1`.
- Gasto e teto: `dervs_gasto.py` (`registrar`, `pode_gastar`, `teto_gasto_dia_usd` em `dervs_config.py:257`).
- Testes de medição prontos (scratchpad desta sessão, a portar para `scripts/`): `teste_realtime.py`, `teste_turno.py`, `teste_locutor.py`, `g_tts.py`, `g_live.py`, `groq_stt.py`.

## fontes_externas

- OpenAI preços e Realtime VAD: https://developers.openai.com/api/docs/pricing , https://developers.openai.com/api/docs/guides/realtime-vad (15/10/2026)
- Gemini preços e Live: https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/gemini-api/docs/live-guide (15/10/2026)
- Groq STT e limites: https://console.groq.com/docs/speech-to-text , https://console.groq.com/docs/rate-limits (15/10/2026)
- Smart Turn v3: https://github.com/pipecat-ai/smart-turn ; Silero VAD: https://github.com/snakers4/silero-vad ; sherpa-onnx modelos de locutor: https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models (15/10/2026)
- Claude Code voz (só ditado): https://code.claude.com/docs/en/voice-dictation ; ChatGPT Plus sem API: https://help.openai.com/en/articles/8156019 (15/10/2026)

## fora_de_escopo

GPT-Live-1; ElevenLabs/Cartesia/Azure; voz ou persona por perfil; microfone pelo Electron; trocar porteiro e modos de escuta; tradução simultânea.

## contradicoes_resolvidas

- Voz direta OpenAI (mais natural, ~US$ 35–45/mês) × econômico: venceu o econômico por decisão do dono; OpenAI fica premium por config.
- VAD semântico do servidor × árbitro local: o teste de 15/10 mostrou o semântico cortando após "éé… hum…" + 1 s; venceu o árbitro local, com a detecção do servidor desligada em todos os motores.
- Gemini TTS flash (mais natural?) × flash-lite: flash bateu 429 a ~4 pedidos/min na faixa grátis; venceu flash-lite na cascata.
- Interrupção ≤ 0,4 s × reconhecer o perfil (precisa ~1 s de fala): resolvido com abaixar o volume já no início da fala e parar só após confirmar o perfil.

## duvidas_para_o_dono

nenhuma (voz final é escolha de ouvido depois, com padrão definido).
