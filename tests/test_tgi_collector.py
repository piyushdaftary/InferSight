"""Tests for the TGI Prometheus collector."""

from __future__ import annotations

import httpx
import pytest

from infersight.plugins.collectors.tgi import TGICollector


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
async def test_collect_normalizes_tgi_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        200,
        text="tgi_queue_size 3\ntgi_request_success 2\ntgi_request_generated_tokens_sum 10",
        request=httpx.Request("GET", "http://tgi"),
    )
    monkeypatch.setattr(
        "infersight.plugins.collectors.vllm.httpx.AsyncClient", lambda **_: FakeClient(response)
    )

    metric = await TGICollector("http://tgi", "deployment-a").collect()

    assert metric.engine == "tgi"
    assert metric.queue_depth == 3
    assert metric.kv_cache is None
