"""Transforma um snapshot da branch data em tabelas e um relatório legível.

Só usa a biblioteca padrão. Não faz fetch, pedidos às APIs, merge ou push.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCES = ("players", "store", "metadata", "steamspy")
LABELS = {"competitive": "Competitivos", "strategy_sim": "Estratégia e simulação",
          "survival_coop": "Sobrevivência e cooperação", "aaa": "AAA", "indie": "Independentes"}
STATES = {"ok": "OK", "no_data": "Sem dados", "error": "Erro"}
RANK = {"error": 0, "no_data": 1, "ok": 2}
IDENTITY = ["appid", "jogo", "categoria"]
PLAYER = ["jogadores", "estado_jogadores", "recolha_jogadores_utc"]
STORE = ["preco_usd", "preco_original_usd", "desconto_pct", "fim_desconto_utc",
         "gratuito", "avaliacoes_total", "avaliacoes_positivas_pct", "avaliacao_loja",
         "estado_loja", "recolha_loja_utc"]
META = ["estado_metadados", "recolha_metadados_utc", "nome_na_loja", "editora", "produtora",
        "lancamento", "situacao_loja", "tipo_loja_id", "etiquetas_com_peso", "funcionalidades_ids",
        "categorias_funcionalidades_ids", "categorias_comando_ids", "windows", "mac", "linux",
        "steam_deck", "idiomas", "idiomas_audio_completo", "descricao"]
SPY = ["estado_steamspy", "recolha_steamspy_utc", "proprietarios_min_estimados",
       "proprietarios_max_estimados", "ccu_steamspy", "avaliacoes_positivas_steamspy",
       "avaliacoes_negativas_steamspy", "preco_steamspy_centavos_usd",
       "preco_original_steamspy_centavos_usd", "desconto_steamspy_pct"]
DAILY = ["data_utc", *IDENTITY, "horas_esperadas", "horas_jogadores_ok", "horas_jogadores_erro",
         "horas_jogadores_sem_dados", "horas_jogadores_ausentes", "jogadores_media",
         "jogadores_min", "jogadores_pico", "hora_pico_utc", "horas_loja_ok", "preco_min_usd",
         "preco_max_usd", "desconto_max_pct"]
QUALITY = ["fonte", "recolha_utc", "fim_recolha_utc", "hora_utc", "run_id", "jogos",
           "ok", "sem_dados", "erros", "ficheiro", "linha"]
GAPS = ["fonte", "periodo_utc", "jogos_esperados", "ok", "sem_dados", "erros", "ausentes"]
FAILURES = ["fonte", "recolha_utc", *IDENTITY, "estado", "http_status", "motivo", "run_id"]


def timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Data sem fuso horário: {value}")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def content_hash(path: Path) -> str:
    """Hash de texto independente de CRLF (Windows) / LF (GitHub Actions)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def input_files(raw: Path | None, ref: str, repo: Path | None = None):
    """Abre apenas raw/<fonte>/*.jsonl; nunca extrai ficheiros do Git para disco."""
    if raw is not None:
        for source in SOURCES:
            for path in sorted((raw / source).glob("*.jsonl")):
                with path.open("rb") as stream:
                    yield f"raw/{source}/{path.name}", stream
        return
    with tempfile.TemporaryFile() as archive:
        # git archive também aplica core.autocrlf: desativar para ler os bytes
        # originais dos blobs e obter hashes iguais no Windows e no Linux.
        subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(repo or Path.cwd()),
                        "archive", ref, "raw"], stdout=archive, check=True)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tree:
            for member in tree:
                parts = member.name.split("/")
                if (member.isfile() and len(parts) == 3 and parts[0] == "raw"
                        and parts[1] in SOURCES and parts[2].endswith(".jsonl")):
                    with tree.extractfile(member) as stream:
                        yield member.name, stream


