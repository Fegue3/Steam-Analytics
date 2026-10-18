"""Cliente SteamSpy com cache de 24h, rate limiting conservador e logging."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

API_URL = "https://steamspy.com/api.php"
LOGGER = logging.getLogger(__name__)


class SteamSpyClient:
    def __init__(self, cache_dir: Path, cache_hours: float = 24.0,
                 min_interval: float = 1.1, all_interval: float = 61.0,
                 max_retries: int = 3, timeout: int = 45):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hours = cache_hours
        self.min_interval = min_interval
        self.all_interval = all_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AcademicSteamAnalytics/0.1 (research; contact-in-README)"})
        self.last_request_at = 0.0
        self.last_all_at = 0.0
        self.calls = 0
        self.cache_hits = 0

    def _cache_path(self, params: dict) -> Path:
        key = json.dumps(params, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        return self.cache_dir / f"{params['request']}_{digest}.json"

    def _rate_wait(self, request_type: str) -> None:
        now = time.monotonic()
        wait = max(0.0, self.min_interval - (now - self.last_request_at))
        if request_type == "all":
            wait = max(wait, self.all_interval - (now - self.last_all_at))
        if wait:
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

    def get(self, **params) -> dict:
        if "request" not in params:
            raise ValueError("Falta parâmetro request")
        request_type = str(params["request"])
        path = self._cache_path(params)
        if path.exists():
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if age < timedelta(hours=self.cache_hours):
                try:
                    cached = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(cached, dict):
                        raise ValueError("Cache inválida")
                    self.cache_hits += 1
                    LOGGER.info("CACHE HIT %s", params)
                    return cached
                except (ValueError, OSError):
                    LOGGER.warning("Cache inválida, novo pedido: %s", path)

        for attempt in range(self.max_retries):
            self._rate_wait(request_type)
            self.last_request_at = time.monotonic()
            if request_type == "all":
                self.last_all_at = self.last_request_at
            self.calls += 1
            try:
                response = self.session.get(API_URL, params=params, timeout=self.timeout)
                if response.status_code in (429, 500, 502, 503, 504):
                    pause = self._retry_after(response.headers)
                    if pause is None:
                        pause = min(120.0, 3.0 * (2 ** attempt))
                    if attempt + 1 < self.max_retries:
                        LOGGER.warning("HTTP %s (%s), aguardar %.1fs", response.status_code, params, pause)
                        time.sleep(pause)
                        continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"JSON inesperado, tipo {type(payload).__name__}")
                # Uma resposta de erro textual/HTML nunca é guardada como se fossem jogos.
                if "error" in payload and len(payload) <= 2:
                    raise ValueError(f"Erro SteamSpy: {payload['error']}")
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)
                LOGGER.info("OK %s (%s registos)", params, len(payload))
                return payload
            except (requests.RequestException, ValueError) as exc:
                LOGGER.warning("Tentativa %d/%d falhou %s: %s", attempt+1, self.max_retries, params, exc)
                if attempt + 1 < self.max_retries:
                    time.sleep(min(90.0, 2 ** (attempt + 1)))
                else:
                    raise RuntimeError(f"Não foi possível recolher {params}") from exc
        raise RuntimeError("Número de tentativas excedido")
