# Agendamento da recolha

O `schedule` do GitHub Actions funciona em regime de "melhor esforço": as
execuções podem atrasar horas ou nem chegar a correr. Por isso os workflows
são disparados pelo [cron-job.org](https://cron-job.org), que chama a API do
GitHub à hora exata (ver abaixo). Os crons do GitHub ficam ativos como reserva.

## Histórico

- **19/10/2026:** um cron por hora. As recolhas das 01:17 e 02:17 UTC de 20/10
  nunca foram lançadas e a diária das 18:40 UTC arrancou às 22:37 UTC.
- **20/10/2026:** cinco crons por hora e três por dia. Mesmo assim, o GitHub
  não lançou nenhum run em 12 das 20 horas entre as 00h e as 19h UTC (01, 02,
  04 a 07, 10 a 13, 16 e 17) e as diárias das 05:40 e 12:40 UTC arrancaram às
  10:23 e 17:31 UTC. Mais crons do GitHub não resolvem o problema.
- **20/10/2026, 20:30 UTC:** o disparo passou a ser feito pelo cron-job.org. Os
  dados de 20/10, incompletos, foram removidos da branch `data` e o teste de 48
  horas foi reiniciado para 21/10/2026 00:00 UTC a 23/10/2026 00:00 UTC.

## Crons do GitHub (reserva)

Há várias tentativas por hora e por dia, e só a primeira que chega recolhe:

| Workflow | Crons do GitHub (UTC) |
|---|---|
| `collect_hourly.yml` | minutos 7, 17, 29, 41 e 53 de cada hora |
| `collect_daily.yml` | 05:40, 12:40 e 18:40 |

Não há dados duplicados: a recolha horária não recolhe se já existir uma
recolha com dados nessa hora UTC (`collected_this_hour`), e a diária só recolhe
as fontes sem recolha completa nesse dia. A hora exata de cada recolha varia
consoante a tentativa que corre primeiro, mas fica sempre registada em
`collected_at_utc` e `hour_utc`. O período de recolha é definido pelas
variáveis `COLLECT_START` e `COLLECT_END`, que se aplicam a todos os runs
agendados.

## Disparo pelo cron-job.org

O cron-job.org chama a API do GitHub (`workflow_dispatch` com `scheduled=true`)
ao minuto 17 de cada hora (recolha horária) e às 05:40 UTC (recolha diária).
Este disparo aplica o período de recolha e a mesma regra contra duplicados, por
isso pode coincidir com os crons do GitHub sem duplicar dados.

Configuração (já feita; os passos ficam para referência ou para refazer):

## 1. Criar o token do GitHub

O token tem de ser criado por alguém com permissão de escrita no repositório
`Fegue3/Steam-Analytics`.

1. GitHub > Settings (da conta) > Developer settings > Personal access tokens >
   **Fine-grained tokens** > Generate new token.
2. Token name: `cron-job-steam-analytics`. Expiration: pelo menos até ao fim da
   recolha (p.ex. 60 dias).
3. Resource owner: `Fegue3`. Repository access: **Only select repositories** >
   `Steam-Analytics`.
4. Permissions > Repository permissions > **Actions: Read and write**. Mais
   nenhuma permissão é necessária (Metadata: Read-only é automática).
5. Generate token e copiar o valor (`github_pat_...`). Não voltar a mostrá-lo
   nem fazer commit dele.

## 2. Criar os jobs no cron-job.org

Criar conta em <https://console.cron-job.org/signup> e, em Settings, pôr o
fuso horário em **UTC**. Depois criar dois jobs (Create cronjob):

### Job "Recolha horaria"

- **URL:** `https://api.github.com/repos/Fegue3/Steam-Analytics/actions/workflows/collect_hourly.yml/dispatches`
- **Execution schedule:** Custom, `17 * * * *` (minuto 17 de todas as horas).
- Separador **Advanced**:
  - Request method: `POST`
  - Headers:
    - `Accept: application/vnd.github+json`
    - `Authorization: Bearer github_pat_...` (o token do passo 1)
    - `X-GitHub-Api-Version: 2022-11-28`
    - `Content-Type: application/json`
  - Request body: `{"ref":"main","inputs":{"scheduled":"true"}}`
- Ativar notificações de falha (Notifications > on failure).

### Job "Recolha diaria"

Igual ao anterior, com:

- **URL:** `https://api.github.com/repos/Fegue3/Steam-Analytics/actions/workflows/collect_daily.yml/dispatches`
- **Execution schedule:** Custom, `40 5 * * *` (05:40 UTC).

## 3. Testar

No cron-job.org, usar **Test run** em cada job. A resposta esperada é
`HTTP 204 No Content`. Na aba Actions do repositório aparece uma execução nova
com o evento `workflow_dispatch`.

- Se o teste for feito dentro do período de recolha, a execução recolhe (ou
  salta, se essa hora/dia já estiver recolhido).
- Fora do período, o job `gate` mostra `recolher: false` e termina.
- `401`/`403`: token errado, expirado ou sem a permissão Actions: Read and write.
- `404`: URL errado (nome do workflow ou do repositório).
- `422`: body errado, ou o workflow na `main` ainda não tem o input `scheduled`.

## 4. Mudar de período

Para passar do teste de 48 horas aos 14 dias basta alterar `COLLECT_START` e
`COLLECT_END` nas variáveis do repositório. Os jobs do cron-job.org podem ficar
sempre ativos; fora do período não recolhem. No fim da recolha, desativar os
jobs e apagar o token.
