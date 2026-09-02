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

---

## 3. O programa inteiro, no Windows

| O que foi verificado | Como | Resultado |
|---|---|---|
| `dervs.py` importa toda a cadeia | importação direta no ambiente isolado | **passa**, sem erro |
| O app sobe e fica de pé | `QT_QPA_PLATFORM=offscreen`, 25 s | **passa**, saída de erro vazia |
| O microfone capta de verdade | classe `Microfone` por 3 s | **100 quadros** de 30 ms em 3 s (exatamente o esperado), pico 1938 |
| O daemon responde ao protocolo novo | áudio real pelo `stdin` | `PORTEIRO {"acordou": true, "texto": "Ok Dervs. Abriu Chrome para mim."}` e `{"acordou": false}` para "Meu Deus, que susto você me deu" |
| A suíte de testes | `pytest -q` no ambiente isolado | **173 passam, 0 falham** (antes da rodada: 112 passavam, 4 falhavam) |

## 3b. A rede de segurança, depois da revisão (02/09/2026)

A revisão de segurança encontrou seis achados de gravidade alta, todos obtidos
**executando** o classificador, não lendo os padrões. O pior era estrutural: a
lista de comandos seguros casava em qualquer posição da linha, então bastava um
comando inocente na frente para a guarda baixar.

Depois da correção, verificado executando de novo (não confiando no relatório
de quem corrigiu):

| Comando de ataque | Antes | Depois |
|---|---|---|
| `notepad && net user invasor 123 /add` | reversível | **destrutivo** |
| `chrome ... & schtasks /create /tn B /tr p.exe /sc onlogon` | reversível | **destrutivo** |
| `echo oi; Remove-Item C:\Users\Dono\x -Rec` | reversível | **destrutivo** |
| `Get-ChildItem C:\Users\Dono -Recurse \| Remove-Item` | reversível | **destrutivo** |
| `Start-Process ...\payload.exe -Verb RunAs` | reversível | **destrutivo** |
| `Remove-Item ...\Documentos -Rec -Fo` | muda_estado | **destrutivo** |
| `del C:\Users\Dono\Documentos\*.*` | muda_estado | **destrutivo** |
| `powershell -EncodedCommand <base64>` | muda_estado | **destrutivo** |
| `Add-MpPreference -ExclusionPath C:` (desliga antivírus) | muda_estado | **destrutivo** |
| `wevtutil cl Security` (apaga log de auditoria) | muda_estado | **destrutivo** |
| `net localgroup administrators invasor /add` | muda_estado | **destrutivo** |
| `schtasks /create ... /sc onlogon` (persistência) | muda_estado | **destrutivo** |
| `robocopy vazio Documentos /MIR` | muda_estado | **destrutivo** |
| `type C:\Users\Dono\.ssh\id_rsa` | reversível | **destrutivo + pede autorização** |
| `Get-Content $env:USERPROFILE\.aws\credentials` | reversível | **destrutivo + pede autorização** |

E os falsos positivos, que são risco de segurança porque treinam o dono a
clicar sem ler:

| Comando inofensivo | Antes | Depois |
|---|---|---|
| `chrome http://192.168.0.1` (abrir o roteador) | destrutivo, exigia "tenho autorização" | **reversível** |
| `chrome .../search?q=windows+11+24.2.1.0` | destrutivo, exigia autorização | **reversível** |
| `dir`, `Get-Date`, `notepad`, `chrome https://google.com` | reversível | reversível |

A regra de ouro continua de pé: comando desconhecido cai em `muda_estado`,
nunca em `reversível`. E o executor deixou de tratar comando encadeado como
"app de tela" — era por ali que a cauda arbitrária escapava da rede.

Duas travas novas do lado do comportamento, também verificadas por teste:

- **Voz não confirma o irreversível.** Qualquer som audível pelo microfone
  podia dizer "OK DERVS, faça X" e, segundos depois, "ok". Agora o plano é
  classificado antes de começar, e a voz só vale para plano inteiramente
  reversível; acima disso é preciso clique.
- **A janela de desperto tem teto de 90 s**, que não é renovado por continuação
  de conversa — antes ela se renovava a cada resposta e nunca fechava, e
  enquanto ele está desperto tudo o que é falado vai direto para a nuvem.

**Suíte: 284 testes passam, zero falham.**

## 4. Tempo até responder — o que está medido e o que falta

| Etapa | Tempo | Como se sabe |
|---|---|---|
| Perceber que a frase acabou | ~1,10 s | valor configurado (`fim_ms`), não medido — é a espera de silêncio que decide que você terminou |
| **O porteiro decidir** | **0,49 s** | medido, média de 14 frases |
| Transcrição precisa na nuvem | **não medido** | falta a chave da OpenAI nesta máquina |
| O cérebro entender | **não medido** | idem |
| Primeiro som da voz | **0,68 a 0,96 s** | medido, por frase |

**Parcial medido: ~2,3 s** de perceber o fim da frase até o primeiro som, *sem*
contar nuvem. Com a nuvem, a expectativa é 3 a 4 s no total — mas isso é
expectativa, não medição, e só fecha quando a chave existir.

Se esse tempo incomodar, a primeira alavanca é reduzir `janela de silêncio` de
1,10 s para ~0,8 s (custa cortar a fala de quem respira no meio da frase; o
projeto já tentou 0,7 s e voltou atrás). A segunda é a transcrição em streaming
(`gpt-live-transcribe`), que custa quase 4× e economiza cerca de 1 s.

### Limite honesto desta medição

O áudio de teste foi **gerado por síntese de voz**, não gravado do dono. Isso prova o
mecanismo (o aviso de vocabulário resolve a troca por "Deus") e mede a velocidade real
na máquina, mas **não** prova a taxa de acerto com a voz e o microfone dele, em ambiente
com ruído. Isso só se mede com ele falando ao microfone — é o critério de aceitação nº 5
do briefing e continua pendente.
