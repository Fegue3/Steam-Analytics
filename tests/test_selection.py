import csv
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.classify import (
    classify, genre_match, is_aaa, is_indie, non_game_reason, parse_owners, top_tags,
)
from src.select_games import add_batch, discovery_tasks, top_by_players, validate
from src.api import SteamPlayersClient, SteamSpyClient, SteamStoreClient

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/categories.json").read_text(encoding="utf-8"))
CATS = CONFIG["categories"]
BROAD = CONFIG["broad_tags"]


def game(name, tags, publisher="Small Studio", genre="Action", price="1999", owners="1,000,000 .. 2,000,000", ccu=500):
    votes = {t: 1000 - 10 * i for i, t in enumerate(tags)}
    return {"name": name, "tags": votes, "publisher": publisher, "genre": genre,
            "price": price, "initialprice": price, "owners": owners, "ccu": ccu}


class ParsingTest(unittest.TestCase):
    def test_owners_range(self):
        self.assertEqual(parse_owners("1,000,000 .. 2,000,000"), (1000000, 2000000))
        self.assertEqual(parse_owners(None), (0, 0))

    def test_top_tags_sorted_by_votes(self):
        g = {"tags": {"B": 5, "A": 50, "C": 1}}
        self.assertEqual(top_tags(g), ["A", "B", "C"])
        self.assertEqual(top_tags({"tags": []}), [])  # SteamSpy devolve [] sem etiquetas


class ClassificationTest(unittest.TestCase):
    def test_fps_alone_is_not_competitive(self):
        g = game("Single FPS", ["FPS", "Singleplayer", "Story Rich"])
        self.assertIsNone(genre_match(g, CATS[0], 5, BROAD))

    def test_competitive_has_priority_over_survival(self):
        # PUBG: Survival é a 1.ª etiqueta, mas Battle Royale também está no top-5.
        g = game("PUBG", ["Survival", "Shooter", "Battle Royale", "Multiplayer", "FPS"])
        self.assertEqual(classify(g, CATS, 5, BROAD)[0], "competitive")

    def test_tag_outside_top_k_is_ignored(self):
        g = game("Tag fraca", ["Action", "Adventure", "RPG", "Story Rich", "Fantasy", "PvP"])
        self.assertIsNone(classify(g, CATS, 5, BROAD)[0])

    def test_broad_tag_needs_top_positions(self):
        g = game("Zuma", ["Match 3", "Puzzle", "Arcade", "2D", "Strategy"], genre="Casual")
        self.assertIsNone(genre_match(g, CATS[1], 5, BROAD))
        g = game("Civ", ["Strategy", "Turn-Based", "4X"])
        self.assertEqual(genre_match(g, CATS[1], 5, BROAD), 0)

    def test_sports_is_not_simulation(self):
        g = game("FC", ["Sports", "Football (Soccer)", "Simulation"], publisher="Electronic Arts")
        self.assertIsNone(genre_match(g, CATS[1], 5, BROAD))
        self.assertEqual(classify(g, CATS, 5, BROAD)[0], "aaa")

    def test_genre_wins_over_production(self):
        # Valheim é indie, mas é classificado pelo género dominante.
        g = game("Valheim", ["Open World Survival Craft", "Survival", "Online Co-Op"], genre="Indie")
        cid, eligible, _ = classify(g, CATS, 5, BROAD)
        self.assertEqual(cid, "survival_coop")
        self.assertIn("indie", eligible)

    def test_aaa_proxy(self):
        aaa = next(c for c in CATS if c["id"] == "aaa")
        self.assertTrue(is_aaa(game("Elden", ["Souls-like"], publisher="BANDAI NAMCO Entertainment"), aaa, 5))
        self.assertFalse(is_aaa(game("Free", ["RPG"], publisher="Ubisoft", price="0"), aaa, 5))
        self.assertFalse(is_aaa(game("Indie pub", ["Indie", "RPG"], publisher="Ubisoft"), aaa, 5))
        self.assertFalse(is_aaa(game("Desconhecida", ["RPG"], publisher="Dream Studios"), aaa, 5))

    def test_feature_fallback(self):
        order = CONFIG["fallback_order"]
        # THE FINALS: sem PvP nas etiquetas, mas declara Online PvP e é um FPS.
        finals = {**game("THE FINALS", ["Destruction", "Free to Play", "FPS", "Multiplayer", "Shooter"],
                         price="0"), "features": [1, 36, 49]}
        self.assertEqual(classify(finals, CATS, 5, BROAD, order)[0], "competitive")
        # GTA V: declara PvP, mas não é shooter -> fica AAA.
        gta = {**game("GTA V", ["Open World", "Action", "Multiplayer", "Crime"], publisher="Rockstar Games"),
               "features": [1, 2, 36, 38, 49]}
        self.assertEqual(classify(gta, CATS, 5, BROAD, order)[0], "aaa")
        # DOOM Eternal: declara PvP e é FPS, mas sem Multiplayer no top 5 -> não é competitivo.
        doom = {**game("DOOM Eternal", ["Gore", "FPS", "Action", "Great Soundtrack", "Fast-Paced"],
                       publisher="Bethesda Softworks"), "features": [1, 2, 36, 49]}
        self.assertEqual(classify(doom, CATS, 5, BROAD, order)[0], "aaa")
        # Warframe: Online Co-op declarado + Co-op no top 10.
        warframe = {**game("Warframe", ["Free to Play", "Looter Shooter", "Action RPG", "Third-Person Shooter",
                                        "Action", "RPG", "Co-op"], publisher="Digital Extremes", price="0"),
                    "features": [1, 2, 9, 38]}
        self.assertEqual(classify(warframe, CATS, 5, BROAD, order)[0], "survival_coop")
        # Declarar Online Co-op sem etiqueta de co-op não chega.
        mmo = {**game("MMO", ["Free to Play", "MMORPG", "Open World"], price="0"), "features": [1, 38]}
        self.assertIsNone(classify(mmo, CATS, 5, BROAD, order)[0])

    def test_desktop_companion_is_not_a_game(self):
        bongo = game("Bongo Cat", ["Desktop Companion", "Free to Play", "Cats"], genre="Casual, Indie")
        self.assertEqual(non_game_reason(bongo, CONFIG["non_game"]), "etiqueta_software")

    def test_indie_excludes_big_publishers(self):
        indie = next(c for c in CATS if c["id"] == "indie")
        self.assertTrue(is_indie(game("Celeste", ["Platformer"], genre="Action, Indie"), indie, 5))
        self.assertFalse(is_indie(game("LiS", ["Story Rich"], genre="Adventure, Indie", publisher="Square Enix"), indie, 5))

    def test_non_games(self):
        rules = CONFIG["non_game"]
        self.assertEqual(non_game_reason(game("Wallpaper Engine", ["Utilities"], genre="Casual, Utilities"), rules),
                         "genero_software")
        self.assertEqual(non_game_reason(game("Example OST Soundtrack", ["Music"]), rules), "nome_nao_jogo")
        self.assertIsNone(non_game_reason(game("Example", ["Action"]), rules))


