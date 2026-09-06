"""Decode Bottleneck Analyzer.

Fires when decode throughput is consistently below threshold AND GPU
utilization is high, indicating the GPU is saturated on decode work.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any

from infersight.config import DecodeBottleneckConfig
from infersight.plugins.base import AnalyzerPlugin, Issue, Severity
from infersight.schema import CanonicalMetric


class DecodeBottleneckAnalyzer(AnalyzerPlugin):
    """Detects when decode throughput is throttled while GPUs are busy."""

    def __init__(self, config: DecodeBottleneckConfig | None = None) -> None:
        self._cfg = config or DecodeBottleneckConfig()

    @property
    def analyzer_name(self) -> str:
        return "decode_bottleneck"

    @property
    def required_metrics(self) -> list[str]:
        return ["decode_throughput_tps", "gpu_devices"]

    async def analyze(self, metrics: list[CanonicalMetric]) -> list[Issue]:
        if not metrics:
            return []

        # Filter to only metrics that have the required fields populated
        usable = [m for m in metrics if m.gpu_devices]
        if not usable:
            return []

        # Check how many samples fall below the throughput threshold
        low_tps = [
            m for m in usable if m.decode_throughput_tps < self._cfg.throughput_threshold_tps
        ]
        if len(low_tps) < len(usable):
            # Not consistently low — only fire if all samples are below threshold
            return []

        # Check GPU utilization is high (GPU is actually busy, not just idle)
        avg_gpu_utils: list[float] = []
        for m in usable:
            utils = [g.compute_utilization_pct for g in m.gpu_devices]
            if utils:
                avg_gpu_utils.append(statistics.mean(utils))

        if not avg_gpu_utils:
            return []

        overall_avg_gpu = statistics.mean(avg_gpu_utils)
        if overall_avg_gpu < self._cfg.gpu_utilization_threshold_pct:
            # GPU is not under load — low throughput is not a bottleneck
            return []

        latest = usable[-1]
        avg_tps = statistics.mean(m.decode_throughput_tps for m in usable)
        per_gpu: list[dict[str, Any]] = [
            {
                "device_index": g.device_index,
                "compute_utilization_pct": g.compute_utilization_pct,
            }
            for g in latest.gpu_devices
        ]

        return [
            Issue(
                issue_id="decode_bottleneck",
                issue_type="decode_bottleneck",
                severity=Severity.WARNING,
                deployment_id=latest.deployment_id,
                detected_at=datetime.now(tz=UTC),
                supporting_metrics={
                    "avg_decode_throughput_tps": round(avg_tps, 2),
                    "threshold_tps": self._cfg.throughput_threshold_tps,
                    "avg_gpu_utilization_pct": round(overall_avg_gpu, 2),
                    "gpu_utilization_threshold_pct": self._cfg.gpu_utilization_threshold_pct,
                    "sample_count": len(usable),
                    "gpu_devices": per_gpu,
                },
                description=(
                    f"Decode throughput ({avg_tps:.1f} tps) is below threshold "
                    f"({self._cfg.throughput_threshold_tps} tps) while average GPU utilization "
                    f"is {overall_avg_gpu:.1f}% — GPUs are saturated on decode work."
                ),
                plugin_name=self.analyzer_name,
            )
        ]
