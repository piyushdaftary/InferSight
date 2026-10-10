"""Recommendations routes.

GET   /api/v1/recommendations           — list with filters
GET   /api/v1/recommendations/{rec_id}  — get single recommendation
PATCH /api/v1/recommendations/{rec_id}  — update status
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from infersight.api.auth import require_api_key
from infersight.plugins.base import Recommendation

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

_VALID_STATUSES = {"open", "acknowledged", "applied", "dismissed"}


class StatusUpdate(BaseModel):
    status: str


@router.get("", response_model=list[Recommendation])
async def list_recommendations(
    request: Request,
    deployment_id: list[str] | None = Query(default=None),
    status_filter: list[str] | None = Query(
        default=None, alias="status", description="open | acknowledged | applied | dismissed"
    ),
    _: None = Depends(require_api_key),
) -> list[Recommendation]:
    """List recommendations, optionally filtered by deployment and status."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    return await storage.query_recommendations(
        deployment_ids=deployment_id or None,
        status=status_filter or None,
    )


@router.get("/{rec_id}", response_model=Recommendation)
async def get_recommendation(
    rec_id: str,
    request: Request,
    _: None = Depends(require_api_key),
) -> Recommendation:
    """Get a specific recommendation by ID."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    results = await storage.query_recommendations(deployment_ids=None, status=None)
    for rec in results:
        if rec.rec_id == rec_id:
            return rec
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Recommendation '{rec_id}' not found",
    )


@router.patch("/{rec_id}", response_model=Recommendation)
async def update_recommendation_status(
    rec_id: str,
    request: Request,
    body: StatusUpdate = Body(...),
    _: None = Depends(require_api_key),
) -> Recommendation:
    """Update the status of a recommendation."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{body.status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    try:
        return await storage.update_recommendation(rec_id, body.status)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation '{rec_id}' not found",
        ) from None