class SelectionTest(unittest.TestCase):
    def test_add_batch_unions_sources(self):
        reg, src = {}, defaultdict(set)
        add_batch(reg, src, {"1": {"appid": 1, "name": "A", "ccu": 5}}, "tag:FPS")
        add_batch(reg, src, {"1": {"appid": 1, "name": "A", "ccu": 44},
                             "999999": {"appid": 999999, "name": "lixo"}}, "tag:PvP")
        self.assertEqual(src[1], {"tag:FPS", "tag:PvP"})
        self.assertEqual(reg[1]["ccu"], 44)
        self.assertNotIn(999999, reg)

    def test_discovery_tasks_are_unique(self):
        tasks = discovery_tasks(CATS)
        self.assertEqual(len(tasks), len(set(tasks)))
        self.assertIn(("tag", "Indie"), tasks)
        self.assertIn(("genre", "Strategy"), tasks)

    def test_top_by_players(self):
        cats = [{"id": "x"}, {"id": "y"}]
        primary = {1: "x", 2: "x", 3: "x", 4: "y"}
        players = {1: 10, 2: 300, 3: 300, 4: 5}
        top = top_by_players(cats, primary, players, 2)
        self.assertEqual(top, {"x": [2, 3], "y": [4]})  # empate -> AppID mais baixo

    def test_validate(self):
        names = {1: "A", 2: "B", 3: ""}
        self.assertEqual(validate({"x": [1, 2]}, names, 2), [])
        errors = validate({"x": [1], "y": [1, 3]}, names, 2)
        self.assertEqual(len(errors), 3)  # x incompleta, AppID 1 repetido, AppID 3 sem nome


