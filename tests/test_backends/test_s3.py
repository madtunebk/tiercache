"""
Integration tests for S3 dry backend against MinIO.

Requires MinIO running:
    docker compose up -d minio
"""

import pytest
from tests.conftest import requires_minio

ENDPOINT  = "http://localhost:9000"
BUCKET    = "tiercache-test"
ACCESS    = "minioadmin"
SECRET    = "minioadmin"


@pytest.fixture
async def backend():
    import aioboto3
    # Create bucket if it doesn't exist
    session = aioboto3.Session(
        aws_access_key_id=ACCESS,
        aws_secret_access_key=SECRET,
    )
    async with session.client("s3", endpoint_url=ENDPOINT) as s3:
        existing = [b["Name"] for b in (await s3.list_buckets())["Buckets"]]
        if BUCKET not in existing:
            await s3.create_bucket(Bucket=BUCKET)

    from tiercache.backends.dry.s3 import S3Backend
    b = S3Backend(
        bucket=BUCKET,
        endpoint_url=ENDPOINT,
        access_key=ACCESS,
        secret_key=SECRET,
        prefix="test/",
    )
    yield b
    await b.flush()


@requires_minio
async def test_set_and_get(backend):
    await backend.set("img1", b"hello s3")
    assert await backend.get("img1") == b"hello s3"


@requires_minio
async def test_miss_returns_none(backend):
    assert await backend.get("nonexistent") is None


@requires_minio
async def test_delete(backend):
    await backend.set("img2", b"data")
    await backend.delete("img2")
    assert await backend.get("img2") is None


@requires_minio
async def test_flush(backend):
    await backend.set("a", b"1")
    await backend.set("b", b"2")
    await backend.flush()
    assert await backend.get("a") is None
    assert await backend.get("b") is None


@requires_minio
async def test_large_value(backend):
    large = b"x" * (2 * 1024 * 1024)  # 2MB
    await backend.set("large", large)
    result = await backend.get("large")
    assert result == large


@requires_minio
async def test_dict_value(backend):
    entry = {"data": b"image bytes", "content_type": "image/png"}
    await backend.set("img3", entry)
    result = await backend.get("img3")
    assert result == entry


@requires_minio
async def test_size_bytes(backend):
    await backend.set("img4", b"x" * 1000)
    size = await backend.size_bytes()
    assert size > 0


@requires_minio
async def test_ttl_expiry(backend):
    import asyncio
    await backend.set("short", b"data", ttl_seconds=1)
    assert await backend.get("short") == b"data"
    await asyncio.sleep(1.1)
    assert await backend.get("short") is None
