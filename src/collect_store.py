"""Recolha horária de preços, descontos e resumo de reviews da loja."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.api import STEAM_ITEMS_URL, SteamStoreClient
from src.collect_common import (append_jsonl, collection_record, day_path, load_games,
                                setup_collection_logging, utc_now)


def collect(games: list[dict], out: Path, cache: Path | None = None) -> dict:
    started = utc_now()
    logger = setup_collection_logging(out, "store", started)
    client = SteamStoreClient(cache or out / "cache" / "store", cache_hours=0, batch_size=200)
    appids = [game["appid"] for game in games]
    found, missing, failed = client.get_games(appids, include_reviews=True)
    records = []
    for game in games:
        appid = game["appid"]
        if appid in failed:
            records.append({"appid": appid, "status": "error", "error": "falha no lote"})
        elif appid in missing:
            records.append({"appid": appid, "status": "no_data"})
        else:
            records.append({"appid": appid, **{
                key: value for key, value in found[appid].items()
                if key in {"is_free", "price", "initialprice", "discount_pct",
                           "discount_end_utc", "review_count", "review_pct_positive",
                           "review_score_label"}} , "status": "ok"})
            records[-1]["price_cents"] = int(records[-1].pop("price")) if records[-1].get("price") else None
            records[-1]["original_price_cents"] = (
                int(records[-1].pop("initialprice"))
                if records[-1].get("initialprice") else records[-1]["price_cents"])
    finished = utc_now()
    output = collection_record("steam_store", STEAM_ITEMS_URL, games[0]["selection_date_utc"],
                                started, finished, records)
    append_jsonl(day_path(out, "store", started), output)
    logger.info("Início: %d jogos em lotes de 200", len(games))
    logger.info("Fim: %d ok, %d sem dados, %d erros", output["n_ok"],
                output["n_no_data"], output["n_error"])
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recolha horária da loja Steam")
    parser.add_argument("--games", type=Path, default=Path("config/games.csv"))
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit tem de ser >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    games = load_games(args.games)
    collect(games[:args.limit] if args.limit else games, args.out, args.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
