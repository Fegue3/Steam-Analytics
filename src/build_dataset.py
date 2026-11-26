"""Gera o dataset final de análise a partir das tabelas limpas em review/.

Uma linha por jogo e por hora UTC. Junta os jogadores e a loja (horário) com
a ficha do jogo e as estimativas SteamSpy (diárias), trata os valores em falta
e cria variáveis novas para a análise. Não faz pedidos às APIs.

Uso (na raiz do repositório):
    python -m src.build_dataset
    python -m src.build_dataset --review review --out data/processed/steam_dataset.csv
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_REVIEW = Path("review")
DEFAULT_OUT = Path("data/processed/steam_dataset.csv")

# Lacunas de jogadores até este número de horas seguidas são interpoladas.
MAX_INTERP_HOURS = 2
# Número de etiquetas mais votadas guardadas por jogo.
TOP_TAGS = 3
DAYS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
POPULARITY = ["Baixa", "Média-baixa", "Média-alta", "Alta"]
YES = {"Sim": True, "Não": False}

COLUMNS = [
    # Identificação e tempo
    "hora_utc", "data_utc", "appid", "jogo", "categoria",
    "hora_dia_utc", "dia_semana", "fim_de_semana",
    # Jogadores (observado e tratado)
    "jogadores", "estado_jogadores", "jogadores_tratado", "jogadores_interpolado",
    "log_jogadores", "jogadores_media_jogo", "jogadores_rel_media", "jogadores_z",
    "var_jogadores_1h_pct", "popularidade",
    # Loja (horário)
    "estado_loja", "preco_usd", "preco_original_usd", "desconto_pct", "em_desconto",
    "gratuito", "avaliacoes_total", "novas_avaliacoes_1h", "avaliacoes_positivas_pct",
    "avaliacao_loja",
    # Ficha do jogo (fixa no período)
    "editora", "produtora", "lancamento", "idade_anos", "etiquetas_top",
    "n_idiomas", "n_plataformas", "steam_deck",
    # SteamSpy (fixo no período)
    "proprietarios_estimados",
]


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def read_hourly(review: Path) -> pd.DataFrame:
    files = sorted((review / "horario").glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"Sem ficheiros horários em {review / 'horario'}")
    return pd.concat([read(f) for f in files], ignore_index=True)


def latest_ok(table: pd.DataFrame, state: str) -> pd.DataFrame:
    """Última ficha válida de cada jogo (os valores quase não mudam no período)."""
    ok = table[table[state] == "OK"].sort_values("data_utc")
    return ok.groupby("appid", as_index=False).last()


def top_tags(weighted: str | float, n: int = TOP_TAGS) -> str | float:
    """'Action (1613); FPS (1446); ...' -> 'Action; FPS; ...' (já vem ordenado por votos)."""
    if not isinstance(weighted, str) or not weighted.strip():
        return np.nan
    names = [re.sub(r"\s*\(\d+\)\s*$", "", part).strip() for part in weighted.split(";")]
    return "; ".join(name for name in names[:n] if name)


def game_features(review: Path, start: pd.Timestamp) -> pd.DataFrame:
    meta = latest_ok(read(review / "metadados_diarios.csv"), "estado_metadados")
    released = pd.to_datetime(meta["lancamento"], errors="coerce")
    platforms = meta[["windows", "mac", "linux"]].replace(YES)
    features = pd.DataFrame({
        "appid": meta["appid"],
        "editora": meta["editora"],
        "produtora": meta["produtora"],
        "lancamento": released.dt.date,
        "idade_anos": ((start.tz_localize(None) - released).dt.days / 365.25).round(2),
        "etiquetas_top": meta["etiquetas_com_peso"].map(top_tags),
        "n_idiomas": meta["idiomas"],
        "n_plataformas": platforms.sum(axis=1).astype("Int64"),
        "steam_deck": meta["steam_deck"],
    })
    spy = latest_ok(read(review / "steamspy_diario.csv"), "estado_steamspy")
    spy = spy.assign(proprietarios_estimados=(spy["proprietarios_min_estimados"]
                                              + spy["proprietarios_max_estimados"]) / 2)
    return features.merge(spy[["appid", "proprietarios_estimados"]], on="appid", how="left")


def interpolate_players(df: pd.DataFrame) -> pd.DataFrame:
    """Interpola só lacunas curtas (≤ MAX_INTERP_HOURS) entre duas leituras válidas."""
    filled = df.groupby("appid")["jogadores"].transform(
        lambda s: s.interpolate(method="linear", limit=MAX_INTERP_HOURS, limit_area="inside"))
    # interpolate(limit=...) preenche parte de lacunas longas: anula-se essas lacunas inteiras.
    missing = df["jogadores"].isna()
    run_id = (missing != missing.groupby(df["appid"]).shift()).cumsum()
    run_len = missing.groupby([df["appid"], run_id]).transform("sum")
    filled = filled.where(~missing | (run_len <= MAX_INTERP_HOURS))
    df["jogadores_tratado"] = filled.round()
    df["jogadores_interpolado"] = missing & filled.notna()
    return df


def build_dataset(review: Path = DEFAULT_REVIEW) -> pd.DataFrame:
    df = read_hourly(review)
    df["hora_utc"] = pd.to_datetime(df["hora_utc"], utc=True)
    df = df.sort_values(["appid", "hora_utc"], ignore_index=True)
    expected = df["appid"].nunique() * df["hora_utc"].nunique()
    if len(df) != expected or df.duplicated(["appid", "hora_utc"]).any():
        raise ValueError("A grelha jogo × hora não está completa ou tem repetidos")

    # Tempo
    df["data_utc"] = df["hora_utc"].dt.date
    df["hora_dia_utc"] = df["hora_utc"].dt.hour
    weekday = df["hora_utc"].dt.day_of_week
    df["dia_semana"] = weekday.map(dict(enumerate(DAYS_PT)))
    df["fim_de_semana"] = weekday >= 5

    # Jogadores: valores em falta, transformação e normalização por jogo
    df = interpolate_players(df)
    by_game = df.groupby("appid")["jogadores_tratado"]
    df["log_jogadores"] = np.log1p(df["jogadores_tratado"])
    df["jogadores_media_jogo"] = by_game.transform("mean").round(2)
    df["jogadores_rel_media"] = (df["jogadores_tratado"] / df["jogadores_media_jogo"]).round(4)
    std = by_game.transform("std").replace(0, np.nan)
    df["jogadores_z"] = ((df["jogadores_tratado"] - df["jogadores_media_jogo"]) / std).round(4)
    previous = by_game.shift()
    df["var_jogadores_1h_pct"] = ((df["jogadores_tratado"] - previous)
                                  / previous.replace(0, np.nan) * 100).round(2)
    means = df.groupby("appid")["jogadores_media_jogo"].first()
    tiers = pd.qcut(means, q=len(POPULARITY), labels=POPULARITY)
    df["popularidade"] = df["appid"].map(tiers).astype(str)

    # Loja
    df["gratuito"] = df["gratuito"].map(YES).astype("boolean")
    df["em_desconto"] = (df["desconto_pct"] > 0).astype("boolean").where(df["desconto_pct"].notna())
    df["novas_avaliacoes_1h"] = df.groupby("appid")["avaliacoes_total"].diff()

    # Ficha do jogo e SteamSpy
    start = df["hora_utc"].min()
    df = df.merge(game_features(review, start), on="appid", how="left", validate="many_to_one")

    df["hora_utc"] = df["hora_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df[COLUMNS]


def summary(df: pd.DataFrame) -> str:
    lines = [
        f"Linhas: {len(df):,} ({df['appid'].nunique()} jogos × {df['hora_utc'].nunique()} horas)",
        f"Período: {df['hora_utc'].min()} a {df['hora_utc'].max()}",
        f"Jogadores em falta (observado): {df['jogadores'].isna().sum():,}",
        f"Jogadores interpolados: {int(df['jogadores_interpolado'].sum()):,}",
        f"Jogadores em falta (tratado): {df['jogadores_tratado'].isna().sum():,}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    df = build_dataset(args.review)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8", lineterminator="\n")
    print(summary(df))
    print(f"Gravado em {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
