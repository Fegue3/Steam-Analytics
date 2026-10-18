# Steam Game Selector — seleção auditável de 500 jogos

**Projeto para o trabalho de Ciência de Dados (rascunho técnico).** Seleciona **100 jogos distintos por grupo** a partir do SteamSpy, recorrendo a uniões lógicas (OU) de etiquetas e géneros. **Não monitoriza ainda jogadores de hora a hora**; esta é apenas a fase de seleção inicial. O código foi testado localmente com respostas simuladas; a execução real depende do acesso ao SteamSpy.

## 1. Configuração

Usar Python 3.10+:

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Executar os comandos **na pasta onde está este README**.

## 2. Começar com um teste pequeno (recomendado)

```bash
python -m src.select_games --per-category 5 --catalog-pages 1
```

Resultado: até 25 jogos, para confirmar ligação à API, campos e seleção. A categoria AAA apenas procura editoras em `--catalog-pages` páginas do catálogo global.

## 3. Seleção completa dos 500 jogos

```bash
python -m src.select_games --per-category 100 --catalog-pages 3 --strict
```

Se tiveres menos de 100 AAA válidos, aumenta as páginas:

```bash
python -m src.select_games --per-category 100 --catalog-pages 5 --strict
```

**Nota:** o endpoint `request=all` tem intervalo mínimo de ~60 segundos entre pedidos. Com cinco páginas não esperes resultados instantâneos. As consultas são guardadas em cache por 24 horas, para evitar repetir pedidos desnecessários.

## 4. Saídas

```
config/categories.json        # regras das 5 categorias; editável
config/exclusions.csv         # IDs a excluir após revisão manual
src/select_games.py           # recolhe, classifica e seleciona
src/steamspy_client.py        # HTTP, cache, retries e rate limit
src/audit_games.py            # auditoria ao CSV gerado
logs/selection.log            # registo de operações

# Criados pela execução:
data/cache/*.json             # respostas originais da API (cache 24h)
data/output/all_candidates.csv # todos os candidatos por grupo
data/output/games_500.csv    # seleção completa (só se houver 500)
data/output/games_INCOMPLETE.csv # se faltar algum grupo
data/output/report.json       # contagens, fontes e falhas
```

Valida o CSV:

```bash
python -m src.audit_games data/output/games_500.csv
```

Caso queiras escolher mais pela atividade recente do que por proprietários estimados:

```bash
python -m src.select_games --ranking ccu --per-category 100 --catalog-pages 3 --strict
```

**Não confundir:** o campo `ccu` do SteamSpy é o pico de utilizadores simultâneos **do dia anterior**, não o número de utilizadores em tempo real. O ranking padrão `owners` usa o limite inferior da estimativa de proprietários, com desempate por limite superior, CCU e volume de reviews; não são vendas verificadas.

## 5. Critérios de seleção

A correspondência a uma categoria utiliza **OU**: basta pertencer a um dos géneros ou etiquetas definidos em `config/categories.json`.

- `competitive`: FPS **OU** MOBA **OU** PvP **OU** Battle Royale.
- `aaa`: **aproximação operacional**, com editora numa lista configurável **E** preço positivo em USD; obtida das páginas `all`, requer verificação humana.
- `indie`: etiqueta **OU** género Indie.
- `strategy_sim`: etiquetas Strategy, Simulation, City Builder, Management **OU** géneros Strategy/Simulation.
- `survival_coop`: Survival, Crafting, Co-op, Online Co-Op **OU** Open World Survival Craft.

**Importante:** Estas classes misturam géneros, modos e tipos de produção. Não são uma taxonomia oficial e são parcialmente sobrepostas. O resultado exige validação académica, particularmente para `AAA`. Os jogos que apresentam etiquetas FPS podem ser single-player; não assumimos que qualquer etiqueta individual prova que é um jogo competitivo. Muitos jogos Indie podem ter grandes editoras, etc.

### Sobre jogos presentes em várias categorias

Primeiro são calculadas as listas/rankings de candidatos de cada categoria. Depois, as categorias com **menos candidatos** recebem prioridade na atribuição, selecionando os TOP 100 **ainda disponíveis**. Este método guloso não garante uma atribuição ótima em todos os casos possíveis; rever o relatório caso faltem jogos. Outros grupos ficam com os 100 mais bem classificados entre os restantes; assim, o CSV final tem 500 AppIDs **únicos**, mas não constitui necessariamente os TOP 100 absolutos de cada categoria. Guardamos `rank_before_dedup` e `other_categories` para auditoria. Se faltar uma categoria, a lista fica marcada como INCOMPLETE.

### Revisão manual obrigatória antes de recolher dados

Abrir `games_500.csv` e `all_candidates.csv` e conferir:

1. Se cada entrada é um jogo Steam, e não DLC, soundtrack, demo ou outro conteúdo. O filtro automático por nome é apenas aproximado.
2. Se está efetivamente lançado e se devolve dados no endpoint de jogadores ativos.
3. Se a classificação principal faz sentido. **AAA não é classe oficial**; editoras grandes também publicam jogos Indie ou pequenos.
4. Se uma categoria foi dominada por jogos erradamente classificados. Se sim, acrescentar `appid,reason` a `config/exclusions.csv`, repetir a seleção usando cache e rever novamente.
5. Se o SteamSpy devolveu menos candidatos do que o esperado, consultar `report.json` e alterar os critérios/páginas, em vez de inventar jogos.

## 6. Robustez, utilização responsável e limites

- Cache de respostas por 24h (recomendado pelo SteamSpy).
- Intervalo >=1.1 s para pedidos `tag`/`genre` e >=61 s entre pedidos `all`.
- Retentativas de erros transitórios (429, 5xx), respeito pelo cabeçalho `Retry-After`, registo de falhas.
- Não faz scraping HTML, não usa proxies nem tenta contornar bloqueios.
- Dados da SteamSpy são estimativas, não vendas. Não inferir causalidade nem representatividade de todos os jogos Steam a partir dos TOP 100 escolhidos.
- A disponibilidade da API e a dimensão das listas por etiqueta podem mudar. Verificar o relatório da execução: falhas e faltas de candidatos não devem ser ocultadas.
- A seleção deve ficar **congelada**, com CSV + data de referência antes da recolha horária, para não alterar o conjunto estudado a meio da experiência.

## 7. Testes locais sem internet

```bash
python -m unittest discover -s tests -v
```

## 8. Próxima fase (ainda não implementada aqui)

Utilizar os AppIDs de `games_500.csv` para executar `ISteamUserStats/GetNumberOfCurrentPlayers` a cada hora e guardar snapshots JSON/logs durante 14 dias; os metadados/estimativas do SteamSpy só precisam de atualização diária.

Fontes: API SteamSpy `https://steamspy.com/api.php`, explicação SteamSpy `https://steamspy.com/about`, documentação da Steam `https://partner.steamgames.com/doc/webapi/ISteamUserStats`.
