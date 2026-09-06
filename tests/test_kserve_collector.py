"""Integration-style tests for the KServe collector."""

from __future__ import annotations

import httpx
import pytest

from infersight.plugins.collectors.kserve import KServeCollector

METRICS = """
kserve_request_count{model_name="iris"} 12
kserve_queue_depth{model_name="iris"} 4
kserve_request_latency_seconds_bucket{le="0.01"} 8
kserve_request_latency_seconds_bucket{le="0.02"} 12
kserve_request_latency_seconds_count 12
kserve_request_latency_seconds_sum 0.18
"""


class FakeClient:
    """Small route-aware async HTTP client fixture."""

    def __init__(self, responses: dict[str, httpx.Response]) -> None:
        self.responses = responses

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> httpx.Response:
        return self.responses[url.rsplit("/", 1)[-1] if url.endswith("/metrics") else url]


def response(status: int, url: str, **kwargs: object) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("GET", url), **kwargs)


@pytest.mark.asyncio
async def test_collects_metrics_and_v2_model_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = "http://kserve"
    client = FakeClient(
        {
            "metrics": response(200, f"{endpoint}/metrics", text=METRICS),
            f"{endpoint}/v2/models/iris": response(
                200, f"{endpoint}/v2/models/iris", json={"name": "iris"}
            ),
        }
    )
    monkeypatch.setattr(
        "infersight.plugins.collectors.kserve.httpx.AsyncClient", lambda **_: client
    )

    metric = await KServeCollector(endpoint, "iris-service", model_name="iris").collect()

    assert metric.engine == "kserve"
    assert metric.deployment_id == "iris-service"
    assert metric.model_name == "iris"
    assert metric.total_requests == 12
    assert metric.queue_depth == 4
    assert metric.ttft_ms is not None and metric.ttft_ms.p50 == 10


@pytest.mark.asyncio
async def test_uses_v1_metadata_when_v2_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = "http://kserve"
    client = FakeClient(
        {
            "metrics": response(200, f"{endpoint}/metrics", text=METRICS),
            f"{endpoint}/v2": response(404, f"{endpoint}/v2"),
            f"{endpoint}/v1/models": response(
                200, f"{endpoint}/v1/models", json={"models": ["iris"]}
            ),
        }
    )
    monkeypatch.setattr(
        "infersight.plugins.collectors.kserve.httpx.AsyncClient", lambda **_: client
    )

    metric = await KServeCollector(endpoint, "iris-service").collect()

    assert metric.model_name == "iris"


@pytest.mark.asyncio
async def test_health_check_falls_back_to_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = "http://kserve"
    client = FakeClient(
        {
            f"{endpoint}/v2/health/ready": response(404, f"{endpoint}/v2/health/ready"),
            f"{endpoint}/v1/models": response(200, f"{endpoint}/v1/models", json={"models": []}),
        }
    )
    monkeypatch.setattr(
        "infersight.plugins.collectors.kserve.httpx.AsyncClient", lambda **_: client
    )

    assert await KServeCollector(endpoint, "iris-service").health_check()
