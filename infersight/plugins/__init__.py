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
from infersight.plugins.registry import PluginRegistry

__all__ = [
    "CollectorPlugin",
    "AnalyzerPlugin",
    "RecommenderPlugin",
    "NotificationPlugin",
    "PluginRegistry",
    "Severity",
    "Issue",
    "Recommendation",
]
