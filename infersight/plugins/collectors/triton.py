"""Collector for NVIDIA Triton's model statistics and Prometheus endpoints.

Triton's ``/v2/models/stats`` response supplies per-model request counters and
latency totals.  Its Prometheus endpoint supplies instantaneous queue depth;
when GPU utilization metrics are exposed there they are normalized too.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from infersight.plugins.base import CollectorPlugin
from infersight.plugins.collectors.vllm import _parse_metrics
from infersight.scheduler import CollectionError
from infersight.schema import CanonicalMetric, GPUDeviceMetrics, HistogramBuckets


class TritonCollector(CollectorPlugin):
    """Collect aggregate deployment metrics from an NVIDIA Triton server."""

    def __init__(self, endpoint: str, deployment_id: str, timeout_seconds: int = 10) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._deployment_id = deployment_id
        self._timeout_seconds = timeout_seconds
        self._previous: tuple[datetime, int] | None = None

    @property
    def engine_name(self) -> str:
        return "triton"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(f"{self._endpoint}/v2/health/ready")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def collect(self) -> CanonicalMetric:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                stats_response, metrics_response = await asyncio.gather(
                    client.get(f"{self._endpoint}/v2/models/stats"),
                    client.get(f"{self._endpoint}/metrics"),
                )
                stats_response.raise_for_status()
                metrics_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectionError(f"Could not collect Triton metrics: {exc}") from exc

        model_stats = _model_stats(stats_response.json())
        now = datetime.now(UTC)
        total_requests = sum(_count(stat, "success") for stat in model_stats)
        errors = sum(_count(stat, "fail") for stat in model_stats)
        request_rps = self._request_rate(now, total_requests)
        values, labels = _parse_metrics(metrics_response.text)
        return CanonicalMetric(
            timestamp=now,
            engine=self.engine_name,
            deployment_id=self._deployment_id,
            model_name=_model_name(model_stats, labels),
            decode_throughput_tps=0,
            request_throughput_rps=request_rps,
            queue_depth=_queue_depth(values),
            queue_wait_ms=_queue_wait(model_stats),
            gpu_devices=_gpu_devices(metrics_response.text),
            total_requests=total_requests,
            error_count=errors,
        )

    def _request_rate(self, now: datetime, total_requests: int) -> float:
        previous = self._previous
        self._previous = (now, total_requests)
        if previous is None:
            return 0
        seconds = (now - previous[0]).total_seconds()
        if seconds <= 0:
            return 0
        return max(0, (total_requests - previous[1]) / seconds)


def _model_stats(payload: Any) -> list[dict[str, Any]]:
    """Return only well-formed model entries from a Triton stats response."""
    if not isinstance(payload, dict):
        return []
    raw_stats = payload.get("model_stats", [])
    return (
        [entry for entry in raw_stats if isinstance(entry, dict)]
        if isinstance(raw_stats, list)
        else []
    )


def _count(stat: dict[str, Any], name: str) -> int:
    inference = stat.get("inference_stats", {})
    value = inference.get(name, {}) if isinstance(inference, dict) else {}
    count = value.get("count", 0) if isinstance(value, dict) else 0
    return int(count) if isinstance(count, int | float) else 0


def _model_name(stats: list[dict[str, Any]], labels: dict[str, str]) -> str:
    names = {str(stat["name"]) for stat in stats if stat.get("name")}
    if len(names) == 1:
        return names.pop()
    if len(names) > 1:
        return "multiple"
    return labels.get("model", labels.get("model_name", "unknown"))


def _queue_depth(values: dict[str, float]) -> int:
    names = ("nv_inference_pending_request_count", "nv_inference_queue_size")
    return int(sum(values.get(name, 0) for name in names))


def _queue_wait(stats: list[dict[str, Any]]) -> HistogramBuckets | None:
    count = sum(_count(stat, "queue") for stat in stats)
    total_ns = 0
    for stat in stats:
        inference = stat.get("inference_stats", {})
        queue = inference.get("queue", {}) if isinstance(inference, dict) else {}
        if isinstance(queue, dict) and isinstance(queue.get("ns"), int | float):
            total_ns += queue["ns"]
    if count == 0:
        return None
    average_ms = total_ns / count / 1_000_000
    return HistogramBuckets(
        p50=average_ms,
        p90=average_ms,
        p95=average_ms,
        p99=average_ms,
        count=count,
        sum_ms=total_ns / 1_000_000,
    )


_GPU_SAMPLE = re.compile(
    r"^(nv_gpu_(?:utilization|memory_used_bytes|memory_total_bytes))(?:\{([^}]*)\})?\s+([\d.eE+-]+)$"
)
_GPU_LABEL = re.compile(r'(?:gpu|device)="(\d+)"')


def _gpu_devices(payload: str) -> list[GPUDeviceMetrics]:
    """Normalize common Triton/DCGM GPU gauges when they are exposed."""
    values_by_device: dict[int, dict[str, float]] = {}
    for line in payload.splitlines():
        match = _GPU_SAMPLE.match(line)
        if match is None:
            continue
        name, raw_labels, raw_value = match.groups()
        label = _GPU_LABEL.search(raw_labels or "")
        if label is None:
            continue
        values_by_device.setdefault(int(label.group(1)), {})[name] = float(raw_value)

    devices: list[GPUDeviceMetrics] = []
    for index, values in sorted(values_by_device.items()):
        utilization = values.get("nv_gpu_utilization")
        memory_used = values.get("nv_gpu_memory_used_bytes")
        memory_total = values.get("nv_gpu_memory_total_bytes")
        if utilization is None or memory_used is None or memory_total is None:
            continue
        devices.append(
            GPUDeviceMetrics(
                device_index=index,
                compute_utilization_pct=utilization,
                memory_used_bytes=int(memory_used),
                memory_total_bytes=int(memory_total),
            )
        )
    return devices
