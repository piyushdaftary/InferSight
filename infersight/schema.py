"""Canonical metric schema for InferSight.

All collector plugins normalize engine output into these Pydantic v2 models.
Schema version is tracked via the SCHEMA_VERSION constant (currently "1.0").
Breaking changes increment the major version.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0"


class HistogramBuckets(BaseModel):
    """Configurable percentile buckets for latency histograms."""

    p50: float = Field(..., description="50th percentile in milliseconds")
    p90: float = Field(..., description="90th percentile in milliseconds")
    p95: float = Field(..., description="95th percentile in milliseconds")
    p99: float = Field(..., description="99th percentile in milliseconds")
    count: int = Field(..., ge=0, description="Total sample count in window")
    sum_ms: float = Field(..., ge=0, description="Sum of all values in ms")


class GPUDeviceMetrics(BaseModel):
    """Per-GPU device metrics."""

    device_index: int = Field(..., ge=0)
    compute_utilization_pct: float = Field(..., ge=0, le=100)
    memory_used_bytes: int = Field(..., ge=0)
    memory_total_bytes: int = Field(..., gt=0)

    @property
    def memory_utilization_pct(self) -> float:
        return (self.memory_used_bytes / self.memory_total_bytes) * 100


class KVCacheMetrics(BaseModel):
    """KV cache health metrics (optional — only emitted by supporting engines)."""

    hit_rate: float = Field(..., ge=0, le=1, description="Fraction of requests hitting cache")
    miss_rate: float = Field(..., ge=0, le=1)
    eviction_rate: float = Field(..., ge=0, description="Evictions per second")
    used_blocks: int = Field(..., ge=0)
    total_blocks: int = Field(..., gt=0)
    prefix_caching_enabled: bool = False

    @model_validator(mode="after")
    def rates_sum_to_one(self) -> KVCacheMetrics:
        if abs(self.hit_rate + self.miss_rate - 1.0) > 1e-3:
            raise ValueError("hit_rate + miss_rate must equal 1.0")
        return self


class BatchMetrics(BaseModel):
    """Batch efficiency metrics."""

    avg_batch_size: float = Field(..., ge=0)
    max_batch_size: int = Field(..., gt=0)
    fill_rate: float = Field(..., ge=0, le=1, description="avg_batch_size / max_batch_size")
    prefill_tokens: int = Field(..., ge=0)
    decode_tokens: int = Field(..., ge=0)
    prefill_decode_ratio: float = Field(..., ge=0)


class CanonicalMetric(BaseModel):
    """
    Top-level normalized metric snapshot from a single engine scrape.
    This is the unit of storage and the input to all analyzers.
    """

    schema_version: str = Field(default=SCHEMA_VERSION)
    timestamp: datetime
    engine: str = Field(..., description="Engine type, e.g. 'vllm', 'sglang', 'tgi'")
    engine_version: str | None = None
    deployment_id: str = Field(..., description="Unique identifier for this replica/deployment")
    model_name: str

    # Latency
    ttft_ms: HistogramBuckets | None = None
    inter_token_latency_ms: HistogramBuckets | None = None

    # Throughput
    decode_throughput_tps: float = Field(..., ge=0, description="Tokens per second, aggregate")
    request_throughput_rps: float = Field(..., ge=0, description="Requests per second")

    # Queue
    queue_depth: int = Field(..., ge=0)
    queue_wait_ms: HistogramBuckets | None = None

    # GPU
    gpu_devices: list[GPUDeviceMetrics] = Field(default_factory=list)

    # KV cache (optional)
    kv_cache: KVCacheMetrics | None = None

    # Batch
    batch: BatchMetrics | None = None

    # Request metadata (aggregated counts in collection window)
    total_requests: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    avg_prompt_tokens: float | None = None
    avg_output_tokens: float | None = None
