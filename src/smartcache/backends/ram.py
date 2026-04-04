import asyncio
import sys
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Optional

from .base import AbstractBackend

EvictCallback = Callable[[str, Any], Awaitable[None]]


class RamBackend(AbstractBackend):
    """
    In-process RAM cache using an OrderedDict for O(1) LRU eviction.
    TTL is checked lazily on get. Size is estimated from value length (bytes)
    or sys.getsizeof for other types.

    on_evict: optional async callback(key, value) fired when an entry is
    dropped due to LRU pressure or TTL expiry. Used by CacheManager to
    demote evicted entries to dry cache (failsafe).
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
        # key -> (value, expiry_monotonic)  expiry=0 means no expiry
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._current_size = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if self._expired(expiry):
                self._remove(key, evict=False)  # expired — don't demote to dry
                return None
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        expiry = time.monotonic() + ttl if ttl else 0.0
        size = self._measure(value)
        async with self._lock:
            if key in self._store:
                old_value, _ = self._store[key]
                self._current_size -= self._measure(old_value)
            while self._current_size + size > self._max_size and self._store:
                self._remove(next(iter(self._store)), evict=True)  # LRU — demote to dry
            self._store[key] = (value, expiry)
            self._store.move_to_end(key)
            self._current_size += size

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

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove(self, key: str, evict: bool = False) -> None:
        value, _ = self._store.pop(key)
        self._current_size -= self._measure(value)
        if evict and self._on_evict is not None:
            asyncio.create_task(self._on_evict(key, value))

    @staticmethod
    def _expired(expiry: float) -> bool:
        return expiry != 0.0 and time.monotonic() > expiry

    @staticmethod
    def _measure(value: Any) -> int:
        if isinstance(value, (bytes, bytearray, memoryview)):
            return len(value)
        return sys.getsizeof(value)
