# TierCache

RAM-first three-tier cache for Python. Designed to keep your SSD/HDD out of the hot path.

```
pip install tiercache
```

---

## How it works

Every request walks down the tier chain until a hit is found:

```
GET request
  │
  ├─ Hot cache  (RAM, 2GB, 4h TTL)   ──── HIT → serve, reset TTL
  │                                   MISS ↓
  ├─ Cold cache (RAM, 10GB, 24h TTL) ──── HIT → promote to hot → serve
  │                                   MISS ↓
  └─ Dry cache  (Disk / S3 / MongoDB) ─── HIT → promote to hot → serve
                                      MISS → return None (fetch from origin)

SET request
  └─ Writes to hot only (zero disk I/O)
       │
       └─ When hot evicts or expires → auto-demote to dry (failsafe, background)
```

Both hot and cold live entirely in RAM. Dry is only hit on a true cache miss.
After a server restart, the first GET recovers each item from dry back into hot.

---

## Installation

```bash
# Base (RAM + local filesystem + SQLite tracking)
pip install tiercache

# With Memcached backends (multi-process / multi-server)
pip install "tiercache[memcached]"

# With Redis tracking
pip install "tiercache[redis]"

# With S3 dry cache
pip install "tiercache[s3]"

# With MongoDB
pip install "tiercache[mongodb]"

# With PostgreSQL tracking
pip install "tiercache[postgres]"

# Everything
pip install "tiercache[all]"
```

---

## Quick start

### From a config file

```python
from tiercache import CacheManager

cache = CacheManager.from_config("tiercache.yaml")

# Async (FastAPI, aiohttp, Sanic)
value = await cache.get("my-key")
await cache.set("my-key", data)

# Sync (Flask, Django)
value = cache.get_sync("my-key")
cache.set_sync("my-key", data)
```

### In code

```python
from tiercache import CacheManager
from tiercache.backends.ram import RamBackend
from tiercache.backends.dry.local import LocalBackend
from tiercache.tracking.sqlite import SQLiteTracking

cache = CacheManager(
    hot=RamBackend(ttl_seconds=14400, max_size_bytes=2 * 1024**3),
    cold=RamBackend(ttl_seconds=86400, max_size_bytes=10 * 1024**3),
    dry=LocalBackend(base_path="/var/cache/myapp/dry", max_size_bytes=100 * 1024**3),
    tracking=SQLiteTracking(path="/var/cache/myapp/index.db"),
)
```

---

## Configuration

```yaml
# tiercache.yaml

hot_cache:
  backend: ram          # ram | memcached
  ttl_hours: 4
  max_size_gb: 2

cold_cache:
  backend: ram          # ram | memcached
  ttl_hours: 24
  max_size_gb: 10

dry_cache:
  backend: local        # local | s3 | mongodb
  max_size_gb: 100
  path: /var/cache/myapp/dry

tracking:
  backend: sqlite       # sqlite | redis | postgres | mongodb

# Optional: TTL rules by tag
ttl_rules:
  - tag: { type: thumbnail }
    hot_ttl_hours: 1
    cold_ttl_hours: 6
  - tag: { type: raw }
    hot_ttl_hours: 8
    cold_ttl_hours: 48
```

### Memcached (multi-process / multi-server)

```yaml
hot_cache:
  backend: memcached
  ttl_hours: 4
  max_size_gb: 2

cold_cache:
  backend: memcached
  ttl_hours: 24
  max_size_gb: 10

memcached:
  host: localhost
  port: 11211
```

### S3 dry cache

```yaml
dry_cache:
  backend: s3

s3:
  endpoint_url: https://s3.amazonaws.com   # or MinIO, Cloudflare R2, etc.
  bucket: my-cache-bucket
  access_key: ...
  secret_key: ...
```

### MongoDB dry cache + tracking

```yaml
dry_cache:
  backend: mongodb

tracking:
  backend: mongodb

mongodb:
  uri: mongodb://localhost:27017
  database: tiercache
```

### Redis tracking

```yaml
tracking:
  backend: redis

redis:
  host: localhost
  port: 6379
  db: 0
```

---

## API

```python
# Fetch a value (returns None on miss)
value = await cache.get("key")

# Store a value using tier default TTL
await cache.set("key", data)

# Override TTL for this key only
await cache.set("key", data, ttl_hours=2)

# Tag-based TTL (matched against ttl_rules in config)
await cache.set("key", data, tags={"type": "thumbnail"})

# Delete from all tiers
await cache.delete("key")

# Flush a specific tier or all
await cache.flush(tier="hot")   # hot | cold | dry | all

# Hit/miss stats + tier sizes
stats = await cache.stats()
# {
#   "hot_hits": 120, "cold_hits": 30, "dry_hits": 5, "misses": 2,
#   "hot_size_bytes": 1048576, "cold_size_bytes": 0, "dry_size_bytes": 4096
# }

# Sync equivalents (Flask, Django)
cache.get_sync("key")
cache.set_sync("key", data, ttl_hours=2, tags={"type": "thumbnail"})
cache.delete_sync("key")
cache.flush_sync(tier="hot")
cache.stats_sync()

# Always close on shutdown
await cache.close()
```

### TTL priority (highest wins)

| Priority | Example |
|---|---|
| 1. Per-key override | `cache.set("k", v, ttl_hours=1)` |
| 2. Tag rule | `cache.set("k", v, tags={"type": "thumbnail"})` → matched in config |
| 3. Tier default | `hot_cache.ttl_hours` in yaml |
| 4. Global default | hot: 4h, cold: 24h, dry: no expiry |

---

## Backends

| Tier | Backend | Notes |
|---|---|---|
| Hot / Cold | `ram` | In-process, single server |
| Hot / Cold | `memcached` | Shared pool, multi-process/server |
| Dry | `local` | Local filesystem, SSD/HDD |
| Dry | `s3` | AWS S3, MinIO, Cloudflare R2 |
| Dry | `mongodb` | GridFS + native TTL indexes |
| Tracking | `sqlite` | Zero deps, single machine |
| Tracking | `redis` | In-memory, fast, recommended |
| Tracking | `postgres` | Production relational |
| Tracking | `mongodb` | Flexible schema, TTL indexes |

---

## Example HTTP app (FastAPI)

```bash
pip install fastapi uvicorn

# Single process (RAM)
uvicorn example.app:app --port 8989

# Multi-process (Memcached — shared cache across all workers)
SMARTCACHE_CONFIG=example/config_memcached.yaml \
uvicorn example.app:app --workers 4 --port 8989
```

```bash
# Store an image
curl -X PUT "http://localhost:8989/cache/photo.png?tag_type=thumbnail" \
    -H "Content-Type: image/png" \
    --data-binary @photo.png

# Fetch it (opens directly in browser)
curl "http://localhost:8989/cache/photo.png" -o out.png

# Stats
curl "http://localhost:8989/stats"
```

---

## Why not just use Redis for everything?

Redis is great but it is a network service — every cache hit is a round trip.
TierCache's RAM backend (`ram`) stores values directly in the Python process
memory, making hot-path lookups **microsecond-range** with zero network overhead.

Use `memcached` when you need shared cache across multiple processes or servers.
Use `redis` for tracking metadata (tiny footprint, fast, persistent).

---

## License

MIT
