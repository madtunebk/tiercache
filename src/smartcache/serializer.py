"""
Central serializer for SmartCache.
Uses msgpack instead of pickle — safe, fast, compact.
msgpack cannot execute code on deserialization unlike pickle.

Supported types: bytes, str, int, float, bool, None, list, dict.
This covers all SmartCache use cases (images, metadata dicts, etc.)
"""

import msgpack


def dumps(value: object) -> bytes:
    return msgpack.packb(value, use_bin_type=True)


def loads(data: bytes) -> object:
    return msgpack.unpackb(data, raw=False)
