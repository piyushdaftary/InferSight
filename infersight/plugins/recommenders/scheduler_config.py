"""Scheduler Config Recommender.

Recommends adjustments to max_num_batched_tokens and scheduling policy
when scheduling inefficiency is detected. References the specific metric
that triggered the issue.
"""

from __future__ import annotations

from datetime import UTC, datetime

from infersight.plugins.base import Issue, Recommendation, RecommenderPlugin

# Default max_num_batched_tokens if current value not in supporting_metrics
_DEFAULT_MAX_BATCHED_TOKENS = 2048
_RECOMMENDED_MAX_BATCHED_TOKENS = 8192


def _vllm_snippet(max_batched_tokens: int) -> str:
    return (
        f"python -m vllm.entrypoints.openai.api_server \\\n"
        f"  --max-num-batched-tokens {max_batched_tokens} \\\n"
        "  --enable-chunked-prefill \\\n"
        "  # ... other args"
    )


def _sglang_snippet(max_batched_tokens: int) -> str:
    return (
        f"python -m sglang.launch_server \\\n"
        f"  --max-prefill-tokens {max_batched_tokens} \\\n"
        "  # ... other args"
    )


class SchedulerConfigRecommender(RecommenderPlugin):
    """Recommends scheduler tuning to reduce prefill stalls and context-switch overhead."""

    @property
    def recommender_name(self) -> str:
        return "scheduler_config_recommender"

    @property
    def handles_issue_types(self) -> list[str]:
        return ["scheduling_inefficiency"]

    async def recommend(self, issue: Issue) -> list[Recommendation]:
        recs: list[Recommendation] = []
        engine = str(issue.supporting_metrics.get("engine", "unknown"))

        # --- Recommendation 1: increase max_num_batched_tokens ---
        current_tokens = int(
            issue.supporting_metrics.get("max_num_batched_tokens", _DEFAULT_MAX_BATCHED_TOKENS)
        )
        recommended_tokens = max(current_tokens * 2, _RECOMMENDED_MAX_BATCHED_TOKENS)

        if engine in ("vllm", "sglang", "unknown"):
            snippet = (
                _vllm_snippet(recommended_tokens)
                if engine != "sglang"
                else _sglang_snippet(recommended_tokens)
            )

            # Surface the triggering metric in the reasoning
            ratio = issue.supporting_metrics.get("avg_prefill_decode_ratio")
            itl_ratio = issue.supporting_metrics.get("avg_itl_ttft_ratio")
            if ratio is not None:
                trigger = f"prefill/decode ratio of {float(ratio):.1f}x"
            elif itl_ratio is not None:
                trigger = f"ITL/TTFT ratio of {float(itl_ratio):.1f}x"
            else:
                trigger = "scheduling inefficiency"

            recs.append(
                Recommendation(
                    rec_id=f"scheduler_batched_tokens-{issue.deployment_id}",
                    issue_id=issue.issue_id,
                    deployment_id=issue.deployment_id,
                    plugin_name=self.recommender_name,
                    target_parameter="max_num_batched_tokens",
                    current_value=current_tokens,
                    recommended_value=recommended_tokens,
                    reasoning=(
                        f"Detected {trigger}. Increasing max_num_batched_tokens from "
                        f"{current_tokens} to {recommended_tokens} allows the scheduler to "
                        "process larger prefill chunks per step, reducing the number of "
                        "scheduling iterations and context-switch overhead."
                    ),
                    estimated_impact=(
                        "10–30% reduction in TTFT for long-prompt workloads; "
                        "improved decode throughput by reducing scheduler preemptions."
                    ),
                    engine_config_snippet=snippet,
                    rank=2,
                    created_at=datetime.now(tz=UTC),
                )
            )

        # --- Recommendation 2: enable chunked prefill for prefill dominance ---
        if issue.issue_id == "scheduling_inefficiency_prefill" and engine in ("vllm", "unknown"):
            recs.append(
                Recommendation(
                    rec_id=f"chunked_prefill-{issue.deployment_id}",
                    issue_id=issue.issue_id,
                    deployment_id=issue.deployment_id,
                    plugin_name=self.recommender_name,
                    target_parameter="--enable-chunked-prefill",
                    current_value=False,
                    recommended_value=True,
                    reasoning=(
                        "Prefill/decode ratio indicates prefill work is dominating the "
                        "scheduler. Chunked prefill interleaves prefill and decode steps, "
                        "preventing long-prefill requests from blocking decode progress."
                    ),
                    estimated_impact=(
                        "Reduces p99 TTFT by spreading prefill cost across multiple steps; "
                        "improves decode throughput consistency."
                    ),
                    engine_config_snippet=(
                        "python -m vllm.entrypoints.openai.api_server \\\n"
                        "  --enable-chunked-prefill \\\n"
                        "  # ... other args"
                    ),
                    rank=1,
                    created_at=datetime.now(tz=UTC),
                )
            )

        return recs
