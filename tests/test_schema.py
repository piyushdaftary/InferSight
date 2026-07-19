"""Tests for canonical metric schema validation."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from infersight.schema import SCHEMA_VERSION, CanonicalMetric, GPUDeviceMetrics, KVCacheMetrics


def test_gpu_memory_utilization_is_derived_from_bytes() -> None:
    """GPU memory utilization is calculated as a percentage."""
    gpu = GPUDeviceMetrics(
        device_index=0,
        compute_utilization_pct=75,
        memory_used_bytes=6,
        memory_total_bytes=8,
    )

    assert gpu.memory_utilization_pct == 75


def test_kv_cache_rates_must_sum_to_one() -> None:
    """Invalid cache hit/miss rate combinations are rejected."""
    with pytest.raises(ValidationError, match=r"hit_rate \+ miss_rate must equal 1.0"):
        KVCacheMetrics(
            hit_rate=0.8,
            miss_rate=0.3,
            eviction_rate=0,
            used_blocks=1,
            total_blocks=2,
        )


def test_canonical_metric_uses_current_schema_version() -> None:
    """Metric snapshots default to the published schema version."""
    metric = CanonicalMetric(
        timestamp=datetime(2026, 7, 19),
        engine="vllm",
        deployment_id="deployment-a",
        model_name="model-a",
        decode_throughput_tps=10,
        request_throughput_rps=2,
        queue_depth=0,
    )

    assert metric.schema_version == SCHEMA_VERSION


@pytest.mark.parametrize(
    ("field", "value"),
    [("compute_utilization_pct", 101), ("memory_total_bytes", 0), ("device_index", -1)],
)
def test_gpu_metrics_enforce_value_ranges(field: str, value: int) -> None:
    """GPU metrics reject values outside their documented ranges."""
    values = {
        "device_index": 0,
        "compute_utilization_pct": 75,
        "memory_used_bytes": 6,
        "memory_total_bytes": 8,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        GPUDeviceMetrics(**values)
