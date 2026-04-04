from abc import ABC, abstractmethod
from typing import Any, Optional


class AbstractBackend(ABC):

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Return value for key, or None if missing / expired."""

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
    async def close(self) -> None:
        """Release any connections or resources."""
