import asyncio
from typing import Any, Optional

from .backends.base import AbstractBackend, MISS
from .tracking.base import AbstractTracking


def _run(coro: Any) -> Any:
    """Run a coroutine from sync code (Flask, Django, etc.)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError(
            "Cannot use sync methods inside a running event loop. "
            "Use the async methods (get, set, delete, ...) instead."
        )
    return asyncio.run(coro)


class TTLResolver:
    """Resolves TTL in seconds using the priority chain: per-key > tag rules > tier default."""

    def __init__(self, defaults: dict[str, Optional[int]], rules: list[dict]) -> None:
        # defaults: {"hot": 14400, "cold": 86400, "dry": None}
        self._defaults = defaults
        # rules: [{"tag": {"type": "thumbnail"}, "hot": 3600, "cold": 43200}, ...]
        self._rules = rules

    def resolve(
        self,
        tier: str,
        ttl_seconds: Optional[int],
        tags: Optional[dict],
    ) -> Optional[int]:
        if ttl_seconds is not None:
            return ttl_seconds
        if tags:
            for rule in self._rules:
                tag_filter = rule.get("tag", {})
                if all(tags.get(k) == v for k, v in tag_filter.items()):
                    if tier in rule:
                        return rule[tier]
        return self._defaults.get(tier)


class CacheManager:
    """
    Orchestrates the three-tier lookup chain: hot → cold → dry.

    On get:  hot HIT → serve. hot MISS → cold HIT → promote to hot → serve.
             cold MISS → dry HIT → promote to hot → serve. dry MISS → None.
    On set:  write to hot only. Dry acts as a failsafe — populated automatically
             when hot evicts or expires an entry (demotion), not on every write.
    """

    def __init__(
        self,
        hot: AbstractBackend,
        cold: AbstractBackend,
        dry: AbstractBackend,
        tracking: AbstractTracking,
        ttl_resolver: Optional[TTLResolver] = None,
    ) -> None:
        self._hot = hot
        self._cold = cold
        self._dry = dry
        self._tracking = tracking
        self._ttl_resolver = ttl_resolver or TTLResolver(
            defaults={"hot": hot.default_ttl, "cold": cold.default_ttl, "dry": dry.default_ttl},
            rules=[],
        )
        self._wire_eviction_hooks()

    # ------------------------------------------------------------------
    # Eviction wiring
    # ------------------------------------------------------------------

    def _wire_eviction_hooks(self) -> None:
        from .backends.ram import RamBackend
        if isinstance(self._hot, RamBackend):
            self._hot._on_evict = self._on_hot_evict
        if isinstance(self._cold, RamBackend):
            self._cold._on_evict = self._on_cold_evict

    async def _on_hot_evict(self, key: str, value: Any) -> None:
        await self._dry.set(key, value)
        await self._tracking.record_set(key, "dry", reset_hits=False)

    async def _on_cold_evict(self, key: str, value: Any) -> None:
        await self._dry.set(key, value)
        await self._tracking.record_set(key, "dry", reset_hits=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        value = await self._hot.get(key)
        if value is not MISS:
            await self._tracking.record_hit(key, "hot")
            return value

        value = await self._cold.get(key)
        if value is not MISS:
            await self._tracking.record_hit(key, "cold")
            await self._hot.set(key, value)
            await self._tracking.record_set(key, "hot", reset_hits=False)
            return value

        value = await self._dry.get(key)
        if value is not MISS:
            await self._tracking.record_hit(key, "dry")
            await self._hot.set(key, value)
            await self._tracking.record_set(key, "hot", reset_hits=False)
            return value

        await self._tracking.record_miss(key)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_hours: Optional[float] = None,
        tags: Optional[dict] = None,
    ) -> None:
        ttl_seconds = int(ttl_hours * 3600) if ttl_hours is not None else None

        hot_ttl = self._ttl_resolver.resolve("hot", ttl_seconds, tags)
        await self._hot.set(key, value, ttl_seconds=hot_ttl)
        await self._tracking.record_set(key, "hot", tags=tags, ttl_seconds=hot_ttl, reset_hits=True)

    async def delete(self, key: str) -> None:
        await self._hot.delete(key)
        await self._cold.delete(key)
        await self._dry.delete(key)
        await self._tracking.record_delete(key)

    async def flush(self, tier: str = "all") -> None:
        if tier in ("hot", "all"):
            await self._hot.flush()
        if tier in ("cold", "all"):
            await self._cold.flush()
        if tier in ("dry", "all"):
            await self._dry.flush()

    async def stats(self) -> dict[str, Any]:
        base = await self._tracking.get_stats()
        base["hot_size_bytes"]  = await self._hot.size_bytes()
        base["cold_size_bytes"] = await self._cold.size_bytes()
        base["dry_size_bytes"]  = await self._dry.size_bytes()
        return base

    async def keys(self) -> list[str]:
        return await self._hot.keys()

    async def purge(self, pattern: str) -> list[str]:
        """Delete all hot keys matching a glob-style pattern. Returns deleted keys."""
        import fnmatch
        all_keys = await self._hot.keys()
        matched = [k for k in all_keys if fnmatch.fnmatch(k, pattern)]
        for k in matched:
            await self.delete(k)
        return matched

    async def cleanup_expired(self) -> int:
        """
        Scan hot and cold RAM tiers for expired entries, demote them to dry,
        and update tracking. Call periodically to keep tier tracking accurate.
        Returns the number of entries demoted.
        """
        from .backends.ram import RamBackend
        count = 0
        if isinstance(self._hot, RamBackend):
            for key, value in await self._hot.pop_expired():
                await self._on_hot_evict(key, value)
                count += 1
        if isinstance(self._cold, RamBackend):
            for key, value in await self._cold.pop_expired():
                await self._on_cold_evict(key, value)
                count += 1
        return count

    async def close(self) -> None:
        await self._hot.close()
        await self._cold.close()
        await self._dry.close()
        await self._tracking.close()

    # ------------------------------------------------------------------
    # Sync wrappers — for Flask, Django, and other sync frameworks
    # ------------------------------------------------------------------

    def get_sync(self, key: str) -> Optional[Any]:
        return _run(self.get(key))

    def set_sync(
        self,
        key: str,
        value: Any,
        ttl_hours: Optional[float] = None,
        tags: Optional[dict] = None,
    ) -> None:
        _run(self.set(key, value, ttl_hours=ttl_hours, tags=tags))

    def delete_sync(self, key: str) -> None:
        _run(self.delete(key))

    def flush_sync(self, tier: str = "all") -> None:
        _run(self.flush(tier=tier))

    def stats_sync(self) -> dict[str, Any]:
        return _run(self.stats())

    def cleanup_expired_sync(self) -> int:
        return _run(self.cleanup_expired())

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, path: str) -> "CacheManager":
        from .config import load_config
        return load_config(path)
