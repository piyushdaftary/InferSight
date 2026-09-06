"""Batch Efficiency Analyzer.

Fires when the average batch fill rate is consistently below threshold,
indicating underutilized batching capacity. Distinguishes genuine low
traffic from misconfiguration by correlating with request throughput.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from infersight.config import BatchEfficiencyConfig
from infersight.plugins.base import AnalyzerPlugin, Issue, Severity
from infersight.schema import CanonicalMetric

# Requests-per-second below which low fill rate is considered normal (low traffic)
_LOW_TRAFFIC_RPS_THRESHOLD = 1.0


class BatchEfficiencyAnalyzer(AnalyzerPlugin):
    """Detects underutilized batch capacity."""

    def __init__(self, config: BatchEfficiencyConfig | None = None) -> None:
        self._cfg = config or BatchEfficiencyConfig()

    @property
    def analyzer_name(self) -> str:
        return "batch_efficiency"

    @property
    def required_metrics(self) -> list[str]:
        return ["batch"]

    async def analyze(self, metrics: list[CanonicalMetric]) -> list[Issue]:
        if not metrics:
            return []

        usable = [m for m in metrics if m.batch is not None]
        if not usable:
            return []

        fill_rates = [m.batch.fill_rate for m in usable if m.batch is not None]
        if not fill_rates:
            return []

        avg_fill_rate = statistics.mean(fill_rates)
        if avg_fill_rate >= self._cfg.fill_rate_threshold:
            return []

        latest = usable[-1]
        avg_rps = statistics.mean(m.request_throughput_rps for m in usable)

        # Low traffic — informational only, not a misconfiguration
        if avg_rps < _LOW_TRAFFIC_RPS_THRESHOLD:
            severity = Severity.INFO
            description = (
                f"Batch fill rate ({avg_fill_rate:.2f}) is below threshold "
                f"({self._cfg.fill_rate_threshold}) but request throughput is low "
                f"({avg_rps:.2f} rps) — likely insufficient traffic rather than misconfiguration."
            )
        else:
            severity = Severity.WARNING
            description = (
                f"Batch fill rate ({avg_fill_rate:.2f}) is below threshold "
                f"({self._cfg.fill_rate_threshold}) with {avg_rps:.2f} rps — "
                "consider increasing max_num_seqs or adjusting scheduler settings."
            )

        batch = latest.batch
        return [
            Issue(
                issue_id="batch_efficiency",
                issue_type="batch_efficiency",
                severity=severity,
                deployment_id=latest.deployment_id,
                detected_at=datetime.now(tz=UTC),
                supporting_metrics={
                    "avg_fill_rate": round(avg_fill_rate, 4),
                    "fill_rate_threshold": self._cfg.fill_rate_threshold,
                    "avg_batch_size": batch.avg_batch_size if batch else None,
                    "max_batch_size": batch.max_batch_size if batch else None,
                    "avg_request_throughput_rps": round(avg_rps, 4),
                    "sample_count": len(usable),
                },
                description=description,
                plugin_name=self.analyzer_name,
            )
        ]
