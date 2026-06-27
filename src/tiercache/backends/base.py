from abc import ABC, abstractmethod
from typing import Any, Optional

# Sentinel returned by backends when a key is not found or expired.
# Distinct from None so that None can be stored as a real cached value.
MISS = object()


class AbstractBackend(ABC):

    @abstractmethod
    async def get(self, key: str) -> Any:
        """Return value for key, or MISS if not found / expired."""

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Store value. ttl_seconds=None means no expiry."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove a key. No-op if not found."""

    @abstractmethod
    async def flush(self) -> None:
        """Clear all entries."""

    @abstractmethod
    async def size_bytes(self) -> int:
        """Current memory/storage usage in bytes."""

    @abstractmethod
    async def keys(self) -> list[str]:
        """Return all live (non-expired) keys."""

    @abstractmethod
    async def close(self) -> None:
        """Release any connections or resources."""

    @property
    def default_ttl(self) -> Optional[int]:
        """Default TTL in seconds for this backend. None means no expiry."""
        return None
