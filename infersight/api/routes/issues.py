"""Issues routes.

GET  /api/v1/issues                   — list issues with filters
GET  /api/v1/issues/{issue_id}        — get a single issue
POST /api/v1/issues/{issue_id}/clear  — mark an issue as cleared
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from infersight.api.auth import require_api_key
from infersight.plugins.base import Issue

router = APIRouter(prefix="/api/v1/issues", tags=["issues"])


@router.get("", response_model=list[Issue])
async def list_issues(
    request: Request,
    deployment_id: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None, description="info | warning | critical"),
    active_only: bool = Query(default=True, description="Exclude cleared issues"),
    _: None = Depends(require_api_key),
) -> list[Issue]:
    """List issues, optionally filtered by deployment, severity, and active status."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    return await storage.query_issues(
        deployment_ids=deployment_id or None,
        severity=severity or None,
        active_only=active_only,
    )


@router.get("/{issue_id}", response_model=Issue)
async def get_issue(
    issue_id: str,
    request: Request,
    _: None = Depends(require_api_key),
) -> Issue:
    """Get a specific issue by its issue_id."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    results = await storage.query_issues(
        deployment_ids=None,
        severity=None,
        active_only=False,
    )
    for issue in results:
        if issue.issue_id == issue_id:
            return issue
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Issue '{issue_id}' not found",
    )


@router.post("/{issue_id}/clear", response_model=Issue)
async def clear_issue(
    issue_id: str,
    request: Request,
    _: None = Depends(require_api_key),
) -> Issue:
    """Mark an issue as cleared (sets cleared_at to now)."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )

    results = await storage.query_issues(
        deployment_ids=None,
        severity=None,
        active_only=False,
    )
    target: Issue | None = None
    for issue in results:
        if issue.issue_id == issue_id:
            target = issue
            break

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found",
        )

    cleared = target.model_copy(update={"cleared_at": datetime.now(UTC)})
    await storage.write_issues([cleared])
    return cleared
