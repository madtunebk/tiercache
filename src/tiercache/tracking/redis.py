import json
import time
from typing import Any, Optional

from .base import AbstractTracking

_STATS_KEY = "smartcache:stats"
_META_PREFIX = "smartcache:meta:"


class RedisTracking(AbstractTracking):
    """
    Redis-backed tracking store. Default tracking backend.
    Entirely in-memory — fits the RAM-first philosophy.
    Stats and metadata survive process restarts (persisted by Redis).

    Requires: pip install smartcache[redis]
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "Redis tracking requires redis-py. "
                "Install it with: pip install smartcache[redis]"
            )
        self._aioredis = aioredis
        self._host = host
        self._port = port
        self._db = db
        self._client: Optional[Any] = None

    async def _conn(self) -> Any:
        if self._client is None:
            self._client = self._aioredis.Redis(
                host=self._host, port=self._port, db=self._db, decode_responses=True
            )
        return self._client

    async def record_hit(self, key: str, tier: str) -> None:
        r = await self._conn()
        pipe = r.pipeline()
        pipe.hincrby(_STATS_KEY, f"{tier}_hits", 1)
        pipe.hincrby(f"{_META_PREFIX}{key}", "hit_count", 1)
        await pipe.execute()

    async def record_miss(self, key: str) -> None:
        r = await self._conn()
        await r.hincrby(_STATS_KEY, "misses", 1)

    async def record_set(self, key: str, tier: str, tags: Optional[dict] = None, ttl_seconds: Optional[int] = None, reset_hits: bool = True) -> None:
        r = await self._conn()
        meta: dict[str, str] = {
            "tier": tier,
            "created_at": str(time.time()),
            "hit_count": "0",
        }
        if tags:
            meta["tags"] = json.dumps(tags)
        await r.hset(f"{_META_PREFIX}{key}", mapping=meta)

    async def record_delete(self, key: str) -> None:
        r = await self._conn()
        await r.delete(f"{_META_PREFIX}{key}")

    async def get_stats(self) -> dict[str, Any]:
        r = await self._conn()
        raw = await r.hgetall(_STATS_KEY)
        return {
            "hot_hits":  int(raw.get("hot_hits", 0)),
            "cold_hits": int(raw.get("cold_hits", 0)),
            "dry_hits":  int(raw.get("dry_hits", 0)),
            "misses":    int(raw.get("misses", 0)),
        }

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
