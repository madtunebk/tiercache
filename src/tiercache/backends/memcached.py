from typing import Any, Optional

from ..serializer import dumps, loads
from .base import AbstractBackend

# Memcached default max item size is 1MB.
# We chunk at 900KB to stay safely under the limit regardless of server config.
_CHUNK_SIZE = 900 * 1024  # 900 KB
_META_SUFFIX = b"__chunks__"


class MemcachedBackend(AbstractBackend):
    """
    Memcached-backed RAM cache using aiomcache.
    Values are pickled before storage.
    Large values are automatically split into 900KB chunks and reassembled
    on get — no server-side config needed regardless of item size.
    TTL is enforced natively by Memcached.
    Suitable for multi-process or multi-server deployments.

    Requires: pip install tiercache[memcached]
    """

    def __init__(self, host: str, port: int, ttl_seconds: int, max_size_bytes: int) -> None:
        try:
            import aiomcache
        except ImportError:
            raise ImportError(
                "Memcached backend requires aiomcache. "
                "Install it with: pip install tiercache[memcached]"
            )
        self._aiomcache = aiomcache
        self._host = host
        self._port = port
        self._ttl = ttl_seconds
        self._max_size = max_size_bytes
        self._client: Optional[Any] = None

    async def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._aiomcache.Client(self._host, self._port)
        return self._client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        client = await self._get_client()
        bkey = key.encode()

        # Check if this key was stored in chunks
        meta_raw = await client.get(bkey + _META_SUFFIX)
        if meta_raw is not None:
            n_chunks = int(meta_raw)
            chunks = []
            for i in range(n_chunks):
                chunk = await client.get(f"{key}__chunk_{i}".encode())
                if chunk is None:
                    return None  # partial expiry — treat as miss
                chunks.append(chunk)
            return loads(b"".join(chunks))

        # Single item
        raw = await client.get(bkey)
        if raw is None:
            return None
        return loads(raw)

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        exptime = ttl or 0
        client = await self._get_client()
        raw = dumps(value)

        if len(raw) <= _CHUNK_SIZE:
            await client.set(key.encode(), raw, exptime=exptime)
            return

        # Split into chunks
        chunks = [raw[i: i + _CHUNK_SIZE] for i in range(0, len(raw), _CHUNK_SIZE)]
        for i, chunk in enumerate(chunks):
            await client.set(f"{key}__chunk_{i}".encode(), chunk, exptime=exptime)
        # Store chunk count as metadata key
        await client.set(
            key.encode() + _META_SUFFIX,
            str(len(chunks)).encode(),
            exptime=exptime,
        )

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        bkey = key.encode()

        meta_raw = await client.get(bkey + _META_SUFFIX)
        if meta_raw is not None:
            n_chunks = int(meta_raw)
            for i in range(n_chunks):
                await client.delete(f"{key}__chunk_{i}".encode())
            await client.delete(bkey + _META_SUFFIX)
        else:
            await client.delete(bkey)

    async def flush(self) -> None:
        client = await self._get_client()
        await client.flush_all()

    async def size_bytes(self) -> int:
        # Memcached does not expose per-key sizes
        return 0

    async def keys(self) -> list[str]:
        # aiomcache does not provide a portable async key listing API and
        # Memcached does not guarantee safe key iteration in production.
        return []

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
