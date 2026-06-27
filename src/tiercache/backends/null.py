from .base import AbstractBackend, MISS


class NullBackend(AbstractBackend):
    """No-op backend — use when a tier is not needed."""

    async def get(self, key: str): return MISS
    async def set(self, key: str, value, ttl_seconds=None) -> None: return None
    async def delete(self, key: str) -> None: return None
    async def flush(self) -> None: return None
    async def keys(self) -> list[str]: return []
    async def size_bytes(self) -> int: return 0
    async def close(self) -> None: return None
