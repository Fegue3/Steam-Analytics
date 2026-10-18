# Steam Analytics

**Projeto de Ciência de Dados (UBI, MEI 2026/27).** Monitorização da atividade e da popularidade de 500 jogos da Steam: jogadores de hora a hora, preços, descontos e avaliações, em 5 categorias de 100 jogos.

**Estado atual:** só a **seleção dos jogos** está feita. As recolhas, o processamento, o notebook e a app estão planeados. A estrutura do repositório (o que existe e o que falta) está em [`docs/estrutura.md`](docs/estrutura.md).

## 1. Instalação

Python 3.10+ e uma dependência (`requests`). Nenhuma API precisa de chave e não é preciso instalar o projeto.

```bash
pip install -r requirements.txt
```

## 2. Seleção dos jogos

Todos os comandos correm **na raiz do repositório**.

```bash
python3 -m unittest discover -s tests -v   # testes offline (sem internet)
python3 -m src.select_games                # gera config/games.csv
```

O resultado é **`config/games.csv`**, a lista que as recolhas usam:

```
appid,name,category,selection_date_utc
730,Counter-Strike 2,competitive,2026-10-18T18:52:31+00:00
570,Dota 2,competitive,2026-10-18T18:52:31+00:00
```

O seletor só grava se a lista estiver completa (100 jogos por categoria, sem AppIDs repetidos, todos com nome) e se nenhuma fonte tiver falhado. Caso contrário termina com código 2 e **não toca** na lista anterior. O resumo de cada execução (elegíveis por categoria, jogadores mínimo e mediano, rejeições por motivo) fica em `logs/selection.log`.

Demora **~1,5 min sem cache** e **~15 s com cache** (`data/cache/`: 24 h para listas e loja, 1 h para jogadores).

**A lista é uma fotografia da hora em que corre** (`selection_date_utc`): o ranking usa os jogadores desse momento. A versão oficial gera-se logo antes da recolha e o commit dessa versão fica como referência.

## 3. Como funciona

| Passo | Fonte | O quê |
|---|---|---|
| 1. Descoberta | SteamSpy `tag`/`genre` (~42 listas) + Steam `ISteamChartsService/GetMostPlayedGames` | União (OU) das listas das categorias. O TOP 100 oficial cobre jogos que faltam no SteamSpy (p.ex. Dota 2) |
| 2. Pool | — | Remove exclusões manuais, DLC/demos/OST pelo nome e jogos com CCU de ontem < 50 |
| 3. Detalhes | Steam `IStoreBrowseService/GetItems` (lotes de 200) + `IStoreService/GetTagList` | Etiquetas **com peso**, funcionalidades declaradas (Online PvP, Online Co-op…), editora, preço, tipo (jogo/software) e nome atual |
| 4. Classificação | `src/classify.py` | **Uma** categoria principal por jogo (regras abaixo). Remove software/companheiros de ecrã e jogos com CCU de ontem < 100 |
| 5. Jogadores | Steam `ISteamUserStats/GetNumberOfCurrentPlayers` (6 em paralelo) | Jogadores **agora** para todos os elegíveis, com a **mesma fonte que a recolha horária vai usar**. Jogos sem resposta (p.ex. Deadlock, 404) ficam de fora, porque não seria possível recolhê-los |
| 6. Escolha | — | **TOP 100 por jogadores atuais** em cada categoria |

### Regras de classificação (`config/categories.json`)

As categorias combinam etiquetas com **OU**: basta uma (p.ex. Strategy **ou** Simulation **ou** City Builder). Mas ter a etiqueta não chega, porque qualquer jogo pode ter uma etiqueta com 3 votos. Ela tem de estar entre as **5 mais votadas** do jogo. Etiquetas genéricas (Strategy, Simulation, Co-op, Online Co-Op, Survival, Automobile Sim) só contam no **top 4**.

1. **Etiquetas dominantes**:
   - `competitive`: PvP, Competitive, eSports, MOBA, Battle Royale, Hero/Arena/Extraction Shooter, Fighting. Tem **prioridade**: PUBG tem "Survival" como 1.ª etiqueta mas é competitivo. FPS sozinho não conta (Half-Life não é competitivo).
   - `strategy_sim` e `survival_coop`: ganha a etiqueta mais bem posicionada. Jogos de desporto (1.ª etiqueta "Sports") não contam como simulação.
2. **Sem etiqueta dominante**, por esta ordem:
   1. `competitive`: declara Online PvP/PvP na loja **e** tem, no top 5, uma etiqueta de tiro/combate **e** uma de multijogador (THE FINALS, Call of Duty/Warzone, Battlefield 6, Destiny 2).
   2. `aaa`: editora da lista + jogo pago + sem "Indie" no top 5. **É um proxy**, não uma classe oficial.
   3. `indie`: género Indie (lista `genre:Indie` do SteamSpy, declarado pelo programador) ou etiqueta Indie no top 5, e editora fora da lista de grandes editoras.
   4. `survival_coop`: declara Online Co-op **e** tem etiqueta de co-op no top 10 (Warframe).
3. Jogos que não encaixam em nenhuma (Path of Exile 2, AION 2, Garry's Mod, ...) ficam de fora.

**Consequência a declarar no relatório:** `aaa` e `indie` não incluem jogos de estratégia, sobrevivência ou competitivos (Valheim conta como `survival_coop`, Civilization como `strategy_sim`, Battlefield 6 como `competitive`).

### Revisão manual

Para retirar um jogo, acrescenta-se `appid,reason` a `config/exclusions.csv` e volta-se a correr (com cache, é rápido). As exclusões atuais (VRChat, treinadores de pontaria, …) estão lá com o motivo.

## 4. Utilização responsável e limites

- Cache em disco; ≥1,1 s entre pedidos SteamSpy; ≥0,5 s entre lotes da loja; no máximo 6 pedidos simultâneos de jogadores (~1700 por seleção, muito abaixo da quota diária de 100 000).
- Retentativas só para 429/5xx, respeitando `Retry-After`; os 4xx não são repetidos.
- Sem scraping de HTML, sem proxies, sem contornar bloqueios.
- A amostra é intencional (TOP 100 por jogadores de cada categoria) e não representa o catálogo da Steam.

Fontes: [SteamSpy API](https://steamspy.com/api.php), [Steam Web API — ISteamUserStats](https://partner.steamgames.com/doc/webapi/ISteamUserStats), [IStoreBrowseService](https://steamapi.xpaw.me/#IStoreBrowseService), [ISteamChartsService](https://steamapi.xpaw.me/#ISteamChartsService).
