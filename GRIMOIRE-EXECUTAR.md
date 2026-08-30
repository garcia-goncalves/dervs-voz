# Grimoire — o Executar

O Grimoire é um selo flutuante que grava sua voz, transcreve offline (Whisper) e
te dá três ações. Este documento é sobre a terceira, o **Executar** — a conversa
que entende o que você quer e faz, sempre com confirmação.

## As três ações

| Ação | O que faz |
|---|---|
| **Copiar** | Copia o texto que você falou. Risco zero. |
| **Enviar** | Copia e cola na janela onde você estava (ditado clássico). |
| **Executar** | Abre uma conversa com o cérebro (Claude), que pergunta até entender, propõe um plano com o comando à vista, e só roda depois que você confirma. |

## Como o Executar funciona

O Grimoire **age sem pedir licença** para coisa segura. Você fala o objetivo; ele
faz. Só para nos casos perigosos é que ele para e pede confirmação.

1. **Entender e agir.** Você fala. O cérebro age direto no que é claro (ver a hora,
   abrir um app, listar). Só faz **uma** pergunta quando falta um dado essencial
   (qual arquivo, qual alvo) — nunca para pedir permissão do óbvio.
2. **Rodar sem atrito.** Passo **reversível** ou que só **muda estado** roda
   sozinho: você vê "fazendo: comando" e o resultado. Sem clique.
3. **Parar só no perigoso.** Passo **destrutivo** ou que **toca uma rede de fora**
   mostra um cartão com o comando à vista (editável) e espera seu Confirmar — com
   dupla confirmação e a caixa de autorização quando toca alvo.
4. **Prova, não "feito".** Cada passo mostra o código de saída e a saída real.

## Fluxo assertivo: entender → confirmar → só então executar

O dono pediu para ser assertivo e organizado. **Nada roda antes do OK dele.** O
laço é sempre:
1. **Entender.** Se ficou dúvida que muda o que fazer, o cérebro **pergunta** (uma
   coisa de cada vez); o dono responde.
2. **Confirmar.** Sem mais dúvida, o Grimoire **resume o que entendeu e o que vai
   fazer** e pede o OK — por voz ("...Posso?") e mostrando o plano na barra.
3. **OK e executa.** O dono dá o OK **por voz** ("ok", "pode", "faz", "isso") ou
   pelo botão. Aí — e só aí — os passos rodam. "não/cancela" cancela; uma frase
   maior ("não, faz no Firefox") é tratada como **correção** e o cérebro re-planeja.

## Os três trilhos de risco — e a palavra final é da máquina

Depois do OK do plano, cada passo ainda passa pela rede de segurança local:

- **Reversível** (abrir app, listar, ler) e **muda estado** (instala, edita, cria)
  → rodam após o OK do plano.
- **Destrutivo** (apaga, formata) **ou toca um alvo de rede** → **pedem um OK
  EXTRA**, com dupla confirmação; e, se toca alvo, uma caixa de **autorização**
  trava o botão até você marcar que é seu/laboratório/autorizado.

O cérebro sugere o risco, mas `grimoire_safety.py` — uma lista local aqui na
máquina — pode **subir** o trilho e nunca descer. Se o Claude disser "tranquilo"
e a lista reconhecer `rm -rf`, vence a lista. Comando desconhecido nunca fica em
"reversível": no mínimo pede uma confirmação. É isso que garante que **nada roda
sem você confirmar** — não a perfeição do modelo.

## Velocidade — onde vai cada segundo

Um turno seu passa por três etapas, em sequência. Medido nesta máquina:

| Etapa | Antes | Depois | Como |
|---|---|---|---|
| Ouvir (Whisper) | 8,1 s | 4,7 s | `cpu_threads=8` (os núcleos físicos; 16 fica pior por disputa) |
| Pensar (`claude`) | 10,6 s | ~2,7 s* | sessão persistente em vez de reiniciar o CLI a cada frase |
| Falar (voz) | ~7 s | **0,00 s** | Piper com daemon quente, no lugar do XTTS |

