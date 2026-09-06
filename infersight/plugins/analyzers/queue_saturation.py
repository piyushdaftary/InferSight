"""Queue Saturation Analyzer.

Fires when queue depth exceeds max_batch_size * depth_multiplier for a
sustained window. Severity escalates to CRITICAL at 3× the multiplier.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from infersight.config import QueueSaturationConfig
from infersight.plugins.base import AnalyzerPlugin, Issue, Severity
from infersight.schema import CanonicalMetric


class QueueSaturationAnalyzer(AnalyzerPlugin):
    """Detects when the request queue is persistently backed up."""

    def __init__(self, config: QueueSaturationConfig | None = None) -> None:
        self._cfg = config or QueueSaturationConfig()

    @property
    def analyzer_name(self) -> str:
        return "queue_saturation"

    @property
    def required_metrics(self) -> list[str]:
        return ["queue_depth", "batch"]

    async def analyze(self, metrics: list[CanonicalMetric]) -> list[Issue]:
        if not metrics:
            return []

        usable = [m for m in metrics if m.batch is not None]
        if not usable:
            return []

        latest = usable[-1]
        assert latest.batch is not None  # narrowing — checked above
        max_batch = latest.batch.max_batch_size
        warning_threshold = max_batch * self._cfg.depth_multiplier
        critical_threshold = max_batch * self._cfg.depth_multiplier * 3

        # All samples in the window must exceed the threshold to avoid flapping
        queue_depths = [m.queue_depth for m in usable]
        above_warning = [d for d in queue_depths if d > warning_threshold]
        if len(above_warning) < len(usable):
            return []

        avg_depth = statistics.mean(queue_depths)
        avg_rps = statistics.mean(m.request_throughput_rps for m in usable)

        severity = Severity.CRITICAL if avg_depth > critical_threshold else Severity.WARNING

        # Include p99 queue wait if available from latest snapshot
        queue_wait_p99: float | None = None
        if latest.queue_wait_ms is not None:
            queue_wait_p99 = latest.queue_wait_ms.p99

        return [
            Issue(
                issue_id="queue_saturation",
                issue_type="queue_saturation",
                severity=severity,
                deployment_id=latest.deployment_id,
                detected_at=datetime.now(tz=UTC),
                supporting_metrics={
                    "avg_queue_depth": round(avg_depth, 1),
                    "max_batch_size": max_batch,
                    "depth_multiplier": self._cfg.depth_multiplier,
                    "warning_threshold": warning_threshold,
                    "critical_threshold": critical_threshold,
                    "queue_wait_ms_p99": queue_wait_p99,
                    "avg_request_throughput_rps": round(avg_rps, 4),
                    "sample_count": len(usable),
                },
                description=(
                    f"Queue depth ({avg_depth:.0f}) exceeds "
                    f"{self._cfg.depth_multiplier}× max_batch_size ({max_batch}) "
                    f"for all {len(usable)} samples in the window. "
                    + (
                        f"Queue wait p99: {queue_wait_p99:.0f}ms. "
                        if queue_wait_p99 is not None
                        else ""
                    )
                    + "Consider scaling up replicas or increasing batch capacity."
                ),
                plugin_name=self.analyzer_name,
            )
        ]
