"""Batch Size Recommender.

Recommends increasing max_num_seqs (or engine equivalent) when batch
efficiency is low or decode throughput is bottlenecked. Doubles the
current value, capped at a safety maximum.
"""

from __future__ import annotations

from datetime import UTC, datetime

from infersight.plugins.base import Issue, Recommendation, RecommenderPlugin

# Safety cap — never recommend more than this many concurrent sequences
_MAX_SAFE_SEQS = 1024

# Engine-specific parameter names for max concurrent sequences
_MAX_SEQS_PARAM: dict[str, str] = {
    "vllm": "max_num_seqs",
    "sglang": "max-running-requests",
    "tgi": "max-concurrent-requests",
    "triton": "dynamic_batching.max_queue_size",
    "kserve": "max-concurrent-requests",
}
_DEFAULT_PARAM = "max_num_seqs"


def _engine_snippet(engine: str, param: str, value: int) -> str:
    if engine == "vllm":
        return (
            f"python -m vllm.entrypoints.openai.api_server \\\n"
            f"  --{param} {value} \\\n"
            "  # ... other args"
        )
    if engine == "sglang":
        return (
            f"python -m sglang.launch_server \\\n" f"  --{param} {value} \\\n" "  # ... other args"
        )
    if engine == "tgi":
        return f"text-generation-launcher \\\n" f"  --{param}={value} \\\n" "  # ... other args"
    return f"# Set {param}={value} in your engine configuration"


class BatchSizeRecommender(RecommenderPlugin):
    """Recommends doubling max concurrent sequences to improve batch utilization."""

    @property
    def recommender_name(self) -> str:
        return "batch_size_recommender"

    @property
    def handles_issue_types(self) -> list[str]:
        return ["batch_efficiency", "decode_bottleneck"]

    async def recommend(self, issue: Issue) -> list[Recommendation]:
        max_batch = issue.supporting_metrics.get("max_batch_size")
        if max_batch is None:
            return []

        current = int(max_batch)
        # Formula: double, cap at safety maximum
        recommended = min(current * 2, _MAX_SAFE_SEQS)
        if recommended <= current:
            return []

        engine = str(issue.supporting_metrics.get("engine", "unknown"))
        param = _MAX_SEQS_PARAM.get(engine, _DEFAULT_PARAM)

        fill_rate = issue.supporting_metrics.get("avg_fill_rate")
        fill_context = (
            f" (current fill rate: {float(fill_rate):.2f})" if fill_rate is not None else ""
        )

        return [
            Recommendation(
                rec_id=f"batch_size-{issue.deployment_id}",
                issue_id=issue.issue_id,
                deployment_id=issue.deployment_id,
                plugin_name=self.recommender_name,
                target_parameter=param,
                current_value=current,
                recommended_value=recommended,
                reasoning=(
                    f"Batch capacity is underutilized{fill_context}. "
                    f"Doubling {param} from {current} to {recommended} "
                    f"(capped at safety maximum {_MAX_SAFE_SEQS}) allows the engine to "
                    "process more concurrent requests, improving throughput and fill rate."
                ),
                estimated_impact=(
                    f"Expected 20–50% improvement in batch fill rate and decode throughput "
                    f"by increasing {param} from {current} to {recommended}."
                ),
                engine_config_snippet=_engine_snippet(engine, param, recommended),
                rank=2,
                created_at=datetime.now(tz=UTC),
            )
        ]
