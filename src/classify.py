"""Regras de classificação: cada jogo recebe no máximo UMA categoria principal.

Categorias de género (competitive, strategy_sim, survival_coop) usam as etiquetas
mais votadas do jogo na loja Steam (GetItems). Ter uma etiqueta não basta: tem de
estar entre as `top_k` mais votadas. Se várias categorias de género coincidirem,
ganha a que tem a etiqueta mais bem posicionada.

Jogos sem etiqueta dominante seguem uma ordem de recurso: AAA (produção), depois
competitivo/cooperativo pelas funcionalidades declaradas na loja (Online PvP / Online
Co-op), e indie. Assim aaa e indie recebem sobretudo jogos fora dos géneros estudados
(ação, RPG, aventura, plataformas, ...). Assim, um survival indie
como Valheim conta como survival_coop e não como indie, e a comparação entre grupos
não mistura o mesmo jogo em duas classes.
"""
from __future__ import annotations

import re

BAD_NAME = re.compile(r"(?:\b(?:demo|playtest|soundtrack|artbook|dedicated server|beta test|benchmark)\b|\bDLC\b)", re.I)


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


def split_list(value: object) -> list[str]:
    return [p.strip() for p in re.split(r"[,;|]", str(value or "")) if p.strip()]


def top_tags(game: dict, k: int | None = None) -> list[str]:
    """Etiquetas ordenadas por votos (desc). O SteamSpy devolve um dict tag -> votos."""
    tags = game.get("tags") or {}
    if isinstance(tags, list):  # jogos sem etiquetas vêm como []
        return []
    ordered = sorted(tags.items(), key=lambda kv: -int_val(kv[1]))
    names = [name for name, _ in ordered]
    return names if k is None else names[:k]


def publisher_matches(game: dict, publishers: list[str]) -> bool:
    found = [normalize(p) for p in split_list(game.get("publisher"))]
    allow = [normalize(p) for p in publishers]
    return any(p == a or (len(a) >= 4 and p.startswith(a + " ")) for p in found for a in allow)


def non_game_reason(game: dict, rules: dict) -> str | None:
    """Software, utilitários, etc. Devolve o motivo ou None se parecer um jogo."""
    name = str(game.get("name") or "").strip()
    if not name:
        return "sem_nome"
    if BAD_NAME.search(name):
        return "nome_nao_jogo"
    if game.get("store_type") not in (None, 0):  # Steam Store: 0 = jogo, 6 = software, ...
        return "tipo_nao_jogo"
    genres = {normalize(g) for g in split_list(game.get("genre"))}
    if genres & {normalize(g) for g in rules.get("genres", [])}:
        return "genero_software"
    software = {normalize(t) for t in rules.get("tags", [])}
    if any(normalize(t) in software for t in top_tags(game, int(rules.get("top_k", 1)))):
        return "etiqueta_software"
    return None


def genre_match(game: dict, category: dict, top_k: int, broad: dict | None = None) -> int | None:
    """Posição (0 = mais votada) da melhor etiqueta da categoria no top-k, ou None.

    Etiquetas genéricas (`broad["tags"]`, p.ex. Co-op ou Simulation) só contam se
    estiverem entre as `broad["top_k"]` mais votadas.
    """
    tags = top_tags(game, top_k)
    if tags and normalize(tags[0]) in {normalize(t) for t in category.get("not_if_first_tag", [])}:
        return None
    wanted = {normalize(t) for t in category.get("tags", [])}
    broad = broad or {}
    broad_tags = {normalize(t) for t in broad.get("tags", [])}
    broad_k = int(broad.get("top_k", top_k))
    for pos, tag in enumerate(tags):
        tag = normalize(tag)
        if tag in wanted and (tag not in broad_tags or pos < broad_k):
            return pos
    return None


