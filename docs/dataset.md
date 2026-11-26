# Dataset final

Ficheiro: [`data/processed/steam_dataset.csv`](../data/processed/steam_dataset.csv)
(UTF-8, vírgula, ponto decimal). **Uma linha por jogo e por hora UTC**:
500 jogos × 336 horas (28/10/2026 00h a 10/11/2026 23h) = 168 000 linhas.

```bash
python -m src.build_dataset          # review/ -> data/processed/steam_dataset.csv
```

```python
from src.data import load_dataset
df = load_dataset()                  # DataFrame com os tipos certos
```

## Origem

O gerador [`src/build_dataset.py`](../src/build_dataset.py) parte das tabelas já
limpas em [`review/`](../review/README.md) (ver [`review.md`](review.md): uma
observação por jogo/hora, zeros falsos marcados como `Sem dados`) e:

1. junta os 14 ficheiros de `review/horario/` (jogadores + loja, por hora);
2. valida que a grelha jogo × hora está completa e sem repetidos;
3. trata os valores em falta dos jogadores (abaixo);
4. cria variáveis de tempo, de jogadores normalizados e de loja;
5. junta a ficha do jogo (última ficha válida em `metadados_diarios.csv`) e a
   estimativa de proprietários (última válida em `steamspy_diario.csv`). Estes
   valores praticamente não mudam em 14 dias, por isso são fixos por jogo.

## Valores em falta

| Coluna | Em falta | Tratamento |
|---|---:|---|
| `jogadores` | 1 654 | Mantido como observado (vazio = desconhecido) |
| `jogadores_tratado` | 106 | Interpolação linear por jogo, **só em lacunas de até 2 horas seguidas entre duas leituras válidas**. As 2 horas sem recolha (04/11 11h, 09/11 18h) e os zeros falsos isolados ficam preenchidos (1 548 linhas, `jogadores_interpolado = True`). Os 106 que restam são `Sem dados` na última hora (10/11 23h), sem leitura depois, e por isso não se interpolam |
| Loja (`preco_usd`, `desconto_pct`, avaliações…) | 1 000 | As 2 horas sem recolha. Não se interpolam (preços e descontos mudam por degraus) |
| `preco_usd` | +4 286 | Jogos pagos sem preço na loja nesse momento (p.ex. não estão à venda) |
| `proprietarios_estimados` | 20 jogos | SteamSpy não conhece o jogo |
| `lancamento`, `idade_anos` | 2 jogos | Sem data na loja |

Os valores observados nunca são alterados: as colunas tratadas são colunas novas.

## Colunas

| Coluna | Tipo | Descrição |
|---|---|---|
| `hora_utc` | datetime UTC | Hora da observação |
| `data_utc` | data | Dia UTC |
| `appid`, `jogo` | int, texto | Identificador Steam e nome (lista congelada) |
| `categoria` | categoria | Competitivos, AAA, Independentes, Estratégia e simulação, Sobrevivência e cooperação |
| `hora_dia_utc` | 0–23 | Hora do dia UTC |
| `dia_semana`, `fim_de_semana` | categoria, bool | Dia da semana (UTC) e se é sábado/domingo |
| `jogadores` | int | Jogadores simultâneos observados (`GetNumberOfCurrentPlayers`) |
| `estado_jogadores` | categoria | OK, Sem dados, Ausente |
| `jogadores_tratado` | int | `jogadores` com lacunas curtas interpoladas |
| `jogadores_interpolado` | bool | Valor de `jogadores_tratado` foi interpolado |
| `log_jogadores` | float | `log(1 + jogadores_tratado)`; reduz a assimetria (CS2 tem ~1 milhão, a mediana ~2 000) |
| `jogadores_media_jogo` | float | Média de `jogadores_tratado` do jogo no período |
| `jogadores_rel_media` | float | `jogadores_tratado / jogadores_media_jogo`; 1 = hora típica do jogo. Permite comparar jogos de tamanhos diferentes |
| `jogadores_z` | float | z-score dentro do jogo; útil para outliers (picos e quedas) |
| `var_jogadores_1h_pct` | float | Variação % face à hora anterior do mesmo jogo |
| `popularidade` | categoria | Quartil de `jogadores_media_jogo` entre os 500 jogos: Baixa, Média-baixa, Média-alta, Alta |
| `estado_loja` | categoria | OK ou Ausente |
| `preco_usd`, `preco_original_usd` | float | Preço atual e sem desconto (loja US, USD) |
| `desconto_pct` | float | Desconto em % |
| `em_desconto` | bool | `desconto_pct > 0` |
| `gratuito` | bool | Jogo gratuito |
| `avaliacoes_total` | int | Número de avaliações na loja |
| `novas_avaliacoes_1h` | int | Diferença de `avaliacoes_total` face à hora anterior. Pode ser negativa ou ter saltos quando a Steam recalcula as contagens |
| `avaliacoes_positivas_pct` | float | % de avaliações positivas |
| `avaliacao_loja` | categoria ordenada | Classificação da Steam (Mostly Negative … Overwhelmingly Positive) |
| `editora`, `produtora` | texto | Publisher e developer |
| `lancamento`, `idade_anos` | data, float | Data de lançamento e idade do jogo em anos no início da recolha |
| `etiquetas_top` | texto | As 3 etiquetas mais votadas, separadas por `; ` |
| `n_idiomas` | int | Idiomas suportados |
| `n_plataformas` | int | Windows + macOS + Linux (1–3) |
| `steam_deck` | categoria | Verificado, Jogável, Não suportado, Desconhecido |
| `proprietarios_estimados` | float | Ponto médio do intervalo de proprietários do SteamSpy (estimativa grosseira) |

## Notas

- Horas em UTC: o padrão diário mistura jogadores de vários fusos.
- `popularidade` e `jogadores_media_jogo` usam o período inteiro; não devem ser
  usadas como variáveis de entrada para prever o futuro dentro do mesmo período.
- O ficheiro tem ~58 MB (abaixo do limite de 100 MB do GitHub), porque os
  atributos fixos de cada jogo se repetem nas 336 horas, para o dataset ficar
  num único CSV.
