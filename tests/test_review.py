"""Casos de qualidade e rastreabilidade da transformação, sem rede."""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.build_review import build, main

SELECTION = "2026-10-18T18:52:31+00:00"


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.out = self.root / "review"
        self.games = self.root / "games.csv"
        with self.games.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["appid", "name", "category", "selection_date_utc"])
            writer.writerow([1, "Jogo, ação | teste", "indie", SELECTION])
            writer.writerow([2, "Outro jogo", "aaa", SELECTION])

    def record(self, source, time, items, **extra):
        day = time[:10]
        path = self.raw / source / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"source": source, "collected_at_utc": time, "finished_at_utc": time,
                  "hour_utc": time[:13] + ":00:00Z", "games_list_date": SELECTION,
                  "run_id": "123", "games": items, **extra}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def generate(self):
        return build(self.games, self.out, self.raw)

    def rows(self, filename):
        with (self.out / filename).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def snapshot(self):
        return {str(p.relative_to(self.out)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.out.rglob("*") if p.is_file()}

    def test_zero_missing_failure_and_partial_day_are_distinct(self):
        self.record("players", "2026-10-28T10:17:00Z", [{"appid": 1, "status": "ok", "players": 0},
            {"appid": 2, "status": "no_data"}])
        self.record("players", "2026-10-28T12:17:00Z", [{"appid": 1, "status": "ok", "players": 20},
            {"appid": 2, "status": "error", "error": "HTTP 503", "http_status": 503}])
        self.generate()
        daily = self.rows("diario.csv")
        self.assertEqual(daily[0]["horas_esperadas"], "3")
        self.assertEqual(daily[0]["horas_jogadores_ausentes"], "1")
        self.assertEqual(daily[0]["jogadores_media"], "10.0")
        self.assertEqual(daily[0]["jogadores_min"], "0")
        self.assertEqual(daily[0]["jogadores_pico"], "20")
        self.assertEqual(daily[1]["jogadores_media"], "")
        hourly = self.rows("horario/2026-10-28.csv")
        self.assertEqual([r["estado_jogadores"] for r in hourly],
                         ["OK", "Sem dados", "Ausente", "Ausente", "OK", "Erro"])
        self.assertEqual(hourly[0]["jogadores"], "0")
        self.assertEqual(hourly[1]["jogadores"], "")
        self.assertEqual(self.rows("falhas.csv")[-1]["motivo"], "HTTP 503")
        self.assertEqual(self.rows("falhas.csv")[-1]["http_status"], "503")

    def test_retry_preserves_success_but_latest_success_wins(self):
        self.record("players", "2026-10-28T10:10:00Z", [{"appid": 1, "status": "ok", "players": 4}])
        self.record("players", "2026-10-28T10:20:00Z", [{"appid": 1, "status": "ok", "players": 8}])
        self.record("players", "2026-10-28T10:30:00Z", [{"appid": 1, "status": "error", "error": "timeout"}])
        self.record("players", "2026-10-28T11:10:00Z", [{"appid": 1, "status": "no_data"}])
        self.generate()
        self.assertEqual(self.rows("horario/2026-10-28.csv")[0]["jogadores"], "8")
        self.assertEqual(self.rows("diario.csv")[0]["horas_jogadores_ok"], "1")
        self.assertEqual(len(self.rows("recolhas.csv")), 4)
        # Não transportar a observação válida da hora anterior para a última hora.
        self.assertEqual(self.rows("jogos.csv")[0]["estado_jogadores"], "Sem dados")
        self.assertEqual(self.rows("jogos.csv")[0]["jogadores"], "")

    def test_prices_free_unknown_and_separate_source_times(self):
        self.record("players", "2026-10-28T10:17:00Z", [{"appid": 1, "status": "ok", "players": 3}])
        self.record("store", "2026-10-28T11:17:00Z", [
            {"appid": 1, "status": "ok", "is_free": True, "price_cents": None, "original_price_cents": None},
            {"appid": 2, "status": "ok", "is_free": False, "price_cents": None}])
        self.record("store", "2026-10-28T12:17:00Z", [
            {"appid": 1, "status": "ok", "price_cents": 1499, "original_price_cents": 2999, "discount_pct": 50}])
        self.generate()
        hourly = self.rows("horario/2026-10-28.csv")
        self.assertEqual(hourly[2]["preco_usd"], "0.00")
        self.assertEqual(hourly[3]["preco_usd"], "")
        self.assertEqual(hourly[4]["preco_usd"], "14.99")
        self.assertEqual(hourly[2]["jogadores"], "")
        self.assertEqual(self.rows("diario.csv")[0]["preco_min_usd"], "0.00")
        overview = self.rows("jogos.csv")[0]
        self.assertEqual(overview["recolha_jogadores_utc"], "2026-10-28T10:17:00Z")
        self.assertEqual(overview["recolha_loja_utc"], "2026-10-28T12:17:00Z")

    def test_daily_metadata_steamspy_and_whole_missing_day(self):
        self.record("metadata", "2026-10-28T05:40:00Z", [{"appid": 1, "status": "ok",
            "tags": {"Action": 5, "Indie": 10}, "features": [1, 9], "windows": False, "steam_deck_compat": 3,
            "short_description": "Texto original.  \nOutra linha.  "}])
        self.record("metadata", "2026-10-30T05:40:00Z", [{"appid": 1, "status": "error"}])
        self.record("steamspy", "2026-10-28T05:45:00Z", [{"appid": 1, "status": "ok",
            "owners": "1,000,000 .. 2,000,000", "ccu": 120, "price": "1999"}])
        self.generate()
        rows = self.rows("metadados_diarios.csv")
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["etiquetas_com_peso"], "Indie (10); Action (5)")
        self.assertEqual(rows[0]["funcionalidades_ids"], "1; 9")
        self.assertEqual(rows[0]["windows"], "Não")
        self.assertEqual(rows[0]["steam_deck"], "Verificado")
        self.assertEqual(rows[0]["descricao"], "Texto original. Outra linha.")
        self.assertEqual(rows[2]["estado_metadados"], "Ausente")
        spy = self.rows("steamspy_diario.csv")[0]
        self.assertEqual(spy["proprietarios_max_estimados"], "2000000")
        self.assertEqual(spy["preco_steamspy_centavos_usd"], "1999")
        gaps = [r for r in self.rows("cobertura.csv") if r["periodo_utc"] == "2026-10-29"]
        self.assertEqual(len(gaps), 2)
        self.assertTrue(all(r["ausentes"] == "2" for r in gaps))

    def test_failure_does_not_replace_existing_results(self):
        path = self.record("players", "2026-10-28T10:17:00Z", [{"appid": 1, "status": "ok", "players": 7}])
        self.generate()
        before = self.snapshot()
        with path.open("a", encoding="utf-8") as stream:
            stream.write('{invalid JSON}\n')
        with self.assertRaisesRegex(ValueError, r"raw/players/2026-10-28.jsonl:2"):
            self.generate()
        self.assertEqual(before, self.snapshot())

    def test_invalid_game_status_or_players_fail_with_location(self):
        for item in [{"appid": 999, "status": "ok", "players": 3},
                     {"appid": 1, "status": "unexpected"},
                     {"appid": 1, "status": "ok", "players": None},
                     {"appid": 1, "status": "ok", "players": -1}]:
            with self.subTest(item=item):
                path = self.record("players", "2026-10-28T10:17:00Z", [item])
                with self.assertRaisesRegex(ValueError, "raw/players/"):
                    self.generate()
                path.unlink()
        self.assertFalse(self.out.exists())

    def test_duplicate_appid_and_mismatched_selection_fail(self):
        item = {"appid": 1, "status": "ok", "players": 3}
        path = self.record("players", "2026-10-28T10:17:00Z", [item, item])
        with self.assertRaisesRegex(ValueError, "repetido"):
            self.generate()
        path.unlink()
        self.record("players", "2026-10-28T10:17:00Z", [item], games_list_date="2026-10-19T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "seleção"):
            self.generate()

    def test_deterministic_utf8_and_stale_partition_removal(self):
        first = self.record("players", "2026-10-28T10:17:00Z", [{"appid": 1, "status": "ok", "players": 3}])
        self.record("players", "2026-10-29T10:17:00Z", [{"appid": 1, "status": "ok", "players": 4}])
        self.generate()
        before = self.snapshot()
        self.generate()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.rows("jogos.csv")[0]["jogo"], "Jogo, ação | teste")
        self.assertTrue((self.out / "jogos.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        first.unlink()
        self.generate()
        self.assertFalse((self.out / "horario/2026-10-28.csv").exists())

    def test_git_snapshot_has_same_tables_and_tracks_exact_commit(self):
        self.record("players", "2026-10-28T10:17:00Z", [{"appid": 1, "status": "ok", "players": 3}])
        self.generate()
        before = self.snapshot()
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()
        git("init", "--quiet")
        git("add", "raw")
        git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture")
        # Código e dados podem estar em checkouts separados, como no Action.
        script = Path(__file__).resolve().parents[1] / "src/build_review.py"
        subprocess.run([sys.executable, str(script), "--games", str(self.games), "--out", str(self.out),
                        "--repo", str(self.root), "--ref", "HEAD"], check=True, capture_output=True)
        after = self.snapshot()
        self.assertEqual({k: v for k, v in before.items() if k != "manifest.json"},
                         {k: v for k, v in after.items() if k != "manifest.json"})
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(manifest["source_commit"], git("rev-parse", "HEAD"))

    def test_windows_and_linux_line_endings_have_same_manifest_hash(self):
        self.record("players", "2026-10-28T10:17:00Z", [{"appid": 1, "status": "ok", "players": 3}])
        self.generate()
        before = self.snapshot()
        self.games.write_bytes(self.games.read_bytes().replace(b"\r\n", b"\n"))
        self.generate()
        self.assertEqual(before, self.snapshot())

    def test_empty_input_and_cli_failure_return_nonzero(self):
        with self.assertRaisesRegex(ValueError, "Não foram encontradas"):
            self.generate()
        with self.assertRaises(SystemExit) as result:
            main(["--games", str(self.games), "--out", str(self.out), "--raw", str(self.raw)])
        self.assertEqual(result.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
