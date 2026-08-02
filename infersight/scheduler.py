"""Scheduled collection orchestration for configured deployments."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from infersight.config import DeploymentConfig, InferSightConfig
from infersight.plugins.base import CollectorPlugin
from infersight.schema import CanonicalMetric
from infersight.storage.base import StorageBackend

logger = logging.getLogger(__name__)

AnalyzerCallback = Callable[[CanonicalMetric], Awaitable[None]]
SleepFunction = Callable[[float], Awaitable[None]]


class CollectionError(Exception):
    """Raised when a collector cannot complete a collection cycle."""


class CollectionScheduler:
    """Schedule isolated collection cycles for each configured deployment."""

    def __init__(
        self,
        config: InferSightConfig,
        storage: StorageBackend,
        collectors: Mapping[str, CollectorPlugin],
        analyze: AnalyzerCallback | None = None,
        scheduler: AsyncIOScheduler | None = None,
        sleep: SleepFunction = asyncio.sleep,
    ) -> None:
        self._config = config
        self._storage = storage
        self._collectors = collectors
        self._analyze = analyze
        self._scheduler = scheduler or AsyncIOScheduler()
        self._sleep = sleep

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """Expose the underlying scheduler for lifecycle management."""
        return self._scheduler

    def start(self) -> None:
        """Register deployment jobs and start collection scheduling."""
        for deployment in self._config.deployments:
            if deployment.id not in self._collectors:
                logger.warning("No collector configured for deployment %s", deployment.id)
                continue
            self._scheduler.add_job(
                self._collect_deployment,
                trigger=IntervalTrigger(seconds=deployment.interval_seconds),
                args=[deployment],
                id=f"collection:{deployment.id}",
                replace_existing=True,
            )
        self._scheduler.start()

    def shutdown(self) -> None:
        """Stop collection scheduling without waiting for active jobs."""
        self._scheduler.shutdown(wait=False)

    async def _collect_deployment(self, deployment: DeploymentConfig) -> None:
        collector = self._collectors[deployment.id]
        attempts = self._config.collection.retry_max_attempts
        for attempt in range(attempts + 1):
            try:
                if not await collector.health_check():
                    raise CollectionError("collector health check failed")
                metric = await collector.collect()
                await self._storage.write_metrics([metric])
                if self._analyze is not None:
                    await self._analyze(metric)
                return
            except CollectionError as exc:
                if attempt == attempts:
                    logger.error(
                        "Collection failed for deployment %s after %s attempts: %s",
                        deployment.id,
                        attempt + 1,
                        exc,
                    )
                    return
                delay = self._config.collection.retry_backoff_seconds * (2**attempt)
                logger.warning(
                    "Collection failed for deployment %s; retrying in %s seconds: %s",
                    deployment.id,
                    delay,
                    exc,
                )
                await self._sleep(delay)
            except Exception:
                logger.exception("Unexpected collection failure for deployment %s", deployment.id)
                return
