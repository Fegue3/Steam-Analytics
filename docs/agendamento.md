# Agendamento da recolha com o cron-job.org

O `schedule` do GitHub Actions funciona em regime de "melhor esforço": as
execuções podem atrasar horas ou nem chegar a correr. No primeiro teste
(20/10/2026) as recolhas das 01:17 e 02:17 UTC nunca foram lançadas e a diária
das 18:40 UTC arrancou às 22:37 UTC.

Por isso, o disparo principal é feito pelo [cron-job.org](https://cron-job.org),
que chama a API do GitHub (`workflow_dispatch`) à hora exata. O código continua
a correr no GitHub Actions e os dados continuam a ir para a branch `data`. Os
crons do GitHub ficam como reserva:

| Workflow | Disparo principal (cron-job.org) | Reserva (cron do GitHub) |
|---|---|---|
| `collect_hourly.yml` | minuto 17 de cada hora | minuto 47 de cada hora |
| `collect_daily.yml` | 05:40 UTC | 08:40 e 18:40 UTC |

Não há dados duplicados: a recolha horária não recolhe se já existir uma
recolha com dados nessa hora UTC (`collected_this_hour`), e a diária só recolhe
as fontes sem recolha completa nesse dia. O período de recolha continua a ser
definido pelas variáveis `COLLECT_START` e `COLLECT_END`, que se aplicam a
todos os runs agendados (cron do GitHub ou cron-job.org com `scheduled=true`).

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
