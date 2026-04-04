"""
TierCache — RAM-first three-tier cache with swappable backends.

Quick start:

    from tiercache import CacheManager

    # From config file
    cache = CacheManager.from_config("smartcache.yaml")

    # Or in code
    from tiercache import CacheManager
    from tiercache.backends.ram import RamBackend
    from tiercache.backends.dry.local import LocalBackend
    from tiercache.tracking.sqlite import SQLiteTracking

    cache = CacheManager(
        hot=RamBackend(ttl_seconds=14400, max_size_bytes=2 * 1024**3),
        cold=RamBackend(ttl_seconds=86400, max_size_bytes=10 * 1024**3),
        dry=LocalBackend(base_path="/var/cache/smartcache", max_size_bytes=100 * 1024**3),
        tracking=SQLiteTracking(path="/var/cache/smartcache/index.db"),
    )

    value = await cache.get("my-key")
    await cache.set("my-key", data)
    await cache.set("my-key", data, ttl_hours=2)
    await cache.set("my-key", data, tags={"type": "thumbnail"})
"""

from .manager import CacheManager, TTLResolver
from .backends.base import AbstractBackend
from .tracking.base import AbstractTracking

__all__ = [
    "CacheManager",
    "TTLResolver",
    "AbstractBackend",
    "AbstractTracking",
]

__version__ = "0.1.0"
