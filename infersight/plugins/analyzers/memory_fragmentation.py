"""Memory Fragmentation Analyzer.

Fires when GPU memory utilization is high but KV cache hit rate is low,
indicating that memory is occupied but not being reused effectively —
a sign of KV cache fragmentation or poor eviction policy.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from infersight.config import MemoryFragmentationConfig
from infersight.plugins.base import AnalyzerPlugin, Issue, Severity
from infersight.schema import CanonicalMetric

_MEMORY_HIGH_THRESHOLD_PCT = 85.0
_HIT_RATE_LOW_THRESHOLD = 0.3


class MemoryFragmentationAnalyzer(AnalyzerPlugin):
    """Detects KV cache fragmentation via high memory + low hit rate."""

    def __init__(self, config: MemoryFragmentationConfig | None = None) -> None:
        self._cfg = config or MemoryFragmentationConfig()

    @property
    def analyzer_name(self) -> str:
        return "memory_fragmentation"

    @property
    def required_metrics(self) -> list[str]:
        return ["gpu_devices", "kv_cache"]

    async def analyze(self, metrics: list[CanonicalMetric]) -> list[Issue]:
        if not metrics:
            return []

        # Skip samples where either gpu_devices or kv_cache is absent
        usable = [m for m in metrics if m.gpu_devices and m.kv_cache is not None]
        if not usable:
            return []

        # Compute average memory utilization across all GPUs and samples
        mem_utils: list[float] = []
        for m in usable:
            utils = [g.memory_utilization_pct for g in m.gpu_devices]
            if utils:
                mem_utils.append(statistics.mean(utils))

        if not mem_utils:
            return []

        avg_mem_util = statistics.mean(mem_utils)
        if avg_mem_util < _MEMORY_HIGH_THRESHOLD_PCT:
            return []

        hit_rates = [m.kv_cache.hit_rate for m in usable if m.kv_cache is not None]
        avg_hit_rate = statistics.mean(hit_rates) if hit_rates else 1.0
        if avg_hit_rate >= _HIT_RATE_LOW_THRESHOLD:
            return []

        latest = usable[-1]
        eviction_rates = [m.kv_cache.eviction_rate for m in usable if m.kv_cache is not None]
        avg_eviction = statistics.mean(eviction_rates) if eviction_rates else 0.0

        return [
            Issue(
                issue_id="memory_fragmentation",
                issue_type="memory_fragmentation",
                severity=Severity.WARNING,
                deployment_id=latest.deployment_id,
                detected_at=datetime.now(tz=UTC),
                supporting_metrics={
                    "avg_memory_utilization_pct": round(avg_mem_util, 2),
                    "memory_high_threshold_pct": _MEMORY_HIGH_THRESHOLD_PCT,
                    "avg_kv_cache_hit_rate": round(avg_hit_rate, 4),
                    "hit_rate_low_threshold": _HIT_RATE_LOW_THRESHOLD,
                    "avg_kv_cache_eviction_rate": round(avg_eviction, 4),
                    "sample_count": len(usable),
                },
                description=(
                    f"GPU memory utilization is high ({avg_mem_util:.1f}%) but KV cache "
                    f"hit rate is low ({avg_hit_rate:.2f}) — possible memory fragmentation. "
                    f"Average eviction rate: {avg_eviction:.2f}/s. "
                    "Consider enabling prefix caching or increasing KV cache allocation."
                ),
                plugin_name=self.analyzer_name,
            )
        ]
