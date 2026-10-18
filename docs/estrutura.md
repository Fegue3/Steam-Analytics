# Estrutura do repositório

Este documento descreve como o projeto está organizado: o que **já existe** e o que está **planeado**. Só se cria uma pasta ou um ficheiro quando for preciso; até lá fica aqui, marcado como planeado.

## Fluxo de dados

```
[0] Seletor (1 vez)  ──►  config/games.csv  (appid, name, category)  ← lista congelada
                                    │
          ┌─────────────────────────┴─────────────────────────┐
[1] Recolha horária (planeado)                     [2] Recolha diária (planeado)
    jogadores atuais × 500                             loja (preço, desconto), reviews, SteamSpy
          │                                                    │
          └──────────►  data/raw/…/*.json  +  logs/  ◄─────────┘
                                    │
[3] Processamento (planeado): JSON → limpeza → junção por appid + hora → data/processed/*.csv
                                    │
[4] Notebook   [5] Streamlit   [6] Modelo de ML        (todos planeados)
```

O seletor só serve para escolher **que jogos** se estudam. Tudo o que se analisa (jogadores, preços, reviews) vem das recolhas, não do seletor.

## Árvore

Legenda: ✅ existe · 🕓 planeado

```
Steam-Analytics/
├── README.md                    ✅ descrição + como correr
├── requirements.txt             ✅ dependências (só requests, por agora)
├── docs/
│   └── estrutura.md             ✅ este documento
├── config/
│   ├── games.csv                ✅ A LISTA: appid, name, category, selection_date_utc
│   ├── categories.json          ✅ regras de classificação do seletor
│   └── exclusions.csv           ✅ jogos retirados à mão, com motivo
├── src/                         ✅ código (correr na raiz: python3 -m src.<módulo>)
│   ├── api.py                   ✅ clientes HTTP partilhados (cache, retries, rate limit, logging)
│   ├── classify.py              ✅ regras que atribuem uma categoria a cada jogo
│   ├── select_games.py          ✅ seletor → config/games.csv
│   ├── collect_players.py       🕓 recolha horária de jogadores
│   ├── collect_daily.py         🕓 recolha diária (loja, reviews, SteamSpy)
│   ├── build_dataset.py         🕓 JSON brutos → CSV tratado
│   └── data.py                  🕓 load_dataset() (exigido pelo enunciado)
├── data/
│   ├── cache/                   ✅ respostas das APIs (local, ignorado pelo git)
│   ├── raw/                     🕓 JSON das recolhas
│   └── processed/               🕓 CSV finais
├── logs/                        ✅ logs de execução (local, ignorado pelo git)
├── tests/                       ✅ testes offline (python3 -m unittest discover -s tests)
├── notebooks/                   🕓 notebook final com os cabeçalhos do enunciado
├── app/                         🕓 Streamlit
└── .github/workflows/           🕓 agendamento das recolhas (decisão em aberto, ver abaixo)
```

## Convenções

- **Correr tudo a partir da raiz do repositório** (`python3 -m src.<módulo>`).
- **Sem venv obrigatório.** Não é preciso instalar o projeto: `python3 -m src.select_games` na raiz.
- **Datas sempre em UTC** (ISO 8601, `2026-10-18T18:38:57+00:00`).
- **Nenhuma API usada até agora precisa de chave.** Se alguma vier a precisar, a chave vai para variáveis de ambiente ou secrets e **nunca** para o repo.
- **Não publicar caminhos pessoais** (p.ex. `/home/...`) em ficheiros versionados.
- `config/games.csv` é gerado pelo seletor e não se edita à mão: para tirar um jogo, acrescenta-se a `config/exclusions.csv` e volta-se a correr. O seletor só grava listas completas e válidas.
- **A lista oficial gera-se logo antes da recolha**, e esse commit fica como referência. Durante a recolha não se volta a correr o seletor.

## Repositórios

| Repositório | Papel |
|---|---|
| `Fegue3/Steam-Analytics` (público) | Desenvolvimento. Tudo é feito aqui primeiro. |
| `ubi-datasciencelabs-students/MEI_CD_20262027_Grupo2` | Entrega ao docente. Só recebe o que já está acabado e validado no repo público. |

## Decisões em aberto

- [ ] **Agendamento das recolhas (GitHub Actions):** em que repo corre e em que branch se guardam os JSON recolhidos.
- [ ] **Fontes diárias:** loja + reviews + SteamSpy (todas ou só algumas).
- [ ] **Calendário:** piloto de 48 h e janela oficial de 14 dias.
- [ ] **Hora a que se congela a lista** (o ranking por jogadores depende da hora do dia).
- [ ] **Divisão do trabalho** entre os três elementos (o enunciado pede % por pessoa).
