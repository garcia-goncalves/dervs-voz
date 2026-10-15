# Verificação — Conversa natural (integração)

Data: 15/10/2026. Máquina do dono (Ryzen 7, sem placa de vídeo). Briefing:
`briefing.md`; spec: `spec.md`.

## 1. Medição real: árbitro de verdade + Gemini Live de verdade

Script: `scripts/medir_conversa_natural.py` (comando abaixo). Ele entrega a fala gravada,
quadro a quadro de 30 ms e em tempo real, à `ConversaNatural` de produção — árbitro
Silero + Smart Turn v3 de verdade, motor `gemini_live` de verdade pela `Conversa` — com um
microfone falso e um player falso que anota quando cada som chegaria à caixa. A trava de
voz fica desligada (a voz é sintética, não há perfil). As ferramentas não fazem nada: o
dublê responde "fácil", então o primeiro som de "Abre o Chrome pra mim" é o **sinal de
feito** (o pedido fácil não tem resposta falada, como o dono pediu).

```
dervs-venv\Scripts\python.exe scripts\medir_conversa_natural.py <pasta_com_os_wavs> --repeticoes 10
```

Os WAVs são os trechos do teste de 15/10 (`tts_<crc32>.wav`, voz "ash" da OpenAI).

| caso | fim real da fala | primeiro som depois do fim | som antes do fim? | o que o motor fez |
|---|---|---|---|---|
| completa 1 | 2,22 s | 1,31 s | não | `abrir_app` → sinal |
| completa 2 | 2,22 s | 2,04 s | não | `abrir_app` → sinal |
| completa 3 | 2,22 s | 1,36 s | não | `abrir_app` → sinal |
| completa 4 | 2,22 s | 1,44 s | não | `abrir_app` → sinal |
| completa 5 | 2,22 s | 1,19 s | não | `abrir_app` → sinal |
| completa 6 | 2,22 s | 1,09 s | não | `abrir_app` → sinal |
| completa 7 | 2,22 s | 1,20 s | não | `abrir_app` → sinal |
| completa 8 | 2,22 s | 1,11 s | não | `abrir_app` → sinal |
| completa 9 | 2,22 s | 1,23 s | não | `abrir_app` → sinal |
| completa 10 | 2,22 s | 1,29 s | não | `abrir_app` → sinal |
| hesita_1,5s ("Eu queria que você…" 1,5 s, "éé… hum…" 1 s, "abrisse o Chrome") | 10,40 s | 1,21 s | **não** | `abrir_app` → sinal |
| hesita_2,5s ("Me lembra de ligar pro…" 2,5 s, "pro dentista amanhã cedo") | 7,10 s | 2,26 s | **não** | respondeu falando |
| gagueja ("Cria uma, uma… uma pasta nova" 1,2 s, "chamada fotos da viagem") | 6,55 s | 1,43 s | **não** | `fazer("Crie uma pasta chamada Fotos da Viagem")` |

Resumo da saída do script: `{"casos": 13, "com_resposta": 13, "mediana_primeiro_som_s": 1.29, "pior_s": 2.26, "algum_som_antes_do_fim": false}`.
Mediana só das 10 completas: **1,26 s** (critério: ≤ 1,5 s).

O que estes números provam e o que não provam:

- **Rapidez:** mediana 1,26 s, dentro do critério. Mas é **a mesma frase dez vezes**, e o
  primeiro som é o sinal (ferramenta), não uma frase falada. A resposta falada (caso
  "ligar pro dentista") levou 2,26 s. Falta medir 10 frases diferentes e faladas.
- **Pausa para pensar:** nenhum som antes do fim real nos três casos de hesitação gravados.
  No "gagueja" o árbitro real fecha a vez 0,33 s depois de "uma pasta nova" (corte cedo
  conhecido); a resposta não toca porque a `ConversaNatural` só solta o som depois de
  **1,3 s sem voz** (`SEGURAR_S`); a pessoa retoma em 1,2 s, a resposta é descartada calada
  (`interromper`) e a fala nova continua o mesmo pedido. O preço: o primeiro som nunca sai
  antes de 1,3 s do fim da fala. O quarto caso do critério ("éé… hum…" + 1 s) está dentro
  do `hesita_1,5s`.

## 2. Testes automáticos (dublês e relógio de quadros)

`test_dervs_conversa_natural.py` (sem microfone, caixa de som ou rede):

- outra voz (ou perfil inativo) nunca vira pedido e **nenhum byte dela chega ao motor**;
  janela de outra pessoa no meio do turno vira silêncio (conferido amostra a amostra);
- trava fecha com perfil gravado: sem modelo, nenhum perfil ativo, erro no `quem_fala` e erro
  de disco → nada enviado, um aviso; com zero perfis, tudo passa e `locutor_aviso` = "grave sua voz";
- os 4 casos de hesitação com as decisões gravadas do árbitro real: nenhum som antes do fim;
- interrupção: o dono por cima abaixa o volume em ≤ 0,3 s e para em ≤ 0,9 s, com
  `interromper` antes da fala nova; outra pessoa por cima só abaixa e o volume volta;
- fácil = calado + sinal, e o que o modelo falaria depois é cortado; dúvida = nenhuma ação;
  grave = cartão com clique (`plano_pede_confirmacao` de verdade); convidado recebe recusa em
  Claude Code, grave e servidor; ferramenta fora da lista ou com args inválidos é descartada;
  pedido vindo de resultado de ferramenta (contado aqui ou marcado `origem="ferramenta"` pelo
  motor) pede confirmação; o "sim" só vale numa vez nova do dono e com a transcrição dizendo sim;
- queda do motor (ou motor que nem sobe) volta ao caminho antigo com aviso; dentro do app a
  `Escuta` devolve o quadro ao `Endpointer`, e a voz direta só tenta de novo depois de 10 min;
- perfis: gravar, listar, ativar, apagar (a pasta some) e o arquivo é só `perfil.json` +
  `voz.bin` cifrado (DPAPI); novo dono só de sessão confirmada como dono ou no 1º cadastro.

## 3. Eco (cancelamento) — medido, mas não ligado por padrão

`livekit` 1.1.20 instala no Windows desta máquina (pip, roda sem compilar). O
`AudioProcessingModule` com AEC, num eco sintético (a própria voz tocada, atrasada 40 ms e
com metade do volume, mais ruído), atenuou **31,2 dB** e gastou **12,7 ms de CPU por segundo**
de áudio. A `ConversaNatural` usa o AEC sozinha se o pacote estiver instalado
(`CancelaEco.criar()`); ele **não** foi instalado no `dervs-venv` nesta etapa (fica como linha
opcional no `requirements.txt`). Sem ele valem a trava de voz (a voz do DERVS não é perfil) e
o VAD mais exigente enquanto ele fala (`LIMIAR_VAD_TOCANDO`).

**Teste manual ainda não feito:** tocar uma resposta longa na caixa de som e conferir que ela
não interrompe o DERVS. Exige o dono, a caixa e um perfil gravado.

## 4. O que falta provar

- 10 frases completas **diferentes**, com resposta falada (não só o sinal).
- Eco na caixa de som (teste manual, acima).
- Voz real do dono e da filha (a trava só foi provada com vozes sintéticas e dublês).
- A tela "Vozes" do painel (a API existe; a tela é a próxima etapa).
- Os 10 minutos de conversa real com o dono.
