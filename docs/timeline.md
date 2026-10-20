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


## 6. Recolha automática de dados

**Responsável:** Daniel
**Commits:** `082ceda`, `1e1d253`, `3608ad3`, `b74f917` (PR #1), `ec45408`, `a9d5bcd` (19/10/2026)

Implementação dos coletores e da sua execução automática com GitHub Actions:

- **Branch `data`:** branch órfã criada só para os dados brutos (`raw/`) e os logs (`logs/`), um ficheiro JSONL por fonte e por dia. É escrita apenas pelos GitHub Actions; o código fica na `main`.
- **Recolha horária** (`collect_players`, `collect_store`): jogadores atuais de cada jogo (`GetNumberOfCurrentPlayers`) e dados da loja Steam (preço, desconto, contagem e percentagem de reviews), com pedidos em lote de 200 jogos.
- **Recolha diária** (`collect_daily`): contagens exatas de reviews (`appreviews`) e estimativas do SteamSpy (proprietários, jogadores, preço).
- **Validação dos coletores:** cada jogo fica marcado como `ok`, `no_data` ou `error`, e cada execução regista contagens, hora UTC e o identificador do run. As fontes são independentes: a falha de uma não impede a recolha das outras. Não são guardados textos, autores ou identificadores de utilizadores das reviews.
- **Workflows:** os dois workflows partilham um grupo de `concurrency`, para nunca escreverem na `data` ao mesmo tempo, e fazem commit e push com retentativas.
- **Teste:** execução manual a 19/10/2026 com os 500 jogos recolhidos em todas as fontes, sem erros. Os dados deste teste foram removidos da `data` antes do início da recolha.

### Horário e período de recolha

- **Horário:** no primeiro teste o cron do GitHub saltou as recolhas das 01:17 e 02:17 UTC de 20/10/2026 e atrasou a diária 4 horas. Por isso a recolha horária tem cinco crons por hora (minutos 7, 17, 29, 41 e 53) e a diária três por dia (05:40, 12:40 e 18:40 UTC). Só a primeira tentativa recolhe: a horária salta se a hora já tiver uma recolha com dados e a diária só recolhe as fontes sem recolha completa nesse dia. Opcionalmente, o cron-job.org pode disparar os workflows pela API (`workflow_dispatch`). Ver [`agendamento.md`](agendamento.md).
- **Período de recolha:** definido pelas variáveis do repositório `COLLECT_START` e `COLLECT_END` (UTC). Fora desse período, os runs agendados terminam sem recolher; as execuções manuais ignoram o período. Os runs agendados só recolhem no repositório `Fegue3/Steam-Analytics`.
- **Primeiro período:** teste de 48 horas, de 20/10/2026 00:00 UTC a 22/10/2026 00:00 UTC.
