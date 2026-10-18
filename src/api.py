"""Clientes HTTP JSON com cache em disco, rate limiting conservador, retries e logging."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

STEAMSPY_URL = "https://steamspy.com/api.php"
STEAM_PLAYERS_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
STEAM_ITEMS_URL = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
STEAM_TAGLIST_URL = "https://api.steampowered.com/IStoreService/GetTagList/v1/"
STEAM_MOST_PLAYED_URL = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
USER_AGENT = "AcademicSteamAnalytics/0.2 (UBI research project; github.com/Fegue3/Steam-Analytics)"
LOGGER = logging.getLogger(__name__)
RETRY_STATUS = (429, 500, 502, 503, 504)


class CachedJsonClient:
    """GET JSON com cache por parâmetros. `cache_hours=0` desliga a cache."""

    def __init__(self, url: str, cache_dir: Path, cache_hours: float = 24.0,
                 min_interval: float = 1.1, slow_requests: dict[str, float] | None = None,
                 max_retries: int = 3, timeout: int = 45, cache_prefix: str = "req"):
        self.url = url
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hours = cache_hours
        self.min_interval = min_interval
        self.slow_requests = slow_requests or {}
        self.max_retries = max_retries
        self.timeout = timeout
        self.cache_prefix = cache_prefix
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.last_request_at = 0.0
        self.last_slow_at: dict[str, float] = {}
        self.calls = 0
        self.cache_hits = 0

    def _cache_path(self, params: dict) -> Path:
        key = json.dumps(params, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        return self.cache_dir / f"{params.get('request', self.cache_prefix)}_{digest}.json"

    def _rate_wait(self, request_type: str) -> None:
        now = time.monotonic()
        wait = max(0.0, self.min_interval - (now - self.last_request_at))
        if request_type in self.slow_requests:
            last = self.last_slow_at.get(request_type, 0.0)
            wait = max(wait, self.slow_requests[request_type] - (now - last))
        if wait:
            if wait > 5:
                LOGGER.info("Aguardar %.1fs pelo intervalo da API (%s)", wait, request_type)
            time.sleep(wait)

    @staticmethod
    def _retry_after(headers) -> float | None:
        val = headers.get("Retry-After")
        if not val:
            return None
        try:
            return max(0.0, float(val))
        except ValueError:
            try:
                when = parsedate_to_datetime(val)
                return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                return None

    def _read_cache(self, path: Path) -> dict | None:
        if self.cache_hours <= 0 or not path.exists():
            return None
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if age >= timedelta(hours=self.cache_hours):
            return None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(cached, dict):
                raise ValueError("Cache inválida")
        except (ValueError, OSError):
            LOGGER.warning("Cache inválida, novo pedido: %s", path)
            return None
        self.cache_hits += 1
        LOGGER.debug("CACHE HIT %s", path.name)
        return cached

    def validate(self, payload: dict) -> None:
        """Hook para rejeitar respostas de erro antes de entrarem na cache."""

    def get(self, **params) -> dict:
        request_type = str(params.get("request", self.cache_prefix))
        path = self._cache_path(params)
        cached = self._read_cache(path)
        if cached is not None:
            return cached

        for attempt in range(self.max_retries):
            self._rate_wait(request_type)
            self.last_request_at = time.monotonic()
            if request_type in self.slow_requests:
                self.last_slow_at[request_type] = self.last_request_at
            self.calls += 1
            try:
                response = self.session.get(self.url, params=params, timeout=self.timeout)
                if response.status_code in RETRY_STATUS and attempt + 1 < self.max_retries:
                    pause = self._retry_after(response.headers)
                    if pause is None:
                        pause = min(120.0, 3.0 * (2 ** attempt))
                    LOGGER.warning("HTTP %s (%s), aguardar %.1fs", response.status_code, params, pause)
                    time.sleep(pause)
                    continue
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    # Erro do pedido (p.ex. 404): repetir não muda a resposta.
                    raise RuntimeError(f"HTTP {response.status_code} para {params}")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"JSON inesperado, tipo {type(payload).__name__}")
                self.validate(payload)
                if self.cache_hours > 0:
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(path)
                LOGGER.debug("OK %s", params)
                return payload
            except (requests.RequestException, ValueError) as exc:
                LOGGER.warning("Tentativa %d/%d falhou %s: %s", attempt + 1, self.max_retries, params, exc)
                if attempt + 1 < self.max_retries:
                    time.sleep(min(90.0, 2 ** (attempt + 1)))
                else:
                    raise RuntimeError(f"Não foi possível recolher {params}") from exc
        raise RuntimeError("Número de tentativas excedido")


class SteamSpyClient(CachedJsonClient):
    """SteamSpy: ~1 pedido/s em geral e 1 pedido/60s para `request=all`."""

    def __init__(self, cache_dir: Path, cache_hours: float = 24.0,
                 min_interval: float = 1.1, all_interval: float = 61.0, **kwargs):
        super().__init__(STEAMSPY_URL, cache_dir, cache_hours=cache_hours,
                         min_interval=min_interval, slow_requests={"all": all_interval}, **kwargs)

    def get(self, **params) -> dict:
        if "request" not in params:
            raise ValueError("Falta parâmetro request")
        return super().get(**params)

    def validate(self, payload: dict) -> None:
        # Uma resposta de erro textual nunca é guardada como se fossem jogos.
        if "error" in payload and len(payload) <= 2:
            raise ValueError(f"Erro SteamSpy: {payload['error']}")


class SteamStoreClient:
    """Steam Web API oficial (sem chave): etiquetas com peso, editora, preço e tipo, em lote.

    IStoreBrowseService/GetItems aceita ~250 AppIDs por pedido (limite do URL), por isso
    ~2500 jogos custam ~13 pedidos em vez de 2500 pedidos `appdetails` no SteamSpy.
    """

    TYPE_GAME = 0

    def __init__(self, cache_dir: Path, cache_hours: float = 24.0, batch_size: int = 200,
                 country: str = "US", **kwargs):
        self.items = CachedJsonClient(STEAM_ITEMS_URL, cache_dir, cache_hours=cache_hours,
                                      min_interval=0.5, cache_prefix="store_items", **kwargs)
        self.taglist = CachedJsonClient(STEAM_TAGLIST_URL, cache_dir, cache_hours=24.0 * 7,
                                        min_interval=0.5, cache_prefix="store_taglist", **kwargs)
        self.charts = CachedJsonClient(STEAM_MOST_PLAYED_URL, cache_dir, cache_hours=cache_hours,
                                       min_interval=0.5, cache_prefix="charts_most_played", **kwargs)
        self.batch_size = batch_size
        self.country = country
        self._tag_names: dict[int, str] | None = None

    @property
    def calls(self) -> int:
        return self.items.calls + self.taglist.calls + self.charts.calls

    @property
    def cache_hits(self) -> int:
        return self.items.cache_hits + self.taglist.cache_hits + self.charts.cache_hits

    def most_played(self) -> dict[int, int]:
        """TOP 100 oficial por pico diário de jogadores: {appid: pico}.

        Cobre jogos que faltam nas listas do SteamSpy (p.ex. Dota 2).
        """
        ranks = self.charts.get().get("response", {}).get("ranks", [])
        return {int(r["appid"]): int(r.get("peak_in_game") or 0) for r in ranks if r.get("appid")}


    def tag_names(self) -> dict[int, str]:
        if self._tag_names is None:
            tags = self.taglist.get(language="english").get("response", {}).get("tags", [])
            self._tag_names = {int(t["tagid"]): t["name"] for t in tags}
        return self._tag_names

    def to_game(self, item: dict) -> dict:
        """Converte um item da loja para o formato usado em src/classify.py."""
        names = self.tag_names()
        tags = {names.get(int(t["tagid"]), str(t["tagid"])): int(t.get("weight", 0))
                for t in item.get("tags") or []}
        info = item.get("basic_info") or {}
        offer = item.get("best_purchase_option") or {}
        final = int_or_none(offer.get("final_price_in_cents"))
        original = int_or_none(offer.get("original_price_in_cents")) or final
        if item.get("is_free"):
            status = "gratuito"
        elif final is not None:
            status = "a_venda"
        else:
            status = "nao_listado" if item.get("unlisted") else "sem_venda"  # p.ex. acesso por convite
        return {
            "name": item.get("name", ""),
            "store_type": item.get("type"),
            "is_free": bool(item.get("is_free")),
            "store_status": status,
            # Funcionalidades declaradas pelo programador: 1 multi, 2 single, 9 co-op,
            # 36 online PvP, 38 online co-op, 49 PvP, ...
            "features": sorted((item.get("categories") or {}).get("supported_player_categoryids") or []),
            "tags": tags,
            "publisher": ", ".join(p["name"] for p in info.get("publishers") or [] if p.get("name")),
            "developer": ", ".join(d["name"] for d in info.get("developers") or [] if d.get("name")),
            "price": "" if final is None else str(final),
            "initialprice": "" if original is None else str(original),
        }

    def get_games(self, appids: list[int]) -> tuple[dict[int, dict], list[int], list[int]]:
        """Devolve ({appid: jogo}, AppIDs que a loja não reconhece, AppIDs cujo pedido falhou)."""
        found, missing, failed = {}, [], []
        for start in range(0, len(appids), self.batch_size):
            batch = appids[start:start + self.batch_size]
            request = {"ids": [{"appid": a} for a in batch],
                       "context": {"language": "english", "country_code": self.country},
                       "data_request": {"include_tag_count": 20, "include_basic_info": True}}
            try:
                payload = self.items.get(input_json=json.dumps(request, separators=(",", ":")))
            except RuntimeError as exc:
                LOGGER.error("GetItems falhou para %d AppIDs: %s", len(batch), exc)
                failed += batch
                continue
            items = {int(it.get("appid") or it.get("id") or 0): it
                     for it in payload.get("response", {}).get("store_items", [])}
            for appid in batch:
                item = items.get(appid)
                if item and item.get("success") == 1:
                    found[appid] = self.to_game(item)
                else:
                    missing.append(appid)
        return found, missing, failed


def int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class SteamPlayersClient(CachedJsonClient):
    """Steam Web API oficial, GetNumberOfCurrentPlayers (não exige chave)."""

    def __init__(self, cache_dir: Path, cache_hours: float = 1.0, min_interval: float = 0.0,
                 workers: int = 6, **kwargs):
        super().__init__(STEAM_PLAYERS_URL, cache_dir, cache_hours=cache_hours,
                         min_interval=min_interval, cache_prefix="players", **kwargs)
        self.workers = workers

    def current_players_many(self, appids: list[int]) -> dict[int, int | None]:
        """Consulta vários AppIDs em paralelo (poucos workers, API oficial com quota diária)."""
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return dict(zip(appids, pool.map(self.current_players, appids)))

    def current_players(self, appid: int) -> int | None:
        """Jogadores agora, ou None se a Steam não tiver estatísticas para o AppID."""
        try:
            payload = self.get(appid=appid)
        except RuntimeError:
            # 404 = AppID sem estatísticas (removido, encerrado ou não é jogo).
            return None
        response = payload.get("response") or {}
        if response.get("result") != 1:
            return None
        try:
            return int(response.get("player_count"))
        except (TypeError, ValueError):
            return None
