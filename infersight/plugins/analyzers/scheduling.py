"""Scheduling Inefficiency Analyzer.

Fires when proxy signals of scheduling overhead are detected: high
prefill-to-decode ratio (prefill dominance), high inter-token latency
relative to TTFT, or very high average prompt token count suggesting
long-prefill stalls.

Falls back gracefully when the engine does not expose the relevant metrics.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime

from infersight.config import SchedulingInefficiencyConfig
from infersight.plugins.base import AnalyzerPlugin, Issue, Severity
from infersight.schema import CanonicalMetric

# Prefill/decode ratio above this value suggests prefill dominance
_PREFILL_DOMINANCE_RATIO = 3.0
# ITL p99 / TTFT p99 ratio above this value suggests context-switch stalls
_ITL_TTFT_RATIO_THRESHOLD = 2.0
# Prompt token count above which long-prefill scheduling stalls are common
_LONG_PROMPT_TOKEN_THRESHOLD = 2048.0


class SchedulingInefficiencyAnalyzer(AnalyzerPlugin):
    """Detects scheduling stalls through prefill dominance and latency ratios."""

    def __init__(self, config: SchedulingInefficiencyConfig | None = None) -> None:
        self._cfg = config or SchedulingInefficiencyConfig()

    @property
    def analyzer_name(self) -> str:
        return "scheduling_inefficiency"

    @property
    def required_metrics(self) -> list[str]:
        return ["batch", "ttft_ms", "inter_token_latency_ms"]

    async def analyze(self, metrics: list[CanonicalMetric]) -> list[Issue]:
        if not metrics:
            return []

        issues: list[Issue] = []

        # --- Signal 1: prefill dominance via batch prefill/decode ratio ---
        batch_usable = [m for m in metrics if m.batch is not None]
        if batch_usable:
            ratios = [
                m.batch.prefill_decode_ratio
                for m in batch_usable
                if m.batch is not None and m.batch.prefill_decode_ratio > 0
            ]
            if ratios:
                avg_ratio = statistics.mean(ratios)
                if avg_ratio > _PREFILL_DOMINANCE_RATIO:
                    latest = batch_usable[-1]
                    assert latest.batch is not None
                    avg_prompt = (
                        statistics.mean(
                            m.avg_prompt_tokens
                            for m in batch_usable
                            if m.avg_prompt_tokens is not None
                        )
                        if any(m.avg_prompt_tokens for m in batch_usable)
                        else None
                    )

                    supporting: dict[str, object] = {
                        "avg_prefill_decode_ratio": round(avg_ratio, 3),
                        "prefill_dominance_threshold": _PREFILL_DOMINANCE_RATIO,
                        "avg_prefill_tokens": latest.batch.prefill_tokens,
                        "avg_decode_tokens": latest.batch.decode_tokens,
                        "sample_count": len(batch_usable),
                    }
                    if avg_prompt is not None:
                        supporting["avg_prompt_tokens"] = round(avg_prompt, 1)

                    issues.append(
                        Issue(
                            issue_id="scheduling_inefficiency_prefill",
                            issue_type="scheduling_inefficiency",
                            severity=Severity.WARNING,
                            deployment_id=latest.deployment_id,
                            detected_at=datetime.now(tz=UTC),
                            supporting_metrics=supporting,
                            description=(
                                f"Prefill/decode ratio ({avg_ratio:.1f}x) exceeds threshold "
                                f"({_PREFILL_DOMINANCE_RATIO}x) — prefill work is dominating "
                                "the scheduler. Consider enabling chunked prefill "
                                "(--enable-chunked-prefill) to interleave prefill and decode."
                            ),
                            plugin_name=self.analyzer_name,
                        )
                    )

        # --- Signal 2: ITL vs TTFT ratio indicating context-switch stalls ---
        latency_usable = [
            m for m in metrics if m.ttft_ms is not None and m.inter_token_latency_ms is not None
        ]
        if latency_usable:
            ratios = []
            for m in latency_usable:
                assert m.ttft_ms is not None
                assert m.inter_token_latency_ms is not None
                if m.ttft_ms.p99 > 0:
                    ratios.append(m.inter_token_latency_ms.p99 / m.ttft_ms.p99)

            if ratios:
                avg_ratio = statistics.mean(ratios)
                if avg_ratio > _ITL_TTFT_RATIO_THRESHOLD:
                    latest_l = latency_usable[-1]
                    assert latest_l.ttft_ms is not None
                    assert latest_l.inter_token_latency_ms is not None
                    issues.append(
                        Issue(
                            issue_id="scheduling_inefficiency_itl",
                            issue_type="scheduling_inefficiency",
                            severity=Severity.WARNING,
                            deployment_id=latest_l.deployment_id,
                            detected_at=datetime.now(tz=UTC),
                            supporting_metrics={
                                "avg_itl_ttft_ratio": round(avg_ratio, 3),
                                "itl_ttft_ratio_threshold": _ITL_TTFT_RATIO_THRESHOLD,
                                "ttft_p99_ms": latest_l.ttft_ms.p99,
                                "itl_p99_ms": latest_l.inter_token_latency_ms.p99,
                                "sample_count": len(latency_usable),
                            },
                            description=(
                                f"Inter-token latency p99 ({latest_l.inter_token_latency_ms.p99:.1f}ms) "
                                f"is {avg_ratio:.1f}x the TTFT p99 ({latest_l.ttft_ms.p99:.1f}ms) — "
                                "possible context-switch overhead or preemption during decode. "
                                "Investigate max_num_batched_tokens and scheduling policy."
                            ),
                            plugin_name=self.analyzer_name,
                        )
                    )

        return issues
