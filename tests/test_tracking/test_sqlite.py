import pytest
from tiercache.tracking.sqlite import SQLiteTracking


@pytest.fixture
async def tracker(tmp_path):
    t = SQLiteTracking(path=str(tmp_path / "test.db"))
    yield t
    await t.close()


async def test_record_and_stats(tracker):
    await tracker.record_set("key1", "hot")
    await tracker.record_hit("key1", "hot")
    await tracker.record_hit("key1", "hot")
    await tracker.record_miss("key2")
    stats = await tracker.get_stats()
    assert stats["hot_hits"] == 2
    assert stats["misses"] == 1


async def test_record_delete(tracker):
    await tracker.record_set("key1", "hot")
    await tracker.record_delete("key1")
    # No error expected; key simply removed


async def test_tags_stored(tracker):
    await tracker.record_set("key1", "hot", tags={"type": "thumbnail"})
    # Just verify no exception; tags are stored internally


async def test_multiple_tiers(tracker):
    await tracker.record_hit("k", "hot")
    await tracker.record_hit("k", "cold")
    await tracker.record_hit("k", "dry")
    stats = await tracker.get_stats()
    assert stats["hot_hits"] == 1
    assert stats["cold_hits"] == 1
    assert stats["dry_hits"] == 1
