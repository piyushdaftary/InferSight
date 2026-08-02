"""Collector for Hugging Face Text Generation Inference metrics."""

from infersight.plugins.collectors.vllm import VLLMCollector


class TGICollector(VLLMCollector):
    """Normalize TGI's Prometheus metrics into the canonical schema.

    TGI does not expose KV-cache metrics, so the inherited collector leaves
    that optional canonical field unset.
    """

    metric_prefix = "tgi_"
    _metric_names = {
        "generation_tokens_total": "request_generated_tokens_sum",
        "request_success_total": "request_success",
        "num_requests_waiting": "queue_size",
        "time_to_first_token_seconds": "request_duration",
        "inter_token_latency_seconds": "request_mean_time_per_token_duration",
        "request_queue_time_seconds": "request_queue_duration",
    }

    @property
    def engine_name(self) -> str:
        return "tgi"

    def _metric(self, name: str) -> str:
        return f"{self.metric_prefix}{self._metric_names.get(name, name)}"
