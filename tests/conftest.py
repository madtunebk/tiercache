"""
Shared fixtures for integration tests.

Run services first:
    docker compose up -d

Then run integration tests:
    pytest tests/ -m integration -v

Unit tests (no services needed):
    pytest tests/ -m "not integration" -v
"""

import asyncio
import socket

import pytest


def _service_up(host: str, port: int) -> bool:
    """Check if a TCP service is reachable."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def requires_minio(fn):
    return pytest.mark.skipif(
        not _service_up("localhost", 9000),
        reason="MinIO not running — start with: docker compose up -d minio",
    )(pytest.mark.integration(fn))


def requires_mongodb(fn):
    return pytest.mark.skipif(
        not _service_up("localhost", 27017),
        reason="MongoDB not running — start with: docker compose up -d mongodb",
    )(pytest.mark.integration(fn))
