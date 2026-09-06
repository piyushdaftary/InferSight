"""Prefix Cache Recommender.

Recommends enabling prefix caching when KV cache effectiveness is low
and prefix caching is currently disabled.
"""

from __future__ import annotations

from datetime import UTC, datetime

from infersight.plugins.base import Issue, Recommendation, RecommenderPlugin

# Engine-specific flags to enable prefix caching
_PREFIX_CACHE_FLAGS: dict[str, str] = {
    "vllm": "--enable-prefix-caching",
    "sglang": "--enable-flashinfer-cache",
    "tgi": "--prefix-caching",
}
_DEFAULT_FLAG = "--enable-prefix-caching"


def _engine_snippet(engine: str, flag: str) -> str:
    if engine == "vllm":
        return f"python -m vllm.entrypoints.openai.api_server \\\n  {flag} \\\n  # ... other args"
    if engine == "sglang":
        return f"python -m sglang.launch_server \\\n  {flag} \\\n  # ... other args"
    if engine == "tgi":
        return "text-generation-launcher \\\n" f"  {flag} \\\n" "  # ... other args"
    return f"# Add {flag} to your engine startup command"


class PrefixCacheRecommender(RecommenderPlugin):
    """Recommends enabling prefix caching to improve KV cache hit rate."""

    @property
    def recommender_name(self) -> str:
        return "prefix_cache_recommender"

    @property
    def handles_issue_types(self) -> list[str]:
        return ["kv_cache_effectiveness"]

    async def recommend(self, issue: Issue) -> list[Recommendation]:
        # Only act when prefix caching is explicitly off
        if issue.supporting_metrics.get("prefix_caching_enabled", True):
            return []

        hit_rate = issue.supporting_metrics.get("avg_hit_rate", 0.0)
        threshold = issue.supporting_metrics.get("hit_rate_threshold", 0.30)
        gap = threshold - float(hit_rate)
        engine = issue.supporting_metrics.get("engine", "unknown")
        flag = _PREFIX_CACHE_FLAGS.get(str(engine), _DEFAULT_FLAG)

        estimated_impact = (
            f"Hit rate gap of {gap:.2f} — enabling prefix caching typically improves "
            "KV cache hit rate by 40–80% for workloads with repeated prompt prefixes, "
            "reducing TTFT proportionally."
        )

        return [
            Recommendation(
                rec_id=f"prefix_cache-{issue.deployment_id}",
                issue_id=issue.issue_id,
                deployment_id=issue.deployment_id,
                plugin_name=self.recommender_name,
                target_parameter=flag,
                current_value=False,
                recommended_value=True,
                reasoning=(
                    f"KV cache hit rate is {float(hit_rate):.2f}, below threshold "
                    f"({threshold}). Prefix caching is disabled. Enabling it allows the "
                    "engine to reuse KV blocks for shared prompt prefixes across requests."
                ),
                estimated_impact=estimated_impact,
                engine_config_snippet=_engine_snippet(str(engine), flag),
                rank=1,
                created_at=datetime.now(tz=UTC),
            )
        ]
