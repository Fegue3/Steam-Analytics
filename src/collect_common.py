"""Utilitários partilhados pelos coletores de dados."""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    value = value or utc_now()
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hour_start(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def day_path(root: Path, source: str, when: datetime | None = None, suffix: str = ".jsonl") -> Path:
    when = (when or utc_now()).astimezone(timezone.utc)
    path = Path(root) / "raw" / source / f"{when:%Y-%m-%d}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()


def load_games(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Lista de jogos inexistente: {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        games = list(csv.DictReader(stream))
    if not games:
        raise ValueError(f"Lista de jogos vazia: {path}")
    required = {"appid", "name", "category", "selection_date_utc"}
    if not required.issubset(games[0]):
        raise ValueError(f"Colunas em falta na lista de jogos: {sorted(required - set(games[0]))}")
    appids = []
    for game in games:
        try:
            appid = int(game["appid"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"AppID inválido: {game.get('appid')}") from exc
        if appid <= 0 or not str(game.get("name") or "").strip():
            raise ValueError(f"Jogo inválido na lista: {game}")
        game["appid"] = appid
        appids.append(appid)
    if len(appids) != len(set(appids)):
        raise ValueError("A lista de jogos contém AppIDs repetidos")
    return games


def run_id() -> str:
    return os.environ.get("GITHUB_RUN_ID", "local")


def setup_collection_logging(root: Path, source: str, when: datetime | None = None) -> logging.Logger:
    when = (when or utc_now()).astimezone(timezone.utc)
    log_path = Path(root) / "logs" / source / f"{when:%Y-%m-%d}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"steam_collection.{source}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def close_collection_logging(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def collection_record(source: str, endpoint: str, games_list_date: str,
                      started: datetime, finished: datetime, games: list[dict],
                      **extra: object) -> dict:
    statuses = [game.get("status") for game in games]
    return {
        "source": source,
        "endpoint": endpoint,
        "collected_at_utc": iso_utc(started),
        "finished_at_utc": iso_utc(finished),
        "hour_utc": iso_utc(hour_start(started)),
        "run_id": run_id(),
        "games_list_date": games_list_date,
        "n_games": len(games),
        "n_ok": statuses.count("ok"),
        "n_no_data": statuses.count("no_data"),
        "n_error": statuses.count("error"),
        "games": games,
        **extra,
    }
