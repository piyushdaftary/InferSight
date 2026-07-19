"""Storage backends for InferSight metrics, issues, and recommendations."""

from infersight.storage.base import StorageBackend
from infersight.storage.sqlite import SQLiteBackend

__all__ = ["SQLiteBackend", "StorageBackend"]
