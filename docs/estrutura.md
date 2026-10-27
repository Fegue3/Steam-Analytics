# Estrutura do repositório

Este documento descreve como o projeto está organizado. As pastas e os ficheiros só se criam quando são precisos.

## Fluxo de dados

```
[0] Seletor (1 vez)  ──►  config/games.csv  (appid, name, category)  ← lista congelada
                                    │
          ┌─────────────────────────┴─────────────────────────┐
[1] Recolha horária                                  [2] Recolha diária
    jogadores atuais × 500                         ficha da loja + SteamSpy
    loja (preço, desconto, reviews)
          │                                                    │
          └──────────►  data/raw/…/*.json  +  logs/  ◄─────────┘
                                    │
[3] Processamento: JSON → limpeza → junção por appid + hora → data/processed/*.csv
                                    │
[4] Notebook   [5] Streamlit   [6] Modelo de ML
```

O seletor só serve para escolher **que jogos** se estudam. Tudo o que se analisa (jogadores, preços, reviews) vem das recolhas, não do seletor.

## Árvore

```
Steam-Analytics/
├── README.md                    descrição + como correr
├── requirements.txt             dependências
├── docs/
│   ├── estrutura.md             este documento
│   └── timeline.md              o que foi feito, por ordem e por quem
├── config/
│   ├── games.csv                a lista: appid, name, category, selection_date_utc
│   ├── categories.json          regras de classificação do seletor
│   └── exclusions.csv           jogos retirados à mão, com motivo
├── src/                         código (correr na raiz: python3 -m src.<módulo>)
│   ├── api.py                   clientes HTTP partilhados (cache, retries, rate limit, logging)
│   ├── classify.py              regras que atribuem uma categoria a cada jogo
│   ├── select_games.py          seletor → config/games.csv
│   ├── collect_common.py        utilitários dos coletores e JSONL
│   ├── collect_players.py       recolha horária de jogadores
│   ├── collect_store.py         recolha horária de loja e reviews resumidas
│   ├── collect_daily.py         recolha diária da ficha da loja e SteamSpy
│   ├── build_dataset.py         JSON brutos → CSV tratado
│   └── data.py                  load_dataset() (exigido pelo enunciado)
├── data/
│   ├── cache/                   respostas das APIs (local, ignorado pelo git)
│   ├── raw/                     JSON das recolhas
│   └── processed/               CSV finais
├── logs/                        logs de execução
├── tests/                       testes offline (python3 -m unittest discover -s tests)
├── notebooks/                   notebook final com os cabeçalhos do enunciado
├── app/                         Streamlit
└── .github/workflows/           agendamento das recolhas
```

Os workflows horários e diários fazem checkout da branch órfã `data` e
acrescentam os resultados em JSONL, sem alterar a `main`. A branch
`feature/data-collection` é usada para desenvolver esta funcionalidade e
depois é integrada na `main` por Pull Request. A branch `data` contém apenas
o README de identificação, dados brutos e logs gerados pelos workflows.

## Repositórios

| Repositório | Papel |
|---|---|
| `Fegue3/Steam-Analytics` (público) | Desenvolvimento e recolha. Tudo é feito aqui primeiro. É aqui que corre o GitHub Actions. |
| `ubi-datasciencelabs-students/MEI_CD_20262027_Grupo2` | Entrega ao docente. Vai sendo atualizado **ao longo do projeto**: cada parte entra quando estiver acabada e validada no repo público (não tudo de uma vez no fim). Não corre GitHub Actions. |

## Decisões tomadas

- **GitHub Actions corre no repo público.**
- **O repo do grupo é atualizado por etapas**, à medida que cada parte fica pronta.
