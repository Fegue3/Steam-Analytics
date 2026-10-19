import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.api import SteamPlayersClient, SteamStoreClient
from src.collect_common import append_jsonl, load_games


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


if __name__ == "__main__":
    unittest.main()
