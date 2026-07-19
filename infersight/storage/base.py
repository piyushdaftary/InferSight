"""Storage backends for InferSight metrics, issues, and recommendations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from infersight.plugins.base import Issue, Recommendation
from infersight.schema import CanonicalMetric


class StorageBackend(ABC):
    """Abstract storage interface for metrics, issues, and recommendations.

    All methods are async to support concurrent collection jobs.
    Concrete implementations: SQLiteBackend, PrometheusBackend, InfluxBackend.
    """

    @abstractmethod
    async def write_metrics(self, metrics: list[CanonicalMetric]) -> None:
        """Persist metric snapshots to storage."""

    @abstractmethod
    async def query_metrics(
        self,
        deployment_ids: list[str] | None,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[CanonicalMetric]:
        """Query metrics with filters and time range."""

    @abstractmethod
    async def write_issues(self, issues: list[Issue]) -> None:
        """Persist issue objects to storage."""

    @abstractmethod
    async def query_issues(
        self,
        deployment_ids: list[str] | None,
        severity: list[str] | None,
        active_only: bool,
    ) -> list[Issue]:
        """Query issues with filters."""

    @abstractmethod
    async def write_recommendations(self, recs: list[Recommendation]) -> None:
        """Persist recommendation objects to storage."""

    @abstractmethod
    async def update_recommendation(self, rec_id: str, status: str) -> Recommendation:
        """Update a recommendation's status and return the updated object."""

    @abstractmethod
    async def query_recommendations(
        self,
        deployment_ids: list[str] | None,
        status: list[str] | None,
    ) -> list[Recommendation]:
        """Query recommendations with filters."""

    @abstractmethod
    async def write_copilot_message(self, session_id: str, role: str, content: str) -> None:
        """Write a message to the copilot chat history."""

    @abstractmethod
    async def query_copilot_history(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, str]]:
        """Query chat history for a session."""