def read_data(raw: Path | None, ref: str, games: list[dict], repo: Path | None = None):
    tables = {source: {} for source in SOURCES}
    quality, failures, hashes, dates = [], [], {}, set()
    catalog = {g["appid"]: g for g in games}
    selection_dates = {timestamp(g["selection_date_utc"]) for g in games}
    if len(selection_dates) != 1:
        raise ValueError("A lista de jogos tem várias datas de seleção")
    for filename, stream in input_files(raw, ref, repo):
        source = filename.split("/")[1]
        digest = hashlib.sha256()
        for line_number, line in enumerate(stream, 1):
            digest.update(line)
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                collected = timestamp(record["collected_at_utc"])
                hour = timestamp(record["hour_utc"])
                if hour != collected[:13] + ":00:00Z":
                    raise ValueError("hour_utc não corresponde à recolha")
                if timestamp(record["games_list_date"]) not in selection_dates:
                    raise ValueError("A seleção dos dados não corresponde a config/games.csv")
                items = record["games"]
                if not isinstance(items, list) or not items:
                    raise ValueError("Recolha sem lista de jogos")
                counts, seen = Counter(), set()
                slot = hour if source in ("players", "store") else collected[:10]
                for item in items:
                    appid, status = int(item["appid"]), item["status"]
                    if appid not in catalog or appid in seen or status not in RANK:
                        raise ValueError(f"AppID desconhecido/repetido ou estado inválido: {appid}, {status}")
                    seen.add(appid)
                    counts[status] += 1
                    if status != "ok":
                        failures.append({"fonte": source, "recolha_utc": collected, **identity(catalog[appid]),
                            "estado": STATES[status], "http_status": item.get("http_status"),
                            "motivo": item.get("error"), "run_id": str(record.get("run_id", ""))})
                    if source == "players" and status == "ok":
                        if type(item.get("players")) is not int or item["players"] < 0:
                            raise ValueError(f"Número de jogadores inválido: {appid}")
                    entry = {**item, "collected_at_utc": collected}
                    key = slot, appid
                    old = tables[source].get(key)
                    # Uma tentativa falhada não apaga uma resposta válida do mesmo período.
                    score = RANK[status], collected
                    if old is None or score >= (RANK[old["status"]], old["collected_at_utc"]):
                        tables[source][key] = entry
                quality.append(dict(zip(QUALITY, [source, collected, timestamp(record["finished_at_utc"]),
                    hour, str(record.get("run_id", "")), len(items), counts["ok"], counts["no_data"],
                    counts["error"], filename, line_number])))
                dates.add(collected[:10])
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                raise ValueError(f"{filename}:{line_number}: {exc}") from exc
        hashes[filename] = digest.hexdigest()
    if not quality:
        raise ValueError("Não foram encontradas recolhas JSONL")
    return tables, quality, failures, hashes, sorted(dates)


def identity(game: dict) -> dict:
    return {"appid": game["appid"], "jogo": game["name"],
            "categoria": LABELS.get(game["category"], game["category"])}


def state(entry: dict | None) -> str:
    return STATES[entry["status"]] if entry else "Ausente"


def money(value):
    return "" if value is None or value == "" else f"{int(value) / 100:.2f}"


def yesno(value):
    return "" if value is None else "Sim" if value else "Não"


def player_values(entry: dict | None) -> dict:
    entry = entry or {}
    return dict(zip(PLAYER, [entry.get("players") if entry.get("status") == "ok" else None,
                            state(entry or None), entry.get("collected_at_utc")]))


def store_values(entry: dict | None) -> dict:
    entry = entry or {}
    valid = entry if entry.get("status") == "ok" else {}
    price = 0 if valid.get("is_free") is True else valid.get("price_cents")
    original = 0 if valid.get("is_free") is True else valid.get("original_price_cents")
    return dict(zip(STORE, [money(price), money(original), valid.get("discount_pct"),
        valid.get("discount_end_utc"), yesno(valid.get("is_free")), valid.get("review_count"),
        valid.get("review_pct_positive"), valid.get("review_score_label"), state(entry or None),
        entry.get("collected_at_utc")]))


def metadata_values(entry: dict | None) -> dict:
    entry = entry or {}
    valid = entry if entry.get("status") == "ok" else {}
    tags = valid.get("tags") or {}
    tag_text = "; ".join(f"{tag} ({weight})" for tag, weight in
                         sorted(tags.items(), key=lambda pair: (-pair[1], pair[0]))) if isinstance(tags, dict) else ""
    sequence = lambda field: "; ".join(str(v) for v in valid.get(field) or [])
    deck = {0: "Desconhecido", 1: "Não suportado", 2: "Jogável", 3: "Verificado"}
    return dict(zip(META, [state(entry or None), entry.get("collected_at_utc"), valid.get("name"),
        valid.get("publisher"), valid.get("developer"), valid.get("release_date_utc"),
        valid.get("store_status"), valid.get("store_type"), tag_text, sequence("features"),
        sequence("feature_categories"), sequence("controller_categories"),
        yesno(valid.get("windows")), yesno(valid.get("mac")), yesno(valid.get("linux")),
        deck.get(valid.get("steam_deck_compat"), ""), valid.get("n_languages"),
        valid.get("n_languages_full_audio"), " ".join((valid.get("short_description") or "").split())]))


