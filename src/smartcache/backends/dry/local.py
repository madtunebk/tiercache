import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

import aiofiles
import aiofiles.os

from ...serializer import dumps, loads
from ..base import AbstractBackend


class LocalBackend(AbstractBackend):
    """
    Local filesystem dry cache. Values are stored as pickled binary files
    with a JSON sidecar for metadata (TTL, key, created_at).

    Files are sharded into subdirectories by the first 4 hex chars of the
    key hash to avoid large flat directories.

    Requires: aiofiles (included in base install)
    """

    def __init__(self, base_path: str, max_size_bytes: int) -> None:
        self._base = Path(base_path)
        self._max_size = max_size_bytes
        self._base.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        data_path, meta_path = self._paths(key)
        if not data_path.exists():
            return None
        meta = self._read_meta(meta_path)
        if meta is None:
            return None
        if self._expired(meta):
            await self._remove_files(data_path, meta_path)
            return None
        async with aiofiles.open(data_path, "rb") as f:
            return loads(await f.read())

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        data_path, meta_path = self._paths(key)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        raw = dumps(value)
        async with aiofiles.open(data_path, "wb") as f:
            await f.write(raw)
        meta = {
            "key": key,
            "created_at": time.time(),
            "ttl_seconds": ttl_seconds,
            "size": len(raw),
        }
        async with aiofiles.open(meta_path, "w") as f:
            await f.write(json.dumps(meta))

    async def delete(self, key: str) -> None:
        data_path, meta_path = self._paths(key)
        await self._remove_files(data_path, meta_path)

    async def flush(self) -> None:
        import shutil
        shutil.rmtree(self._base, ignore_errors=True)
        self._base.mkdir(parents=True, exist_ok=True)

    async def size_bytes(self) -> int:
        total = 0
        for p in self._base.rglob("*.bin"):
            total += p.stat().st_size
        return total

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _paths(self, key: str) -> tuple[Path, Path]:
        h = hashlib.sha256(key.encode()).hexdigest()
        shard = self._base / h[:2] / h[2:4]
        return shard / f"{h}.bin", shard / f"{h}.meta.json"

    @staticmethod
    def _read_meta(path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
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
