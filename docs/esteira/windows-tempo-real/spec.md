# Spec — DERVS no Windows, em tempo real

## problema

O dono quer deixar o DERVS ligado o dia inteiro ouvindo o ambiente, e que ele só
responda quando ouvir o próprio nome. O desenho de hoje torna isso impossível de duas
maneiras ao mesmo tempo:

1. **A palavra de acordar é decidida DEPOIS da transcrição** (`dervs.py:475`, o
   `separar_chamada` só roda sobre o texto que voltou do daemon de transcrição). Com a
   configuração padrão (`stt: "openai"`), isso significa que **todo som que pareça fala
   é enviado à nuvem da OpenAI** e só depois o programa decide se era com ele. Ligado 8
   horas por dia, isso são ~14.400 minutos de áudio por mês na nuvem — cerca de
   **US$ 43/mês** só para escutar, além de mandar reunião, ligação e conversa de família
   para um servidor de terceiro.
2. **Nada disso roda em Windows.** A captura de áudio é `arecord` (ALSA), a reprodução é
   `pw-play`/`paplay`/`aplay`, os arquivos temporários vão para `/tmp`, a configuração
   mora em `~/.config`, os ambientes Python usam `bin/python`, os atalhos abrem
   `firefox`/`konsole`/`kcalc`, a rede de segurança conhece `rm -rf` e não conhece
   `Remove-Item -Recurse -Force`, e o próprio prompt do cérebro manda o LLM sugerir
   binários de Linux.

## solucao

Um **funil de três estágios**, em que cada estágio é mais caro que o anterior e só é
acionado se o anterior deixar passar. É isto que resolve custo, privacidade e latência
com uma decisão só:

| Estágio | O que faz | Onde roda | Custo |
|---|---|---|---|
| 1. Detector de fala | separa fala de silêncio e decide quando a frase acabou | local (código que já existe, `Endpointer`) | zero |
| 2. **Porteiro** | decide "isto foi comigo?" — só procura o nome | **local** | zero |
| 3. Transcrição | transcreve o pedido com precisão | nuvem | por minuto |
| 4. Cérebro + voz | entende e responde falando | nuvem + local | barato + zero |

**Nada sai da máquina antes do estágio 2 abrir.** Esse é o coração da mudança e vira
teste automatizado (critério de aceitação nº 3 do briefing).

Uma peça de apoio torna isso natural de usar: uma **memória circular de áudio** guardando
os últimos ~12 segundos. Quando o porteiro abre, o começo da frase já está guardado —
então "DERVS, abre o Chrome" dito de um fôlego só funciona, sem aquele vexame de
"acordar, esperar o bipe, e só então falar".

## o_que_ja_existe

Com caminhos reais, levantados por leitura completa do código nesta sessão:

- `dervs_listen.py:38-134` — classe `Endpointer`, detecção de fim de fala por energia,
  já bem afinada: 1,1 s de silêncio fecha a frase, 300 ms de pré-gravação para não comer
  a primeira sílaba, histerese de saída, piso de ruído que só aprende fora da fala.
  **Aproveitável inteiro.**
- `dervs_listen.py:159-260` — `separar_chamada` e `_pontuar_nome`: casador difuso do
  nome, recalibrado nesta sessão para "dervs" (prefixo "der", 4 a 7 letras, limiar 0,87).
  **É o estágio 2 já pronto** — falta só alimentá-lo com transcrição local em vez de
  transcrição da nuvem.
- `dervs_stt_daemon.py` — daemon residente de transcrição, com os dois caminhos já
  escritos: OpenAI (`_transcrever_openai`, linhas 88-111) e local via `faster_whisper`
  (`_transcrever_local`, linhas 68-77), com queda automática de um para o outro.
  **A peça do porteiro cabe aqui.**
- `dervs_tts.py` + `dervs_kokoro_daemon.py` — voz Kokoro com streaming por frase
  (sintetiza a frase 1 e já começa a tocar enquanto sintetiza a 2), daemons residentes
  que nascem aquecidos, velocidade já parametrizada (`KOKORO_SPEED = 1.15`).
  **Aproveitável; falta trocar o tocador de áudio de Linux para Windows.**
- `dervs_safety.py` — rede de segurança de comandos, funções puras, só sobe o nível de
  risco e nunca desce. **A estrutura fica; o vocabulário precisa virar Windows.**
- `dervs_brain.py:539` — cérebro com três quedas em cascata (OpenAI → sessão Claude
  persistente → Claude avulso), para nunca ficar mudo. **Aproveitável; o prompt fixo
  precisa parar de mandar usar `konsole` e `firefox`.**
- `dervs.py` — aplicação PyQt6 com thread de escuta, processo separado de transcrição e
  máquina de estados por sinalizadores. **É onde entra o liga/desliga visível.**
- `dervs_painel.py` — programa solto e legado, ninguém importa. **Fica como está.**
- `dervs_enrich.py` — depende de `bbot`, que não roda em Windows. **Fica desligado.**

## fontes_externas

Todas consultadas em 01/09/2026:

- Preços de transcrição da OpenAI — https://developers.openai.com/api/docs/pricing
  Existe um modelo novo, **`gpt-transcribe`** (lançado 28/07/2026), a **US$ 0,0045/min**,
  que a própria OpenAI passou a recomendar à frente do `gpt-4o-transcribe`
  (US$ 0,006/min) e do `whisper-1` (US$ 0,006/min). O que o projeto usa hoje,
  `gpt-4o-mini-transcribe`, custa US$ 0,003/min. Há também um modelo de streaming,
  `gpt-live-transcribe`, a US$ 0,017/min — quase 4× o preço, para ganhar cerca de 1 s.
