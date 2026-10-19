"""Recolha diária de reviews exatas e estimativas SteamSpy."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.api import SteamReviewsClient, SteamSpyClient
from src.collect_common import (append_jsonl, close_collection_logging, collection_record,
                                day_path, load_games, setup_collection_logging, utc_now)


def collect_reviews(games: list[dict], out: Path) -> dict:
    started = utc_now()
    client = SteamReviewsClient()
    records = []
    for game in games:
        payload, status, http_status, error = client.fetch(game["appid"])
        summary = (payload or {}).get("query_summary") or {}
        record = {"appid": game["appid"], "status": status}
        if status == "ok":
            record.update({key: summary.get(key, 0) for key in
                           ("total_positive", "total_negative", "total_reviews", "review_score")})
        else:
            record.update({"http_status": http_status, "error": error})
        records.append(record)
    finished = utc_now()
    result = collection_record(
        "steam_reviews", "https://store.steampowered.com/appreviews/<appid>",
        games[0]["selection_date_utc"], started, finished, records)
    append_jsonl(day_path(out, "reviews", started), result)
    return result


def collect_steamspy(games: list[dict], out: Path, cache: Path | None = None) -> dict:
    started = utc_now()
    client = SteamSpyClient(cache or out / "cache" / "steamspy", cache_hours=0)
    records = []
    for game in games:
        try:
            payload = client.get(request="appdetails", appid=game["appid"])
            if payload.get("error") or not payload:
                records.append({"appid": game["appid"], "status": "no_data"})
            else:
                records.append({"appid": game["appid"], "status": "ok", **{
                    key: payload.get(key) for key in
                    ("owners", "ccu", "positive", "negative", "price", "initialprice", "discount")
                }})
        except RuntimeError as exc:
            records.append({"appid": game["appid"], "status": "error", "error": str(exc)})
    finished = utc_now()
    result = collection_record(
        "steamspy", "https://steamspy.com/api.php?request=appdetails&appid=<appid>",
        games[0]["selection_date_utc"], started, finished, records)
    append_jsonl(day_path(out, "steamspy", started), result)
    return result


def collect(games: list[dict], out: Path, cache: Path | None = None) -> tuple[dict, dict]:
    logger = setup_collection_logging(out, "daily")
    logger.info("Início: %d jogos", len(games))
    try:
        reviews = collect_reviews(games, out)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("Recolha de reviews falhou; a recolha SteamSpy continua")
        reviews = collection_record(
            "steam_reviews", "https://store.steampowered.com/appreviews/<appid>",
            games[0]["selection_date_utc"], utc_now(), utc_now(),
            [{"appid": game["appid"], "status": "error", "http_status": None,
              "error": str(exc)} for game in games])
        append_jsonl(day_path(out, "reviews"), reviews)
    try:
        steamspy = collect_steamspy(games, out, cache)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("Recolha SteamSpy falhou; a recolha de reviews já foi preservada")
        steamspy = collection_record(
            "steamspy", "https://steamspy.com/api.php?request=appdetails&appid=<appid>",
            games[0]["selection_date_utc"], utc_now(), utc_now(),
            [{"appid": game["appid"], "status": "error", "http_status": None,
              "error": str(exc)} for game in games])
        append_jsonl(day_path(out, "steamspy"), steamspy)
    logger.info("Fim: reviews %d ok/%d erros; SteamSpy %d ok/%d erros",
                reviews["n_ok"], reviews["n_error"], steamspy["n_ok"], steamspy["n_error"])
    close_collection_logging(logger)
    return reviews, steamspy


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recolha diária de reviews e SteamSpy")
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
