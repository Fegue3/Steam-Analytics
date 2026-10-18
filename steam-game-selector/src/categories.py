import pandas as pd
from pathlib import Path

df = pd.read_csv("data/output/games_500.csv")

output = Path("data/output/categories")
output.mkdir(parents=True, exist_ok=True)

for category, games in df.groupby("category"):

    games = games.sort_values("rank_in_category")

    games.to_csv(
        output / f"{category}.csv",
        index=False
    )

    print(f"{category}: {len(games)} jogos")