# Briefing — DERVS JARVIS: ativação segura, SSH/PuTTY, projetos e autoconfiguração (03/10/2026)

## pedido_original
"Preciso que o DERVS só ative se eu falar algum código, como OK GOOGLE... Ei DERVS ou OK DERVS. Ele não pode ativar do nada, nem ficar escutando minhas conversas quando eu não quiser. Quero que ele mesmo possa se autoconfigurar, desenvolver/programar e fazer tudo e qualquer coisa. Ele pode mexer no meu PC, no GitHub, servidor, navegador, etc. No servidor ele não precisa entrar, pois eu já tenho o Claude Code lá dentro, mas pode usar o terminal SSH do meu servidor para rodar comandos ou falar com o Claude Code da VPS. Eu uso o PuTTY no Windows; o DERVS pode acessar o PuTTY (eu autorizo). Pode também abrir meus projetos no VS Code ou usar o próprio terminal SSH dele. Quero a melhor voz, mais humana, brasileira, rápida, o mais real do JARVIS possível." (e: "gostei mais do CEDAR")

## entendimento
Três frentes: (1) escuta que só abre por um código (Ei/OK DERVS) ou por atalho de teclado, com indicador visível, desligamento automático e nada de escuta oculta; (2) o DERVS usa o SSH do dono por baixo (sessões salvas do PuTTY via plink ou OpenSSH) para rodar comandos e para conversar com o Claude Code da VPS, abre projetos no VS Code e mexe no GitHub, tudo dentro do painel de permissões; (3) o DERVS ajusta a própria configuração por voz, com lista fixa de chaves. A voz continua cedar; uma voz mais humana de terceiro só entra com teste de ouvido e aceite de custo.

## usuario_alvo
O dono (leigo em terminal, fala português, usa por voz e painel). Depois, sócios e funcionários com o DERVS instalado.

## criterio_de_aceitacao
1. Modos de escuta no painel: `Desligado` (padrão ao abrir, microfone fechado), `Atalho` (microfone só enquanto a tecla está apertada) e `Chamar por voz` (só se o dono ligar). Teste prova que em `Desligado` nenhum stream de microfone é aberto.
2. Indicador visível na bandeja e no painel quando o microfone está aberto; desligamento automático após N minutos sem uso (configurável); comando de voz "pare de ouvir" fecha o microfone.
3. Frase de ativação "Ei DERVS" / "OK DERVS" (e só ela): teste com áudios positivos e negativos ("meu Deus", "ok google", conversa comum) mede acertos e falsos alarmes; meta de zero ativação em 30 min de conversa gravada sem a frase.
4. Nenhum áudio sai do PC antes da ativação; o que não ativa é descartado (já é assim; teste de regressão).
5. SSH: o DERVS lista as sessões salvas do PuTTY (registro do Windows, sem ler senha nem chave) e roda comando por `plink -load <sessão> -batch` ou `ssh`; leitura (ls, status, logs) roda sem cartão; qualquer comando que muda servidor mostra cartão com o comando exato e exige clique. Testes com executor falso.
6. Falar com o Claude Code da VPS: comando de voz vira `claude -p` via SSH, com a saída resumida em voz; sempre cartão (servidor), nunca sozinho.
7. Projetos: "abre o projeto X" encontra a pasta por nome aproximado e abre no VS Code (`code`); "pede pro Claude consertar X" abre sessão do Claude Code naquela pasta, em worktree isolada, e nada vai para a `main` sem o sim.
8. GitHub por voz via `gh`/git: commit e push em branch próprio sob permissão; nunca `push --force`, nunca tornar repositório público, nunca apagar branch remoto sem sim explícito.
9. Autoconfiguração por voz: "fala mais rápido", "troca a voz para onyx", "ativa o modo sempre confirmar" mudam só chaves de uma lista fixa; chave de segurança (permissões, teto de gasto, pastas de projeto) exige clique.
10. Suíte completa verde, documentação atualizada, revisão de segurança antes de cada merge.

## fora_de_escopo
- Entrar dentro da VPS para instalar ou configurar (o dono já tem o Claude Code lá; o DERVS só fala com ele por SSH).
- Clonar a voz de uma pessoa real (Dileira, ator do JARVIS) ou usar áudio de terceiro.
- Dirigir a janela do PuTTY ou do VS Code por teclado simulado (frágil; usa plink/ssh e `code`).
- API Realtime da OpenAI (tempo real de verdade): projeto à parte, precisa do aceite de custo.
- Qualquer coisa em produção sem o sim do dono; Hermes e Bolt.diy na VPS (aguardam chave de API com teto).
- Trocar as travas fixas: nunca ignorar permissões, apagar só por quarentena, segredo nunca em chat.

## riscos
Alto: microfone (privacidade, LGPD), acesso ao servidor e ao GitHub, execução por voz (TV ou vídeo podem falar "Ei DERVS"). Mitigação: microfone fechado por padrão, atalho, indicador visível, auto-desligamento, cartão para tudo que muda servidor, travas fixas do painel de permissões, revisão de segurança e prova na tela real. Dado de paciente: nenhum acesso novo.

## plano_de_voo
Modo enxuto, em ondas: A modos de escuta + atalho + indicador (Python/Electron, `neguin-executor` sonnet); B SSH/PuTTY + Claude da VPS (reaproveita `dervs_ssh.py` e `dervs_integracao_painel.py`); C projetos/VS Code/GitHub; D autoconfiguração por voz; E detector de palavra dedicado (openWakeWord/Porcupine) só se a medição do critério 3 falhar com o porteiro atual. Revisão: security-reviewer em A, B e D; python-reviewer; design-reviewer na tela de modos. Despachos previstos: cerca de 14.
