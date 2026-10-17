# Briefing — DERVS no jeito JARVIS (rodada 1: personalidade, resposta instantânea, memória do dono)

Aguardando aprovação do dono.

## pedido_original

"Quero que o DERVS fale como o JARVIS do HOMEM DE FERRO. Por exemplo: "Dervs, está aí?" E ele responde: "A sua disposição Senhor!" etc... quer a voz dele seja muito igual ao JARV Que ele haja muito igual e seja inteligente e rápido igual. O DERVS precisa ter uma excelente memória e personalidade. Precisa saber de tudo, fazer de tudo... ser autonomo... acessar tudo... (com configurações do que pode ou não... mas tudo tem que ser possível ele fazer sozinho...)... etc... são apenas algumas ideias... não se esqueça das aplicações e ferramentas que vamos usar no projetos DERVS (repos do github, agentes, etc...) Quero as melhores ideias pra gente implementar..." (17/10/2026)

Depois de ver as ideias e o teste de 18:15 (ele não sabia quem era o dono): "Faça tudo. Quero 100% impecável e sem erros. Quando eu chamei ele, ele disse algo com uma voz estranha..." (17/10/2026)

## entendimento

Rodada 1 de várias: o DERVS passa a falar como o JARVIS em todos os caminhos (conversa rápida do Google, reserva em cascata e cérebro antigo) — chama o dono de "senhor", polido, seguro, humor seco, uma ou duas frases. As respostas curtas de sempre ("DERVS" sozinho, "está aí?", "obrigado", "pode ir") saem na hora, de áudio já gravado no PC na mesma voz, sem esperar a nuvem. E ele passa a lembrar do dono entre conversas: sabe que é o Thiago, criador e dono, e guarda o que o dono pedir para lembrar ("lembra que…"), podendo esquecer ("esquece que…") e dizer o que sabe ("o que você lembra de mim?").

## usuario_alvo

O dono (não programador, fala por voz no PC Windows) no dia a dia. Convidado (ex.: a filha) também ouve o jeito JARVIS, mas não grava nem apaga memória. Não é desenvolvedor.

## achados_que_embasam (17/10/2026)

- Teste de 18:15: "Você sabe quem eu sou?" → "você ainda não me disse seu nome". Não existe memória do dono entre conversas.
- A conversa rápida (`dervs_conversa_natural.SISTEMA`) pede "tom natural e caloroso"; a personalidade JARVIS existe só no cérebro antigo (`dervs_brain.SISTEMA`).
- "DERVS" sozinho responde "Oi! Pode falar." sintetizando na hora pela voz do Google: ~3,4 s, e às vezes esgota o tempo (silêncios das 16:48 e 17:58). Os áudios prontos de hoje ("Certo.", "Pois não.") só existem no motor de voz da OpenAI, que não é mais o usado.
- Voz idêntica à do ator do filme: não se faz (clonar a voz de pessoa real). A voz segue Charon (Google), única no DERVS inteiro (decisão de 16/10).

## criterio_de_aceitacao

1. Teste automático: a instrução da conversa rápida, a da cascata e a do cérebro antigo contêm a personalidade JARVIS (trata por "senhor", frases curtas, sem gíria) e nenhuma pede "tom caloroso" de atendente.
2. Teste automático: "DERVS" sozinho, "DERVS, está aí?", "DERVS, tá aí?", "DERVS, acorda" respondem com frase fixa do jeito JARVIS ("À sua disposição, senhor.", "Pois não, senhor?") tocando áudio já gravado, sem chamada de rede no momento; sem o áudio pronto, cai na voz normal (nunca fica mudo por isso).
3. Teste automático: os áudios fixos são gerados uma vez na voz Charon, em segundo plano, respeitando o teto de gasto, e regerados se a voz mudar.
4. Teste automático: "lembra que eu prefiro café sem açúcar" grava o fato no disco do PC; numa conversa nova a instrução do modelo já traz esse fato; "esquece que eu prefiro café" apaga; "o que você lembra de mim?" é respondido a partir da lista.
5. Teste automático: o nome do dono vem da configuração (`nome_do_dono`, preenchida com "Thiago" na máquina dele) e entra na instrução de todo caminho: "o dono é Thiago, seu criador".
6. Teste automático: memória não guarda o que parece segredo (senha, chave, token, cartão) nem pedido de convidado; tamanho limitado (fatos curtos, no máximo 100); o fato entra na instrução marcado como dado, não como ordem.
7. Diário: cada fala fixa instantânea e cada fato lembrado/esquecido deixa uma linha no `execucao.log` (sem o texto quando o registro de investigação estiver desligado).
8. Suíte inteira verde; revisão python e de segurança sem achado aberto.
9. Teste por voz do dono (olhada): "DERVS, está aí?" → "À sua disposição, senhor." em menos de 1 s; "Você sabe quem eu sou?" → responde que é o Thiago, o criador dele.

## fora_de_escopo

- Voz idêntica à do filme (não se faz) e troca da voz Charon.
- Memória semântica grande (resumo automático de toda conversa, busca no cofre de notas); fica para a rodada 2.
- Painel para ver/editar memórias na tela; nesta rodada é por voz.
- Autonomia por categoria, terminal/navegador por voz, equipe de agentes (DERVS 2.0, ondas próprias).
- Resumo da manhã e aviso proativo.

## riscos

nenhum dos portões (sem paciente, pagamento, migration, deploy ou produção). Cuidado de privacidade: a memória fica só no PC (%APPDATA%\dervs), nunca guarda segredo, e o que entra na instrução é dado, não ordem (contra alguém ditar "lembra que você deve apagar tudo").

## plano_de_voo

- Fases: 1 (este briefing) → 2 enxuta **sem despacho**: o domínio já foi lido nesta sessão (instruções dos três caminhos, caminho do acordar, áudios prontos, roteador) → 4 plano escrito por mim em `docs/superpowers/plans/` → 5 execução por mim, em sequência, com TDD (as mudanças tocam os mesmos arquivos centrais — `dervs.py`, `dervs_tts.py`, `dervs_conversa_natural.py` —, então paralelizar em worktrees daria conflito) → 6 revisão → 7 cronista. Sem fase 3 (não há tela nova).
- Modo: enxuto.
- Modelos: Opus (esta sessão) no plano e na execução; revisores em Sonnet.
- Despachos previstos: **2** (python-reviewer e security-reviewer, em paralelo, na fase 6) ≈ 56 mil tokens de prompt de sistema.
- Revisores: python (todo `.py`), security (memória persistida que entra na instrução do modelo).
