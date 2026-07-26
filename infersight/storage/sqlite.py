"""SQLite implementation of the InferSight storage interface."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from infersight.plugins.base import Issue, Recommendation
from infersight.schema import CanonicalMetric
from infersight.storage.base import StorageBackend

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deployment_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    model_name TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_deployment_time
    ON metrics (deployment_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_metrics_engine_time
    ON metrics (engine, captured_at);

CREATE TABLE IF NOT EXISTS issues (
    issue_id TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    cleared_at TEXT,
    severity TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (issue_id, deployment_id, detected_at)
);

CREATE TABLE IF NOT EXISTS recommendations (
    rec_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    rank INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    applied_at TEXT,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS copilot_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class SQLiteBackend(StorageBackend):
    """Persist InferSight domain models in a local SQLite database."""

    def __init__(self, path: str, retention_days: int = 30, wal_mode: bool = True) -> None:
        self._path = Path(path).expanduser()
        self._retention_days = retention_days
        self._wal_mode = wal_mode
        self._initialized = False
        self._initialization_lock = asyncio.Lock()
        self._last_cleanup: datetime | None = None

    async def _connect(self) -> aiosqlite.Connection:
        await self._initialize()
        connection = await aiosqlite.connect(self._path)
        connection.row_factory = aiosqlite.Row
        return connection

    async def _initialize(self) -> None:
        if self._initialized:
            return

        async with self._initialization_lock:
            if self._initialized:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self._path) as connection:
                if self._wal_mode:
                    await connection.execute("PRAGMA journal_mode=WAL")
                await connection.executescript(_SCHEMA)
                await connection.commit()
            self._initialized = True

    async def _maybe_cleanup(self) -> None:
        now = datetime.now(UTC)
        if self._last_cleanup is not None and now - self._last_cleanup < timedelta(days=1):
            return
        await self.cleanup_expired_metrics(now)

    async def cleanup_expired_metrics(self, now: datetime | None = None) -> int:
        """Delete metrics outside the configured retention window and return their count."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=self._retention_days)
        async with await self._connect() as connection:
            cursor = await connection.execute(
                "DELETE FROM metrics WHERE captured_at < ?", (cutoff.isoformat(),)
            )
            await connection.commit()
        self._last_cleanup = now or datetime.now(UTC)
        return int(cursor.rowcount)

    async def write_metrics(self, metrics: list[CanonicalMetric]) -> None:
        await self._maybe_cleanup()
        if not metrics:
            return
        rows = [
            (
                metric.deployment_id,
                metric.engine,
                metric.model_name,
                metric.timestamp.isoformat(),
                metric.model_dump_json(),
            )
            for metric in metrics
        ]
        async with await self._connect() as connection:
            await connection.executemany(
                """INSERT INTO metrics (deployment_id, engine, model_name, captured_at, payload)
                VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
            await connection.commit()

    async def query_metrics(
        self,
        deployment_ids: list[str] | None,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[CanonicalMetric]:
        if deployment_ids == []:
            return []
        clauses = ["captured_at >= ?", "captured_at <= ?"]
        parameters: list[object] = [start.isoformat(), end.isoformat()]
        if deployment_ids is not None:
            clauses.append(f"deployment_id IN ({', '.join('?' for _ in deployment_ids)})")
            parameters.extend(deployment_ids)
        parameters.append(limit)
        async with await self._connect() as connection:
            cursor = await connection.execute(
                f"SELECT payload FROM metrics WHERE {' AND '.join(clauses)} "
                "ORDER BY captured_at ASC LIMIT ?",
                parameters,
            )
            rows = await cursor.fetchall()
        return [CanonicalMetric.model_validate_json(row["payload"]) for row in rows]

    async def write_issues(self, issues: list[Issue]) -> None:
        if not issues:
            return
        rows = [
            (
                issue.issue_id,
                issue.deployment_id,
                issue.detected_at.isoformat(),
                issue.cleared_at.isoformat() if issue.cleared_at else None,
                issue.severity.value,
                issue.model_dump_json(),
            )
            for issue in issues
        ]
        async with await self._connect() as connection:
            await connection.executemany(
                """INSERT OR REPLACE INTO issues
                (issue_id, deployment_id, detected_at, cleared_at, severity, payload)
                VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await connection.commit()

    async def query_issues(
        self,
        deployment_ids: list[str] | None,
        severity: list[str] | None,
        active_only: bool,
    ) -> list[Issue]:
        if deployment_ids == [] or severity == []:
            return []
        clauses: list[str] = []
        parameters: list[object] = []
        if deployment_ids is not None:
            clauses.append(f"deployment_id IN ({', '.join('?' for _ in deployment_ids)})")
            parameters.extend(deployment_ids)
        if severity is not None:
            clauses.append(f"severity IN ({', '.join('?' for _ in severity)})")
            parameters.extend(severity)
        if active_only:
            clauses.append("cleared_at IS NULL")
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with await self._connect() as connection:
            cursor = await connection.execute(
                f"SELECT payload FROM issues {where_clause} ORDER BY detected_at DESC", parameters
            )
            rows = await cursor.fetchall()
        return [Issue.model_validate_json(row["payload"]) for row in rows]

    async def write_recommendations(self, recs: list[Recommendation]) -> None:
        if not recs:
            return
        rows = [
            (
                rec.rec_id,
                rec.issue_id,
                rec.deployment_id,
                rec.status,
                rec.rank,
                rec.created_at.isoformat(),
                rec.applied_at.isoformat() if rec.applied_at else None,
                rec.model_dump_json(),
            )
            for rec in recs
        ]
        async with await self._connect() as connection:
            await connection.executemany(
                """INSERT OR REPLACE INTO recommendations
                (rec_id, issue_id, deployment_id, status, rank, created_at, applied_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await connection.commit()

    async def update_recommendation(self, rec_id: str, status: str) -> Recommendation:
        async with await self._connect() as connection:
            cursor = await connection.execute(
                "SELECT payload FROM recommendations WHERE rec_id = ?", (rec_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise KeyError(f"Recommendation not found: {rec_id}")
            recommendation = Recommendation.model_validate_json(row["payload"])
            applied_at = datetime.now(UTC) if status == "applied" else None
            updated = recommendation.model_copy(update={"status": status, "applied_at": applied_at})
            await connection.execute(
                """UPDATE recommendations SET status = ?, applied_at = ?, payload = ?
                WHERE rec_id = ?""",
                (
                    updated.status,
                    updated.applied_at.isoformat() if updated.applied_at else None,
                    updated.model_dump_json(),
                    rec_id,
                ),
            )
            await connection.commit()
        return updated

    async def query_recommendations(
        self,
        deployment_ids: list[str] | None,
        status: list[str] | None,
    ) -> list[Recommendation]:
        if deployment_ids == [] or status == []:
            return []
        clauses: list[str] = []
        parameters: list[object] = []
        if deployment_ids is not None:
            clauses.append(f"deployment_id IN ({', '.join('?' for _ in deployment_ids)})")
            parameters.extend(deployment_ids)
        if status is not None:
            clauses.append(f"status IN ({', '.join('?' for _ in status)})")
            parameters.extend(status)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with await self._connect() as connection:
            cursor = await connection.execute(
                f"""SELECT payload FROM recommendations {where_clause}
                ORDER BY rank ASC, created_at DESC""",
                parameters,
            )
            rows = await cursor.fetchall()
        return [Recommendation.model_validate_json(row["payload"]) for row in rows]

    async def write_copilot_message(self, session_id: str, role: str, content: str) -> None:
        async with await self._connect() as connection:
            await connection.execute(
                """INSERT INTO copilot_history (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)""",
                (session_id, role, content, datetime.now(UTC).isoformat()),
            )
            await connection.commit()

    async def query_copilot_history(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, str]]:
        async with await self._connect() as connection:
            cursor = await connection.execute(
                """SELECT role, content FROM copilot_history WHERE session_id = ?
                ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            )
            rows = await cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(list(rows))]
