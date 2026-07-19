"""Plugin interfaces and domain models for InferSight.

All plugin types are Python ABCs defined here. Plugins are
discovered at startup by scanning directories listed in
config.plugin_dirs for subclasses of each ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from infersight.schema import CanonicalMetric


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Issue(BaseModel):
    """Canonical output of an AnalyzerPlugin."""
    issue_id: str                          # stable identifier, e.g. "decode_bottleneck"
    issue_type: str                        # human label
    severity: Severity
    deployment_id: str
    detected_at: datetime
    cleared_at: datetime | None = None
    supporting_metrics: dict[str, Any]     # subset of CanonicalMetric fields as evidence
    description: str
    plugin_name: str


class Recommendation(BaseModel):
    """Canonical output of a RecommenderPlugin."""
    rec_id: str
    issue_id: str                          # links back to the triggering Issue
    deployment_id: str
    plugin_name: str
    target_parameter: str                  # e.g. "max_num_seqs"
    current_value: Any  # noqa: ANN401
    recommended_value: Any  # noqa: ANN401
    reasoning: str
    estimated_impact: str                  # e.g. "15–30% reduction in TTFT"
    engine_config_snippet: str | None   # native config diff/flag
    rank: int = 0                          # lower = higher priority
    status: str = "open"                   # open | acknowledged | applied | dismissed
    created_at: datetime
    applied_at: datetime | None = None


class CollectorPlugin(ABC):
    """
    Implement this ABC to add support for a new inference engine.
    One instance is created per configured deployment endpoint.
    """

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return a lowercase slug, e.g. 'vllm', 'tgi'."""

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Returns True if the engine endpoint is reachable and healthy.
        Called before each collection cycle; failures are logged and retried.
        """

    @abstractmethod
    async def collect(self) -> CanonicalMetric:
        """
        Scrape the engine and return a normalized CanonicalMetric.
        Raise CollectionError on unrecoverable failure.
        """


class AnalyzerPlugin(ABC):
    """Implement this ABC to add a new anomaly detector."""

    @property
    @abstractmethod
    def analyzer_name(self) -> str:
        """Stable identifier, e.g. 'decode_bottleneck'."""

    @property
    @abstractmethod
    def required_metrics(self) -> list[str]:
        """
        List of CanonicalMetric field names this analyzer reads.
        Used to skip the analyzer when fields are unavailable.
        """

    @abstractmethod
    async def analyze(
        self,
        metrics: list[CanonicalMetric],  # recent window, oldest first
    ) -> list[Issue]:
        """
        Inspect the metric window and return zero or more Issue objects.
        Analyzers MUST be stateless; window management is done by the engine.
        """


class RecommenderPlugin(ABC):
    """Implement this ABC to add a new recommendation generator."""

    @property
    @abstractmethod
    def recommender_name(self) -> str:
        """Stable identifier, e.g. 'prefix_cache_recommender'."""

    @property
    @abstractmethod
    def handles_issue_types(self) -> list[str]:
        """Issue type slugs this recommender handles."""

    @abstractmethod
    async def recommend(self, issue: Issue) -> list[Recommendation]:
        """
        Generate ranked recommendations for a given Issue.
        Returns an empty list if no actionable recommendation exists.
        """


class NotificationPlugin(ABC):
    """Implement this ABC to add a new alert channel."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """e.g. 'slack', 'pagerduty', 'email'"""

    @abstractmethod
    async def notify(self, issue: Issue) -> None:
        """
        Send an alert for the given issue.
        Implementations MUST be idempotent — called once per new/re-triggered issue.
        Failures MUST be logged but MUST NOT propagate exceptions to the caller.
        """
