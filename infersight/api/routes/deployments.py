"""Deployments routes.

GET /api/v1/deployments                      — list all configured deployments
GET /api/v1/deployments/{id}                 — get a single deployment
GET /api/v1/deployments/{id}/metrics/latest  — latest metric snapshot
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from infersight.api.auth import require_api_key
from infersight.config import DeploymentConfig
from infersight.schema import CanonicalMetric

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])


class DeploymentResponse(BaseModel):
    id: str
    name: str
    engine: str
    endpoint: str
    collection_mode: str
    labels: dict[str, str]


def _to_response(d: DeploymentConfig) -> DeploymentResponse:
    return DeploymentResponse(
        id=d.id,
        name=d.name or d.id,
        engine=d.engine,
        endpoint=d.endpoint,
        collection_mode=d.collection_mode,
        labels=d.labels,
    )


def _get_deployments(request: Request) -> list[DeploymentConfig]:
    from infersight.config import InferSightConfig

    config: InferSightConfig | None = getattr(request.app.state, "config", None)
    return config.deployments if config is not None else []


@router.get("", response_model=list[DeploymentResponse])
async def list_deployments(
    request: Request,
    _: None = Depends(require_api_key),
) -> list[DeploymentResponse]:
    """List all configured deployments."""
    return [_to_response(d) for d in _get_deployments(request)]


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: str,
    request: Request,
    _: None = Depends(require_api_key),
) -> DeploymentResponse:
    """Get a single deployment by ID."""
    for d in _get_deployments(request):
        if d.id == deployment_id:
            return _to_response(d)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Deployment '{deployment_id}' not found",
    )


@router.get("/{deployment_id}/metrics/latest", response_model=CanonicalMetric | None)
async def get_latest_metrics(
    deployment_id: str,
    request: Request,
    _: None = Depends(require_api_key),
) -> CanonicalMetric | None:
    """Return the most recent metric snapshot for a deployment."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    now = datetime.now(UTC)
    results = await storage.query_metrics(
        deployment_ids=[deployment_id],
        start=now - timedelta(hours=1),
        end=now,
        limit=1,
    )
    return results[0] if results else None
