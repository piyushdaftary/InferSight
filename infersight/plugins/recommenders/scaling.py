"""Scaling Recommender.

Generates scale-up recommendations for queue saturation and scale-down
recommendations for persistent GPU underutilization. Actual scaling
requires user action via their orchestrator (Kubernetes HPA, etc.).
"""

from __future__ import annotations

from datetime import UTC, datetime

from infersight.plugins.base import Issue, Recommendation, RecommenderPlugin


class ScalingRecommender(RecommenderPlugin):
    """Recommends replica scaling based on queue saturation or GPU underutilization."""

    @property
    def recommender_name(self) -> str:
        return "scaling_recommender"

    @property
    def handles_issue_types(self) -> list[str]:
        return ["queue_saturation", "gpu_underutilization"]

    async def recommend(self, issue: Issue) -> list[Recommendation]:
        if issue.issue_type == "queue_saturation":
            return self._scale_up(issue)
        if issue.issue_type == "gpu_underutilization":
            return self._scale_down(issue)
        return []

    def _scale_up(self, issue: Issue) -> list[Recommendation]:
        avg_depth = float(issue.supporting_metrics.get("avg_queue_depth", 0))
        max_batch = int(issue.supporting_metrics.get("max_batch_size", 1))
        multiplier = float(issue.supporting_metrics.get("depth_multiplier", 2.0))
        avg_rps = float(issue.supporting_metrics.get("avg_request_throughput_rps", 0))

        # Recommend enough replicas to bring queue depth below the threshold
        # Simple heuristic: add ceil(avg_depth / max_batch) replicas
        import math

        extra = math.ceil(avg_depth / max_batch) if max_batch > 0 else 1
        recommended_replicas = f"current + {extra}"

        return [
            Recommendation(
                rec_id=f"scale_up-{issue.deployment_id}",
                issue_id=issue.issue_id,
                deployment_id=issue.deployment_id,
                plugin_name=self.recommender_name,
                target_parameter="replicas",
                current_value="current",
                recommended_value=recommended_replicas,
                reasoning=(
                    f"Queue depth ({avg_depth:.0f}) exceeds {multiplier}× max_batch_size "
                    f"({max_batch}) at {avg_rps:.2f} rps. Adding {extra} replica(s) should "
                    "distribute load and bring queue depth below the saturation threshold. "
                    "NOTE: Actual scaling requires action via your orchestrator "
                    "(Kubernetes HPA, Ray autoscaler, etc.)."
                ),
                estimated_impact=(
                    f"Adding {extra} replica(s) expected to reduce queue depth by ~50% and "
                    "improve p99 latency by reducing queue wait time."
                ),
                engine_config_snippet=(
                    "# Kubernetes HPA example:\n"
                    "kubectl scale deployment <your-deployment> \\\n"
                    f"  --replicas=$(( $(kubectl get deployment <your-deployment> "
                    f"-o jsonpath='{{.spec.replicas}}') + {extra} ))\n\n"
                    "# Or update your HPA minReplicas/maxReplicas in values.yaml"
                ),
                rank=1,
                created_at=datetime.now(tz=UTC),
            )
        ]

    def _scale_down(self, issue: Issue) -> list[Recommendation]:
        avg_util = float(issue.supporting_metrics.get("avg_gpu_utilization_pct", 0))
        threshold = float(issue.supporting_metrics.get("utilization_threshold_pct", 40.0))
        avg_rps = float(issue.supporting_metrics.get("avg_request_throughput_rps", 0))

        return [
            Recommendation(
                rec_id=f"scale_down-{issue.deployment_id}",
                issue_id=issue.issue_id,
                deployment_id=issue.deployment_id,
                plugin_name=self.recommender_name,
                target_parameter="replicas",
                current_value="current",
                recommended_value="current - 1",
                reasoning=(
                    f"Average GPU utilization ({avg_util:.1f}%) has been below threshold "
                    f"({threshold}%) at {avg_rps:.2f} rps. Reducing replicas by 1 can "
                    "lower infrastructure cost while maintaining adequate capacity. "
                    "NOTE: Actual scaling requires action via your orchestrator. "
                    "Monitor latency after scaling down to confirm SLOs are maintained."
                ),
                estimated_impact=(
                    "Removing 1 replica reduces infrastructure cost proportionally. "
                    "Expected latency increase is minimal if current utilization is low — "
                    "verify p99 TTFT remains within SLO after the change."
                ),
                engine_config_snippet=(
                    "# Kubernetes example:\n"
                    "kubectl scale deployment <your-deployment> \\\n"
                    "  --replicas=$(( $(kubectl get deployment <your-deployment> "
                    "-o jsonpath='{.spec.replicas}') - 1 ))\n\n"
                    "# Or reduce HPA minReplicas in values.yaml"
                ),
                rank=3,
                created_at=datetime.now(tz=UTC),
            )
        ]
