"""API key authentication dependency.

Applied to all /api/v1/* routes when auth.api_key_enabled is True.
/health and /ready are always public and never use this dependency.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_API_KEY_HEADER),
) -> None:
    """FastAPI dependency — raises 401 when API key auth is enabled and key is wrong."""
    from infersight.config import InferSightConfig

    config: InferSightConfig | None = getattr(request.app.state, "config", None)
    if config is None or not config.auth.api_key_enabled:
        return

    expected = config.auth.api_key.get_secret_value()
    if not expected:
        return

    if api_key is None or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
