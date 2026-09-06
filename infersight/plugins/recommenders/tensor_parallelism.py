"""Tensor Parallelism Recommender.

Analyzes GPU utilization imbalance and recommends adjusting
tensor_parallel_size. Validates that the recommended value is a
power of 2 and flags memory risk when reducing TP.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from infersight.plugins.base import Issue, Recommendation, RecommenderPlugin

# Threshold: if max GPU util - min GPU util exceeds this, flag imbalance
_IMBALANCE_THRESHOLD_PCT = 20.0


def _nearest_power_of_two(n: int) -> int:
    """Return the largest power of 2 less than or equal to n."""
    if n <= 1:
        return 1
    return int(2 ** math.floor(math.log2(n)))


def _validate_tp_value(tp: int, num_gpus: int) -> int:
    """Ensure TP is a valid power of 2 and does not exceed GPU count."""
    tp = _nearest_power_of_two(tp)
    return min(tp, _nearest_power_of_two(num_gpus))


class TensorParallelismRecommender(RecommenderPlugin):
    """Recommends TP size adjustments based on GPU utilization imbalance."""

    @property
    def recommender_name(self) -> str:
        return "tensor_parallelism_recommender"

    @property
    def handles_issue_types(self) -> list[str]:
        return ["gpu_underutilization"]

    async def recommend(self, issue: Issue) -> list[Recommendation]:
        gpu_devices: list[dict[str, Any]] = issue.supporting_metrics.get("gpu_devices", [])
        if len(gpu_devices) < 2:
            # TP tuning only makes sense with multiple GPUs
            return []

        utils = [float(g.get("compute_utilization_pct", 0)) for g in gpu_devices]
        imbalance = max(utils) - min(utils)
        if imbalance < _IMBALANCE_THRESHOLD_PCT:
            return []

        num_gpus = len(gpu_devices)
        current_tp = num_gpus  # assume current TP = all GPUs
        recommended_tp = _validate_tp_value(current_tp // 2, num_gpus)

        if recommended_tp >= current_tp:
            return []

        avg_util = sum(utils) / len(utils)

        # Flag memory risk when reducing TP — each GPU holds more model weight
        memory_risk_note = (
            f"WARNING: Reducing tensor_parallel_size from {current_tp} to {recommended_tp} "
            "will increase per-GPU memory usage proportionally. Verify the model fits in "
            f"GPU memory at TP={recommended_tp} before applying."
        )

        engine = str(issue.supporting_metrics.get("engine", "unknown"))
        snippet = (
            f"python -m vllm.entrypoints.openai.api_server \\\n"
            f"  --tensor-parallel-size {recommended_tp} \\\n"
            "  # ... other args"
            if engine in ("vllm", "unknown")
            else f"# Set tensor_parallel_size={recommended_tp} in your engine config"
        )

        return [
            Recommendation(
                rec_id=f"tensor_parallelism-{issue.deployment_id}",
                issue_id=issue.issue_id,
                deployment_id=issue.deployment_id,
                plugin_name=self.recommender_name,
                target_parameter="tensor_parallel_size",
                current_value=current_tp,
                recommended_value=recommended_tp,
                reasoning=(
                    f"GPU utilization imbalance of {imbalance:.1f}% detected across "
                    f"{num_gpus} GPUs (avg: {avg_util:.1f}%, max-min spread: {imbalance:.1f}%). "
                    f"Reducing tensor_parallel_size from {current_tp} to {recommended_tp} "
                    "may improve utilization balance. "
                    f"{memory_risk_note}"
                ),
                estimated_impact=(
                    "Conservative estimate: 10–25% improvement in GPU utilization balance. "
                    "Actual impact depends on model architecture and attention head count "
                    "(TP value must evenly divide the number of attention heads)."
                ),
                engine_config_snippet=snippet,
                rank=3,
                created_at=datetime.now(tz=UTC),
            )
        ]