def is_aaa(game: dict, category: dict, top_k: int) -> bool:
    """AAA não é classe oficial: editora grande + jogo pago + base de proprietários."""
    if not publisher_matches(game, category.get("publisher_allowlist", [])):
        return False
    if category.get("require_paid", True) and max(int_val(game.get("initialprice")), int_val(game.get("price"))) <= 0:
        return False
    if parse_owners(game.get("owners"))[0] < int(category.get("min_owners", 0)):
        return False
    banned = {normalize(t) for t in category.get("exclude_top_tags", [])}
    return not any(normalize(t) in banned for t in top_tags(game, top_k))


def is_indie(game: dict, category: dict, top_k: int) -> bool:
    """Indie = género/etiqueta Indie e editora fora da lista de editoras grandes."""
    if publisher_matches(game, category.get("publisher_blocklist", [])):
        return False
    genres = {normalize(g) for g in split_list(game.get("genre"))}
    tags = {normalize(t) for t in top_tags(game, top_k)}
    return "indie" in genres or "indie" in tags


def feature_match(game: dict, category: dict, top_k: int) -> bool:
    """Recurso para jogos sem etiqueta dominante: funcionalidade declarada na loja.

    `feature_fallback = {"features": [36, 49], "top_tags_any": [[tiro...], [multijogador...]]}`:
    o jogo declara Online PvP/PvP e tem, no top-k, uma etiqueta de cada grupo (p.ex. THE
    FINALS: FPS + Multiplayer). DOOM Eternal declara PvP mas não tem Multiplayer no top-k.
    """
    rule = category.get("feature_fallback")
    if not rule:
        return False
    if not set(rule.get("features", [])) & set(game.get("features") or []):
        return False
    # Cada grupo de `top_tags_any` precisa de pelo menos uma etiqueta (OU dentro do grupo).
    groups = rule.get("top_tags_any", [])
    if groups and isinstance(groups[0], str):
        groups = [groups]
    tags = {normalize(t) for t in top_tags(game, int(rule.get("top_k", top_k)))}
    return all(tags & {normalize(t) for t in group} for group in groups)


def classify(game: dict, categories: list[dict], top_k: int, broad: dict | None = None,
             fallback_order: list[str] | None = None) -> tuple[str | None, list[str], str]:
    """Devolve (categoria principal, categorias elegíveis, justificação).

    1. Etiquetas dominantes: entre géneros ganha a menor `priority` (competitive = 0:
       um battle royale com etiqueta Survival continua competitivo); depois a etiqueta
       mais votada.
    2. Sem etiqueta dominante, percorre `fallback_order` (p.ex. aaa, competitive, indie,
       survival_coop): regras de produção para aaa/indie, funcionalidades da loja para
       os géneros. A ordem decide que GTA V (pago, editora grande, com PvP) é AAA.
    """
    by_id = {cat["id"]: cat for cat in categories}
    genre_hits = []
    for order, cat in enumerate(categories):
        if cat.get("type") == "genre":
            pos = genre_match(game, cat, top_k, broad)
            if pos is not None:
                genre_hits.append((int(cat.get("priority", 1)), pos, order, cat["id"]))
    fallback = []
    for cid in fallback_order or [c["id"] for c in categories if c.get("type") == "production"]:
        cat = by_id[cid]
        if cat.get("type") == "production":
            rule = is_aaa if cat.get("rule") == "aaa" else is_indie
            if rule(game, cat, top_k):
                fallback.append((cid, f"regra de produção {cid}"))
        elif feature_match(game, cat, top_k):
            fallback.append((cid, f"funcionalidade da loja ({cid})"))
    eligible = list(dict.fromkeys([hit[-1] for hit in sorted(genre_hits)] + [cid for cid, _ in fallback]))
    if genre_hits:
        _, pos, _, cid = min(genre_hits)
        tag = top_tags(game, top_k)[pos]
        return cid, eligible, f"etiqueta '{tag}' na posição {pos + 1}"
    if fallback:
        return fallback[0][0], eligible, fallback[0][1]
    return None, eligible, "sem_categoria"
