import asyncio
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional

import aiofiles
import aiofiles.os

from ...serializer import dumps, loads
from ..base import AbstractBackend, MISS


class LocalBackend(AbstractBackend):
    """
    Local filesystem dry cache. Values are stored as binary files
    with a JSON sidecar for metadata (TTL, key, created_at, size).

    Files are sharded into subdirectories by the first 4 hex chars of the
    key hash to avoid large flat directories.

    max_size_bytes is enforced on every set() — oldest files are evicted
    first (by created_at) to make room for new entries.

    Requires: aiofiles (included in base install)
    """

    def __init__(self, base_path: str, max_size_bytes: int) -> None:
        self._base = Path(base_path)
        self._max_size = max_size_bytes
        self._base.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any:
        data_path, meta_path = self._paths(key)
        if not data_path.exists():
            return MISS
        meta = await self._read_meta(meta_path)
        if meta is None:
            return MISS
        if self._expired(meta):
            await self._remove_files(data_path, meta_path)
            return MISS
        async with aiofiles.open(data_path, "rb") as f:
            return loads(await f.read())

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        data_path, meta_path = self._paths(key)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        raw = dumps(value)
        incoming_size = len(raw)

        await self._make_room(incoming_size)

        async with aiofiles.open(data_path, "wb") as f:
            await f.write(raw)
        meta = {
            "key": key,
            "created_at": time.time(),
            "ttl_seconds": ttl_seconds,
            "size": incoming_size,
        }
        async with aiofiles.open(meta_path, "w") as f:
            await f.write(json.dumps(meta))

    async def delete(self, key: str) -> None:
        data_path, meta_path = self._paths(key)
        await self._remove_files(data_path, meta_path)

    async def flush(self) -> None:
        await asyncio.to_thread(shutil.rmtree, self._base, True)
        self._base.mkdir(parents=True, exist_ok=True)

    async def size_bytes(self) -> int:
        return await asyncio.to_thread(
            lambda: sum(p.stat().st_size for p in self._base.rglob("*.bin"))
        )

    async def keys(self) -> list[str]:
        meta_paths = await asyncio.to_thread(lambda: list(self._base.rglob("*.meta.json")))
        keys: list[str] = []
        for meta_path in meta_paths:
            meta = await self._read_meta(meta_path)
            if meta is None:
                continue
            if self._expired(meta):
                data_path = meta_path.with_suffix("").with_suffix(".bin")
                await self._remove_files(data_path, meta_path)
                continue
            key = meta.get("key")
            if isinstance(key, str):
                keys.append(key)
        return keys

    async def cleanup_expired(self) -> int:
        """Delete all expired files. Returns number of files removed."""
        meta_paths = await asyncio.to_thread(lambda: list(self._base.rglob("*.meta.json")))
        removed = 0
        for meta_path in meta_paths:
            meta = await self._read_meta(meta_path)
            if meta and self._expired(meta):
                data_path = meta_path.with_suffix("").with_suffix(".bin")
                await self._remove_files(data_path, meta_path)
                removed += 1
        return removed

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _make_room(self, incoming_size: int) -> None:
        current = await self.size_bytes()
        if current + incoming_size <= self._max_size:
            return

        meta_paths = await asyncio.to_thread(lambda: list(self._base.rglob("*.meta.json")))
        entries = []
        for meta_path in meta_paths:
            meta = await self._read_meta(meta_path)
            if meta:
                data_path = meta_path.with_suffix("").with_suffix(".bin")
                entries.append((meta.get("created_at", 0), meta.get("size", 0), data_path, meta_path))

        entries.sort(key=lambda x: x[0])

        for _, size, data_path, meta_path in entries:
            if current + incoming_size <= self._max_size:
                break
            await self._remove_files(data_path, meta_path)
            current -= size

    def _paths(self, key: str) -> tuple[Path, Path]:
        h = hashlib.sha256(key.encode()).hexdigest()
        shard = self._base / h[:2] / h[2:4]
        return shard / f"{h}.bin", shard / f"{h}.meta.json"

    @staticmethod
    async def _read_meta(path: Path) -> Optional[dict]:
        try:
            async with aiofiles.open(path) as f:
                return json.loads(await f.read())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _expired(meta: dict) -> bool:
        ttl = meta.get("ttl_seconds")
        if not ttl:
            return False
        return time.time() > meta["created_at"] + ttl

    @staticmethod
    async def _remove_files(*paths: Path) -> None:
        for p in paths:
            try:
                await aiofiles.os.remove(p)
            except FileNotFoundError:
                pass
