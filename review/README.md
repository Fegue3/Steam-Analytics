# Revisão dos dados Steam

Dados organizados automaticamente a partir da branch `data`.

**Amostra:** 500 jogos. **Período observado:** 2026-10-28 a 2026-11-10 (UTC).

## Por onde começar

- [Jogos: última observação de cada fonte e estatísticas do período](jogos.csv)
- [Resumo diário por jogo](diario.csv)
- [Histórico por hora e por dia](horario/)
- [Fichas dos jogos por dia](metadados_diarios.csv)
- [Estimativas SteamSpy por dia](steamspy_diario.csv)
- [Cobertura: erros, respostas sem dados e períodos ausentes](cobertura.csv)
- [Todas as tentativas de recolha, incluindo repetições](recolhas.csv)
- [Falhas por jogo, com o motivo registado pelo coletor](falhas.csv)
- [Dicionário das colunas e regras](../docs/review.md)

Os CSV têm cabeçalhos em português, texto UTF-8, vírgula como separador e ponto decimal. No Excel, usar **Dados → De Texto/CSV**, escolhendo UTF-8 e vírgula se necessário.

## Estado das fontes

| Fonte | Última tentativa (UTC) | OK | Sem dados | Erros | Ausentes |
|---|---|---:|---:|---:|---:|
| players | 2026-11-10T23:17:25Z | 166346 | 654 | 0 | 1000 |
| store | 2026-11-10T23:17:27Z | 167000 | 0 | 0 | 1000 |
| metadata | 2026-11-10T01:45:27Z | 7000 | 0 | 0 | 0 |
| steamspy | 2026-11-10T01:45:28Z | 6720 | 280 | 0 | 0 |

Contagens após escolher uma observação por jogo e hora/dia. `recolhas.csv` conserva todas as tentativas.
O intervalo horário vai da primeira à última hora observada nas fontes horárias; os dias das extremidades podem ser parciais.
As fontes diárias são verificadas em todos os dias do período observado.

**Datas de recolha não são a data de hoje:** este relatório mostra o último snapshot disponível. A atualização dos CSV não faz novas recolhas nem preenche lacunas.

## Lacunas de cobertura

| Fonte | Período UTC | Jogos sem registo |
|---|---|---:|
| players | 2026-11-04T11:00:00Z | 500 |
| players | 2026-11-09T18:00:00Z | 500 |
| store | 2026-11-04T11:00:00Z | 500 |
| store | 2026-11-09T18:00:00Z | 500 |

## Mais jogadores na hora mais completa e recente (2026-11-10T22:00:00Z)

| Jogo | Categoria | Jogadores |
|---|---|---:|
| Counter-Strike 2 | Competitivos | 704,609 |
| Dota 2 | Competitivos | 501,249 |
| Call of Duty® | Competitivos | 132,562 |
| PUBG: BATTLEGROUNDS | Competitivos | 123,751 |
| Team Fortress 2 | Competitivos | 95,494 |
| Cyberpunk 2077 | AAA | 88,764 |
| Rust | Sobrevivência e cooperação | 81,289 |
| Apex Legends™ | Competitivos | 60,784 |
| Tom Clancy's Rainbow Six Siege | Competitivos | 58,556 |
| WARDOGS | Competitivos | 54,753 |
| ARC Raiders | Competitivos | 52,149 |
| Warframe | Sobrevivência e cooperação | 48,862 |
| Valheim | Sobrevivência e cooperação | 46,714 |
| Overwatch® | Competitivos | 45,444 |
| Geometry Dash | Independentes | 44,391 |

## Como interpretar

- Um campo vazio significa desconhecido; zero é um valor observado. Jogos gratuitos válidos têm preço 0.00 USD.
- `Ausente`: não houve registo; `Sem dados`: a API respondeu sem dados; `Erro`: a tentativa falhou.
- Zeros implausíveis da API e fichas vazias do SteamSpy contam como `Sem dados`; o motivo está em `falhas.csv`.
- As médias e picos usam apenas respostas válidas, sem interpolação. Jogadores são simultâneos, não utilizadores únicos.
- Preços da loja usam o contexto US do coletor (USD); SteamSpy é uma fonte separada de estimativas.
- A última observação de cada fonte pode ter uma data diferente: confirmar as colunas `recolha_*_utc`.
