"""Regras do dataset final e do load_dataset(), sem rede."""
import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.build_dataset import build_dataset, main, top_tags
from src.data import load_dataset

HOURLY = ["hora_utc", "appid", "jogo", "categoria", "jogadores", "estado_jogadores",
          "recolha_jogadores_utc", "preco_usd", "preco_original_usd", "desconto_pct",
          "fim_desconto_utc", "gratuito", "avaliacoes_total", "avaliacoes_positivas_pct",
          "avaliacao_loja", "estado_loja", "recolha_loja_utc"]
META = ["data_utc", "appid", "estado_metadados", "editora", "produtora", "lancamento",
        "etiquetas_com_peso", "windows", "mac", "linux", "steam_deck", "idiomas"]
SPY = ["data_utc", "appid", "estado_steamspy", "proprietarios_min_estimados",
       "proprietarios_max_estimados"]
# Jogo 1: lacuna de 1 hora (interpolada). Jogo 2: lacuna de 3 horas (fica vazia).
PLAYERS = {1: [100, 200, None, 400, 500, 600], 2: [10, None, None, None, 50, 60]}


def write(path: Path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        writer.writerows(rows)


class DatasetTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.review = self.root / "review"
        rows = []
        for appid, values in PLAYERS.items():
            for hour, players in enumerate(values):
                missing = players is None
                rows.append({
                    "hora_utc": f"2026-10-31T{hour + 20:02d}:00:00Z" if hour < 4
                    else f"2026-11-01T{hour - 4:02d}:00:00Z",
                    "appid": appid, "jogo": f"Jogo {appid}",
                    "categoria": "Independentes" if appid == 1 else "AAA",
                    "jogadores": "" if missing else players,
                    "estado_jogadores": "Sem dados" if missing else "OK",
                    "preco_usd": "4.99", "preco_original_usd": "9.99" if appid == 1 else "4.99",
                    "desconto_pct": 50 if appid == 1 else 0, "gratuito": "Não",
                    "avaliacoes_total": 1000 + hour * 3, "avaliacoes_positivas_pct": 90,
                    "avaliacao_loja": "Very Positive", "estado_loja": "OK",
                })
        for day in ("2026-10-31", "2026-11-01"):
            write(self.review / "horario" / f"{day}.csv", HOURLY,
                  [r for r in rows if r["hora_utc"].startswith(day)])
        write(self.review / "metadados_diarios.csv", META, [
            {"data_utc": "2026-11-01", "appid": 1, "estado_metadados": "OK", "editora": "E1",
             "produtora": "P1", "lancamento": "2020-10-31",
             "etiquetas_com_peso": "Indie (900); Roguelike (500); Action (20); Pixel (3)",
             "windows": "Sim", "mac": "Sim", "linux": "Não", "steam_deck": "Verificado",
             "idiomas": 5},
            {"data_utc": "2026-11-01", "appid": 2, "estado_metadados": "OK", "editora": "E2",
             "produtora": "P2", "lancamento": "", "etiquetas_com_peso": "",
             "windows": "Sim", "mac": "Não", "linux": "Não", "steam_deck": "Desconhecido",
             "idiomas": 1},
        ])
        write(self.review / "steamspy_diario.csv", SPY, [
            {"data_utc": "2026-11-01", "appid": 1, "estado_steamspy": "OK",
             "proprietarios_min_estimados": 100000, "proprietarios_max_estimados": 200000},
            {"data_utc": "2026-11-01", "appid": 2, "estado_steamspy": "Sem dados",
             "proprietarios_min_estimados": 0, "proprietarios_max_estimados": 0},
        ])

    def test_grid_and_time_features(self):
        df = build_dataset(self.review)
        self.assertEqual(len(df), 12)
        first = df.iloc[0]
        self.assertEqual(first["dia_semana"], "Sábado")  # 31/10/2026
        self.assertTrue(first["fim_de_semana"])
        self.assertEqual(first["hora_dia_utc"], 20)

    def test_interpolates_only_short_gaps(self):
        df = build_dataset(self.review).set_index(["appid", "hora_utc"])
        self.assertEqual(df.loc[(1, "2026-10-31T22:00:00Z"), "jogadores_tratado"], 300)
        self.assertTrue(df.loc[(1, "2026-10-31T22:00:00Z"), "jogadores_interpolado"])
        long_gap = df.loc[2, "jogadores_tratado"]
        self.assertEqual(long_gap.isna().sum(), 3)
        self.assertFalse(df.loc[2, "jogadores_interpolado"].any())
        self.assertTrue(pd.isna(df.loc[(1, "2026-10-31T22:00:00Z"), "jogadores"]))

    def test_normalised_and_derived_columns(self):
        df = build_dataset(self.review)
        game = df[df["appid"] == 1]
        self.assertAlmostEqual(game["jogadores_rel_media"].mean(), 1.0, places=3)
        self.assertAlmostEqual(game["jogadores_z"].mean(), 0.0, places=3)
        self.assertEqual(game["var_jogadores_1h_pct"].iloc[1], 100.0)
        self.assertEqual(game["novas_avaliacoes_1h"].iloc[1], 3)
        self.assertTrue(game["em_desconto"].all())
        self.assertFalse(df[df["appid"] == 2]["em_desconto"].any())

    def test_game_features(self):
        df = build_dataset(self.review).groupby("appid").first()
        self.assertEqual(df.loc[1, "etiquetas_top"], "Indie; Roguelike; Action")
        self.assertEqual(df.loc[1, "n_plataformas"], 2)
        self.assertAlmostEqual(df.loc[1, "idade_anos"], 6.0, places=1)
        self.assertEqual(df.loc[1, "proprietarios_estimados"], 150000)
        self.assertTrue(pd.isna(df.loc[2, "proprietarios_estimados"]))
        self.assertTrue(pd.isna(df.loc[2, "idade_anos"]))

    def test_top_tags(self):
        self.assertEqual(top_tags("A (3); B b (2)"), "A; B b")
        self.assertTrue(pd.isna(top_tags(float("nan"))))

    def test_load_dataset_types(self):
        out = self.root / "processed" / "steam_dataset.csv"
        main(["--review", str(self.review), "--out", str(out)])
        df = load_dataset(out)
        self.assertEqual(len(df), 12)
        self.assertEqual(str(df["hora_utc"].dt.tz), "UTC")
        self.assertEqual(df["jogadores"].dtype, "Int64")
        self.assertEqual(df["em_desconto"].dtype, "boolean")
        self.assertTrue(df["categoria"].cat.ordered)
        self.assertEqual(df["jogadores"].isna().sum(), 4)

    def test_load_dataset_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_dataset(self.root / "nao_existe.csv")


if __name__ == "__main__":
    unittest.main()
