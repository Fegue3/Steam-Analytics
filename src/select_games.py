"""Seleciona os N jogos com mais jogadores em cada categoria e grava config/games.csv.

A lista (appid, name, category) é o ponto de partida das recolhas; tudo o que se analisa
(jogadores, preços, reviews) vem das recolhas, não daqui.

Pipeline (~1,5 min sem cache):
  1. Descoberta  - listas SteamSpy tag/genre (OU) + TOP 100 oficial da Steam
                   (GetMostPlayedGames), que cobre falhas do SteamSpy (p.ex. Dota 2).
  2. Pool        - candidatos com CCU de ontem (SteamSpy) >= --pool-min-ccu.
  3. Detalhes    - Steam IStoreBrowseService/GetItems, 200 jogos por pedido: etiquetas com
                   peso, funcionalidades, editora, preço, tipo (jogo/software), nome atual.
  4. Classificar - uma categoria principal por jogo (ver src/classify.py).
  5. Medir       - Steam GetNumberOfCurrentPlayers para todos os elegíveis (em paralelo),
                   a mesma fonte da recolha horária. Jogos sem resposta ficam de fora.
  6. Escolher    - TOP N por jogadores atuais em cada categoria; validar e gravar.

Executar na raiz do repositório:
  python3 -m src.select_games
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.api import SteamPlayersClient, SteamSpyClient, SteamStoreClient
from src.classify import BAD_NAME, classify, int_val, non_game_reason

ROOT = Path(__file__).resolve().parents[1]  # raiz do repositório
LOGGER = logging.getLogger("steam_selection")
GAMES_HEADER = ["appid", "name", "category", "selection_date_utc"]


def parse_appid(key: object, game: dict) -> int | None:
    try:
        appid = int(game.get("appid", key))
        return appid if appid > 0 else None
    except (ValueError, TypeError):
        return None


def merge_summary(old: dict, new: dict) -> dict:
    """Junta registos do mesmo AppID vindos de listas diferentes sem perder valores."""
    out = dict(old)
    for k, v in new.items():
        if v not in (None, "", [], {}) and out.get(k) in (None, "", [], {}):
            out[k] = v
    if int_val(new.get("ccu")) > int_val(out.get("ccu")):
        out["ccu"] = new["ccu"]
    return out


def add_batch(registry: dict, sources: dict, payload: dict, source: str) -> int:
    seen = 0
    for key, game in payload.items():
        if not isinstance(game, dict):
            continue
        appid = parse_appid(key, game)
        if appid is None or appid == 999999:
            continue
        registry[appid] = merge_summary(registry.get(appid, {}), game)
        sources[appid].add(source)
        seen += 1
    return seen


def discovery_tasks(categories: list[dict]) -> list[tuple[str, str]]:
    tasks = []
    for cat in categories:
        tags = cat.get("discovery_tags", cat.get("tags", []) if cat.get("type") == "genre" else [])
        tasks += [("tag", t) for t in tags]
        tasks += [("genre", g) for g in cat.get("discovery_genres", [])]
    return list(dict.fromkeys(tasks))


def load_exclusions(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    excluded = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            value = (row.get("appid") or "").strip()
            if not value or value.startswith("#"):
                continue
            try:
                excluded[int(value)] = (row.get("reason") or "").strip()
            except ValueError:
                LOGGER.warning("AppID inválido ignorado em exclusões: %s", value)
    return excluded


def top_by_players(categories: list[dict], primary: dict[int, str], players: dict[int, int],
                   per_category: int) -> dict[str, list[int]]:
    """TOP N por jogadores atuais em cada categoria (desempate: AppID mais baixo)."""
    ranked = {cat["id"]: [] for cat in categories}
    for appid, cid in primary.items():
        ranked[cid].append(appid)
    return {cid: sorted(apps, key=lambda a: (-players[a], a))[:per_category]
            for cid, apps in ranked.items()}


def validate(chosen: dict[str, list[int]], names: dict[int, str], per_category: int) -> list[str]:
    """Erros que impedem gravar a lista (vazio = tudo bem)."""
    errors = []
    for cid, apps in chosen.items():
        if len(apps) != per_category:
            errors.append(f"{cid}: {len(apps)} jogos (esperados {per_category})")
    appids = [a for apps in chosen.values() for a in apps]
    repeated = [a for a, n in Counter(appids).items() if n > 1]
    if repeated:
        errors.append(f"AppIDs repetidos: {repeated[:20]}")
    nameless = [a for a in appids if not str(names.get(a) or "").strip()]
    if nameless:
        errors.append(f"AppIDs sem nome: {nameless[:20]}")
    return errors


def write_games(path: Path, chosen: dict[str, list[int]], names: dict[int, str], when: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=GAMES_HEADER)
        writer.writeheader()
        for cid, apps in chosen.items():
            writer.writerows({"appid": a, "name": names[a], "category": cid, "selection_date_utc": when}
                             for a in apps)


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Selecionar os N jogos com mais jogadores por categoria")
    parser.add_argument("--per-category", type=int, default=100)
    parser.add_argument("--top-k-tags", type=int, default=5,
                        help="Uma etiqueta só conta se estiver entre as K mais votadas do jogo")
    parser.add_argument("--pool-min-ccu", type=int, default=50,
                        help="CCU de ontem mínimo (listas SteamSpy) para pedir detalhes à loja")
    parser.add_argument("--min-ccu", type=int, default=100,
                        help="CCU de ontem mínimo (SteamSpy) para o jogo ser elegível")
    parser.add_argument("--min-players", type=int, default=1,
                        help="Jogadores mínimos agora (GetNumberOfCurrentPlayers)")
    parser.add_argument("--config", type=Path, default=ROOT / "config/categories.json")
    parser.add_argument("--exclusions", type=Path, default=ROOT / "config/exclusions.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "config/games.csv")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache")
    parser.add_argument("--cache-hours", type=float, default=24.0, help="Validade da cache em disco")
    parser.add_argument("--log-file", type=Path, default=ROOT / "logs/selection.log")
    args = parser.parse_args(argv)
    if args.per_category < 1 or args.top_k_tags < 1:
        parser.error("valores inválidos: --per-category>=1, --top-k-tags>=1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_file)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    categories = config["categories"]
    excluded = load_exclusions(args.exclusions)
    lists = SteamSpyClient(args.cache, cache_hours=args.cache_hours)
    store = SteamStoreClient(args.cache / "store", cache_hours=args.cache_hours)
    players_client = SteamPlayersClient(args.cache / "players")
    failures = []

    # 1. Descoberta.
    registry: dict[int, dict] = {}
    sources: dict[int, set[str]] = defaultdict(set)
    tasks = discovery_tasks(categories)
    LOGGER.info("Descoberta: %d listas tag/genre do SteamSpy + TOP 100 oficial", len(tasks))
    for kind, label in tasks:
        try:
            add_batch(registry, sources, lists.get(request=kind, **{kind: label}), f"{kind}:{label}")
        except RuntimeError as exc:
            LOGGER.error("Fonte indisponível: %s", exc)
            failures.append(f"{kind}:{label}")
    try:
        for appid, peak in store.most_played().items():
            registry[appid] = merge_summary(registry.get(appid, {}), {"appid": appid, "ccu": peak})
            sources[appid].add("steam:most_played")
    except RuntimeError as exc:
        LOGGER.error("TOP 100 oficial indisponível: %s", exc)
        failures.append("steam:most_played")

    # 2. Pool: filtros baratos antes de pedir detalhes.
    rejected: dict[int, str] = {}
    pool = []
    for appid, game in registry.items():
        if int_val(game.get("ccu")) < args.pool_min_ccu:
            continue
        if appid in excluded:
            rejected[appid] = "excluido_manual"
        elif BAD_NAME.search(str(game.get("name") or "")):
            rejected[appid] = "nome_nao_jogo"
        else:
            pool.append(appid)
    LOGGER.info("Descobertos %d AppIDs; pool com CCU>=%d: %d", len(registry), args.pool_min_ccu, len(pool))

    # 3. Detalhes da loja Steam, em lotes. Os dados da loja têm prioridade sobre as listas.
    details: dict[int, dict] = {}
    store_games, not_in_store, store_failed = store.get_games(pool)
    rejected.update({a: "fora_da_loja" for a in not_in_store})
    rejected.update({a: "loja_falhou" for a in store_failed})
    for appid, game in store_games.items():
        details[appid] = {**registry[appid], **{k: v for k, v in game.items() if v not in (None, "")}}
        if not details[appid].get("genre"):
            # As listas tag/genre do SteamSpy não trazem `genre`; derivar das listas genre:X.
            details[appid]["genre"] = ", ".join(sorted(s.split(":", 1)[1] for s in sources[appid]
                                                       if s.startswith("genre:")))
    LOGGER.info("Loja Steam: %d com detalhes, %d fora da loja, %d falhados",
                len(store_games), len(not_in_store), len(store_failed))

    # 4. Classificação: uma categoria principal por jogo.
    primary: dict[int, str] = {}
    for appid, game in details.items():
        why = non_game_reason(game, config.get("non_game", {}))
        if why:
            rejected[appid] = why
        elif int_val(game.get("ccu")) < args.min_ccu:
            rejected[appid] = "ccu_baixo"
        else:
            cid, _, _ = classify(game, categories, args.top_k_tags, config.get("broad_tags"),
                                 config.get("fallback_order"))
            if cid is None:
                rejected[appid] = "sem_categoria"
            else:
                primary[appid] = cid

    # 5. Jogadores atuais, com a mesma fonte que a recolha horária vai usar.
    measured = players_client.current_players_many(list(primary))
    players = {}
    for appid, count in measured.items():
        if count is None:
            rejected[appid] = "sem_resposta_steam"
        elif count < args.min_players:
            rejected[appid] = "poucos_jogadores_agora"
        else:
            players[appid] = count
    primary = {a: c for a, c in primary.items() if a in players}
    LOGGER.info("Jogadores atuais medidos para %d jogos (%d pedidos)", len(measured), players_client.calls)

    # 6. TOP N por categoria, validar e gravar.
    chosen = top_by_players(categories, primary, players, args.per_category)
    names = {a: details[a].get("name", "") for a in primary}
    for cid, apps in chosen.items():
        eligible = sum(1 for c in primary.values() if c == cid)
        counts = sorted(players[a] for a in apps)
        LOGGER.info("%-14s %3d de %4d elegíveis; jogadores mín %s, mediana %s", cid, len(apps), eligible,
                    counts[0] if counts else None, counts[len(counts) // 2] if counts else None)
    LOGGER.info("Rejeitados: %s", dict(Counter(rejected.values()).most_common()))

    errors = validate(chosen, names, args.per_category)
    if failures or store_failed:
        errors.append(f"fontes falhadas: {failures}; detalhes da loja falhados: {len(store_failed)}")
    if errors:
        for error in errors:
            LOGGER.error(error)
        LOGGER.error("Seleção inválida: %s não foi alterado", args.output)
        logging.shutdown()
        return 2
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_games(args.output, chosen, names, when)
    LOGGER.info("Lista gravada: %s (%d jogos, %s)", args.output, sum(map(len, chosen.values())), when)
    logging.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
