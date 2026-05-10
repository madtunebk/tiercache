from .base import AbstractTracking


class NullTracking(AbstractTracking):
    """No-op tracking — use when tracking is not needed."""

    async def record_set(self, *args, **kwargs) -> None: return None
    async def record_hit(self, *args, **kwargs) -> None: return None
    async def record_miss(self, *args, **kwargs) -> None: return None
    async def record_delete(self, *args, **kwargs) -> None: return None
    async def get_stats(self, *args, **kwargs): return {}
    async def close(self) -> None: return None
