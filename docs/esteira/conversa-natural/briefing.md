# Briefing — Conversa natural (voz direta, interrupção só por quem fala com ele)

Aprovado em: 2026-10-15 ("sim, pode seguir pelo econômico" e "Prossiga até o fim!")

## pedido_original

"testei o DERVS VOZ e parece que a voz está lenta e robotizada. Quero a voz mais rápida, fluida e humanizada. Teste tudo e me sugira o melhor! Quero que o DERVS converse comigo numa conversa fluida e normal... como se fosse o chat de voz do ChatGPT... parece que estou conversando com uma pessoa mesmo. O DERVS precisa saber quando eu gaguejo, quando eu estou respirando ou dando tempo para pensar. Não podemos um interromper o outro. Quasndo eu solicitar algo pra ele QUE SEJA FÁCIL DELE ENTENDER E FAZER, ele não precisa me responder nada. APENAS FAÇA! Caso ele fique comk dúvidas, ele SEMPRE precisa alinhar tudo comigo antes de fazer. NUNCA FICAR COM DUVIDAS." (15/10/2026)

Complementos do mesmo dia: "quero poder interromper ele, como no ChatGPT... e ele vai mudando as tarefas na hora e atendendo minhas mudanças... mas ele não pode escutar se outras pessoas estiverem falando ao meu redor (não pode ser interrompido por conversas de outras pessoas que estiverem próximas). Pois o GPT interrompe por qualquer barulho..." e "outras pessoas podem querer usar/testar (como minha filha por exemplo) e ele precisará atender ela tbm (temos que poder configurar isso eu acho)... tipo: sempre poder gravar a voz de quem vai interagir naquele momento..."

## entendimento

A conversa do DERVS ganha uma camada local (no PC, grátis) que decide quem está falando, quando a pessoa terminou de verdade e quando ela interrompe; e um motor de conversa trocável que ouve e fala. Padrão econômico: Gemini Live 3.8 (voz direta do Google, faixa grátis); reserva barata: Groq transcreve + cérebro de hoje + voz do Google/OpenAI em fluxo; premium opcional: voz direta da OpenAI. Pedido claro e fácil é feito em silêncio com um sinal curto; ambíguo vira pergunta antes; grave continua pedindo confirmação.

## usuario_alvo

O dono (não programador, fala por voz, PC Windows sem placa de vídeo, com fone ou caixa de som) e quem ele cadastrar (por exemplo a filha), conversando com o DERVS no dia a dia. Não é desenvolvedor.

## medicoes_que_embasam (15/10/2026, nesta máquina)

- Hoje: ~5,0 s do fim da fala ao primeiro som; a voz atual levou 4,0 s para gerar uma frase e ainda é acelerada no PC (WSOLA 1,25x), provável causa do "robótico".
- Voz direta: primeiro som em 0,7 s (mini) e 1,0 s (completo); resposta inteira em 1,4 s (mini). As 10 vozes funcionaram em pt-BR; amostras em `amostras_voz/conversa_15-10/ouvir.html`.
- Pausa para pensar (fala hesitante mandada em tempo real): só silêncio de 0,5 s cortou "Eu queria que você…" no meio; o modo semântico NÃO cortou ali nem em "me lembra de ligar pro…" + 2,5 s, mas cortou depois de "éé… hum…" + 1 s e depois de "cria uma pasta nova" + 1,2 s. Conclusão: o semântico da OpenAI sozinho não basta; precisa do árbitro local.
- Reconhecer quem fala (modelo local ERes2Net, sherpa-onnx, CPU): 9 de 10 vozes certas usando 5 s de amostra, 65 ms de CPU por segundo de fala. Vozes sintéticas são mais parecidas entre si que pessoas; prova real exige o dono e a filha.

## decisoes_do_dono (15/10/2026)

1. Caminho ECONÔMICO (o dono achou a voz direta da OpenAI cara: ~US$ 35–45/mês no mini). Meta: ~US$ 0–3/mês no uso pesado (3 h/dia).
2. Motor padrão `gemini_live` (gemini-3.8-live, 0,78 s até o 1º som, faixa grátis); reserva `cascata` (Groq whisper-large-v3-turbo 0,3–0,5 s + cérebro atual + voz em fluxo gemini-3.8-flash-lite-tts → gpt-4o-mini-tts → Kokoro); premium `openai_realtime` (gpt-realtime-2.1-mini) só por chave de config. Troca sozinha ao bater limite (429), sem internet ou teto de gasto.
3. Claude Max e ChatGPT Plus não dão voz por API (conferido em docs oficiais); a assinatura do Claude segue como cérebro de tarefas pesadas, sem custo extra.
4. Voz: o dono escolhe de ouvido em `amostras_voz/conversa_15-10/ouvir.html`; padrão até lá: Charon (Gemini) e cedar (OpenAI).
5. Pedido fácil feito em silêncio dá um sinal: som curto + luz do widget.
6. Perfis de voz por pessoa (ex.: a filha), gravados pelo painel, ativáveis na hora; só a impressão numérica fica no PC.
7. Permissão por perfil: dono tudo; convidado conversa e faz só ação fácil e reversível.
8. Chaves: GROQ_API_KEY e GEMINI_API_KEY gravadas em 15/10 por `scripts/guardar-chave.ps1` e validadas.

## aviso_de_privacidade

