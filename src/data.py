"""Carrega em memória o dataset final gerado por src/build_dataset.py.

Exemplo:
    from src.data import load_dataset
    df = load_dataset()
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "steam_dataset.csv"

CATEGORIES = ["Competitivos", "AAA", "Independentes", "Estratégia e simulação",
              "Sobrevivência e cooperação"]
DAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
POPULARITY = ["Baixa", "Média-baixa", "Média-alta", "Alta"]
REVIEW_SCORES = ["Overwhelmingly Negative", "Very Negative", "Negative", "Mostly Negative",
                 "Mixed", "Mostly Positive", "Positive", "Very Positive",
                 "Overwhelmingly Positive"]

DTYPES = {
    "appid": "int64",
    "hora_dia_utc": "int8",
    "jogadores": "Int64",
    "jogadores_tratado": "Int64",
    "avaliacoes_total": "Int64",
    "novas_avaliacoes_1h": "Int64",
    "n_idiomas": "Int64",
    "n_plataformas": "Int64",
    "fim_de_semana": "boolean",
    "jogadores_interpolado": "boolean",
    "em_desconto": "boolean",
    "gratuito": "boolean",
    "jogo": "string",
    "editora": "string",
    "produtora": "string",
    "etiquetas_top": "string",
    "estado_jogadores": "category",
    "estado_loja": "category",
    "steam_deck": "category",
}
ORDERED = {
    "categoria": CATEGORIES,
    "dia_semana": DAYS,
    "popularidade": POPULARITY,
    "avaliacao_loja": REVIEW_SCORES,
}


def load_dataset(path: str | Path = DATASET_PATH) -> pd.DataFrame:
    """Lê o CSV final com os tipos certos.

    - `hora_utc`: datetime com fuso UTC; `data_utc` e `lancamento`: datetime (dia).
    - Inteiros com falta usam `Int64` e booleanos com falta usam `boolean` (pd.NA).
    - `categoria`, `dia_semana`, `popularidade` e `avaliacao_loja` são categorias ordenadas.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} não existe. Gerar com: python -m src.build_dataset")
    df = pd.read_csv(path, dtype=DTYPES, encoding="utf-8")
    df["hora_utc"] = pd.to_datetime(df["hora_utc"], utc=True)
    df["data_utc"] = pd.to_datetime(df["data_utc"])
    df["lancamento"] = pd.to_datetime(df["lancamento"])
    for column, order in ORDERED.items():
        df[column] = pd.Categorical(df[column], categories=order, ordered=True)
    return df
