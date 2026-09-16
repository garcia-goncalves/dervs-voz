# TEXTOS — dervs-cara-nova

Escrito pelo Redator de interface (fase 3), a partir de `spec.md`, `design.md` e
`direcao-c.md`. Cobre todo texto visível nos quatro estados da janela, a bandeja, os
tooltips e os dados de demonstração. Português do Brasil em tudo; nenhum termo técnico ou
em inglês chega à tela.

## rotulos_de_estado

| Estado | Texto na tela | Cor (token) | Observação |
|---|---|---|---|
| Ocioso | `DERVS` | `--texto-primario` | Só o nome, sem rótulo de status embaixo — é a tela de "nada precisa da sua atenção". Não escrevi "pronto" nem "aguardando": para quem deixa o programa aberto o dia inteiro, um rótulo de status parado o dia todo vira ruído visual, e a onda em repouso já avisa que o programa está vivo. |
| Ouvindo | `ouvindo` | `--rosa` | Minúsculo, como nos outros dois — rótulo de estado nunca grita em caixa alta. |
| Pensando (estado intermediário, entre "ouvindo" acabar e "falando" começar) | `pensando` | `--texto-secundario` (a onda ainda não pende para nenhuma cor de estado; fica no roxo neutro) | O `design.md` já reserva 22px/Space Grotesk para este rótulo na escala tipográfica, mas as 4 telas descritas não o desenham à parte — ele existe porque **há um intervalo real** entre o dono parar de falar e a resposta chegar (a chamada ao cérebro na OpenAI não é instantânea), e deixar a tela muda nesse intervalo pareceria trava. Decisão: mostrar `pensando` nesse vão, com a mesma física de "faixa respirando devagar" do estado ocioso. |
| Falando | `falando` | `--limao` | Minúsculo, mesma régua. |

## erros_e_avisos

Seguem o padrão do `ESTADO.md`: dizem o que aconteceu em uma frase curta e o que fazer,
nunca um código técnico. Cartão em `--bg-elevado`, borda `--rosa`, ícone de alerta gerado
por código.

**1. Sem som / silêncio detectado**
> Não chegou som nenhum. Fale mais perto do microfone, ou confira se ele não está mudo.

*(Não manda nada para a internet nesse caso — não há custo escondido em ficar em silêncio
perto do DERVS.)*

**2. Microfone desconectado**
> Não encontrei nenhum microfone ligado. Conecte um na entrada rosa do computador — o
> DERVS volta a ouvir sozinho, sem precisar reabrir nada.

**3. Um dos ajudantes do DERVS caiu (STT, TTS ou cérebro)**
> Uma parte do DERVS parou de responder. Feche e abra o DERVS de novo pelo atalho da Área
> de Trabalho — se continuar acontecendo, me avise.

*(Texto único para os três ajudantes de propósito: o dono não precisa saber se foi o que
ouve, o que fala ou o que decide — só precisa saber o que fazer. Se um dia isso exigir
diagnóstico, o detalhe técnico vai para o registro de queda que já existe, não para a
tela.)*

**4. Sem conexão com a internet**
> Sem internet agora, e o DERVS precisa dela para entender sua voz e decidir o que fazer.
> Confira sua conexão e tente de novo assim que voltar.

## bandeja_do_sistema

Os três itens do spec (`C8`) estão certos como decididos — confirmo os três, sem trocar
nenhuma palavra:

- **Abrir DERVS** — traz a janela para frente.
- **Recolher janela** — esconde a janela sem fechar o programa. Mantive "Recolher" em vez
  de "Minimizar" ou "Esconder": "recolher" é a palavra que uma pessoa leiga já usa para
  "guardar sem desligar" (guardar a persiana, recolher uma toalha), enquanto "minimizar" é
  jargão de barra de tarefas e "esconder" soa a algo que se esconde de alguém.
- **Sair do DERVS** — fecha o programa de vez. Mantive "Sair do DERVS" (nomeando o
  produto) em vez de só "Sair": é o único item que devolve controle, e nomear o que está
  saindo evita clique errado num menu de três linhas parecidas.

## tooltip_da_bandeja

Ao passar o mouse sobre o ícone da bandeja, o texto muda com o estado — é a única pista de
status disponível quando a janela está recolhida:

| Estado | Tooltip |
|---|---|
| Ocioso | `DERVS` |
| Ouvindo | `DERVS — ouvindo você` |
| Pensando | `DERVS — pensando` |
| Falando | `DERVS — respondendo` |
| Erro/aviso ativo | `DERVS — precisa de atenção` |

*(O tooltip de erro é deliberadamente vago: o dono só saberá que algo pede atenção dele ao
abrir a janela e ler o cartão — o tooltip é curto demais para caber a frase toda, e um
tooltip cortado no meio é pior que nenhum.)*

## tooltip_e_apoio_na_janela

- Sobre a faixa da onda, sem tooltip nenhum — a régua da direção C é que a onda se
  explica por cor e movimento, não por texto sobreposto.
- No cartão de erro, um texto de apoio menor (13px, `--texto-secundario`), abaixo da
  frase principal, só quando o problema tende a se repetir:
  > Isso costuma resolver na hora. Se insistir, feche e abra o DERVS de novo.
  (Aparece nos avisos 2, 3 e 4 acima; não aparece no aviso 1, porque silêncio pontual não
  é "problema que se repete", é o dia a dia normal de um microfone.)

## dados_de_demonstracao

Quatro trocas plausíveis, para captura de tela ou demonstração ao vivo — cobrindo o que o
`ESTADO.md` confirma que already funciona hoje (hora, abrir programa, pergunta geral ao
cérebro, anotar um lembrete). Nada de navegador nas trocas: o piloto de navegador está
marcado como não funcional no Windows (`ESTADO.md`, item 2.2), e um exemplo de demonstração
que mostra algo quebrado é pior que nenhum exemplo.

**1 — hora**
> Dono: "Que horas são?"
> DERVS: "Agora são 14h32."

**2 — abrir programa**
> Dono: "Abre o Bloco de Notas pra mim."
> DERVS: "Abrindo o Bloco de Notas."

**3 — pergunta geral (cérebro respondendo, não executando nada)**
> Dono: "Quantos gramas tem uma xícara de farinha?"
> DERVS: "Uma xícara de farinha de trigo dá em torno de 120 gramas."

**4 — lembrete falado**
> Dono: "Anota aí: ligar pro Ricardo amanhã de manhã."
> DERVS: "Anotado: ligar para o Ricardo amanhã de manhã."

*(Nomes fictícios — "Ricardo" — plausíveis para um lembrete pessoal, sem dado real de
ninguém.)*
