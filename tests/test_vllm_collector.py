"""Integration-style tests for the vLLM Prometheus collector."""

from __future__ import annotations

import httpx
import pytest

from infersight.plugins.collectors.vllm import VLLMCollector

METRICS = """
vllm:num_requests_waiting{model_name="test-model"} 3
vllm:kv_cache_usage_perc{model_name="test-model"} 0.7
vllm:prefix_cache_queries{model_name="test-model"} 10
vllm:prefix_cache_hits{model_name="test-model"} 8
vllm:generation_tokens_total{model_name="test-model"} 100
vllm:request_success_total{model_name="test-model"} 5
vllm:time_to_first_token_seconds_bucket{le="0.01"} 5
vllm:time_to_first_token_seconds_bucket{le="0.02"} 10
vllm:time_to_first_token_seconds_count 10
vllm:time_to_first_token_seconds_sum 0.15
"""


class FakeClient:
    """Small async HTTP client fixture for collector endpoint tests."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, _: str) -> httpx.Response:
        return self.response


@pytest.mark.asyncio
async def test_collect_normalizes_vllm_prometheus_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mocked metrics endpoint produces a populated canonical metric."""
    response = httpx.Response(200, text=METRICS, request=httpx.Request("GET", "http://vllm"))
    monkeypatch.setattr(
        "infersight.plugins.collectors.vllm.httpx.AsyncClient", lambda **_: FakeClient(response)
    )
    collector = VLLMCollector("http://vllm", "deployment-a")

    metric = await collector.collect()

    assert metric.engine == "vllm"
    assert metric.deployment_id == "deployment-a"
    assert metric.model_name == "test-model"
    assert metric.queue_depth == 3
    assert metric.ttft_ms is not None and metric.ttft_ms.p50 == 10
    assert metric.kv_cache is not None and metric.kv_cache.hit_rate == 0.8


@pytest.mark.asyncio
async def test_health_check_reflects_endpoint_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Health is false for a non-successful vLLM health response."""
    response = httpx.Response(503, request=httpx.Request("GET", "http://vllm"))
    monkeypatch.setattr(
        "infersight.plugins.collectors.vllm.httpx.AsyncClient", lambda **_: FakeClient(response)
    )

    assert not await VLLMCollector("http://vllm", "deployment-a").health_check()
