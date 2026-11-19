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
| players | 2026-11-10T23:17:25Z | 167000 | 0 | 0 | 1000 |
| store | 2026-11-10T23:17:27Z | 167000 | 0 | 0 | 1000 |
| metadata | 2026-11-10T01:45:27Z | 7000 | 0 | 0 | 0 |
| steamspy | 2026-11-10T01:45:28Z | 7000 | 0 | 0 | 0 |

Contagens após escolher uma observação por jogo e hora/dia. `recolhas.csv` conserva todas as tentativas.
O intervalo horário vai da primeira à última hora observada nas fontes horárias; os dias das extremidades podem ser parciais.
As fontes diárias são verificadas em todos os dias do período observado.

**Datas de recolha não são a data de hoje:** este relatório mostra o último snapshot disponível. A atualização da review não faz novas recolhas nem preenche lacunas.

## Lacunas de cobertura

| Fonte | Período UTC | Jogos sem registo |
|---|---|---:|
| players | 2026-11-04T11:00:00Z | 500 |
| players | 2026-11-09T18:00:00Z | 500 |
| store | 2026-11-04T11:00:00Z | 500 |
| store | 2026-11-09T18:00:00Z | 500 |

## Mais jogadores na última hora observada (2026-11-10T23:00:00Z)

| Jogo | Categoria | Jogadores |
|---|---|---:|
| Counter-Strike 2 | Competitivos | 459,849 |
| Dota 2 | Competitivos | 255,367 |
| Call of Duty® | Competitivos | 124,833 |
| PUBG: BATTLEGROUNDS | Competitivos | 98,702 |
| Rust | Sobrevivência e cooperação | 65,995 |
| Apex Legends™ | Competitivos | 51,986 |
| Warframe | Sobrevivência e cooperação | 46,238 |
| Overwatch® | Competitivos | 42,805 |
| Geometry Dash | Independentes | 42,533 |
| Dead by Daylight | Sobrevivência e cooperação | 37,214 |
| War Thunder | Estratégia e simulação | 36,491 |
| Project Zomboid | Sobrevivência e cooperação | 35,879 |
| Enshrouded | Sobrevivência e cooperação | 35,456 |
| Slay the Spire 2 | Sobrevivência e cooperação | 35,361 |
| EA SPORTS FC™ 27 | AAA | 32,466 |

## Como interpretar

- Um campo vazio significa desconhecido; zero é um valor observado. Jogos gratuitos válidos têm preço 0.00 USD.
- `Ausente`: não houve registo; `Sem dados`: a API respondeu sem dados; `Erro`: a tentativa falhou.
- As médias e picos usam apenas respostas válidas, sem interpolação. Jogadores são simultâneos, não utilizadores únicos.
- Preços da loja usam o contexto US do coletor (USD); SteamSpy é uma fonte separada de estimativas.
- A última observação de cada fonte pode ter uma data diferente: confirmar as colunas `recolha_*_utc`.
