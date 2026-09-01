# Medições nesta máquina — 01/09/2026

Máquina do dono: AMD Ryzen 7 5700G (8 núcleos / 16 threads), 31,4 GB RAM,
**sem placa de vídeo dedicada** (só o gráfico integrado AMD, 0,5 GB — sem CUDA).
Windows 11 Pro 10.0.26200. Python 3.12.10. Microfone e alto-falantes Realtek.

Ambiente isolado do projeto: `dervs-venv\` (fora do git).
Modelos em `%LOCALAPPDATA%\dervs\modelos\`.

---

## 1. A voz (Kokoro, offline, grátis) — FUNCIONA

Carregar o modelo uma vez: **1,72 s**. Depois disso, por frase:

| Voz | Velocidade | Tempo para sintetizar | Duração do áudio | Quantas vezes mais rápido que o tempo real |
|---|---|---|---|---|
| pm_santa | 1,0 | 2,68 s (primeira chamada, inclui aquecimento) | 2,22 s | 0,8× |
| pm_santa | 1,2 | 0,76 s | 2,01 s | 2,6× |
| pm_alex | 1,0 | 0,77 s | 2,22 s | 2,9× |
| pm_alex | 1,2 | 0,68 s | 1,94 s | 2,8× |
| pf_dora | 1,0 | 0,96 s | 2,20 s | 2,3× |
| pf_dora | 1,2 | 0,73 s | 1,92 s | 2,6× |

**Conclusões:** roda em Windows sem depender de nada externo; a primeira chamada é
lenta (aquecimento), então o daemon precisa nascer aquecido — como já faz hoje. A
velocidade 1,2 não custa mais caro que a 1,0. Amostras gravadas em
`%LOCALAPPDATA%\dervs\modelos\amostra_*.wav` para o dono escolher a voz.

---

## 2. O porteiro local (decidir "é comigo?" sem mandar áudio para a nuvem)

Método: gerar as frases com a voz Kokoro, transcrever localmente com Whisper pequeno
(faster-whisper, CPU, int8, 8 threads) e passar o texto pelo casador difuso que já
existe em `dervs_listen.separar_chamada`. 14 frases: 6 com o nome (têm de acordar) e
8 sem (não podem acordar), incluindo duas armadilhas com "Deus".

| Configuração | Acertos | Tempo médio | Pior tempo |
|---|---|---|---|
| `tiny`, sem aviso de vocabulário | 10/14 | 0,66 s | 1,88 s |
| **`tiny`, com aviso de vocabulário** | **14/14** | **0,49 s** | **1,20 s** |
| `base`, sem aviso | 10/14 | 1,04 s | 2,61 s |
| `base`, com aviso | 14/14 | 0,92 s | 1,37 s |
| `small`, sem aviso | 7/14 (medido antes, com 11 frases: 7/11) | 2,26 s | 4,58 s |

### O achado que mudou o projeto

Sem o aviso, o Whisper **não erra ao acaso — ele conserta o desconhecido para a palavra
comum mais próxima.** "Dervs" virou:

- `Ok Dervs, abre o Chrome` → ouviu **"Ok, Deus abriu Chrome"**
- `Por favor Dervs, liga a luz da sala` → ouviu **"Por favor, Deus liga luz da sala"**
- `Dervs, desliga o som` → ouviu **"Deus desliga o song"**
- `Dervs.` → ouviu **"Derros."**

Isso é fatal para um porteiro, e não se conserta afrouxando o casador difuso: aceitar
"Deus" faria o DERVS acordar toda vez que alguém dissesse "meu Deus".

A correção é passar `initial_prompt` ao Whisper com a palavra
(`"Dervs. Ok Dervs. Ei Dervs. O assistente se chama Dervs."`). Com isso o modelo passa
a ter a palavra no vocabulário e acerta as 6 que deviam acordar **sem** acordar em
nenhuma das 8 que não deviam — incluindo "Meu Deus, que susto você me deu" e
"Deus me livre disso aí".

**Modelo escolhido para o porteiro: `tiny` com aviso de vocabulário.** É o mais rápido
(0,49 s) e empata em acerto com o `base`. O `small` é pior nos dois eixos e está fora.

### Limite honesto desta medição

O áudio de teste foi **gerado por síntese de voz**, não gravado do dono. Isso prova o
mecanismo (o aviso de vocabulário resolve a troca por "Deus") e mede a velocidade real
na máquina, mas **não** prova a taxa de acerto com a voz e o microfone dele, em ambiente
com ruído. Isso só se mede com ele falando ao microfone — é o critério de aceitação nº 5
do briefing e continua pendente.
