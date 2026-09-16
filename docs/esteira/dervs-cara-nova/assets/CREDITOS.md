# CRÉDITOS — assets de dervs-cara-nova

Registro de origem e licença, como manda a regra da casa: todo asset entra
aqui, mesmo quando "gerado por código" também é uma origem que precisa
ficar dita.

## Fontes tipográficas (origem externa — Google Fonts)

**Atualizado após a decisão final de direção visual (HUD/JARVIS) — as fontes
da Direção C (Space Grotesk, IBM Plex Mono) foram substituídas por estas
duas, escolhidas pela Direção E por carregarem a referência de painel de
nave/ficção científica:**

| Fonte | Autor/mantenedor | Licença | Link |
|---|---|---|---|
| Orbitron | Matt McInerney, publicada via Google Fonts | SIL Open Font License 1.1 | https://fonts.google.com/specimen/Orbitron |
| Share Tech Mono | Carrois Type Design (Ralph du Carrois), publicada via Google Fonts | SIL Open Font License 1.1 | https://fonts.google.com/specimen/Share+Tech+Mono |

A licença SIL OFL 1.1 permite uso, modificação e **embarque em software**
sem custo e sem exigir atribuição visível dentro do app — o que este
arquivo faz é a prática da casa de registrar a origem mesmo assim, para
qualquer auditoria futura de licença. `design.md` já decide que as duas
vêm "empacotadas localmente no Electron (sem depender de rede em tempo de
execução — o app precisa abrir sem internet)"; a fase 5 deve baixar os
arquivos `.woff2` de cada família a partir do Google Fonts (ou do
repositório oficial de cada projeto) e trazer também o arquivo `OFL.txt`
de cada uma para a pasta de assets da fonte, como cópia da licença.

## Ícones e formas gráficas (gerados por código — sem origem externa)

Todo o restante especificado em `assets.md` — ícone do app, ícone de
bandeja, ícone de erro/aviso — é forma geométrica (círculo, anel, tick)
descrita em SVG, sem foto, sem banco de imagem, sem asset de terceiro.
Não há origem externa a creditar; a autoria é o próprio código deste
projeto, escrito a partir da Direção E ("HUD/JARVIS", decisão final em
`design.md`). Não é necessário repetir aqui o SVG de cada um — a
especificação exata está em `assets.md`.

## O que não existe nesta entrega

Não há foto real, vídeo real, ilustração de banco de imagem, nem asset
baixado de terceiro além das duas fontes acima. Ver justificativa completa
em `assets.md`, seção "confirmação — não falta nenhuma foto real".
