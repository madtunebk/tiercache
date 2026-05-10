# TierCache TODO

## Hot-only mode cleanup

- Add a built-in `NullBackend` under `tiercache.backends.null`.
- Export `NullBackend` from `tiercache.__init__`.
- Use `NullBackend` in app code instead of defining a local dummy backend.

## CacheManager ergonomics

- Consider making `cold` and `dry` optional in `CacheManager`.
- If `cold` or `dry` are omitted, default them to `NullBackend()` internally.
- Keep the current hot-only setup as a first-class supported configuration.

```python
class NullBackend(AbstractBackend):
    async def get(self, key: str):
        return None

    async def set(self, key: str, value, ttl_seconds=None) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def size_bytes(self) -> int:
        return 0

    async def close(self) -> None:
        return None
```       

## Docs

- Document the hot-only cache pattern.
- Document that `set()` currently writes only to `hot`.
- Clarify tier behavior for `hot`, `cold`, and `dry` in the README.
- Clarify that RAM TTL expiry drops entries unless another tier already has them.

## Future backends

- Evaluate Redis or Memcached for a shared `cold` tier.
- Evaluate MongoDB, local disk, or object storage for a more durable `dry` tier.
