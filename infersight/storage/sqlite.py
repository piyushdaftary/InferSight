"""SQLite storage backend for InferSight.

Uses aiosqlite for async SQLite operations.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from infersight.plugins.base import Issue, Recommendation
from infersight.schema import CanonicalMetric
from infersight.storage.base import StorageBackend


class SQLiteBackend(StorageBackend):
    """SQLite storage backend implementing StorageBackend ABC.

    Creates all required tables on first connection.
    Implements daily TTL cleanup for metrics older than retention_days.
    Thread-safe for concurrent writes via connection pooling.
    """

    def __init__(
        self, db_path: str = "~/.infersight/infersight.db", retention_days: int = 30
    ) -> None:
        """Initialize SQLiteBackend with database path and retention policy.

        Args:
            db_path: Path to SQLite database file. Expands ~ if present.
            retention_days: Number of days to retain metrics before deletion.
        """
        self._db_path = Path(db_path).expanduser().as_posix()
        self._retention_days = retention_days
        self._local = threading.local()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Create directory for database file if it doesn't exist."""
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _connection(self) -> aiosqlite.Connection:
        """Get or create thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            raise RuntimeError("Connection not initialized. Use async context manager.")
        assert isinstance(self._local.connection, aiosqlite.Connection)
        return self._local.connection

    async def __aenter__(self) -> SQLiteBackend:
        """Async context manager entry - open connection."""
        self._local.connection = await aiosqlite.connect(self._db_path)
        self._local.connection.row_factory = sqlite3.Row
        await self._create_tables()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - close connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            await self._local.connection.close()
            self._local.connection = None

    async def _create_tables(self) -> None:
        """Create all required tables if they don't exist."""
        async with self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deployment_id TEXT NOT NULL,
                engine TEXT NOT NULL,
                model_name TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        ):
            pass

        async with self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_metrics_deployment_time
            ON metrics (deployment_id, captured_at)
            """
        ):
            pass

        async with self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_metrics_engine_time
            ON metrics (engine, captured_at)
            """
        ):
            pass

        async with self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS issues (
                issue_id TEXT NOT NULL,
                deployment_id TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                cleared_at TEXT,
                severity TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (issue_id, deployment_id, detected_at)
            )
            """
        ):
            pass

        async with self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                rec_id TEXT PRIMARY KEY,
                issue_id TEXT NOT NULL,
                deployment_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                rank INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                applied_at TEXT,
                payload TEXT NOT NULL
            )
            """
        ):
            pass

        async with self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS copilot_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        ):
            pass

        await self._connection.commit()

    async def write_metrics(self, metrics: list[CanonicalMetric]) -> None:
        """Persist metric snapshots to storage.

        Args:
            metrics: List of CanonicalMetric snapshots to write.
        """
        rows = [
            (
                m.deployment_id,
                m.engine,
                m.model_name,
                m.timestamp.isoformat(),
                json.dumps(m.model_dump(mode="json")),
            )
            for m in metrics
        ]
        async with self._connection.executemany(
            """
            INSERT INTO metrics (deployment_id, engine, model_name, captured_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        ):
            pass
        await self._connection.commit()
        await self._cleanup_old_metrics()

    async def query_metrics(
        self,
        deployment_ids: list[str] | None,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[CanonicalMetric]:
        """Query metrics with filters and time range.

        Args:
            deployment_ids: List of deployment IDs to filter by, or None for all.
            start: Start datetime for time range filter.
            end: End datetime for time range filter.
            limit: Maximum number of results to return.

        Returns:
            List of CanonicalMetric instances matching the criteria.
        """
        where_clauses = ["captured_at >= ?", "captured_at <= ?"]
        params: list[str] = [start.isoformat(), end.isoformat()]

        if deployment_ids:
            placeholders = ",".join("?" * len(deployment_ids))
            where_clauses.append(f"deployment_id IN ({placeholders})")
            params.extend(deployment_ids)

        where_clause = " AND ".join(where_clauses)

        metrics: list[CanonicalMetric] = []
        async with self._connection.execute(
            f"SELECT payload FROM metrics WHERE {where_clause} ORDER BY captured_at DESC LIMIT ?",
            params + [limit],
        ) as cursor:
            async for row in cursor:
                if row and row["payload"]:
                    data = json.loads(row["payload"])
                    metrics.append(CanonicalMetric(**data))

        return metrics

    async def write_issues(self, issues: list[Issue]) -> None:
        """Persist issue objects to storage.

        Args:
            issues: List of Issue objects to write.
        """
        rows = [
            (
                i.issue_id,
                i.deployment_id,
                i.detected_at.isoformat(),
                i.cleared_at.isoformat() if i.cleared_at else None,
                i.severity.value,
                json.dumps(i.model_dump(mode="json")),
            )
            for i in issues
        ]
        async with self._connection.executemany(
            """
            INSERT OR REPLACE INTO issues (issue_id, deployment_id, detected_at, cleared_at, severity, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        ):
            pass
        await self._connection.commit()

    async def query_issues(
        self,
        deployment_ids: list[str] | None,
        severity: list[str] | None,
        active_only: bool,
    ) -> list[Issue]:
        """Query issues with filters.

        Args:
            deployment_ids: List of deployment IDs to filter by, or None for all.
            severity: List of severity levels to filter by, or None for all.
            active_only: If True, only return issues with cleared_at = NULL.

        Returns:
            List of Issue objects matching the criteria.
        """
        where_clauses: list[str] = []
        params: list[str] = []

        if deployment_ids:
            placeholders = ",".join("?" * len(deployment_ids))
            where_clauses.append(f"deployment_id IN ({placeholders})")
            params.extend(deployment_ids)

        if severity:
            placeholders = ",".join("?" * len(severity))
            where_clauses.append(f"severity IN ({placeholders})")
            params.extend(severity)

        if active_only:
            where_clauses.append("cleared_at IS NULL")

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        issues: list[Issue] = []
        async with self._connection.execute(
            f"SELECT payload FROM issues WHERE {where_clause} ORDER BY detected_at DESC",
            params,
        ) as cursor:
            async for row in cursor:
                if row and row["payload"]:
                    data = json.loads(row["payload"])
                    issues.append(Issue(**data))

        return issues

    async def write_recommendations(self, recs: list[Recommendation]) -> None:
        """Persist recommendation objects to storage.

        Args:
            recs: List of Recommendation objects to write.
        """
        rows = [
            (
                r.rec_id,
                r.issue_id,
                r.deployment_id,
                r.status,
                r.rank,
                r.created_at.isoformat(),
                r.applied_at.isoformat() if r.applied_at else None,
                json.dumps(r.model_dump(mode="json")),
            )
            for r in recs
        ]
        async with self._connection.executemany(
            """
            INSERT OR REPLACE INTO recommendations (rec_id, issue_id, deployment_id, status, rank, created_at, applied_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        ):
            pass
        await self._connection.commit()

    async def update_recommendation(self, rec_id: str, status: str) -> Recommendation:
        """Update a recommendation's status and return the updated object.

        Args:
            rec_id: The recommendation ID to update.
            status: New status value ('open', 'acknowledged', 'applied', 'dismissed').

        Returns:
            The updated Recommendation object.
        """
        async with self._connection.execute(
            "SELECT payload FROM recommendations WHERE rec_id = ?",
            (rec_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row or not row["payload"]:
                raise ValueError(f"Recommendation {rec_id} not found")
            data = json.loads(row["payload"])

        data["status"] = status
        if status == "applied" and not data.get("applied_at"):
            data["applied_at"] = datetime.utcnow().isoformat()

        async with self._connection.execute(
            """
            UPDATE recommendations
            SET status = ?, applied_at = ?, payload = ?
            WHERE rec_id = ?
            """,
            (
                status,
                data.get("applied_at"),
                json.dumps(data),
                rec_id,
            ),
        ):
            pass
        await self._connection.commit()

        return Recommendation(**data)

    async def query_recommendations(
        self,
        deployment_ids: list[str] | None,
        status: list[str] | None,
    ) -> list[Recommendation]:
        """Query recommendations with filters.

        Args:
            deployment_ids: List of deployment IDs to filter by, or None for all.
            status: List of status values to filter by, or None for all.

        Returns:
            List of Recommendation objects matching the criteria.
        """
        where_clauses: list[str] = []
        params: list[str] = []

        if deployment_ids:
            placeholders = ",".join("?" * len(deployment_ids))
            where_clauses.append(f"deployment_id IN ({placeholders})")
            params.extend(deployment_ids)

        if status:
            placeholders = ",".join("?" * len(status))
            where_clauses.append(f"status IN ({placeholders})")
            params.extend(status)

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        recs: list[Recommendation] = []
        async with self._connection.execute(
            f"SELECT payload FROM recommendations WHERE {where_clause} ORDER BY rank ASC, created_at DESC",
            params,
        ) as cursor:
            async for row in cursor:
                if row and row["payload"]:
                    data = json.loads(row["payload"])
                    recs.append(Recommendation(**data))

        return recs

    async def write_copilot_message(self, session_id: str, role: str, content: str) -> None:
        """Write a message to the copilot chat history.

        Args:
            session_id: Session identifier.
            role: Message role ('user' or 'assistant').
            content: Message content.
        """
        now = datetime.utcnow().isoformat()
        async with self._connection.execute(
            """
            INSERT INTO copilot_history (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now),
        ):
            pass
        await self._connection.commit()

    async def query_copilot_history(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, str]]:
        """Query chat history for a session.

        Args:
            session_id: Session identifier.
            limit: Maximum number of messages to return.

        Returns:
            List of {role, content} dicts in chronological order.
        """
        messages: list[dict[str, str]] = []
        async with self._connection.execute(
            """
            SELECT role, content FROM copilot_history
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, limit),
        ) as cursor:
            async for row in cursor:
                if row:
                    messages.append({"role": row["role"], "content": row["content"]})

        return messages

    async def _cleanup_old_metrics(self) -> None:
        """Delete metrics older than retention_days."""
        datetime.utcnow().isoformat()
        days_ago = f"-{self._retention_days} days"
        async with self._connection.execute(
            """
            DELETE FROM metrics WHERE captured_at < datetime('now', ?)
            """,
            (days_ago,),
        ):
            pass
        await self._connection.commit()
