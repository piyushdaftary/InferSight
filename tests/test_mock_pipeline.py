"""Mock-backed end-to-end validation of one InferSight collection cycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from infersight.config import CollectionConfig, DeploymentConfig, InferSightConfig
from infersight.plugins.analyzers.queue_saturation import QueueSaturationAnalyzer
from infersight.plugins.base import CollectorPlugin, Issue, NotificationPlugin
from infersight.plugins.notifications.alert_router import AlertRouter
from infersight.scheduler import CollectionScheduler
from infersight.schema import BatchMetrics, CanonicalMetric
from infersight.storage.sqlite import SQLiteBackend


class MockInferenceCollector(CollectorPlugin):
    """A deterministic high-queue inference server used in place of a cluster."""

    @property
    def engine_name(self) -> str:
        return "mock-triton"

    async def health_check(self) -> bool:
        return True

    async def collect(self) -> CanonicalMetric:
        return CanonicalMetric(
            timestamp=datetime.now(UTC),
            engine=self.engine_name,
            deployment_id="mock-triton",
            model_name="mock-model",
            decode_throughput_tps=100,
            request_throughput_rps=4,
            queue_depth=70,
            batch=BatchMetrics(
                avg_batch_size=8,
                max_batch_size=10,
                fill_rate=0.8,
                prefill_tokens=100,
                decode_tokens=400,
                prefill_decode_ratio=0.25,
            ),
        )


class RecordingNotifier(NotificationPlugin):
    """Captures notifications rather than delivering them to an external service."""

    def __init__(self) -> None:
        self.issues: list[Issue] = []

    @property
    def channel_name(self) -> str:
        return "recording"

    async def notify(self, issue: Issue) -> None:
        self.issues.append(issue)


@pytest.mark.asyncio
async def test_mock_collection_analysis_storage_and_alert_pipeline(tmp_path: Path) -> None:
    """A mock server can exercise collection through durable alert dispatch."""
    config = InferSightConfig(
        collection=CollectionConfig(retry_max_attempts=0),
        deployments=[
            DeploymentConfig(
                id="mock-triton",
                engine="triton",
                endpoint="http://mock-triton",
            )
        ],
    )
    collector = MockInferenceCollector()
    analyzer = QueueSaturationAnalyzer()

    async with SQLiteBackend(str(tmp_path / "infersight.db")) as storage:
        router = AlertRouter(config.alerting, storage=storage)
        notifier = RecordingNotifier()
        router.add_channel(notifier)

        async def analyze(metric: CanonicalMetric) -> None:
            issues = await analyzer.analyze([metric])
            await storage.write_issues(issues)
            for detected_issue in issues:
                await router.dispatch(detected_issue)

        scheduler = CollectionScheduler(
            config, storage, {"mock-triton": collector}, analyze=analyze
        )
        await scheduler._collect_deployment(config.deployments[0])

        metrics = await storage.query_metrics(
            None,
            datetime.now(UTC) - timedelta(minutes=1),
            datetime.now(UTC) + timedelta(minutes=1),
        )
        issues = await storage.query_issues(None, None, active_only=True)

    assert len(metrics) == 1
    assert metrics[0].queue_depth == 70
    assert len(issues) == 1
    assert issues[0].issue_type == "queue_saturation"
    assert len(notifier.issues) == 1
