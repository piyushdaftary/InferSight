"""Collector for SGLang's Prometheus-compatible metrics endpoint."""

from infersight.plugins.collectors.vllm import VLLMCollector


class SGLangCollector(VLLMCollector):
    """Normalize SGLang's vLLM-like Prometheus metric surface."""

    metric_prefix = "sglang:"

    @property
    def engine_name(self) -> str:
        return "sglang"
