import json
import time
from typing import Any, Optional

from .base import AbstractTracking

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_tracking (
    key         TEXT PRIMARY KEY,
    tier        TEXT NOT NULL,
    created_at  REAL NOT NULL,
    ttl_seconds INTEGER,
    hit_count   INTEGER NOT NULL DEFAULT 0,
    tags        TEXT
);
CREATE TABLE IF NOT EXISTS cache_stats (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO cache_stats (name, value) VALUES
    ('hot_hits', 0), ('cold_hits', 0), ('dry_hits', 0), ('misses', 0);
"""


class SQLiteTracking(AbstractTracking):
    """
    SQLite-backed tracking store. Zero extra dependencies.
    Good for single-process / single-machine deployments.

    Requires: aiosqlite (included in base install)
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._db: Optional[Any] = None

    async def _conn(self) -> Any:
        if self._db is None:
            import aiosqlite
            self._db = await aiosqlite.connect(self._path)
            self._db.row_factory = aiosqlite.Row
            await self._db.executescript(_SCHEMA)
            await self._db.commit()
        return self._db

    async def record_hit(self, key: str, tier: str) -> None:
        db = await self._conn()
        await db.execute(
            "UPDATE cache_tracking SET hit_count = hit_count + 1 WHERE key = ?", (key,)
        )
        await db.execute(
            f"UPDATE cache_stats SET value = value + 1 WHERE name = ?", (f"{tier}_hits",)
        )
        await db.commit()

    async def record_miss(self, key: str) -> None:
        db = await self._conn()
        await db.execute("UPDATE cache_stats SET value = value + 1 WHERE name = 'misses'")
        await db.commit()

    async def record_set(self, key: str, tier: str, tags: Optional[dict] = None) -> None:
        db = await self._conn()
        await db.execute(
            """
            INSERT INTO cache_tracking (key, tier, created_at, tags)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                tier = excluded.tier,
                created_at = excluded.created_at,
                tags = excluded.tags,
                hit_count = 0
            """,
            (key, tier, time.time(), json.dumps(tags) if tags else None),
        )
        await db.commit()

    async def record_delete(self, key: str) -> None:
        db = await self._conn()
        await db.execute("DELETE FROM cache_tracking WHERE key = ?", (key,))
        await db.commit()

    async def get_stats(self) -> dict[str, Any]:
        db = await self._conn()
        async with db.execute("SELECT name, value FROM cache_stats") as cur:
            rows = await cur.fetchall()
        return {row["name"]: row["value"] for row in rows}

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
