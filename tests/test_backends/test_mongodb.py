"""
Integration tests for MongoDB GridFS dry backend.

Requires MongoDB running:
    docker compose up -d mongodb
"""

import pytest
from tests.conftest import requires_mongodb

MONGO_URI = "mongodb://localhost:27017"
DATABASE  = "tiercache_test"


@pytest.fixture
async def backend():
    from tiercache.backends.dry.mongodb import MongoDBBackend
    b = MongoDBBackend(uri=MONGO_URI, database=DATABASE)
    yield b
    await b.flush()
    await b.close()


@requires_mongodb
async def test_set_and_get(backend):
    await backend.set("img1", b"hello mongodb")
    assert await backend.get("img1") == b"hello mongodb"


@requires_mongodb
async def test_miss_returns_none(backend):
    assert await backend.get("nonexistent") is None


@requires_mongodb
async def test_delete(backend):
    await backend.set("img2", b"data")
    await backend.delete("img2")
    assert await backend.get("img2") is None


@requires_mongodb
async def test_flush(backend):
    await backend.set("a", b"1")
    await backend.set("b", b"2")
    await backend.flush()
    assert await backend.get("a") is None
    assert await backend.get("b") is None


@requires_mongodb
async def test_large_value(backend):
    large = b"x" * (5 * 1024 * 1024)  # 5MB — GridFS handles this natively
    await backend.set("large", large)
    result = await backend.get("large")
    assert result == large


@requires_mongodb
async def test_dict_value(backend):
    entry = {"data": b"image bytes", "content_type": "image/webp"}
    await backend.set("img3", entry)
    result = await backend.get("img3")
    assert result == entry


@requires_mongodb
async def test_overwrite(backend):
    await backend.set("img4", b"old")
    await backend.set("img4", b"new")
    assert await backend.get("img4") == b"new"


@requires_mongodb
async def test_size_bytes(backend):
    await backend.set("img5", b"x" * 1000)
    size = await backend.size_bytes()
    assert size > 0


@requires_mongodb
async def test_ttl_expiry(backend):
    import asyncio
    await backend.set("short", b"data", ttl_seconds=1)
    assert await backend.get("short") == b"data"
    await asyncio.sleep(1.1)
    assert await backend.get("short") is None
