"""Recolha horária de jogadores atuais da Steam."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from src.api import STEAM_PLAYERS_URL, SteamPlayersClient
from src.collect_common import (append_jsonl, close_collection_logging, collection_record,
                                day_path, load_games, setup_collection_logging, utc_now)


def collect(games: list[dict], out: Path, cache: Path | None = None) -> dict:
    started = utc_now()
    logger = setup_collection_logging(out, "players", started)
    client = SteamPlayersClient(cache or out / "cache" / "players", cache_hours=0, workers=6)
    results = client.fetch_players_many([game["appid"] for game in games])
    records = []
    for game in games:
        players, status, http_status, error = results[game["appid"]]
        record = {"appid": game["appid"], "players": players, "status": status}
        if status != "ok":
            record.update({"http_status": http_status, "error": error})
        records.append(record)
    finished = utc_now()
    output = collection_record("steam_players", STEAM_PLAYERS_URL, games[0]["selection_date_utc"],
                                started, finished, records)
    append_jsonl(day_path(out, "players", started), output)
    logger.info("Início: %d jogos", len(games))
    logger.info("Fim: %d ok, %d sem dados, %d erros", output["n_ok"],
                output["n_no_data"], output["n_error"])
    close_collection_logging(logger)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recolha horária de jogadores Steam")
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
