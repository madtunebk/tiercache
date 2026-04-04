import asyncio
import pytest
from tiercache.backends.ram import RamBackend


@pytest.fixture
def backend():
    return RamBackend(ttl_seconds=10, max_size_bytes=1024 * 1024)  # 1 MB


async def test_set_and_get(backend):
    await backend.set("key1", b"hello")
    assert await backend.get("key1") == b"hello"


async def test_miss_returns_none(backend):
    assert await backend.get("nonexistent") is None


async def test_delete(backend):
    await backend.set("key1", b"hello")
    await backend.delete("key1")
    assert await backend.get("key1") is None


async def test_flush(backend):
    await backend.set("key1", b"a")
    await backend.set("key2", b"b")
    await backend.flush()
    assert await backend.get("key1") is None
    assert await backend.get("key2") is None


async def test_ttl_expiry():
    backend = RamBackend(ttl_seconds=1, max_size_bytes=1024 * 1024)
    await backend.set("key1", b"data", ttl_seconds=1)
    assert await backend.get("key1") == b"data"
    await asyncio.sleep(1.1)
    assert await backend.get("key1") is None


async def test_lru_eviction():
    # Only 10 bytes capacity
    backend = RamBackend(ttl_seconds=60, max_size_bytes=10)
    await backend.set("a", b"12345")   # 5 bytes
    await backend.set("b", b"67890")   # 5 bytes — fills up
    await backend.set("c", b"ABCDE")   # 5 bytes — should evict LRU (a)
    assert await backend.get("a") is None
    assert await backend.get("b") == b"67890"
    assert await backend.get("c") == b"ABCDE"


async def test_per_key_ttl_override(backend):
    await backend.set("short", b"data", ttl_seconds=1)
    await backend.set("long", b"data", ttl_seconds=9999)
    await asyncio.sleep(1.1)
    assert await backend.get("short") is None
    assert await backend.get("long") == b"data"


async def test_size_bytes(backend):
    await backend.set("key", b"x" * 100)
    assert await backend.size_bytes() == 100
