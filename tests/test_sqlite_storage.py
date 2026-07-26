"""Tests for the SQLite storage backend."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from infersight.plugins.base import Issue, Recommendation, Severity
from infersight.schema import CanonicalMetric
from infersight.storage.sqlite import SQLiteBackend


@pytest.fixture
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(str(tmp_path / "infersight.db"), retention_days=30)


def metric(timestamp: datetime, deployment_id: str = "deployment-a") -> CanonicalMetric:
    return CanonicalMetric(
        timestamp=timestamp,
        engine="vllm",
        deployment_id=deployment_id,
        model_name="model-a",
        decode_throughput_tps=10,
        request_throughput_rps=2,
        queue_depth=1,
    )


@pytest.mark.asyncio
async def test_metrics_are_persisted_filtered_and_cleaned(backend: SQLiteBackend) -> None:
    now = datetime.now(UTC)
    current = metric(now)
    expired = metric(now - timedelta(days=31), "deployment-b")
    await backend.write_metrics([current, expired])

    metrics = await backend.query_metrics(
        None, now - timedelta(minutes=1), now + timedelta(minutes=1)
    )
    assert metrics == [current]

    deleted = await backend.cleanup_expired_metrics(now)
    assert deleted == 1
    assert await backend.query_metrics([], now - timedelta(days=1), now) == []


@pytest.mark.asyncio
async def test_issues_and_recommendations_round_trip(backend: SQLiteBackend) -> None:
    now = datetime.now(UTC)
    issue = Issue(
        issue_id="queue-saturation",
        issue_type="queue_saturation",
        severity=Severity.WARNING,
        deployment_id="deployment-a",
        detected_at=now,
        supporting_metrics={"queue_depth": 20},
        description="Queue is saturated.",
        plugin_name="queue_saturation",
    )
    recommendation = Recommendation(
        rec_id="rec-1",
        issue_id=issue.issue_id,
        deployment_id=issue.deployment_id,
        plugin_name="batch_size",
        target_parameter="max_num_seqs",
        current_value=16,
        recommended_value=32,
        reasoning="Increase batch capacity.",
        estimated_impact="Higher throughput",
        engine_config_snippet="--max-num-seqs 32",
        created_at=now,
    )

    await backend.write_issues([issue])
    await backend.write_recommendations([recommendation])

    assert await backend.query_issues(["deployment-a"], ["warning"], active_only=True) == [issue]
    updated = await backend.update_recommendation("rec-1", "applied")
    assert updated.status == "applied"
    assert updated.applied_at is not None
    assert await backend.query_recommendations(None, ["applied"]) == [updated]


@pytest.mark.asyncio
async def test_copilot_history_is_scoped_and_ordered(backend: SQLiteBackend) -> None:
    await backend.write_copilot_message("session-a", "user", "hello")
    await backend.write_copilot_message("session-b", "user", "ignored")
    await backend.write_copilot_message("session-a", "assistant", "hi")

    assert await backend.query_copilot_history("session-a") == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
