import json
import time
from typing import Any, Optional

from .base import AbstractTracking

_STATS_COLLECTION   = "smartcache_stats"
_TRACKING_COLLECTION = "smartcache_tracking"


class MongoDBTracking(AbstractTracking):
    """
    MongoDB-backed tracking store using motor.
    Native TTL indexes handle automatic expiry of stale tracking entries.
    Good choice when MongoDB is already used as the dry cache backend.

    Requires: pip install smartcache[mongodb]
    """

    def __init__(self, uri: str, database: str) -> None:
        try:
            import motor.motor_asyncio as motor
        except ImportError:
            raise ImportError(
                "MongoDB tracking requires motor. "
                "Install it with: pip install smartcache[mongodb]"
            )
        self._motor = motor
        self._uri = uri
        self._database = database
        self._client: Optional[Any] = None
        self._db: Optional[Any] = None

    async def _get_db(self) -> Any:
        if self._db is None:
            import motor.motor_asyncio as motor
            self._client = motor.AsyncIOMotorClient(self._uri)
            self._db = self._client[self._database]
            await self._db[_STATS_COLLECTION].update_one(
                {"_id": "global"},
                {"$setOnInsert": {"hot_hits": 0, "cold_hits": 0, "dry_hits": 0, "misses": 0}},
                upsert=True,
            )
        return self._db

    async def record_hit(self, key: str, tier: str) -> None:
        db = await self._get_db()
        await db[_STATS_COLLECTION].update_one(
            {"_id": "global"}, {"$inc": {f"{tier}_hits": 1}}
        )
        await db[_TRACKING_COLLECTION].update_one(
            {"key": key}, {"$inc": {"hit_count": 1}}, upsert=False
        )

    async def record_miss(self, key: str) -> None:
        db = await self._get_db()
        await db[_STATS_COLLECTION].update_one(
            {"_id": "global"}, {"$inc": {"misses": 1}}
        )

    async def record_set(self, key: str, tier: str, tags: Optional[dict] = None, ttl_seconds: Optional[int] = None, reset_hits: bool = True) -> None:
        db = await self._get_db()
        doc: dict[str, Any] = {
            "key": key,
            "tier": tier,
            "created_at": time.time(),
            "ttl_seconds": ttl_seconds,
            "hit_count": 0,
        }
        if tags:
            doc["tags"] = tags
        await db[_TRACKING_COLLECTION].replace_one({"key": key}, doc, upsert=True)

    async def record_delete(self, key: str) -> None:
        db = await self._get_db()
        await db[_TRACKING_COLLECTION].delete_one({"key": key})

    async def get_stats(self) -> dict[str, Any]:
        db = await self._get_db()
        doc = await db[_STATS_COLLECTION].find_one({"_id": "global"})
        if not doc:
            return {"hot_hits": 0, "cold_hits": 0, "dry_hits": 0, "misses": 0}
        return {k: v for k, v in doc.items() if k != "_id"}

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
