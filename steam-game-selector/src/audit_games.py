"""Audita o CSV de jogos selecionados, sem fazer pedidos HTTP."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def audit(csv_path: Path, config_path: Path, per_category: int) -> tuple[bool, list[str]]:
    categories = json.loads(config_path.read_text(encoding="utf-8"))["categories"]
    expected = {c["id"]: per_category for c in categories}
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    errors = []
    appids = [row.get("appid", "") for row in rows]
    duplicates = [key for key, count in Counter(appids).items() if count > 1]
    if duplicates:
        errors.append(f"AppIDs repetidos: {duplicates[:20]}")
    counts = Counter(row.get("category", "") for row in rows)
    for cat, amount in expected.items():
        if counts[cat] != amount:
            errors.append(f"{cat}: {counts[cat]} jogos (esperados {amount})")
    if len(rows) != sum(expected.values()):
        errors.append(f"Total: {len(rows)}, esperado {sum(expected.values())}")
    empty = [row.get("appid") for row in rows if not row.get("name") or not row.get("appid")]
    if empty:
        errors.append(f"Há {len(empty)} linhas sem AppID ou nome")
    return not errors, errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path, help="CSV resultante da seleção")
    parser.add_argument("--config", type=Path, default=Path("config/categories.json"))
    parser.add_argument("--per-category", type=int, default=100)
    args = parser.parse_args()
    ok, errors = audit(args.csv, args.config, args.per_category)
    print("PASSOU" if ok else "FALHOU")
    for error in errors:
        print(" -", error)
    raise SystemExit(0 if ok else 1)