def spy_values(entry: dict | None) -> dict:
    entry = entry or {}
    valid = entry if entry.get("status") == "ok" else {}
    owners = valid.get("owners")
    limits = [int(part.replace(",", "").strip()) for part in owners.split("..")] if owners else [None, None]
    if len(limits) != 2:
        raise ValueError(f"Intervalo SteamSpy inválido: {owners}")
    return dict(zip(SPY, [state(entry or None), entry.get("collected_at_utc"), *limits,
        valid.get("ccu"), valid.get("positive"), valid.get("negative"), valid.get("price"),
        valid.get("initialprice"), valid.get("discount")]))


def write_csv(path: Path, columns: list[str], rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    # BOM permite abrir nomes portugueses corretamente no Excel; CSV usa vírgula e ponto decimal.
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        count = 0
        for row in rows:
            writer.writerow(row)
            count += 1
        return count


def latest_by_game(table: dict) -> dict:
    latest = {}
    for (_, appid), entry in sorted(table.items()):
        latest[appid] = entry
    return latest


def hours_between(first: str, last: str) -> list[str]:
    now = datetime.fromisoformat(first.replace("Z", "+00:00"))
    end = datetime.fromisoformat(last.replace("Z", "+00:00"))
    hours = []
    while now <= end:
        hours.append(iso(now))
        now += timedelta(hours=1)
    return hours


def render(root: Path, games: list[dict], tables: dict, quality: list[dict], failures: list[dict], dates: list[str]):
    rows_written = {}
    slots = sorted({slot for source in ("players", "store") for slot, _ in tables[source]})
    hours = hours_between(slots[0], slots[-1]) if slots else []
    days = [d[:10] for d in hours_between(dates[0] + "T00:00:00Z", dates[-1] + "T00:00:00Z")
            if d[11:13] == "00"]
    daily, gaps = [], []
    player_history = defaultdict(list)
    by_day = defaultdict(list)
    for hour in hours:
        by_day[hour[:10]].append(hour)
    for day in days:
        day_hours = by_day[day]
        hourly_rows = []
        for game in games:
            appid = game["appid"]
            players, prices, discounts, player_counts, store_counts = [], [], [], Counter(), Counter()
            for hour in day_hours:
                player = tables["players"].get((hour, appid))
                store = tables["store"].get((hour, appid))
                player_counts[state(player)] += 1
                store_counts[state(store)] += 1
                if player and player["status"] == "ok":
                    players.append((player["players"], hour))
                    player_history[appid].append(player["players"])
                store_row = store_values(store)
                if store_row["preco_usd"] != "":
                    prices.append(float(store_row["preco_usd"]))
                if store_row["desconto_pct"] is not None:
                    discounts.append(store_row["desconto_pct"])
                hourly_rows.append({"hora_utc": hour, **identity(game), **player_values(player), **store_row})
            peak = max(players, key=lambda pair: pair[0]) if players else (None, None)
            daily.append(dict(zip(DAILY, [day, *identity(game).values(), len(day_hours),
                player_counts["OK"], player_counts["Erro"], player_counts["Sem dados"], player_counts["Ausente"],
                round(sum(p[0] for p in players) / len(players), 2) if players else None,
                min((p[0] for p in players), default=None), *peak, store_counts["OK"],
                f"{min(prices):.2f}" if prices else None, f"{max(prices):.2f}" if prices else None,
                max(discounts, default=None)])))
        if day_hours:
            filename = f"horario/{day}.csv"
            rows_written[filename] = write_csv(root / filename, ["hora_utc", *IDENTITY, *PLAYER, *STORE],
                                               sorted(hourly_rows, key=lambda r: (r["hora_utc"], r["appid"])))
    for source in SOURCES:
        for period in hours if source in ("players", "store") else days:
            counts = Counter(state(tables[source].get((period, g["appid"]))) for g in games)
            gaps.append(dict(zip(GAPS, [source, period, len(games), counts["OK"], counts["Sem dados"],
                                        counts["Erro"], counts["Ausente"]])))
    latest = {source: latest_by_game(tables[source]) for source in SOURCES}
    overview = []
    stats_columns = ["horas_jogadores_ok", "horas_esperadas", "jogadores_media", "jogadores_min", "jogadores_pico"]
    for game in games:
        appid = game["appid"]
        history = player_history[appid]
        overview.append({**identity(game), **player_values(latest["players"].get(appid)),
            **store_values(latest["store"].get(appid)), **dict(zip(stats_columns, [len(history), len(hours),
            round(sum(history) / len(history), 2) if history else None,
            min(history, default=None), max(history, default=None)]))})
    rows_written["jogos.csv"] = write_csv(root / "jogos.csv", [*IDENTITY, *PLAYER, *STORE, *stats_columns], overview)
    rows_written["diario.csv"] = write_csv(root / "diario.csv", DAILY, daily)
    for source, filename, columns, formatter in [("metadata", "metadados_diarios.csv", META, metadata_values),
                                                ("steamspy", "steamspy_diario.csv", SPY, spy_values)]:
        rows_written[filename] = write_csv(root / filename, ["data_utc", *IDENTITY, *columns],
            ({"data_utc": day, **identity(game), **formatter(tables[source].get((day, game["appid"])))}
             for day in days for game in games))
    rows_written["recolhas.csv"] = write_csv(root / "recolhas.csv", QUALITY,
        sorted(quality, key=lambda r: (r["recolha_utc"], r["fonte"], r["ficheiro"], r["linha"])))
    rows_written["cobertura.csv"] = write_csv(root / "cobertura.csv", GAPS, gaps)
    rows_written["falhas.csv"] = write_csv(root / "falhas.csv", FAILURES,
        sorted(failures, key=lambda r: (r["recolha_utc"], r["fonte"], r["appid"])))
    report = ["# Revisão dos dados Steam", "", "Dados organizados automaticamente a partir da branch `data`.", "",
              f"**Amostra:** {len(games)} jogos. **Período observado:** {dates[0]} a {dates[-1]} (UTC).", "",
              "## Por onde começar", "",
              "- [Jogos: última observação de cada fonte e estatísticas do período](jogos.csv)",
              "- [Resumo diário por jogo](diario.csv)", "- [Histórico por hora e por dia](horario/)",
              "- [Fichas dos jogos por dia](metadados_diarios.csv)",
              "- [Estimativas SteamSpy por dia](steamspy_diario.csv)",
              "- [Cobertura: erros, respostas sem dados e períodos ausentes](cobertura.csv)",
              "- [Todas as tentativas de recolha, incluindo repetições](recolhas.csv)",
              "- [Falhas por jogo, com o motivo registado pelo coletor](falhas.csv)",
              "- [Dicionário das colunas e regras](../docs/review.md)", "",
              "Os CSV têm cabeçalhos em português, texto UTF-8, vírgula como separador e ponto decimal. "
              "No Excel, usar **Dados → De Texto/CSV**, escolhendo UTF-8 e vírgula se necessário.", "",
              "## Estado das fontes", "", "| Fonte | Última tentativa (UTC) | OK | Sem dados | Erros | Ausentes |",
              "|---|---|---:|---:|---:|---:|"]
    for source in SOURCES:
        source_gaps = [g for g in gaps if g["fonte"] == source]
        totals = {key: sum(g[key] for g in source_gaps) for key in ("ok", "sem_dados", "erros", "ausentes")}
        collected = max((q["recolha_utc"] for q in quality if q["fonte"] == source), default="Sem recolhas")
        report.append(f"| {source} | {collected} | {totals['ok']} | {totals['sem_dados']} | {totals['erros']} | {totals['ausentes']} |")
    report += ["", "Contagens após escolher uma observação por jogo e hora/dia. `recolhas.csv` conserva todas as tentativas.",
        "O intervalo horário vai da primeira à última hora observada nas fontes horárias; os dias das extremidades podem ser parciais.",
        "As fontes diárias são verificadas em todos os dias do período observado.", "",
        "**Datas de recolha não são a data de hoje:** este relatório mostra o último snapshot disponível. "
        "A atualização dos CSV não faz novas recolhas nem preenche lacunas.", ""]
    missing = [g for g in gaps if g["ausentes"]]
    if missing:
        report += ["## Lacunas de cobertura", "", "| Fonte | Período UTC | Jogos sem registo |",
                   "|---|---|---:|"]
        report += [f"| {g['fonte']} | {g['periodo_utc']} | {g['ausentes']} |" for g in missing[:20]]
        if len(missing) > 20:
            report += ["", f"Mais {len(missing) - 20} períodos com lacunas em `cobertura.csv`."]
        report.append("")
    if slots:
        final_hour = slots[-1]
        ranking = [(tables["players"].get((final_hour, g["appid"])), g) for g in games]
        ranking = sorted(((p, g) for p, g in ranking if p and p["status"] == "ok"),
                         key=lambda pair: (-pair[0]["players"], pair[1]["appid"]))
        report += [f"## Mais jogadores na última hora observada ({final_hour})", "",
                   "| Jogo | Categoria | Jogadores |", "|---|---|---:|"]
        for entry, game in ranking[:15]:
            name = game["name"].replace("|", "\\|").replace("\n", " ")
            report.append(f"| {name} | {identity(game)['categoria']} | {entry['players']:,} |")
        if not ranking:
            report += ["", "Não há respostas válidas de jogadores nesta hora."]
    report += ["", "## Como interpretar", "",
        "- Um campo vazio significa desconhecido; zero é um valor observado. Jogos gratuitos válidos têm preço 0.00 USD.",
        "- `Ausente`: não houve registo; `Sem dados`: a API respondeu sem dados; `Erro`: a tentativa falhou.",
        "- As médias e picos usam apenas respostas válidas, sem interpolação. Jogadores são simultâneos, não utilizadores únicos.",
        "- Preços da loja usam o contexto US do coletor (USD); SteamSpy é uma fonte separada de estimativas.",
        "- A última observação de cada fonte pode ter uma data diferente: confirmar as colunas `recolha_*_utc`.", ""]
    (root / "README.md").write_text("\n".join(report), encoding="utf-8")
    return rows_written


def build(games_path: Path, out: Path, raw: Path | None = None, ref: str = "origin/data",
          repo: Path | None = None) -> dict:
    with games_path.open(encoding="utf-8-sig", newline="") as stream:
        games = list(csv.DictReader(stream))
    if not games:
        raise ValueError("Lista de jogos vazia")
    for game in games:
        game["appid"] = int(game["appid"])
        if game["appid"] <= 0 or not game["name"].strip() or not game["category"].strip():
            raise ValueError("Lista de jogos inválida")
    games.sort(key=lambda g: g["appid"])
    if len({g["appid"] for g in games}) != len(games):
        raise ValueError("AppIDs repetidos na lista de jogos")
    source_commit = None if raw else subprocess.check_output(
        ["git", "-C", str(repo or Path.cwd()), "rev-parse", "--verify", f"{ref}^{{commit}}"], text=True).strip()
    # Resolve uma única vez: mesmo que outra execução faça fetch, o snapshot é consistente.
    tables, quality, failures, hashes, dates = read_data(raw, source_commit or ref, games, repo)
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".review-build-", dir=out.parent) as tmp:
        stage = Path(tmp)
        rows = render(stage, games, tables, quality, failures, dates)
        manifest = {"schema_version": 1, "source_commit": source_commit,
                    "games_sha256": content_hash(games_path),
                    "builder_sha256": content_hash(Path(__file__)),
                    "input_sha256": hashes, "period_start": dates[0], "period_end": dates[-1],
                    "games": len(games), "rows": rows}
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        generated = [path for path in stage.rglob("*") if path.is_file()]
        expected = {path.relative_to(stage) for path in generated}
        # Publica só depois de validar e gerar tudo. Nunca remove ficheiros brutos.
        for path in generated:
            target = out / path.relative_to(stage)
            target.parent.mkdir(parents=True, exist_ok=True)
            contents = path.read_bytes()
            if target.is_file() and target.read_bytes() == contents:
                continue
            # Mover diretamente da TemporaryDirectory preservaria o ACL privado
            # no Windows. O ficheiro novo deve herdar as permissões da pasta final.
            sibling = target.parent / f".review-{uuid.uuid4().hex}.tmp"
            try:
                with sibling.open("xb") as stream:
                    stream.write(contents)
                os.replace(sibling, target)
            finally:
                sibling.unlink(missing_ok=True)
        for old in (out / "horario").glob("*.csv"):
            if old.relative_to(out) not in expected:
                old.unlink()
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=Path, default=Path("config/games.csv"))
    parser.add_argument("--out", type=Path, default=Path("review"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--ref", default="origin/data", help="Snapshot Git já obtido por git fetch")
    source.add_argument("--raw", type=Path, help="Pasta raw de um checkout da branch data")
    parser.add_argument("--repo", type=Path, help="Repositório Git de origem, usado com --ref")
    args = parser.parse_args(argv)
    if args.raw and args.repo:
        parser.error("--repo só pode ser usado com --ref")
    try:
        result = build(args.games, args.out, args.raw, args.ref, args.repo)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        parser.exit(1, f"Não foi possível gerar a review: {exc}\n")
    print(f"Review: {result['games']} jogos, {result['period_start']} a {result['period_end']}; "
          f"{sum(result['rows'].values())} linhas CSV em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
