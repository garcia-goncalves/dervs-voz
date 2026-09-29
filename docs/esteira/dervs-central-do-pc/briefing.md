# BRIEFING — dervs-central-do-pc

## pedido_original

"Quero a aplicação funcionando e finalizada", "quero o painel ultra revolucionário e muito inteligente", "quero que meu pc sempre esteja sem erros e atualizado". Só o painel grande, com minimizar/diminuir/fechar e acesso fácil (bandeja do Windows). Usar o Claude Code de verdade, "exatamente igual ao que estamos usando, o mesmo Claude", com MCPs (ex.: Playwright para abrir navegador e clicar em tudo). Acesso à máquina inteira para analisar e corrigir tudo. Central do PC: manutenção, análises, saúde, melhorias, atualizações. Sobre autonomia (29/09/2026): "Quero máxima inteligência, assertividade, mas também quero segurança. Não pode apagar nada sem antes analisar tudo profundamente e me dizer o que é cada coisa que quer apagar. Sempre com minha aprovação. Mas terá autonomia para acessar tudo e fazer tudo."

## entendimento

O DERVS passa a ter uma única janela, o painel grande, que vive na bandeja do Windows e abre por atalho, e o widget pequeno deixa de existir. Dentro dele roda o mesmo Claude Code que o dono usa no VS Code (mesmas configurações, skills e MCPs), com acesso amplo à máquina para analisar tudo. Uma Central do PC mostra saúde, erros, atualizações e limpeza; tudo que muda ou apaga algo só acontece depois de uma análise profunda que explica o que é cada item, e do sim explícito do dono.

## usuario_alvo

O dono da máquina, leigo em terminal, que decide o produto e julga pelo que vê na tela e ouve. Não é desenvolvedor.

## criterio_de_aceitacao

1. Existe uma única janela do DERVS (o painel grande). Ela tem minimizar, diminuir/restaurar e fechar; fechar só esconde para a bandeja; o ícone da bandeja tem menu (abrir, sair) e o atalho global abre e esconde. Provado por foto só da janela e por teste da lógica de abrir/esconder.
2. O painel roda o `claude` real do dono (CLI com `~/.claude`, MCPs e skills), pela assinatura, sem chave de API. Provado: uma pergunta feita no painel é respondida pelo Claude Code e o resultado aparece em streaming na tela; o `cerebro: "claude"` funciona por voz e por texto.
3. O Playwright (MCP) responde dentro do painel: o dono pede "abre o site X" e o navegador abre. Provado por execução real.
4. Nenhuma ação que apaga, desinstala, altera configuração do sistema ou instala algo roda sem antes existir um relatório de análise mostrando, item por item, o que é, onde está, tamanho, por que é seguro (ou não) tocar, e o que muda se for feito; e sem o clique de aprovação do dono naquele item. Provado por teste automatizado (a ação recusa sem aprovação registrada) e por revisão de segurança.
5. A Central do PC mostra dados reais de: saúde e espaço do disco, erros recentes do Visualizador de Eventos, atualizações pendentes (Windows Update e winget), programas de inicialização e processos pesados, Defender e firewall, e arquivos temporários candidatos à limpeza. Provado por foto da tela e por testes dos coletores com dados simulados.
6. O "diagnóstico do dia" resume o estado do PC em poucas frases faladas em português, só leitura, sem mudar nada. Provado por execução e teste do resumo.
7. Toda ação sensível (analisar, propor, aprovar, executar, desfazer) fica registrada em um log local que o dono pode abrir no painel. Segredos nunca entram nesse log.
8. `python -m pytest -q` e os testes JS continuam 100% verdes, sem microfone real, e o que funcionava (voz echo, gasto do dia, lembretes, diário, reunião 1h) segue igual. Consumo parado do app abaixo de 0,6 núcleo.

## fora_de_escopo

Correção automática sem aprovação (nem em horário fixo: agendado só analisa e avisa); trocar a voz ou o motor de fala; publicar em servidor ou GitHub Actions; controle do PC por acesso remoto; qualquer coisa nos projetos de outras janelas; instalar programa novo sem aprovação item a item.

## riscos

ALTO. Acesso à máquina inteira somado a comando por voz e por Claude Code: apagar arquivo, desinstalar programa, mexer em serviço, registro ou firewall, e injeção de instrução vinda de conteúdo web ou de arquivo. Mitigações previstas: portão de risco desta esteira; aprovação item a item registrada em código; lista de caminhos protegidos que nunca se apagam (sistema, perfis, pastas de projeto, `.git`, `.claude`, dados de paciente de outros apps); apagar = mandar para a Lixeira ou quarentena reversível, nunca exclusão direta; revisão security-reviewer antes de mesclar; `dervs_safety.py` continua valendo por cima.

## plano_de_voo

Fases 1, 2 (enxuta), 3 (design do painel único), 4, 5, 6 (com portão de risco), 7. Entrega em 4 ondas, cada uma testada e enviada ao GitHub antes da próxima: A) painel único + bandeja; B) Claude Code real dentro do app (streaming, MCPs, Playwright); C) motor de aprovação e trava de análise-antes-de-agir; D) Central do PC (coletores, análise, limpeza reversível, diagnóstico do dia por voz). Modo enxuto na descoberta: um despacho com as quatro perguntas (opus, por causa do risco). Executores em worktree (sonnet), revisores python, typescript e security (obrigatório, por causa do risco). Despachos previstos: 12 a 16.
