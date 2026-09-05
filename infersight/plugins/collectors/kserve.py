"""Collector for KServe InferenceService metadata and Prometheus metrics.

KServe supports both the legacy V1 protocol (``/v1/models``) and the Open
Inference Protocol V2 (``/v2`` and ``/v2/models/<name>``).  The collector
tries V2 first and falls back to V1, while accepting common metric names from
KServe model servers and the Knative queue-proxy sidecar.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from infersight.plugins.base import CollectorPlugin
from infersight.plugins.collectors.vllm import _histogram, _parse_metrics
from infersight.scheduler import CollectionError
from infersight.schema import CanonicalMetric, HistogramBuckets

_REQUEST_COUNTERS = ("kserve_request_count", "kserve_requests_total", "request_count")
_LATENCY_HISTOGRAMS = (
    "kserve_request_latency_seconds",
    "request_latency_seconds",
    "request_processing_seconds",
)
_QUEUE_DEPTHS = ("kserve_queue_depth", "queue_depth", "queue_proxy_queue_depth")


class KServeCollector(CollectorPlugin):
    """Normalize KServe model-server and sidecar metrics into a snapshot."""

    def __init__(
        self,
        endpoint: str,
        deployment_id: str,
        model_name: str | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._deployment_id = deployment_id
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._previous: tuple[datetime, float] | None = None

    @property
    def engine_name(self) -> str:
        return "kserve"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(f"{self._endpoint}/v2/health/ready")
                if response.is_success:
                    return True
                response = await client.get(f"{self._endpoint}/v1/models")
                return response.is_success
        except httpx.HTTPError:
            return False

    async def collect(self) -> CanonicalMetric:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                metrics_response, metadata = await asyncio.gather(
                    client.get(f"{self._endpoint}/metrics"), self._metadata(client)
                )
                metrics_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectionError(f"Could not collect KServe metrics: {exc}") from exc

        values, labels = _parse_metrics(metrics_response.text)
        now = datetime.now(UTC)
        requests = _first_value(values, _REQUEST_COUNTERS)
        return CanonicalMetric(
            timestamp=now,
            engine=self.engine_name,
            deployment_id=self._deployment_id,
            model_name=_model_name(metadata, labels, self._model_name),
            ttft_ms=_first_histogram(values, _LATENCY_HISTOGRAMS),
            request_throughput_rps=self._request_rate(now, requests),
            decode_throughput_tps=0,
            queue_depth=int(_first_value(values, _QUEUE_DEPTHS)),
            total_requests=int(requests),
        )

    async def _metadata(self, client: httpx.AsyncClient) -> dict[str, Any]:
        """Read model metadata with a V2-first, V1-compatible fallback."""
        v2_path = f"/v2/models/{self._model_name}" if self._model_name else "/v2"
        response = await client.get(f"{self._endpoint}{v2_path}")
        if response.is_success:
            return _json_object(response)

        response = await client.get(f"{self._endpoint}/v1/models")
        response.raise_for_status()
        return _json_object(response)

    def _request_rate(self, now: datetime, requests: float) -> float:
        previous = self._previous
        self._previous = (now, requests)
        if previous is None:
            return 0
        seconds = (now - previous[0]).total_seconds()
        return max(0, (requests - previous[1]) / seconds) if seconds > 0 else 0


def _json_object(response: httpx.Response) -> dict[str, Any]:
    """Return JSON object metadata; ignore non-object payloads from custom servers."""
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _model_name(
    metadata: dict[str, Any], labels: dict[str, str], configured_name: str | None
) -> str:
    """Prefer explicitly configured and protocol metadata names over metric labels."""
    if configured_name:
        return configured_name
    name = metadata.get("name")
    if isinstance(name, str) and name:
        return name
    models = metadata.get("models")
    if isinstance(models, list) and models and isinstance(models[0], str):
        return models[0]
    return labels.get("model_name", labels.get("model", "unknown"))


def _first_value(values: dict[str, float], names: tuple[str, ...]) -> float:
    return next((values[name] for name in names if name in values), 0.0)


def _first_histogram(
    values: dict[str, float], names: tuple[str, ...]
) -> HistogramBuckets | None:
    return next((histogram for name in names if (histogram := _histogram(values, name))), None)