- Lançamento do `gpt-transcribe` —
  https://www.explainx.ai/blog/openai-gpt-live-transcribe-gpt-transcribe-july-2026
  e https://techgenyz.com/openai-gpt-transcribe-live-transcribe-models/
- Concorrentes: Deepgram Nova-3 US$ 0,0043/min (https://deepgram.com/pricing);
  AssemblyAI Universal-2 US$ 0,0025/min (https://www.assemblyai.com/pricing).
- Comparativo de precisão — https://artificialanalysis.ai/speech-to-text
  GPT-4o Transcribe 4,0% de erro · Whisper Large v3 4,1% · GPT-4o Mini Transcribe 4,5% ·
  Deepgram Nova-3 5,2%. **Nenhuma fonte encontrada quebra esses números por português do
  Brasil** — o pesquisador disse isso com todas as letras em vez de estimar.
- Porcupine (detector de palavra dedicado) — https://picovoice.ai/docs/faq/porcupine/ e
  https://picovoice.ai/docs/benchmark/wake-word/ : mais de 97% de acerto com **menos de
  1 alarme falso a cada 10 horas**, português nativo, palavra personalizada gerada no
  console deles em segundos, gratuito até 3 usuários ativos por mês, **exige criar conta
  e uma chave de acesso**.
- openWakeWord — https://github.com/dscripka/openWakeWord : gratuito e open source, mas
  não tem palavra pronta em português; treinar uma leva cerca de 1 hora.
- Silero VAD — https://github.com/snakers4/silero-vad : roda em `onnxruntime` sem
  PyTorch, consumo desprezível (~0,4% de CPU).

## contradicoes_resolvidas

**O pesquisador desaconselhou usar Whisper como porteiro; a medição nesta máquina
mostrou que funciona. Quem venceu: os dois, em camadas.**

O pesquisador argumentou — corretamente, e sem achar benchmark do padrão — que Whisper é
um transcritor completo, não um detector de palavra: mais pesado, mais lento e sujeito a
inventar palavra. A medição confirmou o pior desse diagnóstico: sem preparo, o Whisper
`tiny` **não erra ao acaso, ele conserta o desconhecido para a palavra comum mais
próxima** — "Dervs" virou "Deus" em três das seis frases ("Ok, Deus abriu Chrome").

Mas a medição também achou a correção, que nenhuma fonte citava: passar `initial_prompt`
com a palavra. Com ela, o `tiny` acertou **14 de 14** (6 que deviam acordar, 8 que não
deviam, incluindo "meu Deus, que susto você me deu") em **0,49 s** médios.

Resolução: **o porteiro nasce como peça trocável, com uma decisão de sim/não na saída.**
A implementação padrão é o Whisper `tiny` com aviso de vocabulário, que está medido,
custa zero e não exige nada do dono. O Porcupine entra pelo mesmo encaixe se a precisão
no mundo real decepcionar — e aí a métrica documentada dele (menos de 1 alarme falso por
10 horas) é exatamente a que importa para quem deixa ligado o dia inteiro.

**Segunda contradição, menor:** o pesquisador recomendou trocar para `gpt-transcribe`,
que é mais caro por minuto (US$ 0,0045 contra US$ 0,003) que o modelo de hoje. Venceu a
troca: o dono escreveu "TRANSCREVER O QUE EU FALO. COM PRECISÃO" em letra maiúscula, e a
diferença de conta é de cerca de **US$ 1 por mês** no volume previsto. Precisão ganha.

## duvidas_para_o_dono

Uma só, e é dele porque exige a mão dele e é troca de conforto por precisão:

**Qual porteiro?** A implementação padrão (Whisper `tiny` com aviso) está medida em 14/14
nesta máquina, custa zero, não exige conta nem cadastro e já funciona hoje — mas o teste
foi com voz sintetizada, não com a voz dele num ambiente com ruído. O Porcupine tem
métrica documentada de menos de 1 alarme falso a cada 10 horas, que é a garantia certa
para quem deixa ligado o dia inteiro — mas exige que **ele** crie uma conta gratuita no
Picovoice e gere a palavra "DERVS" no console deles, coisa que eu não posso fazer por ele.

**Recomendação: começar pelo padrão medido e só ir para o Porcupine se incomodar.** O
encaixe fica pronto para os dois desde o primeiro dia, então trocar depois é mudar uma
linha da configuração, não refazer trabalho.

## fora_de_escopo

Repetindo o corte já feito no briefing, para não haver dúvida na fase de execução:
`dervs_enrich.py` (depende de `bbot`, que não roda em Windows), `dervs_painel.py`
(legado, ninguém importa), validação ponta a ponta do navegador autônomo, serviço que
sobe sozinho no boot, streaming de áudio dentro da mesma frase (já testado e descartado
pelo projeto por engasgar sem placa de vídeo dedicada), e trocar o provedor do cérebro.

Fora de escopo também, por decisão desta spec: **transcrição em streaming**
(`gpt-live-transcribe`). Custa quase 4× e economiza cerca de 1 segundo. Se depois de
medir o conjunto o tempo de resposta incomodar, é a primeira alavanca a considerar.
