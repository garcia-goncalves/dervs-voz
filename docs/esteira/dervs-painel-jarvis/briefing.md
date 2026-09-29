# BRIEFING — dervs-painel-jarvis

## pedido_original

"Tá tudo bugado e travando. A voz é horrivel. Sotaque ridiculo. Quero sotaque brasileiro... quero voz real. Não quero que pareça robo... quero um painel incrível do dervs... como se fosse o JARVIS bem completo e revolucionário..." — e, à proposta de painel grande com 3 colunas e gasto do dia: "sim faça tudo".

## entendimento

Voz (motor de nuvem com sotaque brasileiro) e travamento (Kokoro pesado) já foram resolvidos em 28/09/2026 (commit bdd3bc9). Falta o painel: uma janela grande estilo JARVIS, aberta por Ctrl+Alt+D ou pelo botão do widget, com reator central animado que reage à voz, sistema ao vivo à esquerda, agenda e diário à direita, conversa e ações embaixo, e no topo o status das peças e o gasto do dia em dólar. O widget compacto de hoje continua existindo.

## usuario_alvo

O dono da máquina, leigo em terminal, que julga tudo pelo que vê na tela. Não é desenvolvedor.

## criterio_de_aceitacao

1. Ctrl+Alt+D (ou botão no widget) abre a janela grande; de novo, esconde. Foto só da janela mostra reator, coluna de sistema, coluna de agenda/diário, faixa de conversa e barra de status.
2. CPU, RAM, disco e rede mostram valores reais com gráfico de histórico (últimos ~60 s), atualizando sozinhos.
3. A agenda mostra os lembretes reais de `dervs_lembretes` e o diário mostra as entradas reais de `dervs_diario`; sem itens, mostra estado vazio com texto claro.
4. A barra de status mostra microfone, voz (nuvem ou local), internet e o gasto do dia em dólar, e o gasto sobe quando o DERVS fala ou transcreve (coberto por teste).
5. O reator reage à amplitude da voz e a animação cai para no máximo 10 quadros por segundo com a janela escondida ou sem foco; parado, o DERVS inteiro fica abaixo de 0,6 núcleo de CPU (medido).
6. `python -m pytest -q` continua 100% verde, sem microfone real, e o que já funcionava (widget, cartão de plano, cartão de erro, reunião 1h) segue igual.

## fora_de_escopo

Login ou cofre do DERVS App; integração funcional profunda com o projeto dervs; clima e notícias (dependem de serviço externo); mudar voz ou cérebro; publicar em servidor.

## riscos

nenhum. Não há dado de paciente, pagamento, migration ou produção. O gasto do dia é estimativa local, gravada só na máquina.

## plano_de_voo

Fases 1, 3, 5, 6, 7. Modo enxuto: descoberta dispensada porque o repositório e o pedido já são conhecidos (esteira anterior dervs-painel-completo). Um despacho gordo de construção em worktree isolada (sonnet), revisão por mim (foto da janela, medição de CPU, suíte) e um revisor typescript/python se o diff justificar. Despachos previstos: 2 a 3.
