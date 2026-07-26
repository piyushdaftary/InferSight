"""Tests for the FastAPI application factory."""

from typing import cast
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from infersight.app import create_app
from infersight.storage.base import StorageBackend


def test_health_is_always_available() -> None:
    """Health checks succeed even when storage has not been configured."""
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_missing_storage() -> None:
    """Readiness is unavailable until a storage backend is configured."""
    client = TestClient(create_app())

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Storage backend is not configured"


def test_ready_probes_storage_connectivity() -> None:
    """Readiness succeeds after a storage query succeeds."""
    storage = AsyncMock(spec=StorageBackend)
    storage.query_metrics.return_value = []
    client = TestClient(create_app(storage=cast(StorageBackend, storage)))

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    storage.query_metrics.assert_awaited_once()


def test_ready_reports_storage_failures() -> None:
    """Readiness does not expose storage errors to callers."""
    storage = AsyncMock(spec=StorageBackend)
    storage.query_metrics.side_effect = RuntimeError("database unavailable")
    client = TestClient(create_app(storage=cast(StorageBackend, storage)))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Storage backend is unavailable"
