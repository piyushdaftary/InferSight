"""Tests for the SGLang Prometheus collector."""

from __future__ import annotations

import httpx
import pytest

from infersight.plugins.collectors.sglang import SGLangCollector


class FakeClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, _: str) -> httpx.Response:
        return self.response


@pytest.mark.asyncio
async def test_sglang_metrics_use_the_sglang_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        200,
        text='sglang:num_requests_waiting{model_name="test-model"} 4',
        request=httpx.Request("GET", "http://sglang"),
    )
    monkeypatch.setattr(
        "infersight.plugins.collectors.vllm.httpx.AsyncClient", lambda **_: FakeClient(response)
    )

    metric = await SGLangCollector("http://sglang", "deployment-a").collect()

    assert metric.engine == "sglang"
    assert metric.model_name == "test-model"
    assert metric.queue_depth == 4
