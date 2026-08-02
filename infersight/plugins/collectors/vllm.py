"""Collector for vLLM's Prometheus-compatible ``/metrics`` endpoint."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx

from infersight.plugins.base import CollectorPlugin
from infersight.scheduler import CollectionError
from infersight.schema import CanonicalMetric, HistogramBuckets, KVCacheMetrics

_SAMPLE = re.compile(r"^([^\s{]+)(?:\{([^}]*)\})?\s+([\d.eE+-]+)$")
_LABEL = re.compile(r'(\w+)="([^"]*)"')


class VLLMCollector(CollectorPlugin):
    """Collect vLLM server metrics and normalize them into a metric snapshot."""

    def __init__(self, endpoint: str, deployment_id: str, timeout_seconds: int = 10) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._deployment_id = deployment_id
        self._timeout_seconds = timeout_seconds
        self._previous: tuple[datetime, float, float] | None = None

    @property
    def engine_name(self) -> str:
        return "vllm"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(f"{self._endpoint}/health")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def collect(self) -> CanonicalMetric:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(f"{self._endpoint}/metrics")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectionError(f"Could not collect vLLM metrics: {exc}") from exc
        values, labels = _parse_metrics(response.text)
        now = datetime.now(UTC)
        generated = values.get("vllm:generation_tokens_total", 0.0)
        requests = values.get("vllm:request_success_total", 0.0)
        decode_tps, request_rps = self._rates(now, generated, requests)
        model_name = labels.get("model_name", "unknown")
        hits = values.get("vllm:prefix_cache_hits", 0.0)
        queries = values.get("vllm:prefix_cache_queries", 0.0)
        return CanonicalMetric(
            timestamp=now,
            engine="vllm",
            deployment_id=self._deployment_id,
            model_name=model_name,
            ttft_ms=_histogram(values, "vllm:time_to_first_token_seconds"),
            inter_token_latency_ms=_histogram(values, "vllm:inter_token_latency_seconds"),
            queue_wait_ms=_histogram(values, "vllm:request_queue_time_seconds"),
            decode_throughput_tps=decode_tps,
            request_throughput_rps=request_rps,
            queue_depth=int(values.get("vllm:num_requests_waiting", 0)),
            kv_cache=KVCacheMetrics(
                hit_rate=hits / queries if queries else 0,
                miss_rate=1 - hits / queries if queries else 1,
                eviction_rate=0,
                used_blocks=int(values.get("vllm:kv_cache_usage_perc", 0) * 100),
                total_blocks=100,
                prefix_caching_enabled=queries > 0,
            )
            if "vllm:kv_cache_usage_perc" in values
            else None,
        )

    def _rates(self, now: datetime, generated: float, requests: float) -> tuple[float, float]:
        previous = self._previous
        self._previous = (now, generated, requests)
        if previous is None:
            return 0, 0
        seconds = (now - previous[0]).total_seconds()
        if seconds <= 0:
            return 0, 0
        return max(0, (generated - previous[1]) / seconds), max(
            0, (requests - previous[2]) / seconds
        )


def _parse_metrics(payload: str) -> tuple[dict[str, float], dict[str, str]]:
    values: dict[str, float] = {}
    labels: dict[str, str] = {}
    for line in payload.splitlines():
        match = _SAMPLE.match(line)
        if match is None:
            continue
        name, raw_labels, raw_value = match.groups()
        metric_labels = dict(_LABEL.findall(raw_labels or ""))
        labels.update(metric_labels)
        if name.endswith("_bucket"):
            values[f"{name}:{metric_labels.get('le', '+Inf')}"] = float(raw_value)
        elif name.endswith("_count") or name.endswith("_sum"):
            values[name] = float(raw_value)
        else:
            values[name] = values.get(name, 0) + float(raw_value)
    return values, labels


def _histogram(values: dict[str, float], name: str) -> HistogramBuckets | None:
    count = values.get(f"{name}_count")
    total = values.get(f"{name}_sum")
    if count is None or total is None:
        return None
    buckets = sorted(
        (float(key.rsplit(":", 1)[1]), value)
        for key, value in values.items()
        if key.startswith(f"{name}_bucket:") and not key.endswith("+Inf")
    )

    def percentile(target: float) -> float:
        return next((boundary * 1000 for boundary, seen in buckets if seen >= count * target), 0)

    return HistogramBuckets(
        p50=percentile(0.5),
        p90=percentile(0.9),
        p95=percentile(0.95),
        p99=percentile(0.99),
        count=int(count),
        sum_ms=total * 1000,
    )