\* medição limpa. Fazendo muitas chamadas seguidas o modelo começa a segurar
(throttle) e o número sobe bastante — não confunda throttle com regressão.

**Três daemons ficam vivos** enquanto o Grimoire roda, todos filhos dele:
`grimoire_piper_daemon.py` (voz), `grimoire_stt_daemon.py` (ouvido) e um
processo `claude` em sessão persistente (cérebro). Juntos ocupam ~1,3 GB — antes
eram ~3,9 GB, porque o XTTS sozinho comia 2,5 GB.

**Piso que não dá para furar sem placa de vídeo:** o Whisper processa sempre uma
janela de 30 s, mesmo que você fale 1 segundo — provado transcrevendo um áudio
cortado em 1 s, que levou o mesmo tempo que um de 11 s. Modelos menores são mais
rápidos mas erram palavra de verdade (`medium` e `small` trocam "pelo" por
"pela"; o `small` chega a comer palavras), então foram reprovados.

### Atalhos locais — o trivial sem esperar o cérebro

Perguntas simples não precisam do Claude. **Que horas são**, **que dia é hoje** e
**abrir um app** (firefox, navegador, chrome, chromium, terminal, arquivos,
calculadora, editor) são respondidas **na hora**, sem os ~2,7 s do cérebro nem
custo de API. Fica em `grimoire_atalhos.py`, interceptado no `executar()` antes
do cérebro.

Regra de ouro do atalho: **na dúvida, deixa o cérebro decidir**. O casamento é
conservador e a lista de apps é curada (só o que existe na máquina). "Abre o
relatório", "abre o site do banco", "marca reunião às três horas" NÃO viram
atalho — vão para o cérebro, como antes. É otimização, nunca fonte de erro.
Coberto por 26 testes (`test_grimoire_atalhos.py`), metade deles de negativa.

### Configuração editável — `~/.config/grimoire/config.json`

O que o dono pode mudar sem tocar no código, num arquivo JSON criado sozinho no
primeiro boot (`grimoire_config.py`):

| Chave | Padrão | O que faz |
|---|---|---|
| `janela_desperto_seg` | 20 | segundos que segue ouvindo depois de te atender, sem repetir "Grimoire"; passado isso, dorme |
| `atalhos_ligados` | true | liga/desliga os atalhos locais acima |
| `stt` | openai | ouvido: `openai` (gpt-4o-mini-transcribe, rápido/preciso, ~US$0,003/min) ou `local` (Whisper, grátis/offline) |
| `stt_openai_modelo` | gpt-4o-mini-transcribe | modelo de transcrição da OpenAI |
| `cerebro` | openai | cérebro: `openai` (gpt-4.1-nano, rápido/barato) ou `claude` (CLI local, grátis na assinatura) |
| `cerebro_openai_modelo` | gpt-4.1-nano | modelo do cérebro na OpenAI (`gpt-4o-mini` = um pouco mais esperto, mais caro) |
| `motor` | kokoro | motor de voz: `kokoro` (humana, padrão), `piper` (sintética, reserva) ou `xtts` (humana, lenta) |
| `voz_kokoro` | pm_santa | voz do Kokoro: `pm_santa` (masculina grave), `pm_alex` (masculina) ou `pf_dora` (feminina) |
| `voz` | jeff | voz do Piper (só se `motor` = piper): `jeff`, `cadu` ou `faber` |

Config faltando ou torta **cai no padrão** em silêncio — nunca derruba a voz.
Mudou o arquivo? Reinicie: `systemctl --user restart grimoire`.

## Voz e conversa contínua

Dois interruptores no topo. Eles **acendem em dourado quando ligados**.