class ClientTest(unittest.TestCase):
    def test_cache_no_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamSpyClient(Path(tmp))
            path = client._cache_path({"request": "tag", "tag": "FPS"})
            path.write_text(json.dumps({"42": {"appid": 42, "name": "Example"}}), encoding="utf-8")
            with patch.object(client.session, "get", side_effect=AssertionError("HTTP not expected")):
                data = client.get(request="tag", tag="FPS")
            self.assertIn("42", data)
            self.assertEqual(client.cache_hits, 1)

    def test_store_items_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SteamStoreClient(Path(tmp), batch_size=2)
            store._tag_names = {9: "Strategy", 1: "Indie"}
            items = {"response": {"store_items": [
                {"appid": 10, "success": 1, "name": "Civ", "type": 0,
                 "tags": [{"tagid": 1, "weight": 50}, {"tagid": 9, "weight": 900}],
                 "basic_info": {"publishers": [{"name": "2K"}, {"name": "Aspyr"}]},
                 "best_purchase_option": {"final_price_in_cents": "1499", "original_price_in_cents": "5999"}},
                {"appid": 0, "success": 15},
            ]}}
            with patch.object(store.items, "get", return_value=items) as get:
                found, missing, failed = store.get_games([10, 11])
            self.assertEqual(get.call_count, 1)
            self.assertEqual((missing, failed), ([11], []))
            civ = found[10]
            self.assertEqual(top_tags(civ), ["Strategy", "Indie"])
            self.assertEqual((civ["publisher"], civ["price"], civ["initialprice"]), ("2K, Aspyr", "1499", "5999"))
            self.assertEqual(civ["store_status"], "a_venda")

    def test_players_404_is_none_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamPlayersClient(Path(tmp), min_interval=0)
            response = MagicMock(status_code=404, headers={})
            with patch.object(client.session, "get", return_value=response) as get:
                self.assertIsNone(client.current_players(123))
            self.assertEqual(get.call_count, 1)


class EndToEndTest(unittest.TestCase):
    def test_offline_selection(self):
        from src import select_games as mod

        def batch(prefix, tags, publisher="Small Studio", genre="Action", n=4):
            return {str(prefix + i): {**game(f"Jogo {prefix + i}", tags, publisher, genre, ccu=1000 - i),
                                      "appid": prefix + i} for i in range(n)}

        catalog = {
            **batch(100, ["PvP", "Shooter"]),
            **batch(200, ["Strategy", "4X"]),
            **batch(300, ["Survival", "Crafting"]),
            **batch(400, ["Open World", "RPG"], publisher="Ubisoft"),
            **batch(500, ["Platformer", "Pixel Graphics"], genre="Action, Indie"),
            "600": {**game("Wallpaper Engine", ["Utilities"], genre="Utilities"), "appid": 600},
            "601": {**game("Morto", ["PvP"], ccu=10), "appid": 601},
        }

        def fake_get(**kw):
            # As listas SteamSpy não trazem etiquetas; só AppID, nome, CCU, proprietários, género.
            return {k: {f: v[f] for f in ("appid", "name", "ccu", "owners", "genre")}
                    for k, v in catalog.items()} if kw.get("tag") == "Action" else {}

        def fake_store(appids):
            found = {}
            for a in appids:
                g = catalog[str(a)]
                found[a] = {"name": g["name"], "tags": g["tags"], "publisher": g["publisher"],
                            "price": g["price"], "initialprice": g["price"], "store_status": "a_venda",
                            "is_free": False, "store_type": 6 if a == 600 else 0}
            return found, [], []

        spy = MagicMock(calls=0, cache_hits=0)
        spy.get.side_effect = fake_get
        store = MagicMock(calls=0, cache_hits=0)
        store.get_games.side_effect = fake_store
        store.most_played.return_value = {}
        live = MagicMock(calls=0)
        live.current_players_many.side_effect = lambda block: {a: None if a == 103 else 10 for a in block}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "games.csv"
            args = ["--per-category", "3", "--pool-min-ccu", "50", "--min-ccu", "100",
                    "--config", str(ROOT / "config/categories.json"),
                    "--exclusions", str(Path(tmp) / "none.csv"), "--output", str(output),
                    "--cache", str(Path(tmp) / "cache"), "--log-file", str(Path(tmp) / "selection.log")]
            with patch.object(mod, "SteamSpyClient", return_value=spy), \
                    patch.object(mod, "SteamStoreClient", return_value=store), \
                    patch.object(mod, "SteamPlayersClient", return_value=live):
                self.assertEqual(mod.main(args), 0)
                with output.open(encoding="utf-8", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(list(rows[0]), ["appid", "name", "category", "selection_date_utc"])
                self.assertEqual(len({r["appid"] for r in rows}), 15)
                by_cat = defaultdict(set)
                for r in rows:
                    by_cat[r["category"]].add(int(r["appid"]))
                # 103 não responde à API de jogadores; 600 é software; 601 tem CCU baixo.
                self.assertEqual(by_cat["competitive"], {100, 101, 102})
                self.assertEqual(by_cat["aaa"], {400, 401, 402})
                self.assertEqual(by_cat["indie"], {500, 501, 502})

                # Com 4 por categoria a competitive fica incompleta: a lista anterior não é tocada.
                before = output.read_text(encoding="utf-8")
                self.assertEqual(mod.main(args[:1] + ["4"] + args[2:]), 2)
                self.assertEqual(output.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