Na faixa grátis do Google o conteúdo enviado (a fala do dono que passou pela trava de perfil) pode ser usado pelo Google para melhorar produtos. Dado de paciente não deve ser ditado ao DERVS no motor grátis; o painel mostra qual motor está ativo e há chave para forçar `cascata`/`openai_realtime`.

## criterio_de_aceitacao

- [ ] Rapidez: em 10 frases completas gravadas, mandadas em tempo real pelo caminho de produção, a mediana do fim da fala até o primeiro som tocado é ≤ 1,5 s. Provado por script em `scripts/` que grava o relatório.
- [ ] Pausa para pensar: nos 4 casos de hesitação do teste de 15/10 (meio de frase + 1,5 s, "éé… hum…" + 1 s, "ligar pro…" + 2,5 s, gagueira) o DERVS não emite nenhum som antes do fim real da fala. Provado pelo mesmo script.
- [ ] Interrupção pelo dono: voz falando por cima do DERVS abaixa o volume dele em ≤ 0,3 s; confirmada como perfil ativo, o som para em ≤ 0,9 s (não confirmada, o volume volta) e o novo pedido é atendido levando em conta o que mudou. Provado por teste com áudio gravado e por teste unitário do árbitro.
- [ ] Outras pessoas: voz não cadastrada (ou de perfil inativo) falando durante e fora da fala do DERVS não interrompe nem vira pedido em ≥ 9 de 10 casos, e esse áudio não é enviado à nuvem. Provado por script com vozes diferentes e por teste que confere o que sai para o socket.
- [ ] Eco: a própria voz do DERVS saindo da caixa de som não o interrompe (cancelamento de eco ligado ou, sem ele, a trava do perfil). Provado tocando uma resposta longa em caixa de som num teste manual registrado em `verificacao.md`.
- [ ] Perfis: gravar, listar, ativar/desativar e apagar perfil pelo painel; arquivo só com a impressão numérica em `%APPDATA%\dervs\vozes\`; apagar remove o arquivo. Provado por testes e por uma olhada no painel.
- [ ] Fácil = só faz: pedidos da lista de ações fáceis (abrir app, hora, volume, abrir pasta, tocar música e afins) executam sem resposta falada, só com o sinal. Provado por teste com frases.
- [ ] Dúvida = pergunta antes: pedido ambíguo ou incompleto ("apaga aquilo", "abre o projeto" sem dizer qual) gera pergunta e nenhuma ação. Provado por teste com frases.
- [ ] Grave continua igual: `plano_pede_confirmacao` e as travas de hoje valem para ação vinda da voz direta; os testes atuais continuam verdes e há teste novo pelo caminho da voz direta.
- [ ] Permissão do convidado: perfil convidado pedindo ação grave, Claude Code, Codex, SSH ou mexer em arquivo recebe recusa falada. Provado por teste.
- [ ] Reserva: sem internet, sem chave ou com o teto de gasto estourado, cai no modo de hoje com aviso falado. Provado por teste.
- [ ] Troca de motor: 429/limite grátis, erro de rede ou teto de gasto no motor ativo passa ao próximo (gemini_live → cascata) com aviso curto, sem perder a conversa. Provado por teste com dublê.
- [ ] Gasto: minutos e tokens de cada motor entram no gasto do dia do painel. Provado por teste do `dervs_gasto`.
- [ ] Suíte inteira verde com `dervs-venv\Scripts\python.exe -m pytest -q`; `COMO-USAR.md`, `ESTADO.md` e `requirements.txt` atualizados no mesmo commit.
- [ ] Prova com o dono: 10 minutos de conversa real (com hesitação de propósito e alguém falando perto); ele diz se aprova.

## fora_de_escopo

- GPT-Live-1 (voz full-duplex nova da OpenAI, outro endpoint): avaliar numa onda seguinte, comparando com esta.
- Vozes de outras empresas (ElevenLabs, Cartesia, Azure, Gemini): só se a voz da OpenAI não agradar de ouvido.
- Trocar o porteiro "DERVS" ou os modos de escuta Desligado/Atalho/Voz: continuam como estão; a conversa nova entra depois de acordar.
- Voz/personalidade diferente por perfil.
- Microfone pelo Electron: o áudio continua em Python.

## riscos

- Custo por minuto de API paga (conta da OpenAI do dono): limitado pelo teto diário que já existe e mostrado no painel.
- Voz de menor de idade (a filha): fica só a impressão numérica no PC, nunca áudio, nunca nuvem; apagar o perfil apaga o arquivo.
- Áudio de terceiros por perto: barrado antes de sair do PC pela trava do perfil.
- Sem dado de paciente, pagamento, migration ou produção.

## plano_de_voo

- Fase 2 (descoberta): já feita nesta sessão: mapa do código (1 despacho) e pesquisa de mercado (1 despacho) + 3 testes medidos. Falta só a spec, escrita por mim (sem despacho).
- Fase 3 (design): enxuta, só a tela de perfis de voz no painel, por mim com o `design-system` existente (sem despacho).
- Fase 4: `neguin-planner` (1 despacho, opus).
- Fase 5: `neguin-executor` ×4 em paralelo, em worktrees (sessão da voz direta e áudio em fluxo; perfis e trava de voz; árbitro de vez, interrupção e eco; política fácil/dúvida/grave, permissões e painel). Sonnet.
- Fase 6: `python-reviewer`, `security-reviewer`, `design-reviewer` em paralelo (3 despachos) + verificação real por mim.
- Fase 7: cronista por mim.
- Modo enxuto. Despachos previstos: ~10 (2 já feitos).
