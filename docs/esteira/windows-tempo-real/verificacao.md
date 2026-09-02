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

## 1.5. O cérebro na nuvem (gpt-4.1-nano) — 02/09/2026, com a chave instalada

Medido com 40 chamadas reais, oito pedidos diferentes em rodízio (conta, hora, abrir
programa, ler o Gmail, listar pasta, enriquecer domínio).

| | Tempo |
|---|---|
| Mediana | **0,96 s** |
| Melhor | 0,64 s |
| Pior | 6,40 s (uma chamada isolada; a rede da OpenAI oscila) |

### O defeito que a medição revelou — e a correção

O código pedia a resposta com `response_format: {"type":"json_object"}`. Isso **pede**
JSON ao modelo, não **obriga**. Medido: o gpt-4.1-nano quebrava em **3 de 20 chamadas
(15%)**. O padrão era sempre o mesmo — fechava o campo `fala`, abria uma aspa a mais e
degringolava em texto repetido até estourar os 800 tokens:

```
{"modo":"conversar","fala":"São 96, é isso mesmo.","}  # Resposta direta...
```

Consequência: `_extrair_json` falhava, `pensar()` engolia o erro e caía no cérebro
reserva (o Claude local). O DERVS **não ficava mudo**, mas ficava lento à toa em uma a
cada sete falas.

Comparação de três configurações, 20 chamadas cada:

| Configuração | JSON quebrado | Tempo (mediana) | Tokens de saída |
|---|---|---|---|
| nano + `json_object` (como estava) | **3/20** | 1,03 s | 148 |
| nano + `json_schema` strict | **0/20** | 1,02 s | 38 |
| gpt-4.1-mini + `json_object` | 0/20 | 1,02 s | 32 |

**Correção aplicada:** trocar para `json_schema` com `strict: true` (Structured
Outputs), que força a gramática no decodificador — sair do formato deixa de ser
possível. Não foi preciso subir para um modelo mais caro. Além de eliminar a falha, a
saída ficou **4× menor** (o lixo repetido é que inflava), o que também baixa a conta.

Validação depois da correção: **0 falhas em 40 chamadas.**

Efeito colateral tratado: com `strict`, o modelo devolve *toda* propriedade, usando
`null` no que não se aplica àquele passo. `dict.setdefault` não substitui `None` — só
chave ausente — então um passo de navegador chegava na tela com `comando: None`. Daí a
função `_preencher()` em `dervs_brain.py`.

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

**Suíte: 293 testes passam, zero falham** (284 + 5 do cérebro travado por schema
+ 4 dos caminhos de voz no Windows).

---

## 3c. A voz não subia nesta máquina (02/09/2026) — CORRIGIDO

Achado durante a medição ponta a ponta: `dervs_tts.Voz(...).disponivel()` respondia
**False**. O DERVS ficava **mudo** no Windows.

Causa: `dervs_tts.py` procurava os daemons e os ambientes isolados em
`~/voice/kokoro-venv`, `~/voice/dervs_kokoro_daemon.py` etc. — o layout do projeto irmão
no Linux. **Essa pasta não existe no Windows.** Aqui os daemons vêm com o repositório e
as bibliotecas estão todas no `dervs-venv` do projeto. O modelo do Kokoro já estava
baixado e o `kokoro-onnx` já estava instalado: faltava só o código apontar para o lugar
certo.

É o mesmo defeito de porte já corrigido em `dervs_config.py` — lá a chave da OpenAI não
era achada porque três arquivos só olhavam o caminho do Linux.

Corrigido com `_dir_daemons()` e `_py_do_motor()` em `dervs_tts.py`. Depois:
`disponivel()` é **True**, o daemon sobe em 4,17 s e sintetiza em 0,41 s.

Travado por `test_dervs_tts.py`, que checa que nenhum caminho de voz aponta para
`/voice/` no Windows e que existe algum motor de pé.

### Por que a medição de 01/09 não pegou isto

A seção 1 mediu o Kokoro **falando com o daemon diretamente**, com o Python certo passado
na mão. Isso prova que o *motor* funciona — e provou. Mas não passa pelo caminho que o
app usa, e era exatamente ali que estava o defeito. Lição: medir o componente não
substitui medir pelo caminho de produção.

## 3d. Voz mais humana — medido, pendente de decisão do dono (02/09/2026)

O dono ouviu as três vozes do Kokoro e escolheu `pm_alex` a 1,3x, mas disse:
*"não gostei muito dessas vozes... quero uma voz melhor, mais fluida e mais humana...
e rápida"*.

O Kokoro é um modelo de 82 milhões de parâmetros rodando em processador sem placa de
vídeo. Ele é bom para o tamanho, mas não vai soar como gente de verdade — esse é o teto
do que roda local e de graça nesta máquina.

A alternativa medida foi a voz da OpenAI (`gpt-4o-mini-tts`), que aceita instrução de
estilo em texto ("fale como um parceiro brasileiro, natural e direto").

### Tempo até começar a falar

