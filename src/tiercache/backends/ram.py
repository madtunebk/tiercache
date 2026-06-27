import asyncio
import sys
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Optional

from .base import AbstractBackend, MISS

EvictCallback = Callable[[str, Any], Awaitable[None]]


class RamBackend(AbstractBackend):
    """
    In-process RAM cache using an OrderedDict for O(1) LRU eviction.
    TTL is checked lazily on get and reset on each hit (sliding window).
    Size is estimated from value length (bytes) or sys.getsizeof for other types.

    on_evict: optional async callback(key, value) fired when an entry is
    dropped due to LRU pressure or TTL expiry. Used by CacheManager to
    demote evicted entries to dry cache (failsafe).
    Callbacks are fired AFTER releasing the lock to avoid holding it during I/O.
    """

    def __init__(
        self,
        ttl_seconds: int,
        max_size_bytes: int,
        on_evict: Optional[EvictCallback] = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size_bytes
        self._on_evict = on_evict
        # key -> (value, expiry_monotonic, ttl_seconds)  expiry=0/ttl=0 means no expiry
        self._store: OrderedDict[str, tuple[Any, float, int]] = OrderedDict()
        self._current_size = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any:
        eviction = None
        result = MISS
        async with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                value, expiry, ttl = entry
                if self._expired(expiry):
                    eviction = self._remove(key, evict=True)
                else:
                    new_expiry = time.monotonic() + ttl if ttl else 0.0
                    self._store[key] = (value, new_expiry, ttl)
                    self._store.move_to_end(key)
                    result = value
        if eviction and self._on_evict:
            await self._on_evict(*eviction)
        return result

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        expiry = time.monotonic() + ttl if ttl else 0.0
        size = self._measure(value)
        evictions: list[tuple[str, Any]] = []
        async with self._lock:
            if key in self._store:
                old_value, _, _ = self._store[key]
                self._current_size -= self._measure(old_value)
            while self._current_size + size > self._max_size and self._store:
                ev = self._remove(next(iter(self._store)), evict=True)
                if ev:
                    evictions.append(ev)
            self._store[key] = (value, expiry, ttl)
            self._store.move_to_end(key)
            self._current_size += size
        if self._on_evict:
            for k, v in evictions:
                await self._on_evict(k, v)

    async def delete(self, key: str) -> None:
        async with self._lock:
            if key in self._store:
                self._remove(key, evict=False)  # explicit delete — don't demote to dry

    async def flush(self) -> None:
        async with self._lock:
            self._store.clear()
            self._current_size = 0

    async def size_bytes(self) -> int:
        return self._current_size

    async def keys(self) -> list[str]:
        async with self._lock:
            return [k for k, (_, expiry, _) in self._store.items() if not self._expired(expiry)]

    async def pop_expired(self) -> list[tuple[str, Any]]:
        """Remove all expired entries and return (key, value) pairs for the caller to demote."""
        expired = []
        async with self._lock:
            for key, (value, expiry, _) in list(self._store.items()):
                if self._expired(expiry):
                    self._store.pop(key)
                    self._current_size -= self._measure(value)
                    expired.append((key, value))
        return expired

    async def close(self) -> None:
        pass

    @property
    def default_ttl(self) -> Optional[int]:
        return self._ttl or None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove(self, key: str, evict: bool = False) -> Optional[tuple[str, Any]]:
        """Remove key from store. Returns (key, value) if caller should fire eviction, else None."""
        value, _, _ = self._store.pop(key)
        self._current_size -= self._measure(value)
        if evict and self._on_evict is not None:
            return (key, value)
        return None

    @staticmethod
    def _expired(expiry: float) -> bool:
        return expiry != 0.0 and time.monotonic() > expiry

    @staticmethod
    def _measure(value: Any) -> int:
        if isinstance(value, (bytes, bytearray, memoryview)):
            return len(value)
        return sys.getsizeof(value)
