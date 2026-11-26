# Timeline do projeto

Registo do que foi feito e por quem, para a secção "Contribution" do notebook final.

Elementos do grupo: Francisco Pereira (@Fegue3), Daniel Cardoso (@imdtcode), Hugo Serra (@Hug00x).

## Contribuição

| Elemento | Horas | Contribuição |
|---|---|---|
| Francisco Pereira | 8 | 34% |
| Daniel Cardoso | 8 | 34% |
| Hugo Serra | 7 | 30% |

Horas estimadas, com uso de LLM no código. Nas tarefas em conjunto, cada elemento conta a sessão inteira. Percentagens do trabalho feito até ao dataset final, a rever no fim do projeto (o RAG fica a cargo do Hugo).

## 1. Ideia do projeto

**Responsáveis:** Francisco, Daniel, Hugo · **Horas:** 2 cada, em conjunto

Definição do tema, das cinco categorias de jogos e das questões de investigação.

## 2. Documento da proposta

**Responsáveis:** Francisco, Daniel · **Horas:** 2 cada, em conjunto

Redação e revisão da proposta segundo o template do enunciado.

## 3. Seleção dos jogos: primeira versão

**Responsável:** Hugo · **Commit:** `54e3017` (18/10/2026) · **Horas:** 2

Seletor de 100 jogos por categoria a partir das etiquetas e géneros do SteamSpy.

## 4. Seleção dos jogos: nova versão

**Responsável:** Francisco · **Commit:** `2081dd5` (18/10/2026) · **Horas:** 3

Uma categoria por jogo pela etiqueta dominante, ranking por jogadores atuais e TOP 100 da Steam como fonte extra.

## 5. Coletores de dados

**Responsável:** Daniel · **Commits:** `1e1d253`, `3608ad3` (PR #1, 19/10/2026) · **Horas:** 3

Recolha horária (jogadores, loja) e diária (SteamSpy) com GitHub Actions, gravada na branch `data`.

## 6. Agendamento e correção da recolha diária

**Responsável:** Francisco · **Commits:** `ec45408`, `a9d5bcd`, `9484794`, `17d1376`, `f37096a`, `7032b6c` (19/10 a 27/10/2026) · **Horas:** 1

Disparo da recolha pelo cron-job.org e correção da recolha diária. Recolha final de 28/10/2026 a 11/11/2026.

## 7. Organização dos dados para revisão

**Responsável:** Hugo · **Commits:** `8e2e1e3`, `5ad986c`, `982ef32`, `0783097` (PR #2, 19/11/2026) · **Horas:** 3

Transformação dos dados brutos em tabelas limpas na pasta `review/`.

## 8. Dataset final de análise

**Responsável:** Daniel · **Commit:** `a9ee506` (PR #4, 26/11/2026) · **Horas:** 1

Dataset único com uma linha por jogo e por hora, e `load_dataset()` para o notebook e a app.
