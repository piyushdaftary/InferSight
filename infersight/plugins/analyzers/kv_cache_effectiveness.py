"""KV Cache Effectiveness Analyzer.

Fires when the KV cache hit rate is persistently below threshold on
deployments where the engine exposes KV cache metrics. Skipped entirely
when kv_cache is None.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from infersight.config import KvCacheEffectivenessConfig
from infersight.plugins.base import AnalyzerPlugin, Issue, Severity
from infersight.schema import CanonicalMetric


class KvCacheEffectivenessAnalyzer(AnalyzerPlugin):
    """Detects low KV cache hit rates that indicate missed reuse opportunities."""

    def __init__(self, config: KvCacheEffectivenessConfig | None = None) -> None:
        self._cfg = config or KvCacheEffectivenessConfig()

    @property
    def analyzer_name(self) -> str:
        return "kv_cache_effectiveness"

    @property
    def required_metrics(self) -> list[str]:
        return ["kv_cache"]

    async def analyze(self, metrics: list[CanonicalMetric]) -> list[Issue]:
        if not metrics:
            return []

        # Skip if the engine doesn't expose KV cache metrics
        usable = [m for m in metrics if m.kv_cache is not None]
        if not usable:
            return []

        hit_rates = [m.kv_cache.hit_rate for m in usable if m.kv_cache is not None]
        avg_hit_rate = statistics.mean(hit_rates)
        if avg_hit_rate >= self._cfg.hit_rate_threshold:
            return []

        latest = usable[-1]
        assert latest.kv_cache is not None  # narrowing
        miss_rates = [m.kv_cache.miss_rate for m in usable if m.kv_cache is not None]
        eviction_rates = [m.kv_cache.eviction_rate for m in usable if m.kv_cache is not None]

        prefix_caching_enabled = latest.kv_cache.prefix_caching_enabled

        return [
            Issue(
                issue_id="kv_cache_effectiveness",
                issue_type="kv_cache_effectiveness",
                severity=Severity.WARNING,
                deployment_id=latest.deployment_id,
                detected_at=datetime.now(tz=UTC),
                supporting_metrics={
                    "avg_hit_rate": round(avg_hit_rate, 4),
                    "hit_rate_threshold": self._cfg.hit_rate_threshold,
                    "avg_miss_rate": round(statistics.mean(miss_rates), 4),
                    "avg_eviction_rate": round(statistics.mean(eviction_rates), 4),
                    "prefix_caching_enabled": prefix_caching_enabled,
                    "used_blocks": latest.kv_cache.used_blocks,
                    "total_blocks": latest.kv_cache.total_blocks,
                    "sample_count": len(usable),
                },
                description=(
                    f"KV cache hit rate ({avg_hit_rate:.2f}) is below threshold "
                    f"({self._cfg.hit_rate_threshold}). "
                    + (
                        "Prefix caching is disabled — enabling it may significantly improve "
                        "hit rate for workloads with repeated prompt prefixes."
                        if not prefix_caching_enabled
                        else "Prefix caching is enabled but hit rate is still low — "
                        "consider reviewing prompt structure or increasing KV cache allocation."
                    )
                ),
                plugin_name=self.analyzer_name,
            )
        ]
