"""Constrói uma lista auditável de N jogos únicos distribuídos por cinco grupos.

Executar a partir da pasta raiz:
  python -m src.select_games --per-category 100 --catalog-pages 3
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.steamspy_client import SteamSpyClient

LOGGER = logging.getLogger("steam_selection")
BAD_NAME = re.compile(r"(?:\b(?:demo|playtest|soundtrack|artbook|dedicated server|beta test)\b|\bDLC\b)", re.I)
GAMES_HEADER = [
    "appid", "name", "category", "category_label", "rank_in_category",
    "rank_before_dedup", "owners_range", "owners_min", "owners_max",
    "ccu_yesterday", "positive_reviews", "negative_reviews", "price_usd_cents",
    "developer", "publisher", "genre", "matched_sources", "other_categories",
    "requires_manual_review", "selection_date_utc",
]
CANDIDATE_HEADER = [
    "appid", "name", "category", "owners_min", "ccu_yesterday", "publisher", "matched_sources",
]


def normalize(value: object) -> str:
    return " ".join(str(value or "").casefold().replace("&", "and").split())


def parse_owners(text: object) -> tuple[int, int]:
    """Lê o intervalo do SteamSpy, p.ex. '1,000,000 .. 2,000,000'."""
    found = re.findall(r"\d[\d,.]*", str(text or ""))
    if len(found) < 2:
        return 0, 0
    try:
        return (int(found[0].replace(",", "").replace(".", "")),
                int(found[1].replace(",", "").replace(".", "")))
    except ValueError:
        return 0, 0


def int_val(v: object) -> int:
    try:
        return max(0, int(float(str(v))))
    except (ValueError, TypeError):
        return 0


def valid_game(appid: int, game: dict, excluded: set[int]) -> bool:
    if appid < 1 or appid in excluded or appid == 999999:
        return False
    title = str(game.get("name") or "").strip()
    if not title or BAD_NAME.search(title):
        return False
    return True


def parse_appid(key: object, game: dict) -> int | None:
    try:
        value = game.get("appid", key)
        appid = int(value)
        return appid if appid > 0 else None
    except (ValueError, TypeError):
        return None


def better_record(old: dict, new: dict) -> dict:
    """Merge seguro dos campos mais úteis sem perder valores já conhecidos."""
    out = dict(old)
    for k, v in new.items():
        if v not in (None, "", [], {}) and (out.get(k) in (None, "", [], {})):
            out[k] = v
    if parse_owners(new.get("owners"))[0] > parse_owners(out.get("owners"))[0]:
        out["owners"] = new["owners"]
    if int_val(new.get("ccu")) > int_val(out.get("ccu")):
        out["ccu"] = new["ccu"]
    return out


def add_batch(registry: dict, memberships: dict, payload: dict, category: str, source: str,
              excluded: set[int]) -> int:
    seen = 0
    for key, game in payload.items():
        if not isinstance(game, dict):
            continue
        appid = parse_appid(key, game)
        if appid is None or not valid_game(appid, game, excluded):
            continue
        registry[appid] = better_record(registry.get(appid, {}), game)
        memberships[category][appid].add(source)
        seen += 1
    return seen


def is_aaa_proxy(game: dict, config: dict) -> bool:
    """AAA não é género oficial: aproximação editável por editora + preço positivo."""
    publishers = [normalize(p) for p in re.split(r"[,;|]", str(game.get("publisher") or "")) if p.strip()]
    allow = [normalize(v) for v in config.get("publisher_allowlist", [])]
    if not publishers or not any(p == a or (len(a) >= 4 and p.startswith(a + " "))
                             for p in publishers for a in allow):
        return False
    price = game.get("price")
    if config.get("require_paid", False) and int_val(price) <= 0:
        return False
    return True


def ranking_key(game: dict, method: str) -> tuple:
    owners_min, owners_max = parse_owners(game.get("owners"))
    ccu = int_val(game.get("ccu"))
    reviews = int_val(game.get("positive")) + int_val(game.get("negative"))
    if method == "ccu":
        return ccu, owners_min, owners_max, reviews
    return owners_min, owners_max, ccu, reviews


def load_exclusions(path: Path) -> set[int]:
    if not path.exists():
        return set()
    excluded = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            value = (row.get("appid") or "").strip()
            if value:
                try:
                    excluded.add(int(value))
                except ValueError:
                    LOGGER.warning("AppID inválido ignorado em exclusões: %s", value)
    return excluded


def rank_categories(categories: list[dict], memberships: dict, registry: dict, method: str):
    candidates = {}
    for category in categories:
        cid = category["id"]
        candidates[cid] = sorted(memberships[cid],
                                 key=lambda a: (ranking_key(registry[a], method), -a),
                                 reverse=True)
    return candidates


def allocate_unique(categories: list[dict], rankings: dict[str, list[int]], per_category: int):
    """Primeiro categorias com menos candidatos: preserva jogos únicos.

    O TOP 100 final é o TOP 100 DISPONÍVEL da categoria após resolver conflitos.
    Não é necessariamente o TOP 100 absoluto da categoria se houver sobreposição.
    """
    priority = sorted(categories, key=lambda cat: (len(rankings[cat["id"]]), cat["id"]))
    used = set()
    chosen: dict[str, list[tuple[int, int]]] = {}
    for cat in priority:
        cid = cat["id"]
        available = [(appid, idx) for idx, appid in enumerate(rankings[cid], start=1)
                     if appid not in used]
        chosen[cid] = available[:per_category]
        used.update(appid for appid, _ in chosen[cid])
    return chosen, [cat["id"] for cat in priority]


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Selecionar TOP N por grupo com SteamSpy")
    parser.add_argument("--per-category", type=int, default=100)
    parser.add_argument("--catalog-pages", type=int, default=3,
                        help="Páginas de 1000 jogos para procurar editoras AAA (cada 'all' espera 60s)")
    parser.add_argument("--ranking", choices=("owners", "ccu"), default="owners")
    parser.add_argument("--config", type=Path, default=Path("config/categories.json"))
    parser.add_argument("--exclusions", type=Path, default=Path("config/exclusions.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/output"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--cache-hours", type=float, default=24.0)
    parser.add_argument("--strict", action="store_true", help="Terminar com erro se não houver exatamente N por categoria")
    args = parser.parse_args()

    if args.per_category < 1 or args.catalog_pages < 0:
        parser.error("--per-category >= 1 e --catalog-pages >= 0")
    args.out.mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler("logs/selection.log", encoding="utf-8")])
    categories = json.loads(args.config.read_text(encoding="utf-8"))["categories"]
    excluded = load_exclusions(args.exclusions)
    registry: dict[int, dict] = {}
    memberships: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    client = SteamSpyClient(args.cache, cache_hours=args.cache_hours)
    successes, failures = [], []

    # Uma chamada por etiqueta/género, combinando por OU com chave AppID.
    tasks = []
    for cat in categories:
        for tag in cat.get("tags", []):
            tasks.append((cat["id"], "tag", tag))
        for genre in cat.get("genres", []):
            tasks.append((cat["id"], "genre", genre))
    unique_tasks = list(dict.fromkeys((kind, label) for _, kind, label in tasks))
    payloads = {}
    LOGGER.info("Consultas previstas: %d tags/géneros e %d páginas de catálogo", len(unique_tasks), args.catalog_pages)
    for kind, label in unique_tasks:
        try:
            payloads[(kind, label)] = client.get(request=kind, **{kind: label})
            successes.append(f"{kind}:{label}")
        except RuntimeError as exc:
            LOGGER.error("Fonte indisponível: %s", exc)
            payloads[(kind, label)] = {}
            failures.append(f"{kind}:{label}")

    for category, kind, label in tasks:
        add_batch(registry, memberships, payloads[(kind, label)], category,
                  f"{kind}:{label}", excluded)

    # Para AAA: consultar páginas globais do catálogo e filtrar editoras predefinidas.
    aaa_categories = [c for c in categories if c.get("candidate_source") == "catalog"]
    if aaa_categories:
        for page in range(args.catalog_pages):
            try:
                payload = client.get(request="all", page=page)
                successes.append(f"all:{page}")
            except RuntimeError as exc:
                LOGGER.error("Catálogo indisponível: %s", exc)
                failures.append(f"all:{page}")
                continue
            for cat in aaa_categories:
                filtered = {}
                for key, value in payload.items():
                    if isinstance(value, dict) and is_aaa_proxy(value, cat):
                        filtered[key] = value
                add_batch(registry, memberships, filtered, cat["id"],
                          f"catalog:publisher_proxy:page_{page}", excluded)

    rankings = rank_categories(categories, memberships, registry, args.ranking)
    chosen, priority = allocate_unique(categories, rankings, args.per_category)
    today = datetime.now(timezone.utc).isoformat(timespec="seconds")
    labels = {cat["id"]: cat["label"] for cat in categories}
    by_app = defaultdict(list)
    for cid, apps in rankings.items():
        for appid in apps:
            by_app[appid].append(cid)

    candidate_rows = []
    for cat in categories:
        cid = cat["id"]
        for appid in rankings[cid]:
            g = registry[appid]
            candidate_rows.append({"appid": appid, "name": g.get("name", ""), "category": cid,
                                   "owners_min": parse_owners(g.get("owners"))[0],
                                   "ccu_yesterday": int_val(g.get("ccu")),
                                   "publisher": g.get("publisher", ""),
                                   "matched_sources": " | ".join(sorted(memberships[cid][appid]))})

    game_rows = []
    for cat in categories:
        cid = cat["id"]
        for rank_final, (appid, rank_abs) in enumerate(chosen[cid], start=1):
            g = registry[appid]
            lo, hi = parse_owners(g.get("owners"))
            game_rows.append({
                "appid": appid, "name": g.get("name", ""),
                "category": cid, "category_label": labels[cid],
                "rank_in_category": rank_final, "rank_before_dedup": rank_abs,
                "owners_range": g.get("owners", ""), "owners_min": lo, "owners_max": hi,
                "ccu_yesterday": int_val(g.get("ccu")),
                "positive_reviews": int_val(g.get("positive")), "negative_reviews": int_val(g.get("negative")),
                "price_usd_cents": g.get("price", ""), "developer": g.get("developer", ""),
                "publisher": g.get("publisher", ""), "genre": g.get("genre", ""),
                "matched_sources": " | ".join(sorted(memberships[cid][appid])),
                "other_categories": " | ".join(c for c in by_app[appid] if c != cid),
                "requires_manual_review": "YES" if cid == "aaa" or BAD_NAME.search(str(g.get("name", ""))) else "CHECK",
                "selection_date_utc": today,
            })

    expected = len(categories) * args.per_category
    complete = len(game_rows) == expected
    output_name = f"games_{expected}.csv" if complete else "games_INCOMPLETE.csv"
    write_csv(args.out / output_name, GAMES_HEADER, game_rows)
    write_csv(args.out / "all_candidates.csv", CANDIDATE_HEADER, candidate_rows)
    summary = {
        "created_utc": today,
        "method": args.ranking,
        "definition": "TOP N dos candidatos que restam após remover jogos atribuídos a outras categorias",
        "planned_games": expected,
        "selected_games": len(game_rows),
        "complete": complete,
        "categories": {c["id"]: {"target": args.per_category,
                                  "candidates": len(rankings[c["id"]]),
                                  "selected": len(chosen[c["id"]])} for c in categories},
        "assignment_priority_by_candidate_scarcity": priority,
        "data_sources_succeeded": successes,
        "data_sources_failed": failures,
        "http_requests": client.calls,
        "cache_hits": client.cache_hits,
        "notes": [
            "AAA é apenas proxy por editoras grandes e preço > 0; validar manualmente.",
            "Tags/géneros são uma união OR e podem ter falsos positivos.",
            "owners são intervalos estimados; não são vendas.",
            "CCU SteamSpy é pico de ontem, não jogadores ativos agora.",
            "Ordenar por owners_min, desempatar por owners_max, ccu e reviews (ou --ranking ccu).",
            "Podem existir jogos não publicados, DLC ou jogos sem suporte adequado: confirmar antes de iniciar recolha.",
            "Nenhuma execução com fontes falhadas deve ser tratada como seleção definitiva.",
        ]
    }
    (args.out / "report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Selecionados %s/%s jogos; ficheiro %s", len(game_rows), expected, args.out / output_name)
    for cid, stats in summary["categories"].items():
        LOGGER.info("%-16s %3d selecionados de %4d candidatos", cid, stats["selected"], stats["candidates"])
    if failures:
        LOGGER.warning("Falharam fontes: %s", ", ".join(failures))
    if args.strict and (not complete or bool(failures)):
        LOGGER.error("Falhou validação strict: não utilizar como versão final")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
