# Dados tratados na main

O código de transformação e os datasets tratados ficam na branch `main`,
com os resultados na pasta [`review/`](../review/README.md). `review/` é o
nome da pasta de saída; não é necessário usar uma branch separada para os
dados tratados. A branch `data` continua a guardar apenas os brutos e logs,
e é lida como um snapshot imutável, sem fazer merge com a `main`.

## Consultar os dados

Começar em [`review/README.md`](../review/README.md). Os nomes e categorias
vêm da lista congelada em `config/games.csv`. Todas as datas são UTC e os
CSV usam UTF-8 com BOM, vírgula e ponto decimal. Para abrir no Excel em
português, usar **Dados → De Texto/CSV**, selecionando vírgula e UTF-8.

| Ficheiro | Uma linha representa |
|---|---|
| `jogos.csv` | Um jogo: última observação de jogadores/loja e estatísticas do período |
| `diario.csv` | Um jogo num dia: média, mínimo, pico, preços e cobertura |
| `horario/AAAA-MM-DD.csv` | Um jogo numa hora, juntando jogadores e loja |
| `metadados_diarios.csv` | Ficha de um jogo num dia |
| `steamspy_diario.csv` | Estimativas de um jogo num dia |
| `cobertura.csv` | Cobertura de uma fonte numa hora ou dia |
| `recolhas.csv` | Uma tentativa completa de um coletor, incluindo repetições |
| `falhas.csv` | Uma resposta sem dados ou com erro, por jogo e tentativa |
| `manifest.json` | Commit de origem, hashes dos inputs/código e contagens dos CSV |

Os ficheiros horários são separados por dia para evitar um CSV enorme. O
GitHub pode limitar a pré-visualização dos CSV grandes; descarregar o ficheiro
para consultar todas as linhas.

## Regras de transformação

- A junção é por **AppID e hora UTC**, sem arrastar preços ou jogadores de
  outra hora. Para cada jogo/fonte/hora (ou dia nas fontes diárias), ganha
  `ok`, depois `no_data`, depois `error`; entre estados iguais ganha a
  tentativa mais recente. Assim um retry falhado não apaga uma resposta válida.
- As tentativas originais continuam em `recolhas.csv` e as falhas em
  `falhas.csv`. As tabelas organizadas mostram o resultado escolhido.
- Um vazio significa desconhecido. `0` é um valor válido. `Ausente` significa
  que não existe registo; `Sem dados` é uma resposta explícita da API;
  `Erro` é uma tentativa falhada. Nunca se preenchem lacunas por interpolação.
- Jogos gratuitos com resposta válida têm preço `0.00`. Outros preços em
  falta continuam vazios. A loja usa o contexto **US** do coletor atual:
  preços em **USD**, convertidos de cêntimos. SteamSpy mantém os seus preços
  em centavos USD, em colunas separadas, sem os misturar com a loja.
- As médias usam só horas válidas; o pico é o maior número de jogadores
  simultâneos observado (em empate, a primeira hora). Não são jogadores
  únicos, vendas nem utilizadores diários.
- O intervalo horário esperado é inclusivo da primeira à última hora
  observada nas fontes horárias. Dias nas extremidades podem ser parciais.
  Dentro desse intervalo, até horas totalmente ausentes ganham linhas.
  Para as fontes diárias, esperam-se todos os dias entre a primeira e a última
  recolha de qualquer fonte. Não se inventam horas antes/depois do snapshot.
- `jogos.csv` mostra a observação da hora mais recente **de cada jogo/fonte**;
  verificar os timestamps e estados antes de comparar jogos. O ranking no
  relatório usa uma única hora comum, a última observada nas fontes horárias.
- As estimativas de proprietários SteamSpy são intervalos, não vendas
  exatas. `ccu_steamspy` conserva a métrica do SteamSpy e não substitui a
  recolha de jogadores atuais da Steam.
- As descrições conservam o texto original, normalizando espaços e quebras
  de linha para facilitar a leitura em tabelas. Os brutos mantêm o original.
- Dados inválidos, AppIDs desconhecidos/repetidos numa tentativa ou uma
  seleção diferente da lista congelada fazem a transformação falhar antes
  de publicar resultados. Uma fonte ausente aparece na cobertura.

## Dicionário das colunas

