"""GPU Underutilization Analyzer.

Fires when average GPU compute utilization stays below threshold across
the metric window. Correlates with request throughput to distinguish
genuine workload gaps from misconfiguration.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any

from infersight.config import GpuUnderutilizationConfig
from infersight.plugins.base import AnalyzerPlugin, Issue, Severity
from infersight.schema import CanonicalMetric

# Requests-per-second below which low GPU utilization is expected (low traffic)
_LOW_TRAFFIC_RPS_THRESHOLD = 0.5


class GpuUnderutilizationAnalyzer(AnalyzerPlugin):
    """Detects when GPUs are persistently idle or underloaded."""

    def __init__(self, config: GpuUnderutilizationConfig | None = None) -> None:
        self._cfg = config or GpuUnderutilizationConfig()

    @property
    def analyzer_name(self) -> str:
        return "gpu_underutilization"

    @property
    def required_metrics(self) -> list[str]:
        return ["gpu_devices"]

    async def analyze(self, metrics: list[CanonicalMetric]) -> list[Issue]:
        if not metrics:
            return []

        usable = [m for m in metrics if m.gpu_devices]
        if not usable:
            return []

        # Compute per-sample average GPU utilization across all devices
        sample_avgs: list[float] = []
        for m in usable:
            utils = [g.compute_utilization_pct for g in m.gpu_devices]
            if utils:
                sample_avgs.append(statistics.mean(utils))

        if not sample_avgs:
            return []

        overall_avg = statistics.mean(sample_avgs)
        if overall_avg >= self._cfg.utilization_threshold_pct:
            return []

        latest = usable[-1]
        avg_rps = statistics.mean(m.request_throughput_rps for m in usable)

        # Build per-GPU breakdown from the latest snapshot
        per_gpu: list[dict[str, Any]] = [
            {
                "device_index": g.device_index,
                "compute_utilization_pct": g.compute_utilization_pct,
                "memory_utilization_pct": round(g.memory_utilization_pct, 2),
            }
            for g in latest.gpu_devices
        ]

        if avg_rps < _LOW_TRAFFIC_RPS_THRESHOLD:
            severity = Severity.INFO
            description = (
                f"Average GPU utilization ({overall_avg:.1f}%) is below threshold "
                f"({self._cfg.utilization_threshold_pct}%) but traffic is very low "
                f"({avg_rps:.2f} rps) — this is expected during idle periods."
            )
        else:
            severity = Severity.WARNING
            description = (
                f"Average GPU utilization ({overall_avg:.1f}%) is below threshold "
                f"({self._cfg.utilization_threshold_pct}%) despite {avg_rps:.2f} rps — "
                "possible misconfiguration (tensor parallelism, batch size, or model placement)."
            )

        return [
            Issue(
                issue_id="gpu_underutilization",
                issue_type="gpu_underutilization",
                severity=severity,
                deployment_id=latest.deployment_id,
                detected_at=datetime.now(tz=UTC),
                supporting_metrics={
                    "avg_gpu_utilization_pct": round(overall_avg, 2),
                    "utilization_threshold_pct": self._cfg.utilization_threshold_pct,
                    "avg_request_throughput_rps": round(avg_rps, 4),
                    "gpu_devices": per_gpu,
                    "sample_count": len(usable),
                },
                description=description,
                plugin_name=self.analyzer_name,
            )
        ]
