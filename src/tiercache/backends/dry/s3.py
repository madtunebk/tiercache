import time
from typing import Any, Optional

from ...serializer import dumps, loads
from ..base import AbstractBackend

_META_TTL_KEY    = "x-smartcache-ttl"
_META_CREATED_KEY = "x-smartcache-created"


class S3Backend(AbstractBackend):
    """
    S3-compatible dry cache using aioboto3.
    TTL is stored as object metadata and checked on get.

    Compatible with: AWS S3, MinIO, Cloudflare R2, and any S3-compatible service.

    Requires: pip install tiercache[s3]
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        prefix: str = "smartcache/",
    ) -> None:
        try:
            import aioboto3
        except ImportError:
            raise ImportError(
                "S3 backend requires aioboto3. "
                "Install it with: pip install tiercache[s3]"
            )
        self._aioboto3 = aioboto3
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._prefix = prefix
        self._session: Optional[Any] = None

    def _object_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _session_kwargs(self) -> dict:
        kwargs: dict = {}
        if self._access_key:
            kwargs["aws_access_key_id"] = self._access_key
        if self._secret_key:
            kwargs["aws_secret_access_key"] = self._secret_key
        return kwargs

    async def get(self, key: str) -> Optional[Any]:
        session = self._aioboto3.Session(**self._session_kwargs())
        async with session.client("s3", endpoint_url=self._endpoint_url) as s3:
            try:
                response = await s3.get_object(
                    Bucket=self._bucket, Key=self._object_key(key)
                )
            except s3.exceptions.NoSuchKey:
                return None
            except Exception:
                return None

            meta = response.get("Metadata", {})
            ttl = meta.get(_META_TTL_KEY)
            created = meta.get(_META_CREATED_KEY)
            if ttl and created:
                if time.time() > float(created) + int(ttl):
                    await self.delete(key)
                    return None

            body = await response["Body"].read()
            return loads(body)

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        session = self._aioboto3.Session(**self._session_kwargs())
        raw = dumps(value)
        meta: dict[str, str] = {_META_CREATED_KEY: str(time.time())}
        if ttl_seconds:
            meta[_META_TTL_KEY] = str(ttl_seconds)
        async with session.client("s3", endpoint_url=self._endpoint_url) as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=self._object_key(key),
                Body=raw,
                Metadata=meta,
            )

    async def delete(self, key: str) -> None:
        session = self._aioboto3.Session(**self._session_kwargs())
        async with session.client("s3", endpoint_url=self._endpoint_url) as s3:
            await s3.delete_object(Bucket=self._bucket, Key=self._object_key(key))

    async def flush(self) -> None:
        session = self._aioboto3.Session(**self._session_kwargs())
        async with session.client("s3", endpoint_url=self._endpoint_url) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
                objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if objects:
                    await s3.delete_objects(
                        Bucket=self._bucket, Delete={"Objects": objects}
                    )

    async def size_bytes(self) -> int:
        total = 0
        session = self._aioboto3.Session(**self._session_kwargs())
        async with session.client("s3", endpoint_url=self._endpoint_url) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
                for obj in page.get("Contents", []):
                    total += obj.get("Size", 0)
        return total

    async def keys(self) -> list[str]:
        keys: list[str] = []
        session = self._aioboto3.Session(**self._session_kwargs())
        async with session.client("s3", endpoint_url=self._endpoint_url) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
                for obj in page.get("Contents", []):
                    object_key = obj.get("Key")
                    if not object_key:
                        continue
                    head = await s3.head_object(Bucket=self._bucket, Key=object_key)
                    meta = head.get("Metadata", {})
                    ttl = meta.get(_META_TTL_KEY)
                    created = meta.get(_META_CREATED_KEY)
                    if ttl and created and time.time() > float(created) + int(ttl):
                        await s3.delete_object(Bucket=self._bucket, Key=object_key)
                        continue
                    if object_key.startswith(self._prefix):
                        keys.append(object_key[len(self._prefix):])
        return keys

    async def close(self) -> None:
        pass
