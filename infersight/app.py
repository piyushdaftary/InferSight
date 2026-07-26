"""FastAPI application factory and operational health endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles

from infersight.config import InferSightConfig
from infersight.storage.base import StorageBackend


def create_app(
    config: InferSightConfig | None = None,
    storage: StorageBackend | None = None,
) -> FastAPI:
    """Create the InferSight API application.

    Authentication middleware is intentionally not attached here while both
    API-key and OIDC authentication remain disabled by default. Health checks
    always remain unauthenticated so container orchestrators can probe them.
    """
    settings = config or InferSightConfig()
    app = FastAPI(title="InferSight", version="0.1.0")
    app.state.storage = storage

    if settings.server.static_dir:
        static_dir = Path(settings.server.static_dir).expanduser()
        if static_dir.is_dir():
            app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Return process health without requiring authentication."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        """Return readiness after confirming that storage is reachable."""
        backend: StorageBackend | None = app.state.storage
        if backend is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage backend is not configured",
            )
        try:
            now = datetime.now(UTC)
            await backend.query_metrics(None, now, now, limit=1)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage backend is unavailable",
            ) from exc
        return {"status": "ready"}

    return app