- **🔊 Voz**: **já vem ligado**. A voz padrão é **XTTS (humana)** — bem mais
  natural que a sintética, mas gerada no processador: cada resposta leva **~5-7s**
  para começar a falar (frase curta é mais rápida; "Oi!" sai em ~2s). Por isso o
  cérebro é instruído a **falar curto** (o detalhe vai para o texto).
- **🎙️ Ei Grimoire**: escuta o tempo todo, mas fica **dormindo** — só reage quando
  você diz **"Grimoire"** (como "Ok Google"). Ao ser chamado, atende e fica
  **desperto ~20s** para você emendar sem repetir o nome. A detecção do nome usa a
  própria transcrição (offline), então tem 1–2s de atraso — não é instantâneo como
  um Porcupine, mas não precisa de modelo novo. Ele só fica surdo **enquanto fala**
  (para não ouvir a própria voz); enquanto *pensa* ou *transcreve* ele continua
  ouvindo, e o que você falar espera na fila.
- Você também pode usar o **▶ Gravar** manual quando quiser (empurrar-para-falar).

### Se ele te ouvir mal (frase pela metade, palavra trocada)

Rode a calibração e fale uma frase longa quando ele pedir:

```bash
~/voice/whisper-venv/bin/python ~/voice/calibrar_microfone.py
```

Ela **guia por bipe**, não por texto (1 bipe = fique calado; 2 bipes = fale;
1 bipe grave = fim), porque rodando pelo `!` da conversa a tela só aparece no
final e você não veria a hora de falar. No fim ela imprime o comando exato do
ganho certo, calculado da sua voz.

**O ganho do microfone é a causa número um, e erra para os dois lados.**

| Ganho | Sua voz | Pico | Resultado |
|---|---|---|---|
| Capture 63 + Boost 2 (**+50 dB**, padrão da placa) | RMS 17080 | **100%** | estoura, distorce, o Whisper erra as palavras |
| Capture 40 + Boost 0 (+12,75 dB) | RMS 183 | 3% | a voz some no chiado do conversor (ruído 109) |
| **Capture 60 + Boost 0 (+27 dB)** | RMS 1164 | 76% | ✓ 4,8× acima do ruído, frase de 11,6 s inteira |

Alto demais estoura, baixo demais afunda no chiado — as duas pontas dão o mesmo
sintoma ("ele me ouve errado"). O alvo é voz com RMS perto de 1800 **e** pico
abaixo de ~70% da escala; vale a restrição mais apertada das duas.

O `grimoire.service` **ajusta o ganho sozinho** ao subir (duas linhas
`ExecStartPre` com `amixer`), porque o mixer volta ao padrão a cada reinício da
máquina — não adianta ajustar só uma vez na mão.

Como ele decide onde a frase começa e acaba (`grimoire_listen.py`):

| Ajuste | Vale | Para quê |
|---|---|---|
| `fim_ms` | 1100 ms | pausa que fecha a frase. Era 700 ms e cortava você no meio quando respirava |
| `saida_frac` | 0,5 | para *continuar* falando basta metade da linha — fim de palavra é sempre mais fraco |
| `max_ms` | 20 s | teto: entrega o que tem em vez de segurar para sempre |
| `pre_roll` | 10 quadros | 300 ms guardados antes da fala, para não cortar a primeira sílaba |
| `limiar_abs` | 380 | a linha do "isto é fala" (sua voz deve ficar bem acima) |

## Sempre disponível (serviço que não some)

O Grimoire roda como **serviço do systemd de usuário** (`~/.config/systemd/user/
grimoire.service`), com `Restart=always`: se cair, for morto, ou você mandar
Fechar, ele **volta sozinho em 2s**. Sobe junto com a sessão gráfica ao ligar o
PC, e também fica na **bandeja do sistema**.

- Ver estado: `systemctl --user status grimoire`
- Reiniciar após mudar o código: `systemctl --user restart grimoire`
- Parar de vez (raro): `systemctl --user disable --now grimoire`

