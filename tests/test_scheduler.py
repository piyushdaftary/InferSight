"""Tests for scheduled collection orchestration."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from infersight.config import InferSightConfig
from infersight.plugins.base import CollectorPlugin
from infersight.scheduler import CollectionScheduler
from infersight.schema import CanonicalMetric
from infersight.storage.base import StorageBackend


def config() -> InferSightConfig:
    """Return a configuration with one deployment and short retry settings."""
    return InferSightConfig(
        collection={"retry_max_attempts": 2, "retry_backoff_seconds": 1},
        deployments=[{"id": "api", "engine": "vllm", "endpoint": "http://api"}],
    )


def metric() -> CanonicalMetric:
    """Create a minimal collected metric."""
    return CanonicalMetric(
        timestamp=datetime.now(UTC),
        engine="vllm",
        deployment_id="api",
        model_name="model",
        decode_throughput_tps=1,
        request_throughput_rps=1,
        queue_depth=0,
    )


@pytest.mark.asyncio
async def test_collection_writes_metrics_and_runs_analyzer() -> None:
    """A successful cycle writes a metric then invokes analysis."""
    collector = AsyncMock(spec=CollectorPlugin)
    collector.health_check.return_value = True
    collector.collect.return_value = metric()
    storage = AsyncMock(spec=StorageBackend)
    analyze = AsyncMock()
    orchestrator = CollectionScheduler(
        config(),
        cast(StorageBackend, storage),
        {"api": cast(CollectorPlugin, collector)},
        analyze,
    )

    await orchestrator._collect_deployment(config().deployments[0])

    storage.write_metrics.assert_awaited_once_with([collector.collect.return_value])
    analyze.assert_awaited_once_with(collector.collect.return_value)


@pytest.mark.asyncio
async def test_collection_retries_with_exponential_backoff() -> None:
    """Collection failures are retried using configured exponential delays."""
    collector = AsyncMock(spec=CollectorPlugin)
    collector.health_check.side_effect = [False, False, True]
    collector.collect.return_value = metric()
    storage = AsyncMock(spec=StorageBackend)
    sleep = AsyncMock()
    orchestrator = CollectionScheduler(
        config(),
        cast(StorageBackend, storage),
        {"api": cast(CollectorPlugin, collector)},
        sleep=sleep,
    )

    await orchestrator._collect_deployment(config().deployments[0])

    assert sleep.await_args_list == [((1,),), ((2,),)]
    storage.write_metrics.assert_awaited_once()


def test_start_registers_one_job_per_configured_collector() -> None:
    """Only deployments with collectors receive a scheduled job."""
    scheduler = AsyncIOScheduler()
    collector = AsyncMock(spec=CollectorPlugin)
    orchestrator = CollectionScheduler(
        config(),
        cast(StorageBackend, AsyncMock(spec=StorageBackend)),
        {"api": cast(CollectorPlugin, collector)},
        scheduler=scheduler,
    )

    orchestrator.start()

    assert [job.id for job in scheduler.get_jobs()] == ["collection:api"]
    orchestrator.shutdown()
