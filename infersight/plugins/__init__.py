"""Plugin system for InferSight collectors, analyzers, and recommenders."""

from infersight.plugins.base import (
    AnalyzerPlugin,
    CollectorPlugin,
    Issue,
    NotificationPlugin,
    Recommendation,
    RecommenderPlugin,
    Severity,
)

__all__ = [
    "CollectorPlugin",
    "AnalyzerPlugin",
    "RecommenderPlugin",
    "NotificationPlugin",
    "Severity",
    "Issue",
    "Recommendation",
]
