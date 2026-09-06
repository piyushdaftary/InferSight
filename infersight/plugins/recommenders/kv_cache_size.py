"""KV Cache Size Recommender.

Recommends increasing KV cache GPU memory allocation when eviction rate
is high and there is available GPU memory headroom. Never recommends
exceeding physical GPU memory.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from infersight.plugins.base import Issue, Recommendation, RecommenderPlugin

# Maximum safe GPU memory utilization fraction to recommend
_MAX_SAFE_GPU_MEMORY_FRACTION = 0.95
# Step size for increasing gpu_memory_utilization
_MEMORY_FRACTION_STEP = 0.05
# High eviction rate threshold (evictions/s) that warrants recommendation
_HIGH_EVICTION_RATE = 1.0


class KvCacheSizeRecommender(RecommenderPlugin):
    """Recommends increasing KV cache allocation when eviction rate is high."""

    @property
    def recommender_name(self) -> str:
        return "kv_cache_size_recommender"

    @property
    def handles_issue_types(self) -> list[str]:
        return ["kv_cache_effectiveness", "memory_fragmentation"]

    async def recommend(self, issue: Issue) -> list[Recommendation]:
        eviction_rate = float(issue.supporting_metrics.get("avg_kv_cache_eviction_rate", 0.0))
        if eviction_rate < _HIGH_EVICTION_RATE:
            return []

        # Estimate current and recommended gpu_memory_utilization
        # from GPU metrics if available, else use safe defaults
        gpu_devices: list[dict[str, Any]] = issue.supporting_metrics.get("gpu_devices", [])
        if gpu_devices:
            avg_mem_util_pct = sum(
                float(g.get("memory_utilization_pct", 0)) for g in gpu_devices
            ) / len(gpu_devices)
            current_fraction = round(avg_mem_util_pct / 100, 2)
        else:
            # Fall back to a conservative default
            current_fraction = 0.85

        recommended_fraction = min(
            current_fraction + _MEMORY_FRACTION_STEP, _MAX_SAFE_GPU_MEMORY_FRACTION
        )

        if recommended_fraction <= current_fraction:
            return []

        # Safety constraint: flag if approaching physical limit
        risk_note = ""
        if recommended_fraction >= 0.92:
            risk_note = (
                " RISK: Allocation is close to physical GPU memory limit. "
                "Monitor for OOM errors after applying."
            )

        engine = str(issue.supporting_metrics.get("engine", "unknown"))
        snippet = (
            f"python -m vllm.entrypoints.openai.api_server \\\n"
            f"  --gpu-memory-utilization {recommended_fraction} \\\n"
            "  # ... other args"
            if engine in ("vllm", "unknown")
            else f"# Set gpu_memory_utilization={recommended_fraction} in your engine config"
        )

        return [
            Recommendation(
                rec_id=f"kv_cache_size-{issue.deployment_id}",
                issue_id=issue.issue_id,
                deployment_id=issue.deployment_id,
                plugin_name=self.recommender_name,
                target_parameter="gpu_memory_utilization",
                current_value=current_fraction,
                recommended_value=recommended_fraction,
                reasoning=(
                    f"KV cache eviction rate is {eviction_rate:.2f}/s, indicating blocks are "
                    "being evicted before reuse. Increasing gpu_memory_utilization from "
                    f"{current_fraction} to {recommended_fraction} allocates more GPU memory "
                    f"to the KV cache, reducing evictions.{risk_note}"
                ),
                estimated_impact=(
                    f"Increasing KV cache allocation by {_MEMORY_FRACTION_STEP*100:.0f}% of "
                    "GPU memory typically reduces eviction rate by 30–60% for workloads with "
                    "long contexts, improving cache hit rate and reducing recomputation cost."
                ),
                engine_config_snippet=snippet,
                rank=2,
                created_at=datetime.now(tz=UTC),
            )
        ]
