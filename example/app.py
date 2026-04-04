"""
SmartCache — example HTTP app using FastAPI.

Endpoints:
  GET    /cache/{key}           → fetch a cached value (served with correct Content-Type)
  PUT    /cache/{key}           → store a value (raw bytes body)
  DELETE /cache/{key}           → remove a key from all tiers
  GET    /stats                 → hit/miss stats + tier sizes
  DELETE /cache                 → flush entire cache (all tiers)

Query params for PUT:
  ttl_hours  float   per-key TTL override  e.g. ?ttl_hours=2
  tag_type   str     tag for TTL rules     e.g. ?tag_type=thumbnail

Content-Type on PUT:
  Pass the Content-Type header and it will be stored and served back on GET.
  If omitted, it is guessed from the key name (e.g. corndude.png → image/png).

Run:
  uvicorn example.app:app --reload --port 8989
"""

import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response

from tiercache import CacheManager

# Override with TIERCACHE_CONFIG env var to switch between configs:
#   TIERCACHE_CONFIG=example/config_ram.yaml        uvicorn ...
#   TIERCACHE_CONFIG=example/config_memcached.yaml  uvicorn ...
_DEFAULT_CONFIG = Path(__file__).parent / "config_ram.yaml"
_CONFIG = Path(os.environ.get("TIERCACHE_CONFIG", _DEFAULT_CONFIG))
_cache: Optional[CacheManager] = None

_FALLBACK_CT = "application/octet-stream"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cache
    _cache = CacheManager.from_config(str(_CONFIG))
    yield
    await _cache.close()


app = FastAPI(title="SmartCache demo", lifespan=lifespan)


def get_cache() -> CacheManager:
    if _cache is None:
        raise RuntimeError("Cache not initialised")
    return _cache


def _detect_content_type(key: str, request: Request) -> str:
    """Use the request Content-Type if provided, otherwise guess from the key name."""
    ct = request.headers.get("content-type")
    if ct and ct != _FALLBACK_CT:
        return ct
    guessed, _ = mimetypes.guess_type(key)
    return guessed or _FALLBACK_CT


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/cache/{key}")
async def cache_get(key: str):
    entry = await get_cache().get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Key '{key}' not found in cache")
    data: bytes = entry["data"]
    content_type: str = entry["content_type"]
    return Response(content=data, media_type=content_type)


@app.put("/cache/{key}", status_code=204)
async def cache_put(
    key: str,
    request: Request,
    ttl_hours: Optional[float] = Query(default=None, description="TTL override in hours"),
    tag_type: Optional[str]   = Query(default=None, description="Tag type for TTL rules"),
):
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Request body is empty")

    content_type = _detect_content_type(key, request)
    entry = {"data": body, "content_type": content_type}
    tags = {"type": tag_type} if tag_type else None
    await get_cache().set(key, entry, ttl_hours=ttl_hours, tags=tags)
    return Response(status_code=204)


@app.delete("/cache/{key}", status_code=204)
async def cache_delete(key: str):
    await get_cache().delete(key)
    return Response(status_code=204)


@app.delete("/cache", status_code=204)
async def cache_flush(tier: str = Query(default="all", description="hot | cold | dry | all")):
    if tier not in ("hot", "cold", "dry", "all"):
        raise HTTPException(status_code=400, detail="tier must be one of: hot, cold, dry, all")
    await get_cache().flush(tier=tier)
    return Response(status_code=204)


@app.get("/stats")
async def stats():
    return await get_cache().stats()
