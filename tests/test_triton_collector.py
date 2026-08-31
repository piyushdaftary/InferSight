"""Integration-style tests for the NVIDIA Triton collector."""

from __future__ import annotations

import httpx
import pytest

from infersight.plugins.collectors.triton import TritonCollector


class FakeClient:
    def __init__(self, responses: dict[str, httpx.Response]) -> None:
        self.responses = responses

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> httpx.Response:
        return self.responses[url]


@pytest.mark.asyncio
async def test_collect_aggregates_triton_model_statistics(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = "http://triton"
    stats = {
        "model_stats": [
            {
                "name": "alpha",
                "inference_stats": {
                    "success": {"count": 8},
                    "fail": {"count": 1},
                    "queue": {"count": 8, "ns": 8_000_000},
                },
            },
            {
                "name": "beta",
                "inference_stats": {
                    "success": {"count": 4},
                    "fail": {"count": 0},
                    "queue": {"count": 4, "ns": 4_000_000},
                },
            },
        ]
    }
    responses = {
        f"{endpoint}/v2/models/stats": httpx.Response(
            200, json=stats, request=httpx.Request("GET", endpoint)
        ),
        f"{endpoint}/metrics": httpx.Response(
            200,
            text=(
                "nv_inference_pending_request_count 3\n"
                'nv_gpu_utilization{gpu="0"} 75\n'
                'nv_gpu_memory_used_bytes{gpu="0"} 120\n'
                'nv_gpu_memory_total_bytes{gpu="0"} 240'
            ),
            request=httpx.Request("GET", endpoint),
        ),
    }
    monkeypatch.setattr(
        "infersight.plugins.collectors.triton.httpx.AsyncClient", lambda **_: FakeClient(responses)
    )

    metric = await TritonCollector(endpoint, "deployment-a").collect()

    assert metric.engine == "triton"
    assert metric.model_name == "multiple"
    assert metric.total_requests == 12
    assert metric.error_count == 1
    assert metric.queue_depth == 3
    assert metric.queue_wait_ms is not None and metric.queue_wait_ms.sum_ms == 12
    assert metric.gpu_devices[0].memory_utilization_pct == 50
