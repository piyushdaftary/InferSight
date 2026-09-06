"""Chunked Prefill Recommender.

Recommends enabling chunked prefill when average prompt token count is
high and scheduling stall signals indicate prefill dominance.
"""

from __future__ import annotations

from datetime import UTC, datetime

from infersight.plugins.base import Issue, Recommendation, RecommenderPlugin

_LONG_PROMPT_THRESHOLD = 512.0  # avg prompt tokens above which chunked prefill helps


class ChunkedPrefillRecommender(RecommenderPlugin):
    """Recommends enabling chunked prefill for long-prompt workloads."""

    @property
    def recommender_name(self) -> str:
        return "chunked_prefill_recommender"

    @property
    def handles_issue_types(self) -> list[str]:
        return ["scheduling_inefficiency", "decode_bottleneck"]

    async def recommend(self, issue: Issue) -> list[Recommendation]:
        avg_prompt_tokens = issue.supporting_metrics.get("avg_prompt_tokens")
        prefill_ratio = issue.supporting_metrics.get("avg_prefill_decode_ratio")

        # Need at least one signal — long prompts or high prefill ratio
        has_long_prompts = (
            avg_prompt_tokens is not None and float(avg_prompt_tokens) >= _LONG_PROMPT_THRESHOLD
        )
        has_prefill_dominance = prefill_ratio is not None and float(prefill_ratio) > 2.0

        if not has_long_prompts and not has_prefill_dominance:
            return []

        engine = str(issue.supporting_metrics.get("engine", "unknown"))
        if engine not in ("vllm", "unknown"):
            # Chunked prefill flag is vLLM-specific in this form
            return []

        context_parts = []
        if avg_prompt_tokens is not None:
            context_parts.append(f"avg_prompt_tokens={float(avg_prompt_tokens):.0f}")
        if prefill_ratio is not None:
            context_parts.append(f"prefill/decode ratio={float(prefill_ratio):.1f}x")
        context = ", ".join(context_parts)

        return [
            Recommendation(
                rec_id=f"chunked_prefill-{issue.deployment_id}",
                issue_id=issue.issue_id,
                deployment_id=issue.deployment_id,
                plugin_name=self.recommender_name,
                target_parameter="--enable-chunked-prefill",
                current_value=False,
                recommended_value=True,
                reasoning=(
                    f"Detected scheduling inefficiency with {context}. "
                    "Chunked prefill splits long prefill sequences across multiple scheduler "
                    "steps, interleaving them with decode work and preventing prefill requests "
                    "from blocking decode throughput."
                ),
                estimated_impact=(
                    "Reduces p99 TTFT for long-prompt requests by spreading prefill cost; "
                    "improves decode throughput consistency and reduces tail latency."
                ),
                engine_config_snippet=(
                    "python -m vllm.entrypoints.openai.api_server \\\n"
                    "  --enable-chunked-prefill \\\n"
                    "  --max-num-batched-tokens 8192 \\\n"
                    "  # ... other args"
                ),
                rank=1,
                created_at=datetime.now(tz=UTC),
            )
        ]