| Coluna ou grupo | Significado |
|---|---|
| `appid`, `jogo`, `categoria` | Identificação e categoria principal congelada do jogo |
| `hora_utc`, `data_utc` | Período da observação, em UTC |
| `recolha_*_utc` | Momento real da tentativa selecionada; fontes podem diferir |
| `estado_*` | `OK`, `Sem dados`, `Erro` ou `Ausente` |
| `jogadores` | Jogadores simultâneos observados pela Steam |
| `jogadores_media`, `jogadores_min`, `jogadores_pico` | Estatísticas das respostas horárias válidas |
| `hora_pico_utc` | Primeira hora com o pico do dia |
| `horas_esperadas`, `horas_*` | Denominador e cobertura; faltas nunca contam como zero jogadores |
| `preco_usd`, `preco_original_usd` | Preço atual/base da loja em dólares americanos |
| `preco_min_usd`, `preco_max_usd` | Extremos diários dos preços conhecidos da loja |
| `desconto_pct`, `desconto_max_pct`, `fim_desconto_utc` | Desconto, máximo diário e fim declarado pela loja |
| `gratuito` | `Sim`/`Não` quando conhecido, vazio quando desconhecido |
| `avaliacoes_total`, `avaliacoes_positivas_pct`, `avaliacao_loja` | Resumo da loja: quantidade, percentagem e rótulo original |
| `nome_na_loja`, `editora`, `produtora`, `lancamento`, `descricao` | Ficha da loja; texto original, sem tradução automática |
| `situacao_loja`, `tipo_loja_id` | Situação e tipo devolvidos pelo coletor |
| `etiquetas_com_peso` | Etiquetas por peso decrescente, separadas por `;`, com pesos entre parênteses |
| `*_ids` | IDs originais das funcionalidades/categorias, separados por `;` |
| `windows`, `mac`, `linux` | Compatibilidade declarada: `Sim`/`Não` ou vazio |
| `steam_deck` | Desconhecido, Não suportado, Jogável ou Verificado |
| `idiomas`, `idiomas_audio_completo` | Quantidade de línguas suportadas e com áudio completo |
| `proprietarios_*_estimados` | Limites inferior e superior do intervalo SteamSpy |
| `*_steamspy`, `*_steamspy_*` | Métricas exclusivas SteamSpy; preços em centavos USD |
| `fonte`, `run_id`, `ficheiro`, `linha` | Rastreabilidade da tentativa até ao JSONL original |
| `jogos`, `jogos_esperados`, `ok`, `sem_dados`, `erros`, `ausentes` | Contagens observadas ou esperadas de registos por jogo |
| `http_status`, `motivo` | Código HTTP e erro original, quando o coletor os registou |

## Atualizar localmente

Na raiz do repositório, sem dependências adicionais:

```bash
git fetch origin data
python -m src.build_review --ref origin/data --out review
python -m unittest discover -s tests -p test_review.py -v
```

Também se pode ler uma cópia local dos brutos:

```bash
python -m src.build_review --raw caminho/para/raw --out review
```

O script não faz pedidos às APIs, fetch, merge, commit ou push. Lê um snapshot
imutável, gera todos os resultados numa pasta temporária e só os publica
depois da validação. Os resultados são determinísticos: o mesmo snapshot,
lista de jogos e código geram os mesmos ficheiros, sem commits só para mudar
a data de geração. Ficheiros iguais aos existentes são mantidos; os que
mudaram são substituídos e os novos são acrescentados. CSV horários de dias
que deixaram de existir no snapshot são removidos para evitar dados antigos.

Para ler o Git de outro checkout sem copiar os dados, usar
`python -m src.build_review --repo caminho/para/checkout-data --ref HEAD`.

## Executar a atualização manual

Depois de integrar este trabalho na `main`, no GitHub:

1. Abrir **Actions → Atualizar dados tratados**.
2. Carregar em **Run workflow** e escolher a branch **main**.
3. Confirmar **Run workflow** e aguardar o resultado.
4. Consultar o resumo do run ou abrir `review/README.md` na `main`.

O workflow [`update_review.yml`](../.github/workflows/update_review.yml)
tem apenas o evento `workflow_dispatch`: não corre por horário, por push ou
depois das recolhas. O job só executa quando é escolhido o repositório do
projeto e a branch `main`.

Em cada execução, lê o código e os resultados atuais da `main`, obtém um
checkout apenas de leitura da `data`, corre os testes offline da transformação
e gera novamente as tabelas a partir desse snapshot. Faz commit apenas das
diferenças na pasta `review/`, incluindo ficheiros novos, alterados e CSV
horários que tenham deixado de fazer parte do snapshot. Se o conteúdo já
estiver atualizado, termina sem criar commit.

Usa o `GITHUB_TOKEN` automático com `contents: write`, sem PAT ou novos
segredos. Não escreve na `data`. Não faz force push nem rebase dos resultados
gerados. Se a `main` avançar durante o processamento, o push falha; repetir
a execução manual para trabalhar sobre a versão mais recente.

**Integração:** o PR deve incluir o workflow, `src/build_review.py`, os testes,
a documentação e todos os resultados de `review/`. Assim a `main` fica
completa e utilizável pela app e pelo notebook. A branch `review` usada no
desenvolvimento inicial pode continuar como histórico, mas deixa de ser o
destino do workflow.

Atualizar os CSV não inicia novas recolhas nem preenche lacunas: os dados
continuam limitados ao snapshot existente na branch `data`.
