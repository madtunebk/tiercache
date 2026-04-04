from abc import ABC, abstractmethod
from typing import Any, Optional


class AbstractTracking(ABC):

    @abstractmethod
    async def record_hit(self, key: str, tier: str) -> None:
        """Increment hit counter for key on the given tier."""

    @abstractmethod
    async def record_miss(self, key: str) -> None:
        """Increment miss counter."""

    @abstractmethod
    async def record_set(self, key: str, tier: str, tags: Optional[dict] = None) -> None:
        """Record a new key being stored."""

    @abstractmethod
    async def record_delete(self, key: str) -> None:
        """Remove tracking entry for key."""

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """Return hit/miss/tier statistics."""

    @abstractmethod
    async def close(self) -> None:
        """Release any connections or resources."""
