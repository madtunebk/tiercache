import pytest
from tiercache import CacheManager
from tiercache.backends.ram import RamBackend
from tiercache.backends.dry.local import LocalBackend
from tiercache.tracking.sqlite import SQLiteTracking


@pytest.fixture
def cache(tmp_path):
    return CacheManager(
        hot=RamBackend(ttl_seconds=14400, max_size_bytes=100 * 1024 * 1024),
        cold=RamBackend(ttl_seconds=86400, max_size_bytes=500 * 1024 * 1024),
        dry=LocalBackend(base_path=str(tmp_path / "dry"), max_size_bytes=1024 ** 3),
        tracking=SQLiteTracking(path=str(tmp_path / "index.db")),
    )


async def test_set_and_get_from_hot(cache):
    await cache.set("img1", b"imagedata")
    result = await cache.get("img1")
    assert result == b"imagedata"


async def test_miss_returns_none(cache):
    assert await cache.get("nonexistent") is None


async def test_cold_promotion(cache):
    # Write directly to cold tier
    await cache._cold.set("img2", b"colddata")
    # get should find it in cold and promote to hot
    result = await cache.get("img2")
    assert result == b"colddata"
    # Now it should be in hot
    hot_result = await cache._hot.get("img2")
    assert hot_result == b"colddata"


async def test_dry_promotion(cache):
    # Write directly to dry tier
    await cache._dry.set("img3", b"drydata")
    result = await cache.get("img3")
    assert result == b"drydata"
    # Now it should be in hot
    hot_result = await cache._hot.get("img3")
    assert hot_result == b"drydata"


async def test_delete_removes_from_all_tiers(cache):
    await cache.set("img4", b"data")
    await cache._cold.set("img4", b"data")
    await cache._dry.set("img4", b"data")
    await cache.delete("img4")
    assert await cache.get("img4") is None


async def test_flush_hot_only(cache):
    await cache.set("a", b"1")
    await cache._cold.set("b", b"2")
    await cache.flush(tier="hot")
    assert await cache._hot.get("a") is None
    assert await cache._cold.get("b") == b"2"


async def test_stats_keys(cache):
    await cache.set("k", b"v")
    await cache.get("k")
    await cache.get("missing")
    stats = await cache.stats()
    assert "hot_hits" in stats
    assert "cold_hits" in stats
    assert "dry_hits" in stats
    assert "misses" in stats


async def test_ttl_hours_override(cache):
    await cache.set("key", b"val", ttl_hours=0)
    # ttl_hours=0 → 0 seconds → treated as no expiry in TTLResolver
    result = await cache.get("key")
    assert result == b"val"


async def test_context_manager_close(tmp_path):
    c = CacheManager(
        hot=RamBackend(ttl_seconds=60, max_size_bytes=1024),
        cold=RamBackend(ttl_seconds=60, max_size_bytes=1024),
        dry=LocalBackend(base_path=str(tmp_path), max_size_bytes=1024),
        tracking=SQLiteTracking(path=str(tmp_path / "idx.db")),
    )
    await c.close()  # should not raise
