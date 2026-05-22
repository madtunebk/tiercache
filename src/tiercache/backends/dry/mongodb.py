import time
from typing import Any, Optional

from ...serializer import dumps, loads
from ..base import AbstractBackend


class MongoDBBackend(AbstractBackend):
    """
    MongoDB GridFS dry cache using motor (async driver).
    Large values are stored via GridFS; metadata (TTL, key) lives in the
    files collection. A TTL index on `metadata.expires_at` lets MongoDB
    handle expiry automatically — no cron job needed.

    Requires: pip install tiercache[mongodb]
    """

    def __init__(self, uri: str, database: str) -> None:
        try:
            import motor.motor_asyncio as motor
        except ImportError:
            raise ImportError(
                "MongoDB backend requires motor. "
                "Install it with: pip install tiercache[mongodb]"
            )
        self._motor = motor
        self._uri = uri
        self._database = database
        self._client: Optional[Any] = None
        self._fs: Optional[Any] = None

    async def _get_fs(self) -> Any:
        if self._fs is None:
            import motor.motor_asyncio as motor
            from motor.motor_asyncio import AsyncIOMotorGridFSBucket
            self._client = motor.AsyncIOMotorClient(self._uri)
            db = self._client[self._database]
            self._fs = AsyncIOMotorGridFSBucket(db, bucket_name="smartcache")
            # Ensure TTL index on expires_at metadata field
            await db["smartcache.files"].create_index(
                "metadata.expires_at",
                expireAfterSeconds=0,
                sparse=True,
            )
        return self._fs

    async def get(self, key: str) -> Optional[Any]:
        fs = await self._get_fs()
        cursor = fs.find({"metadata.cache_key": key})
        docs = await cursor.to_list(length=1)
        if not docs:
            return None
        doc = docs[0]
        expires_at = doc.get("metadata", {}).get("expires_at")
        if expires_at and time.time() > expires_at:
            await fs.delete(doc["_id"])
            return None
        stream = await fs.open_download_stream(doc["_id"])
        raw = await stream.read()
        return loads(raw)

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        fs = await self._get_fs()
        # Delete existing entry for this key first
        await self.delete(key)
        raw = dumps(value)
        metadata: dict[str, Any] = {"cache_key": key, "created_at": time.time()}
        if ttl_seconds:
            metadata["expires_at"] = time.time() + ttl_seconds
        await fs.upload_from_stream(
            key,
            raw,
            metadata=metadata,
        )

    async def delete(self, key: str) -> None:
        fs = await self._get_fs()
        cursor = fs.find({"metadata.cache_key": key})
        docs = await cursor.to_list(length=None)
        for doc in docs:
            await fs.delete(doc["_id"])

    async def flush(self) -> None:
        fs = await self._get_fs()
        cursor = fs.find({})
        docs = await cursor.to_list(length=None)
        for doc in docs:
            await fs.delete(doc["_id"])

    async def size_bytes(self) -> int:
        if self._client is None:
            return 0
        db = self._client[self._database]
        result = await db["smartcache.files"].aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$length"}}}
        ]).to_list(length=1)
        return result[0]["total"] if result else 0

    async def keys(self) -> list[str]:
        fs = await self._get_fs()
        now = time.time()
        keys: list[str] = []
        cursor = fs.find({})
        docs = await cursor.to_list(length=None)
        for doc in docs:
            metadata = doc.get("metadata", {})
            expires_at = metadata.get("expires_at")
            if expires_at and now > expires_at:
                await fs.delete(doc["_id"])
                continue
            key = metadata.get("cache_key")
            if isinstance(key, str):
                keys.append(key)
        return keys

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._fs = None
