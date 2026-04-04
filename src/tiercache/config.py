from __future__ import annotations

from typing import Any

import yaml

from .backends.base import AbstractBackend
from .manager import CacheManager, TTLResolver
from .tracking.base import AbstractTracking

_GB = 1024 ** 3


def load_config(path: str) -> CacheManager:
    with open(path) as f:
        cfg = yaml.safe_load(f)

    hot     = _build_ram_backend(cfg.get("hot_cache", {}), cfg)
    cold    = _build_ram_backend(cfg.get("cold_cache", {}), cfg)
    dry     = _build_dry_backend(cfg.get("dry_cache", {}), cfg)
    tracking = _build_tracking(cfg.get("tracking", {}), cfg)
    resolver = _build_ttl_resolver(cfg)

    return CacheManager(
        hot=hot,
        cold=cold,
        dry=dry,
        tracking=tracking,
        ttl_resolver=resolver,
    )


# ------------------------------------------------------------------
# Backend builders
# ------------------------------------------------------------------

def _build_ram_backend(tier_cfg: dict, root_cfg: dict) -> AbstractBackend:
    backend = tier_cfg.get("backend", "ram")
    ttl_seconds = int(tier_cfg.get("ttl_hours", 4) * 3600)
    max_bytes   = int(tier_cfg.get("max_size_gb", 2) * _GB)

    if backend == "ram":
        from .backends.ram import RamBackend
        return RamBackend(ttl_seconds=ttl_seconds, max_size_bytes=max_bytes)

    if backend == "memcached":
        from .backends.memcached import MemcachedBackend
        mc_cfg = root_cfg.get("memcached", {})
        return MemcachedBackend(
            host=mc_cfg.get("host", "localhost"),
            port=mc_cfg.get("port", 11211),
            ttl_seconds=ttl_seconds,
            max_size_bytes=max_bytes,
        )

    raise ValueError(f"Unknown hot/cold backend: {backend!r}. Options: ram, memcached")


def _build_dry_backend(tier_cfg: dict, root_cfg: dict) -> AbstractBackend:
    backend     = tier_cfg.get("backend", "local")
    max_bytes   = int(tier_cfg.get("max_size_gb", 100) * _GB)
    ttl_seconds = _ttl_to_seconds(tier_cfg.get("ttl_hours"))

    if backend == "local":
        from .backends.dry.local import LocalBackend
        return LocalBackend(
            base_path=tier_cfg.get("path", "/var/cache/smartcache/dry"),
            max_size_bytes=max_bytes,
        )

    if backend == "s3":
        from .backends.dry.s3 import S3Backend
        s3_cfg = root_cfg.get("s3", {})
        return S3Backend(
            bucket=s3_cfg["bucket"],
            endpoint_url=s3_cfg.get("endpoint_url"),
            access_key=s3_cfg.get("access_key"),
            secret_key=s3_cfg.get("secret_key"),
            prefix=s3_cfg.get("prefix", "smartcache/"),
        )

    if backend == "mongodb":
        from .backends.dry.mongodb import MongoDBBackend
        mongo_cfg = root_cfg.get("mongodb", {})
        return MongoDBBackend(
            uri=mongo_cfg.get("uri", "mongodb://localhost:27017"),
            database=mongo_cfg.get("database", "smartcache"),
        )

    raise ValueError(f"Unknown dry backend: {backend!r}. Options: local, s3, mongodb")


def _build_tracking(tracking_cfg: dict, root_cfg: dict) -> AbstractTracking:
    backend = tracking_cfg.get("backend", "sqlite")

    if backend == "sqlite":
        from .tracking.sqlite import SQLiteTracking
        return SQLiteTracking(
            path=tracking_cfg.get("path", "/var/cache/smartcache/index.db")
        )

    if backend == "redis":
        from .tracking.redis import RedisTracking
        r_cfg = root_cfg.get("redis", {})
        return RedisTracking(
            host=r_cfg.get("host", "localhost"),
            port=r_cfg.get("port", 6379),
            db=r_cfg.get("db", 0),
        )

    if backend == "postgres":
        from .tracking.postgres import PostgresTracking
        return PostgresTracking(dsn=tracking_cfg["dsn"])

    if backend == "mongodb":
        from .tracking.mongodb import MongoDBTracking
        mongo_cfg = root_cfg.get("mongodb", {})
        return MongoDBTracking(
            uri=mongo_cfg.get("uri", "mongodb://localhost:27017"),
            database=mongo_cfg.get("database", "smartcache"),
        )

    raise ValueError(
        f"Unknown tracking backend: {backend!r}. Options: sqlite, redis, postgres, mongodb"
    )


def _build_ttl_resolver(root_cfg: dict) -> TTLResolver:
    hot_ttl  = _ttl_to_seconds(root_cfg.get("hot_cache",  {}).get("ttl_hours", 4))
    cold_ttl = _ttl_to_seconds(root_cfg.get("cold_cache", {}).get("ttl_hours", 24))
    dry_ttl  = _ttl_to_seconds(root_cfg.get("dry_cache",  {}).get("ttl_hours", 168))  # 7 days

    defaults = {"hot": hot_ttl, "cold": cold_ttl, "dry": dry_ttl}

    rules = []
    for rule in root_cfg.get("ttl_rules", []):
        resolved: dict[str, Any] = {"tag": rule.get("tag", {})}
        for tier in ("hot", "cold", "dry"):
            key = f"{tier}_ttl_hours"
            if key in rule:
                resolved[tier] = _ttl_to_seconds(rule[key])
        rules.append(resolved)

    return TTLResolver(defaults=defaults, rules=rules)


def _ttl_to_seconds(ttl_hours: Any) -> int | None:
    if ttl_hours is None:
        return None
    return int(float(ttl_hours) * 3600)
