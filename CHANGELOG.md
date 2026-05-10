# Changelog

All notable changes to TierCache will be documented here.

---

## [0.1.3] - 2026-04-04

### Fixed
- Dry cache default TTL changed from `None` (no expiry) to `168h` (7 days).
  A cache with unlimited storage is not a cache — set `ttl_hours: null` in
  config to restore the old behavior if needed.

---

## [0.1.2] - 2026-04-04

### Fixed
- Added `readme = "README.md"` to `pyproject.toml` so PyPI shows the full
  project description instead of a blank page.

---

## [0.1.1] - 2026-04-04

### Changed
- Renamed package from `smartcache` to `tiercache` on PyPI and GitHub.
- Renamed `src/smartcache/` to `src/tiercache/` — all imports updated.
- Updated all optional extras references from `smartcache[x]` to `tiercache[x]`.

---

## [0.1.0] - 2026-04-04

### Added
- Three-tier cache: hot → cold → dry with configurable backends per tier.
- Hot / Cold backends: `ram` (in-process dict, LRU eviction) and `memcached`
  (shared pool, multi-process/server).
- Dry backends: `local` (filesystem), `s3` (S3-compatible), `mongodb` (GridFS).
- Tracking backends: `redis` (default), `sqlite`, `postgres`, `mongodb`.
- TTL priority chain: per-key override → tag rules → tier default → global default.
- Automatic demotion to dry cache on hot/cold LRU eviction (failsafe).
- Promotion from dry → hot on cache miss.
- Async-first API (`get`, `set`, `delete`, `flush`, `stats`).
- Sync wrappers for Flask/Django (`get_sync`, `set_sync`, etc.).
- Safe msgpack serialization — no pickle, no arbitrary code execution on load.
- YAML config with `CacheManager.from_config("tiercache.yaml")`.
- Optional dependencies via extras: `[memcached]`, `[redis]`, `[s3]`,
  `[mongodb]`, `[postgres]`, `[all]`.
- Example FastAPI HTTP app with Content-Type detection and stats endpoint.
- Integration tests for S3 (MinIO) and MongoDB backends.
- Docker Compose setup for local MinIO + MongoDB testing.
- Chunking support in Memcached backend for values larger than 900KB.
