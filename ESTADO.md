# Estado do DERVS — 15/10/2026

Uma página, escrita para o dono (não para programador). O diário completo, rodada por
rodada, está em `docs/historico/estado-ate-2026-10-15.md`.

Última verificação: 15/10/2026 — **3.163** testes verdes (3 pulados) no ambiente do projeto
(`dervs-venv`).

## O que funciona hoje

- **Abrir:** pelo atalho (Área de Trabalho ou menu Iniciar) ou `Ctrl+Alt+D`. Um DERVS só de
  cada vez: o segundo clique traz o primeiro de volta.
- **Falar com ele:** o microfone nasce fechado. Você escolhe no painel: Desligado, Atalho
  (`Ctrl+Alt+Espaço`) ou Chamar por voz ("DERVS, ..."; fecha sozinho após 10 min).
  "DERVS, pare de ouvir" fecha na hora.
- **Entender e fazer:** transcreve a fala, o cérebro (OpenAI) decide, ele diz "Entendi: vou..." e
  executa. Só pede o seu OK no que é grave (apagar, servidor, gastar). Voz masculina `cedar`.
- **Painel único:** CPU/RAM/disco reais, gasto do dia, Central do PC (saúde, atualizações,
  limpeza com quarentena e Desfazer), o que o DERVS pode fazer sozinho (8 categorias),
  integração com o painel web.
- **Por voz:** abrir projeto, commit e push num branch novo, servidor pelo PuTTY, Claude Code
  e Codex (só depois do seu "confirma"), segundo cérebro (notas no cofre).
- **Segurança:** comandos passam por trilhos de risco; segredo nunca no repositório; o que o
  microfone ouve não prova que foi você (confirmação grave só por clique).

## O que está sendo construído

- **Conversa natural (voz direta).** Depois de acordar, ele conversa sem o vai-e-vem de
  frase por frase: sabe quando você terminou, aceita ser interrompido e só obedece à sua
  voz (ou a de um convidado, que faz só o fácil). Já roda no app, com testes. Se a voz
  direta cair, ele avisa e volta ao caminho antigo por 10 minutos — e nesse caminho
  também confere a sua voz (corrigido hoje: antes ele aceitava qualquer um).
  Já há a tela "Vozes" no painel e o cancelamento de eco. **Falta:** a prova com você.
- **Cérebro próprio (15/10).** O DERVS pensa com a configuração dele, em
  `%APPDATA%\dervs\cerebro` (personalidade, regras e memória só dele), fora de qualquer projeto.
  O seu Claude Code de programação só é emprestado quando você cita um projeto, e roda na pasta
  dele, com cartão para mandar ao GitHub. **Falta:** você entrar com a assinatura uma vez (botão
  ENTRAR do painel).

## O que está pendente e só você resolve

1. **Falar com ele de verdade** perto do microfone (10 frases diferentes e 10 minutos de
   conversa) para a conversa natural poder ser dada como pronta.
2. **Gravar a sua voz** (30 s) quando a tela "Vozes" estiver pronta; até lá a trava de voz
   fica aberta (zero perfis = passa tudo).
3. **Passar 20 a 30 nomes** que você fala no dia a dia (clientes, empresas, pessoas) para o
   vocabulário da transcrição.
4. **Decidir** se mantém a voz da nuvem (centavos por fala) ou volta à local (grátis, mais
   robótica).
5. **Provas que dependem de você:** o painel contra o servidor real do DERVS web (parear
   de novo) e "DERVS, como está meu PC?" falado de verdade.

## Como refazer o ambiente

Receita em `docs/historico/estado-ate-2026-10-15.md`, seção 5, e em `COMO-USAR.md`.
