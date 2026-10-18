# Timeline do projeto

Registo, por ordem, do que foi feito e por quem. Serve de base à secção "Contribution" do notebook final.

Elementos do grupo: Francisco Pereira (@Fegue3), Daniel Cardoso (@imdtcode), Hugo Serra (@Hug00x).

## 1. Ideia do projeto

**Responsáveis:** Daniel, Hugo, Francisco

Definição do tema (monitorização da atividade e popularidade de jogos na Steam), das cinco categorias de jogos e das questões de investigação.

## 2. Documento da proposta

**Responsáveis:** Francisco, Daniel

Redação da proposta de trabalho (máximo 2 páginas) segundo o template do enunciado: objetivos, questões de investigação, arquitetura, fontes de dados, considerações éticas, processamento, análise exploratória, visualização e bónus.

## 3. Revisão de português da proposta

**Responsáveis:** Daniel, Hugo, Francisco

Revisão linguística e de conteúdo do documento da proposta antes da submissão.

## 4. Seleção dos jogos: primeira versão

**Responsável:** Hugo
**Commit:** `54e3017` (18/10/2026)

Primeira versão do seletor de jogos (`steam-game-selector/`):

- Cliente SteamSpy com cache, rate limiting, retentativas e logging.
- Seleção de 100 jogos por categoria a partir de listas de etiquetas e géneros do SteamSpy (união OU).
- Proxy para jogos AAA (lista de editoras + jogo pago).
- Atribuição de jogos únicos entre categorias, ficheiros de candidatos e relatório da execução.
- Testes offline.

## 5. Seleção dos jogos: nova versão e estrutura do projeto

**Responsável:** Francisco
**Commits:** `2081dd5`, `93f21ba`, `119ffef` (18/10/2026)

Correção dos problemas da primeira versão:

- **Classificação:** uma etiqueta só conta se estiver entre as mais votadas do jogo. Antes, jogos como Wallpaper Engine ou VRChat entravam em "competitivos" e Hearts of Iron IV em "sobrevivência".
- **Uma categoria por jogo**, pela etiqueta dominante. Antes, a ordem de atribuição tirava jogos à categoria certa.
- **Ranking por jogadores atuais**, medidos com a mesma API que a recolha horária vai usar (`GetNumberOfCurrentPlayers`). Antes usava proprietários estimados, o que favorecia jogos antigos ou já encerrados.
- **Descoberta completa:** acrescentado o TOP 100 oficial da Steam, porque havia jogos em falta no SteamSpy (p.ex. Dota 2).
- **Exclusão de software** e aplicações que não são jogos, com o tipo de aplicação da loja.
- **Exclusões manuais** documentadas com motivo (`config/exclusions.csv`).
- **Execução reduzida a ~1,5 min**, com pedidos em lote à loja Steam (200 jogos por pedido).
- **Validação antes de gravar:** a lista só é escrita se estiver completa e sem fontes falhadas.

