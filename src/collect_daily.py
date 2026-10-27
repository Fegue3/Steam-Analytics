"""Recolha diária da ficha de cada jogo na loja Steam e das estimativas SteamSpy.

A ficha (nome, publisher, developer, tags, lançamento, plataformas, línguas)
vem do `GetItems` em lotes de 200 jogos. O número de reviews e a percentagem positiva vêm da recolha horária da loja
(`collect_store`); o endpoint `appreviews` deixou de responder em outubro de 2026.

Cada execução pede sempre todos os jogos, para os dados de um dia virem todos
do mesmo run; só salta uma fonte se já houver uma recolha do dia sem erros. A
recolha SteamSpy para antes do limite de tempo e grava o que tiver, e desiste
após vários erros seguidos (API em baixo).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from src.api import STEAM_ITEMS_URL, SteamSpyClient, SteamStoreClient
from src.collect_common import (append_jsonl, close_collection_logging, collection_record,
                                day_path, load_games, setup_collection_logging, utc_now)

STEAMSPY_ENDPOINT = "https://steamspy.com/api.php?request=appdetails&appid=<appid>"
MAX_CONSECUTIVE_ERRORS = 20
# Preço e reviews ficam de fora: a recolha horária da loja já os guarda.
METADATA_FIELDS = ("name", "store_type", "store_status", "publisher", "developer",
                   "short_description", "release_date_utc", "tags", "features",
                   "feature_categories", "controller_categories", "windows", "mac", "linux",
                   "steam_deck_compat", "n_languages", "n_languages_full_audio")


def today_records(out: Path, source: str) -> list[dict]:
    path = day_path(out, source)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def completed_today(out: Path, source: str) -> dict | None:
    """Devolve a recolha de hoje desta fonte se já existir uma sem erros."""
    for record in reversed(today_records(out, source)):
        if record.get("n_ok", 0) > 0 and record.get("n_error", 0) == 0:
            return record
    return None


def collect_source(games: list[dict], out: Path, source: str, name: str, endpoint: str,
                   fetch: Callable[[int], dict], deadline: datetime | None = None,
                   logger=None) -> dict:
    """Pede todos os jogos e grava um registo; os não tentados ficam como erro."""
    started = utc_now()
    fetched, consecutive_errors, stop_reason = {}, 0, None
    for game in games:
        if deadline and utc_now() >= deadline:
            stop_reason = "não tentado: limite de tempo do run"
            break
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            stop_reason = f"não tentado: {consecutive_errors} erros seguidos"
            break
        record = fetch(game["appid"])
        fetched[game["appid"]] = record
        consecutive_errors = consecutive_errors + 1 if record["status"] == "error" else 0
        if logger:
            logger.info("%s: %d/%d appid %d %s", source, len(fetched), len(games),
                        game["appid"], record["status"])
    if stop_reason and logger:
        logger.warning("%s: recolha interrompida (%s)", source, stop_reason)
    records = [fetched.get(game["appid"]) or {"appid": game["appid"], "status": "error",
                                              "http_status": None, "error": stop_reason}
               for game in games]
    result = collection_record(name, endpoint, games[0]["selection_date_utc"], started,
                               utc_now(), records)
    append_jsonl(day_path(out, source, started), result)
    return result


def collect_metadata(games: list[dict], out: Path, cache: Path | None = None) -> dict:
    started = utc_now()
    client = SteamStoreClient(cache or out / "cache" / "store", cache_hours=0, batch_size=200)
    found, missing, failed = client.get_games([game["appid"] for game in games],
                                              include_details=True)
    records = []
    for game in games:
        appid = game["appid"]
        if appid in failed:
            records.append({"appid": appid, "status": "error", "error": "falha no lote"})
        elif appid in missing:
            records.append({"appid": appid, "status": "no_data"})
        else:
            records.append({"appid": appid, "status": "ok",
                            **{key: found[appid].get(key) for key in METADATA_FIELDS}})
    result = collection_record("steam_metadata", STEAM_ITEMS_URL, games[0]["selection_date_utc"],
                               started, utc_now(), records)
    append_jsonl(day_path(out, "metadata", started), result)
    return result


def fetch_steamspy(client: SteamSpyClient, appid: int) -> dict:
    try:
        payload = client.get(request="appdetails", appid=appid)
    except RuntimeError as exc:
        return {"appid": appid, "status": "error", "error": str(exc)}
    if payload.get("error") or not payload:
        return {"appid": appid, "status": "no_data"}
    return {"appid": appid, "status": "ok", **{
        key: payload.get(key) for key in
        ("owners", "ccu", "positive", "negative", "price", "initialprice", "discount")
    }}


def collect_steamspy(games: list[dict], out: Path, cache: Path | None = None,
                     deadline: datetime | None = None, logger=None) -> dict:
    client = SteamSpyClient(cache or out / "cache" / "steamspy", cache_hours=0)
    return collect_source(games, out, "steamspy", "steamspy", STEAMSPY_ENDPOINT,
                          lambda appid: fetch_steamspy(client, appid), deadline, logger)


def collect(games: list[dict], out: Path, cache: Path | None = None,
            force: bool = False, max_minutes: float | None = None) -> tuple[dict, dict]:
    logger = setup_collection_logging(out, "daily")
    logger.info("Início: %d jogos", len(games))
    deadline = utc_now() + timedelta(minutes=max_minutes) if max_minutes else None
    metadata = None if force else completed_today(out, "metadata")
    if metadata:
        logger.info("Ficha da loja de hoje já recolhida sem erros; a saltar")
    else:
        metadata = collect_metadata_safe(games, out, cache, logger)
    steamspy = None if force else completed_today(out, "steamspy")
    if steamspy:
        logger.info("SteamSpy de hoje já recolhido sem erros; a saltar")
    else:
        steamspy = collect_steamspy_safe(games, out, cache, logger, deadline)
    logger.info("Fim: ficha da loja %d ok/%d erros; SteamSpy %d ok/%d erros",
                metadata["n_ok"], metadata["n_error"], steamspy["n_ok"], steamspy["n_error"])
    close_collection_logging(logger)
    return metadata, steamspy


def collect_metadata_safe(games: list[dict], out: Path, cache: Path | None, logger) -> dict:
    try:
        return collect_metadata(games, out, cache)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("Recolha da ficha da loja falhou; a recolha SteamSpy continua")
        metadata = collection_record(
            "steam_metadata", STEAM_ITEMS_URL,
            games[0]["selection_date_utc"], utc_now(), utc_now(),
            [{"appid": game["appid"], "status": "error", "http_status": None,
              "error": str(exc)} for game in games])
        append_jsonl(day_path(out, "metadata"), metadata)
        return metadata


def collect_steamspy_safe(games: list[dict], out: Path, cache: Path | None, logger,
                          deadline: datetime | None = None) -> dict:
    try:
        return collect_steamspy(games, out, cache, deadline, logger)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("Recolha SteamSpy falhou")
        steamspy = collection_record(
            "steamspy", STEAMSPY_ENDPOINT,
            games[0]["selection_date_utc"], utc_now(), utc_now(),
            [{"appid": game["appid"], "status": "error", "http_status": None,
              "error": str(exc)} for game in games])
        append_jsonl(day_path(out, "steamspy"), steamspy)
        return steamspy


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recolha diária da ficha da loja e do SteamSpy")
    parser.add_argument("--games", type=Path, default=Path("config/games.csv"))
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true",
                        help="Recolhe mesmo que já exista uma recolha de hoje sem erros")
    parser.add_argument("--max-minutes", type=float,
                        help="Para de pedir jogos ao fim deste tempo e grava o que tiver")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit tem de ser >= 1")
    if args.max_minutes is not None and args.max_minutes <= 0:
        parser.error("--max-minutes tem de ser > 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    games = load_games(args.games)
    collect(games[:args.limit] if args.limit else games, args.out, args.cache, args.force,
            args.max_minutes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