O primeiro número que se mede é enganoso: o áudio **inteiro** demora 2,1 a 3,4 s. Mas
quem conversa não espera o áudio inteiro — espera começar. Lendo a resposta em fluxo
(`response_format: pcm`, primeiro pedaço de 4 KB):

| Voz | Onde | Primeiro som | Custo |
|---|---|---|---|
| **Kokoro `pm_alex` 1,3x** (hoje) | local | **0,48 s** | zero |
| OpenAI `ash` | nuvem | **0,90 s** | ~US$ 0,015 / 1.000 caracteres |
| OpenAI `sage` | nuvem | 1,01 s | idem |

**A conta:** trocar custa **+0,42 s** por resposta — o tempo total iria de 3,94 s para
cerca de 4,4 s. Em dinheiro, uma resposta típica de 100 caracteres sai por ~US$ 0,0015;
100 respostas por dia dão cerca de **US$ 4,50 por mês**.

Amostras gravadas em `amostras_voz/nuvem_*.mp3` (ash, ballad, verse, sage, onyx) para o
dono comparar de ouvido com as do Kokoro. **A decisão é dele**, porque é troca de
dinheiro e de latência por naturalidade — não é decisão técnica.

Se ele escolher a nuvem, o trabalho é um daemon novo no mesmo protocolo de linha do
Kokoro (`READY` / `WAV <caminho>` / `FIM`), tocando cada pedaço conforme chega, e a
queda de volta para o Kokoro quando faltar internet — o encaixe já existe em
`dervs_tts.Voz`.

## 4. Tempo até responder — FECHADO

**Fechado em 02/09/2026**, com a chave da OpenAI instalada. Medição ponta a ponta pelo
caminho de produção (a mesma `dervs_tts.Voz` que o app usa), 3 repetições por estágio,
mediana. Frase de entrada: *"DERVS, que horas são?"* (1,42 s de áudio).

| Etapa | Tempo | Onde roda | Como se sabe |
|---|---|---|---|
| Perceber que a frase acabou | ~1,10 s | local | valor configurado (`fim_ms`), não medido — é a espera de silêncio que decide que você terminou |
| **O porteiro decidir "foi comigo?"** | **0,35 s** | local, grátis | medido |
| **Transcrição precisa** | **1,68 s** | nuvem | medido |
| **O cérebro entender e responder** | **1,50 s** | nuvem | medido |
| **Primeiro som da voz** | **0,41 s** | local, grátis | medido |

**Do fim da fala até o DERVS começar a responder: 3,94 s** (sem contar a espera de
silêncio) — dentro dos 3 a 4 s que a esteira previa. Somando a espera de silêncio, são
~5,0 s desde o momento em que o dono para de falar.

Custo de carga, pago uma vez ao ligar (por isso os daemons nascem aquecidos): daemon da
voz 4,17 s, porteiro 4,12 s.

O porteiro acertou mesmo com a transcrição local saindo torta — ouviu *"Dervs que aura
são."* e ainda assim reconheceu o nome, que é exatamente o trabalho do casador difuso.

### A hora inventada — achada nesta medição, corrigida no mesmo dia

O cérebro respondeu *"São três e meia."*, que é o exemplo literal do prompt, não a hora
real. O modelo não tem relógio nenhum e repetia o exemplo com toda a convicção.

**Ressalva importante, descoberta depois:** *pelo aplicativo* isto nunca chegava ao dono.
"Que horas são" e "que dia é hoje" já eram atendidos por `dervs_atalhos.tentar()`, que
responde localmente, na hora, sem chamar o cérebro — verificado: devolve *"É uma e seis
da tarde."* com o relógio certo. A medição bateu no problema porque chamou
`_pensar_openai` diretamente, contornando os atalhos.

Então o defeito era real, mas **menor do que pareceu**: valia para tudo que os atalhos
não cobrem, que é onde o cérebro precisa da data para raciocinar — *"quanto tempo falta
pro Natal"*, *"marca pra amanhã"*, *"isso foi antes ou depois de agosto"*. Nenhuma dessas
casa com os atalhos (verificado), e todas iam ao cérebro sem saber que dia era.

Corrigido injetando data e hora em **cada** pergunta, como mensagem de **sistema** —
nunca como fala do dono, onde viraria uma ordem a cumprir em vez de contexto. É a função
`_agora()` em `dervs_brain.py`, presente nos dois caminhos (OpenAI e Claude reserva).

Verificado com o relógio do PC marcando 12:50 de 02/09/2026:

| Pergunta | Resposta |
|---|---|
| "que horas são?" | *"São meia dia e cinquenta."* |
| "que dia é hoje?" | *"Hoje é quarta-feira, 2 de setembro de 2026."* |
| "quanto tempo falta pro Natal?" | *"Faltam exatamente 113 dias pro Natal, mais ou menos."* |

Sem `locale` de propósito: `strftime("%A")` devolveria o dia da semana em inglês, e mexer
em locale global é efeito colateral num processo que também sintetiza voz. Duas listas de
nomes resolvem sem dependência.

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
