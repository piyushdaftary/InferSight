"""Metrics routes.

GET /api/v1/metrics  — time-range query with deployment filter and pagination
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from infersight.api.auth import require_api_key
from infersight.schema import CanonicalMetric

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

_MAX_LIMIT = 1000
_DEFAULT_HOURS = 1


@router.get("", response_model=list[CanonicalMetric])
async def query_metrics(
    request: Request,
    deployment_id: list[str] | None = Query(default=None, description="Filter by deployment ID(s)"),
    start: datetime | None = Query(default=None, description="Start of time range (ISO 8601)"),
    end: datetime | None = Query(default=None, description="End of time range (ISO 8601)"),
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT, description="Max results to return"),
    _: None = Depends(require_api_key),
) -> list[CanonicalMetric]:
    """Query metric snapshots within a time range.

    Defaults to the last hour when start/end are omitted.
    Results are ordered oldest-first.
    """
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )

    now = datetime.now(UTC)
    resolved_end = end or now
    resolved_start = start or (resolved_end - timedelta(hours=_DEFAULT_HOURS))

    if resolved_start >= resolved_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must be before end",
        )

    return await storage.query_metrics(
        deployment_ids=deployment_id or None,
        start=resolved_start,
        end=resolved_end,
        limit=limit,
    )