**Limpar** recomeça do zero: apaga o campo de baixo, a conversa de cima **e a
memória do cérebro**.

## A voz: Kokoro (humana E rápida), Piper (reserva), XTTS (opcional)

Três motores. O padrão vem da config (`motor` em `~/.config/grimoire/config.json`);
`MOTOR_PADRAO` em `grimoire_tts.py` é o fallback do código.

- **kokoro** (PADRÃO) — modelo aberto (82M, Apache-2.0), voz **humana E rápida**.
  Daemon `grimoire_kokoro_daemon.py` (venv `kokoro-venv`) carrega o modelo (~325 MB)
  uma vez e fala frase a frase. MEDIDO nesta máquina: **~0,6 s até o primeiro som**
  com o daemon quente, 3–4× o tempo real. Vozes pt-BR: `pm_santa` (masculina grave,
  feiticeiro — padrão), `pm_alex` (masculina), `pf_dora` (feminina); troca em
  `voz_kokoro` na config. É o meio-termo que faltava entre o Piper (robótico) e o
  XTTS (lento). Instalar do zero: `kokoro-venv` com `kokoro-onnx`+`soundfile`, e os
  pesos em `kokoro-model/` (kokoro-v1.0.onnx + voices-v1.0.bin).
- **piper** (RESERVA universal) — sintético, porém instantâneo. Se o Kokoro não
  estiver instalado ou falhar numa fala, a voz **cai no Piper sozinha** (nunca fica
  muda). Vozes em `voz`: jeff/cadu/faber.
- **xtts** (opcional) — Coqui XTTS v2, a mais humana, mas ~5–7 s por frase no CPU.
  Ficou lento demais para conversa; disponível por `motor: "xtts"`.

**Streaming foi testado e descartado:** faria a voz começar em ~2s, mas neste
processador a geração é mais lenta que a fala, então o áudio **engasgaria**. Um
7s limpo é melhor que um começo rápido picotado. A única forma de ter voz humana
E instantânea é uma placa de vídeo (GPU) — que esta máquina não tem.

## As peças (cada uma com uma função clara)

| Arquivo | Função |
|---|---|
| `grimoire.py` | A tela: selo, conversa, cartões de confirmação, as três ações. |
| `grimoire_brain.py` | O cérebro: conversa com o `claude` e devolve uma ficha estruturada (pergunta/plano). |
| `grimoire_safety.py` | A rede de segurança: a palavra final sobre o risco de cada comando. |
| `grimoire_exec.py` | O executor: roda o comando e traz a prova (código + saída). |
| `grimoire_tts.py` | A voz: fala em português com o Piper, offline. |
| `grimoire_listen.py` | A escuta contínua: detecta início/fim da fala pela energia do áudio. |
| `grimoire_stt_daemon.py` | Os ouvidos: transcreve sua fala offline com o Whisper. |

## Testes

`python -m pytest -q` — cobre a rede de segurança (o modelo nunca rebaixa o risco;
destrutivo e alvo de rede sempre no topo; desconhecido sempre confirma) e o
parsing do cérebro e a detecção de fim de fala. Hoje: **22 testes verdes**.

## O que ficou para depois (de propósito)

- **Clicar sozinho no navegador** (apontar-e-clicar por conta própria) é frágil e
  não entrou. O Grimoire abre apps e digita em terminais — isso é sólido. Clicar
  na tela fica como capacidade separada, mais tarde.

## Instalar / rodar

Normalmente **não precisa** — o serviço já o mantém no ar. Para rodar à mão
(depuração): `python3 ~/voice/grimoire.py`. Para gerenciar o serviço:
`systemctl --user restart|status|stop grimoire`.

Dependências já instaladas nesta máquina: `claude` (cérebro), Whisper em
`whisper-venv` (ouvidos), Piper em `tts-venv` + voz em `piper-voices/` (voz),
`ydotool` (colar/digitar), `konsole` (terminal visível).
