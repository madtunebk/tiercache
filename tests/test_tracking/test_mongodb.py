"""
Integration tests for MongoDB tracking backend.

Requires MongoDB running:
    docker compose up -d mongodb
"""

import pytest
from tests.conftest import requires_mongodb

MONGO_URI = "mongodb://localhost:27017"
DATABASE  = "tiercache_test"


@pytest.fixture
async def tracker():
    from smartcache.tracking.mongodb import MongoDBTracking
    t = MongoDBTracking(uri=MONGO_URI, database=DATABASE)
    yield t
    await t.close()


@requires_mongodb
async def test_record_and_stats(tracker):
    await tracker.record_set("key1", "hot")
    await tracker.record_hit("key1", "hot")
    await tracker.record_hit("key1", "cold")
    await tracker.record_miss("key2")
    stats = await tracker.get_stats()
    assert stats["hot_hits"] >= 1
    assert stats["cold_hits"] >= 1
    assert stats["misses"] >= 1


@requires_mongodb
async def test_record_delete(tracker):
    await tracker.record_set("key1", "hot")
    await tracker.record_delete("key1")


@requires_mongodb
async def test_tags_stored(tracker):
    await tracker.record_set("key1", "hot", tags={"type": "thumbnail"})


@requires_mongodb
async def test_multiple_tiers(tracker):
    await tracker.record_hit("k", "hot")
    await tracker.record_hit("k", "cold")
    await tracker.record_hit("k", "dry")
    stats = await tracker.get_stats()
    assert stats["hot_hits"] >= 1
    assert stats["cold_hits"] >= 1
    assert stats["dry_hits"] >= 1
