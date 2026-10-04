# O DERVS como funcionário 24 h, para várias pessoas — onde ele deve morar? (04/10/2026)

Pergunta do dono (03/10): "Quero o DERVS como agente 24 h que me entende 100% e faz tudo, junto com o
DERVS web, usado por outras pessoas em outros PCs, personalizado por usuário. O ideal é pôr numa VPS?"

## Resposta curta

**Não tudo na VPS, e não tudo no PC: híbrido.** A VPS vira o *cérebro que não dorme*; cada PC continua
sendo *ouvido, boca e mãos*. A hipótese do handoff se confirma, com duas correções (abaixo).

| Função | Onde mora | Por quê (motivo físico, não de gosto) |
|---|---|---|
| Ouvir ("Ei DERVS"), falar, atalho, widget | **PC de cada pessoa** | microfone, caixa de som e tela só existem ali |
| Mexer em arquivo, programa, VS Code, navegador logado | **PC de cada pessoa** | é o PC dela; a VPS não alcança |
| Fila de tarefas, perfis, permissões, cota de gasto, histórico | **VPS** (DERVS web) | precisa estar de pé 24 h e ser a mesma para todos |
| Trabalho longo sem ninguém na frente (consertar, pesquisar, relatório) | **VPS**, em contêiner isolado | roda de madrugada com o PC desligado |
| Chaves de API (OpenAI, Anthropic, JEV) | **só na VPS** | o `.exe` é distribuído: o que está dentro dele alguém extrai |

## Como as peças conversam

```
 PC da Maria ──(só saída, HTTPS, crachá do PC)──►  DERVS web na VPS  ◄──(só saída)── PC do João
   ouve / fala / executa o que a fila mandar         fila · perfis · cota · agente 24 h
```

- **O servidor nunca abre porta no PC.** O PC liga para o servidor e pergunta "tem tarefa para mim?".
  Isso já é regra (`arquitetura-plataforma.md`, item 4) e é a razão de operar *outros computadores* ser seguro.
- **Voz só com o PC ligado**; o trabalho do agente 24 h não depende disso: o resultado espera na fila e o
  DERVS do PC conta quando a pessoa chega ("enquanto você dormia, terminei X").

## Duas correções à hipótese

1. **"Me entende 100 %" é memória, não servidor.** Entender a pessoa = guardar preferências, projetos,
   jeito de falar. Isso é *dado pessoal* (LGPD): fica por conta, apagável pelo próprio usuário, e **nunca**
   mistura dado de uma pessoa com outra. Não existe hoje; é tabela nova no DERVS web.
2. **"Faz tudo" sozinho 24 h é o oposto de seguro.** O que já existe e deve continuar mandando:
   permissões por categoria (analisa / pergunta / sozinho), teto de gasto, quarentena em vez de apagar,
   cartão para tudo que muda servidor. O agente 24 h **herda as permissões do dono da conta**, e o que for
   grave espera o clique da pessoa na próxima vez que ela abrir o painel.

## Multiusuário: o que precisa existir (e hoje não existe)

- **Conta e perfil por pessoa** no DERVS web: voz, permissões, pastas de projeto, servidores permitidos.
- **Pareamento de PC**: cada PC tem um crachá revogável (já existe para o dono; falta o fluxo para terceiros).
- **Cota de gasto por conta**: hoje só há teto compartilhado (US$ 3 por sessão, R$ 50 por dia). Cota por
  pessoa exige tabela nova — decisão de produto do dono.
- **Quem paga as chaves**: assinatura pessoal (Claude Max, ChatGPT) **não** serve a terceiros (termos de
  uso); o servidor usa **chave de API** com teto no provedor.
- **Instalador do PC** (`.exe` assinado, com atualização): não existe; é a Onda F da Central do PC.

## Custo e capacidade (medidos em 01/10 pelo Claude Code da VPS)

VPS com 8 núcleos, ~23 GB de RAM (~20 GB livres), 100 GB de disco livre. O agente 24 h (Hermes 2–4 GB)
e o estúdio (Bolt.diy 1–2 GB) **cabem** com ~6 GB de folga no pior caso, desde que com `mem_limit`,
`pids_limit`, rede própria, sem `docker.sock`, e sem acesso ao banco nem ao `.env` de produção (dado de
paciente e pagamento nunca entram nesse contêiner). A parte cara não é a máquina: é a **chave de API**
por uso — cada tarefa 24 h gasta tokens. Sem teto por conta, uma pessoa pode gastar o orçamento de todos.

## Ordem recomendada (cada etapa entrega valor sozinha)

1. **Porteiro do JEV** (`/agente/voz/triagem`) — dono: janela DERVS web; tira a chave do PC do dono.
2. **Conta/perfil/cota por usuário** no DERVS web (decisão do dono sobre cota).
3. **Fila de tarefas + executor local**: o PC busca tarefas e as roda sob as permissões do perfil.
4. **Agente 24 h na VPS** (contêiner isolado, chave de API com teto no provedor).
5. **Instalador** do VOZ para outras pessoas.

**O que não fazer:** abrir o terminal SSH do VOZ como caminho para terceiros chegarem à VPS; pôr
assinatura pessoal do dono para atender outras pessoas; dar ao agente 24 h acesso à produção.

## O que depende de outros (não do VOZ)

DERVS web precisa da rota do porteiro e do deploy (hoje `/agente/voz/triagem` dá 404); o dono precisa
criar a chave de API com teto para Hermes/Bolt.diy e tratar as pendências de segurança da VPS listadas
em `arquitetura-plataforma.md` (seção 7).
