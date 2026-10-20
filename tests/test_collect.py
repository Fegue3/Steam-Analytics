import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.api import SteamPlayersClient, SteamStoreClient
from src.collect_common import (append_jsonl, collected_this_hour, collection_record, day_path,
                                load_games)
from src.collect_daily import collect


class CollectionApiTest(unittest.TestCase):
    def test_players_zero_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamPlayersClient(Path(tmp), cache_hours=0, max_retries=1)
            response = MagicMock(status_code=200)
            response.json.return_value = {"response": {"result": 1, "player_count": 0}}
            with patch.object(client.session, "get", return_value=response):
                self.assertEqual(client.fetch_players(10), (0, "ok", 200, None))

    def test_players_404_is_no_data_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamPlayersClient(Path(tmp), cache_hours=0)
            response = MagicMock(status_code=404)
            with patch.object(client.session, "get", return_value=response) as request:
                self.assertEqual(client.fetch_players(10), (None, "no_data", 404, None))
            request.assert_called_once()

    def test_players_persistent_503_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamPlayersClient(Path(tmp), cache_hours=0, max_retries=3)
            response = MagicMock(status_code=503)
            with patch.object(client.session, "get", return_value=response), \
                    patch("src.api.time.sleep"):
                result = client.fetch_players(10)
            self.assertEqual(result[1], "error")
            self.assertEqual(result[2], 503)

    def test_store_extracts_batches_and_discount(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamStoreClient(Path(tmp), batch_size=200)
            client._tag_names = {1: "Action"}
            item = {
                "appid": 1, "success": 1, "name": "Game", "type": 0, "is_free": False,
                "tags": [{"tagid": 1, "weight": 10}],
                "best_purchase_option": {
                    "final_price_in_cents": "2799", "original_price_in_cents": "6999",
                    "discount_pct": 60, "active_discounts": [{"discount_end_date": 1792515600}],
                },
                "reviews": {"summary_filtered": {"review_count": 42, "percent_positive": 90,
                                                   "review_score_label": "Very Positive"}},
            }
            payload = {"response": {"store_items": [item]}}
            with patch.object(client.items, "get", return_value=payload) as request:
                found, missing, failed = client.get_games([1, 2], include_reviews=True)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(missing, [2])
            self.assertEqual(failed, [])
            self.assertEqual(found[1]["price"], "2799")
            self.assertEqual(found[1]["initialprice"], "6999")
            self.assertEqual(found[1]["discount_pct"], 60)
            self.assertEqual(found[1]["review_count"], 42)

    def test_store_uses_lots_of_200(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamStoreClient(Path(tmp), batch_size=200)
            client._tag_names = {}
            payload = {"response": {"store_items": []}}
            with patch.object(client.items, "get", return_value=payload) as request:
                _, missing, _ = client.get_games(list(range(1, 502)))
            self.assertEqual(request.call_count, 3)
            self.assertEqual(len(missing), 501)

    def test_store_free_game_and_no_discount(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamStoreClient(Path(tmp), batch_size=200)
            client._tag_names = {}
            item = {"appid": 1, "success": 1, "type": 0, "is_free": True,
                    "best_purchase_option": {"final_price_in_cents": "0"}}
            with patch.object(client.items, "get",
                              return_value={"response": {"store_items": [item]}}):
                found, missing, failed = client.get_games([1], include_reviews=True)
            self.assertEqual((missing, failed), ([], []))
            self.assertEqual(found[1]["price"], "0")
            self.assertEqual(found[1]["initialprice"], "0")
            self.assertEqual(found[1]["discount_pct"], 0)

    def test_store_failed_batch_marks_all_games(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamStoreClient(Path(tmp), batch_size=200)
            with patch.object(client.items, "get", side_effect=RuntimeError("offline")):
                found, missing, failed = client.get_games([1, 2])
            self.assertEqual(found, {})
            self.assertEqual(missing, [])
            self.assertEqual(failed, [1, 2])


class CollectionUtilityTest(unittest.TestCase):
    def test_jsonl_appends_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw" / "players" / "day.jsonl"
            append_jsonl(path, {"run": 1})
            append_jsonl(path, {"run": 2})
            lines = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(lines, [{"run": 1}, {"run": 2}])

    def test_load_games_rejects_duplicate_appids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "games.csv"
            path.write_text("appid,name,category,selection_date_utc\n1,A,x,date\n1,B,y,date\n")
            with self.assertRaises(ValueError):
                load_games(path)

    def test_collection_record_has_complete_counts_and_utc_hour(self):
        started = datetime(2026, 10, 19, 14, 17, 5, tzinfo=timezone.utc)
        record = collection_record(
            "steam_players", "endpoint", "2026-10-18T18:52:31+00:00",
            started, datetime(2026, 10, 19, 14, 18, tzinfo=timezone.utc),
            [{"appid": 1, "status": "ok"}, {"appid": 2, "status": "no_data"},
             {"appid": 3, "status": "error"}])
        self.assertEqual(record["hour_utc"], "2026-10-19T14:00:00Z")
        self.assertEqual((record["n_games"], record["n_ok"], record["n_no_data"],
                          record["n_error"]), (3, 1, 1, 1))
        self.assertEqual(record["games_list_date"], "2026-10-18T18:52:31+00:00")

    def test_daily_sources_are_independent(self):
        games = [{"appid": 1, "selection_date_utc": "2026-10-18T18:52:31+00:00"}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.collect_daily.collect_reviews", side_effect=RuntimeError("reviews")), \
                    patch("src.collect_daily.collect_steamspy",
                          return_value={"n_ok": 1, "n_error": 0}), \
                    patch("src.collect_daily.append_jsonl"):
                reviews, steamspy = collect(games, Path(tmp))
            self.assertEqual(reviews["n_error"], 1)
            self.assertEqual(steamspy["n_ok"], 1)

    def test_daily_skips_sources_already_collected_today(self):
        games = [{"appid": 1, "selection_date_utc": "2026-10-18T18:52:31+00:00"}]
        with tempfile.TemporaryDirectory() as tmp:
            append_jsonl(day_path(Path(tmp), "reviews"), {"n_ok": 1, "n_error": 0})
            append_jsonl(day_path(Path(tmp), "steamspy"), {"n_ok": 0, "n_error": 1})
            with patch("src.collect_daily.collect_reviews") as reviews_call, \
                    patch("src.collect_daily.collect_steamspy",
                          return_value={"n_ok": 1, "n_error": 0}) as steamspy_call:
                reviews, _ = collect(games, Path(tmp))
            reviews_call.assert_not_called()
            steamspy_call.assert_called_once()
            self.assertEqual(reviews["n_ok"], 1)

    def test_daily_force_collects_again(self):
        games = [{"appid": 1, "selection_date_utc": "2026-10-18T18:52:31+00:00"}]
        with tempfile.TemporaryDirectory() as tmp:
            append_jsonl(day_path(Path(tmp), "reviews"), {"n_ok": 1, "n_error": 0})
            ok = {"n_ok": 1, "n_error": 0}
            with patch("src.collect_daily.collect_reviews", return_value=ok) as reviews_call, \
                    patch("src.collect_daily.collect_steamspy", return_value=ok):
                collect(games, Path(tmp), force=True)
            reviews_call.assert_called_once()

    def test_collected_this_hour_only_matches_same_hour_with_data(self):
        now = datetime(2026, 10, 20, 14, 40, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(collected_this_hour(Path(tmp), "players", now))
            path = day_path(Path(tmp), "players", now)
            append_jsonl(path, {"hour_utc": "2026-10-20T13:00:00Z", "n_ok": 500})
            append_jsonl(path, {"hour_utc": "2026-10-20T14:00:00Z", "n_ok": 0})
            self.assertFalse(collected_this_hour(Path(tmp), "players", now))
            append_jsonl(path, {"hour_utc": "2026-10-20T14:00:00Z", "n_ok": 500})
            self.assertTrue(collected_this_hour(Path(tmp), "players", now))


if __name__ == "__main__":
    unittest.main()
