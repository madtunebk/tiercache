import json
import time
from typing import Any, Optional

from .base import AbstractTracking


class PostgresTracking(AbstractTracking):
    """
    PostgreSQL-backed tracking store using asyncpg.
    Good for production multi-process deployments with strong querying needs.

    Requires: pip install smartcache[postgres]
    """

    def __init__(self, dsn: str) -> None:
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "PostgreSQL tracking requires asyncpg. "
                "Install it with: pip install smartcache[postgres]"
            )
        self._asyncpg = asyncpg
        self._dsn = dsn
        self._pool: Optional[Any] = None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            self._pool = await self._asyncpg.create_pool(self._dsn)
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS cache_tracking (
                        key         TEXT PRIMARY KEY,
                        tier        TEXT NOT NULL,
                        created_at  DOUBLE PRECISION NOT NULL,
                        ttl_seconds INTEGER,
                        hit_count   INTEGER NOT NULL DEFAULT 0,
                        tags        JSONB
                    );
                    CREATE TABLE IF NOT EXISTS cache_stats (
                        name  TEXT PRIMARY KEY,
                        value BIGINT NOT NULL DEFAULT 0
                    );
                    INSERT INTO cache_stats (name, value)
                    VALUES ('hot_hits', 0), ('cold_hits', 0), ('dry_hits', 0), ('misses', 0)
                    ON CONFLICT DO NOTHING;
                """)
        return self._pool

    async def record_hit(self, key: str, tier: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE cache_tracking SET hit_count = hit_count + 1 WHERE key = $1", key
            )
            await conn.execute(
                "UPDATE cache_stats SET value = value + 1 WHERE name = $1", f"{tier}_hits"
            )

    async def record_miss(self, key: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE cache_stats SET value = value + 1 WHERE name = 'misses'"
            )

    async def record_set(self, key: str, tier: str, tags: Optional[dict] = None, ttl_seconds: Optional[int] = None, reset_hits: bool = True) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cache_tracking (key, tier, created_at, tags)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (key) DO UPDATE SET
                    tier = EXCLUDED.tier,
                    created_at = EXCLUDED.created_at,
                    tags = EXCLUDED.tags,
                    hit_count = 0
                """,
                key, tier, time.time(), json.dumps(tags) if tags else None,
            )

    async def record_delete(self, key: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM cache_tracking WHERE key = $1", key)

    async def get_stats(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT name, value FROM cache_stats")
        return {row["name"]: row["value"] for row in rows}

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
