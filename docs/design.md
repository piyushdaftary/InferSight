# InferSight Technical Design Document

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Technology Stack](#2-technology-stack)
3. [Canonical Metric Schema](#3-canonical-metric-schema)
4. [Plugin Interfaces](#4-plugin-interfaces)
5. [REST API Reference](#5-rest-api-reference)
6. [Storage Layer](#6-storage-layer)
7. [UI Structure](#7-ui-structure)
8. [Deployment](#8-deployment)
9. [Security](#9-security)
10. [AI Copilot](#10-ai-copilot)
11. [Configuration Reference](#11-configuration-reference)
12. [Requirements Traceability](#12-requirements-traceability)

---

## 1. System Architecture

### 1.1 High-Level Overview

InferSight is a read-only intelligence layer that sits beside inference engine deployments.
It never serves models; it only observes, analyzes, and advises.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          InferSight Server                               │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────────┐ │
│  │  Collector   │   │   Analyzer   │   │        Recommender           │ │
│  │  Scheduler   │──▶│   Engine     │──▶│         Engine               │ │
│  │ (APScheduler)│   │ (plugin ABCs)│   │       (plugin ABCs)          │ │
│  └──────┬───────┘   └──────┬───────┘   └──────────────┬───────────────┘ │
│         │                  │                           │                 │
│  ┌──────▼───────────────────▼───────────────────────────▼─────────────┐ │
│  │                     Storage Layer (StorageBackend ABC)              │ │
│  │        SQLite (embedded) │ Prometheus remote-write │ InfluxDB       │ │
│  └─────────────────────────┬───────────────────────────────────────────┘ │
│                             │                                             │
│  ┌──────────────────────────▼───────────────────────────────────────────┐ │
│  │                   FastAPI Application                                 │ │
│  │  /metrics  /issues  /recommendations  /copilot  /health  /ready      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────┬──────────────────────────────────┘
                                        │ HTTP / WebSocket
          ┌─────────────────────────────┼──────────────────────────────┐
          │                             │                              │
   ┌──────▼──────┐              ┌───────▼──────┐              ┌───────▼──────┐
   │  React SPA  │              │  CLI (typer) │              │ 3rd-party    │
   │  (Vite/TS)  │              │              │              │ Prometheus/  │
   └─────────────┘              └──────────────┘              │ Grafana      │
                                                              └──────────────┘

   Inference Engines (pull or push)
   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
   │  vLLM    │ │ SGLang   │ │   TGI    │ │  Triton  │ │  KServe  │
   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

### 1.2 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Collector Scheduler** | Fires per-engine collection jobs at configurable intervals via APScheduler; handles retries with exponential backoff |
| **Collector Plugins** | Engine-specific adapters that translate raw engine metrics into `CanonicalMetric` objects |
| **Analyzer Engine** | Runs registered `AnalyzerPlugin` instances against recent metric windows; produces `Issue` objects |
| **Recommender Engine** | Maps `Issue` objects through `RecommenderPlugin` instances to produce ranked `Recommendation` objects |
| **Storage Layer** | Persists metrics, issues, and recommendations; provides query interface for time-range and deployment filters |
| **FastAPI App** | Exposes REST + WebSocket endpoints; enforces auth middleware; serves OpenAPI spec |
| **React SPA** | Single-page dashboard consuming the REST API via TanStack Query; real-time updates via WebSocket |
| **CLI** | `infersight` command built with Typer; wraps the REST API and provides `analyze-manifest` subcommand |
| **AI Copilot** | Tool-calling loop powered by LiteLLM; tools read from the Storage Layer; never writes to infrastructure |

### 1.3 Data Flow

```
Engine Scrape (every N seconds)
  → CollectorPlugin.collect() → List[CanonicalMetric]
  → StorageBackend.write_metrics()
  → AnalyzerEngine.run() → List[Issue]
  → StorageBackend.write_issues()
  → RecommenderEngine.run() → List[Recommendation]
  → StorageBackend.write_recommendations()
  → NotificationPlugin.notify() (if severity threshold met)
```

---

## 2. Technology Stack

### 2.1 Backend

| Library | Version | Purpose |
|---------|---------|---------|
| Python | 3.11+ | Runtime |
| FastAPI | 0.111.x | REST API framework, OpenAPI generation |
| Pydantic v2 | 2.7.x | Schema validation, serialization |
| APScheduler | 3.10.x | Background collection scheduling |
| LiteLLM | 1.40.x | Unified LLM API client (OpenAI, Anthropic, local) |
| httpx | 0.27.x | Async HTTP client for engine scraping |
| structlog | 24.x | Structured JSON logging |
| SQLite (stdlib) | — | Embedded storage backend |
| Typer | 0.12.x | CLI framework |
| uvicorn | 0.29.x | ASGI server |

### 2.2 Frontend

| Library | Version | Purpose |
|---------|---------|---------|
| React | 18+ | UI framework |
| TypeScript | 5.x | Type safety |
| Vite | 5.x | Build tool and dev server |
| Recharts | 2.x | Time-series and histogram charts |
| TanStack Query | 5.x | Server state management, polling |
| Tailwind CSS | 3.x | Utility-first styling |
| shadcn/ui | latest | Accessible component primitives |
| Zustand | 4.x | Client-side UI state (filters, selected deployment) |
| React Router | 6.x | Client-side routing |

### 2.3 Infrastructure / Tooling

| Tool | Purpose |
|------|---------|
| Docker | Single-container packaging |
| Helm 3 | Kubernetes deployment chart |
| pytest + hypothesis | Python testing and property-based tests |
| Vitest + Testing Library | Frontend unit and integration tests |
| ruff | Python linting and formatting |
| mypy | Python static type checking |

---

## 3. Canonical Metric Schema

All collector plugins normalize engine output into these Pydantic v2 models.
Schema version is tracked via the `SCHEMA_VERSION` constant (currently `"1.0"`).
Breaking changes increment the major version.

### 3.1 Core Models

```python
from __future__ import annotations
from datetime import datetime
from typing import Optional
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
    def rates_sum_to_one(self) -> "KVCacheMetrics":
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
    engine_version: Optional[str] = None
    deployment_id: str = Field(..., description="Unique identifier for this replica/deployment")
    model_name: str

    # Latency
    ttft_ms: Optional[HistogramBuckets] = None
    inter_token_latency_ms: Optional[HistogramBuckets] = None

    # Throughput
    decode_throughput_tps: float = Field(..., ge=0, description="Tokens per second, aggregate")
    request_throughput_rps: float = Field(..., ge=0, description="Requests per second")

    # Queue
    queue_depth: int = Field(..., ge=0)
    queue_wait_ms: Optional[HistogramBuckets] = None

    # GPU
    gpu_devices: list[GPUDeviceMetrics] = Field(default_factory=list)

    # KV cache (optional)
    kv_cache: Optional[KVCacheMetrics] = None

    # Batch
    batch: Optional[BatchMetrics] = None

    # Request metadata (aggregated counts in collection window)
    total_requests: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    avg_prompt_tokens: Optional[float] = None
    avg_output_tokens: Optional[float] = None
```

---

## 4. Plugin Interfaces

All plugin types are Python ABCs defined in `infersight.plugins.base`. Plugins are
discovered at startup by scanning directories listed in `config.plugin_dirs` for
subclasses of each ABC.

### 4.1 Domain Models (shared across plugins)

```python
from enum import Enum
from typing import Any
from pydantic import BaseModel
from datetime import datetime


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Issue(BaseModel):
    """Canonical output of an AnalyzerPlugin."""
    issue_id: str                          # stable identifier, e.g. "decode_bottleneck"
    issue_type: str                        # human label
    severity: Severity
    deployment_id: str
    detected_at: datetime
    cleared_at: datetime | None = None
    supporting_metrics: dict[str, Any]     # subset of CanonicalMetric fields as evidence
    description: str
    plugin_name: str


class Recommendation(BaseModel):
    """Canonical output of a RecommenderPlugin."""
    rec_id: str
    issue_id: str                          # links back to the triggering Issue
    deployment_id: str
    plugin_name: str
    target_parameter: str                  # e.g. "max_num_seqs"
    current_value: Any | None
    recommended_value: Any
    reasoning: str
    estimated_impact: str                  # e.g. "15–30% reduction in TTFT"
    engine_config_snippet: str | None      # native config diff/flag
    rank: int = 0                          # lower = higher priority
    status: str = "open"                   # open | acknowledged | applied | dismissed
    created_at: datetime
    applied_at: datetime | None = None
```

### 4.2 CollectorPlugin ABC

```python
from abc import ABC, abstractmethod
from infersight.schema import CanonicalMetric


class CollectorPlugin(ABC):
    """
    Implement this ABC to add support for a new inference engine.
    One instance is created per configured deployment endpoint.
    """

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return a lowercase slug, e.g. 'vllm', 'tgi'."""

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Returns True if the engine endpoint is reachable and healthy.
        Called before each collection cycle; failures are logged and retried.
        """

    @abstractmethod
    async def collect(self) -> CanonicalMetric:
        """
        Scrape the engine and return a normalized CanonicalMetric.
        Raise CollectionError on unrecoverable failure.
        """
```

### 4.3 AnalyzerPlugin ABC

```python
from abc import ABC, abstractmethod
from infersight.schema import CanonicalMetric
from infersight.plugins.base import Issue


class AnalyzerPlugin(ABC):

    @property
    @abstractmethod
    def analyzer_name(self) -> str:
        """Stable identifier, e.g. 'decode_bottleneck'."""

    @property
    @abstractmethod
    def required_metrics(self) -> list[str]:
        """
        List of CanonicalMetric field names this analyzer reads.
        Used to skip the analyzer when fields are unavailable.
        """

    @abstractmethod
    async def analyze(
        self,
        metrics: list[CanonicalMetric],  # recent window, oldest first
    ) -> list[Issue]:
        """
        Inspect the metric window and return zero or more Issue objects.
        Analyzers MUST be stateless; window management is done by the engine.
        """
```

### 4.4 RecommenderPlugin ABC

```python
from abc import ABC, abstractmethod
from infersight.plugins.base import Issue, Recommendation


class RecommenderPlugin(ABC):

    @property
    @abstractmethod
    def recommender_name(self) -> str:
        """Stable identifier, e.g. 'prefix_cache_recommender'."""

    @property
    @abstractmethod
    def handles_issue_types(self) -> list[str]:
        """Issue type slugs this recommender handles."""

    @abstractmethod
    async def recommend(self, issue: Issue) -> list[Recommendation]:
        """
        Generate ranked recommendations for a given Issue.
        Returns an empty list if no actionable recommendation exists.
        """
```

### 4.5 NotificationPlugin ABC

```python
from abc import ABC, abstractmethod
from infersight.plugins.base import Issue


class NotificationPlugin(ABC):

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """e.g. 'slack', 'pagerduty', 'email'"""

    @abstractmethod
    async def notify(self, issue: Issue) -> None:
        """
        Send an alert for the given issue.
        Implementations MUST be idempotent — called once per new/re-triggered issue.
        Failures MUST be logged but MUST NOT propagate exceptions to the caller.
        """
```

### 4.6 Plugin Discovery

At startup, `PluginRegistry` scans `config.plugin_dirs` using `importlib`:

```python
# infersight/plugins/registry.py (pseudocode)
for path in config.plugin_dirs:
    for module_file in path.glob("*.py"):
        module = importlib.import_module(module_file)
        for cls in all_subclasses(module, CollectorPlugin):
            registry.register_collector(cls)
        # repeat for Analyzer, Recommender, Notification
```

A plugin that raises during instantiation is isolated — other plugins continue loading.

---

## 5. REST API Reference

Base path: `/api/v1`. All endpoints return `application/json`.
Authentication: `Authorization: Bearer <api-key>` header (when auth is enabled).
Full OpenAPI 3.1 spec is auto-generated by FastAPI and served at `/openapi.json`.

### 5.1 Endpoint Table

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe — returns `{"status": "ok"}` |
| GET | `/ready` | Readiness probe — checks storage connectivity |
| GET | `/api/v1/deployments` | List all monitored deployments |
| GET | `/api/v1/deployments/{id}` | Single deployment detail |
| GET | `/api/v1/metrics` | Query metrics with filters |
| GET | `/api/v1/metrics/latest` | Most recent snapshot per deployment |
| GET | `/api/v1/issues` | List detected issues |
| GET | `/api/v1/issues/{issue_id}` | Single issue detail |
| GET | `/api/v1/recommendations` | List recommendations |
| PATCH | `/api/v1/recommendations/{rec_id}` | Update recommendation status |
| GET | `/api/v1/recommendations/{rec_id}/export` | Export as config snippet |
| POST | `/api/v1/copilot/chat` | Send a copilot message |
| GET | `/api/v1/copilot/history` | Retrieve chat history |
| POST | `/api/v1/advisor/analyze` | Submit manifest for infrastructure analysis |
| GET | `/api/v1/plugins` | List loaded plugins |

### 5.2 Request / Response Shapes

#### GET `/api/v1/metrics`

Query parameters:
- `deployment_id` (optional, repeatable)
- `engine` (optional)
- `model_name` (optional)
- `start` — ISO-8601 datetime (default: now − 1h)
- `end` — ISO-8601 datetime (default: now)
- `limit` — integer (default: 500, max: 5000)

Response:
```json
{
  "schema_version": "1.0",
  "count": 42,
  "items": [ /* array of CanonicalMetric */ ]
}
```

#### GET `/api/v1/issues`

Query parameters:
- `deployment_id` (optional, repeatable)
- `severity` — `info | warning | critical` (optional, repeatable)
- `issue_type` (optional)
- `active_only` — boolean (default: true)

Response:
```json
{
  "count": 3,
  "items": [
    {
      "issue_id": "decode_bottleneck",
      "issue_type": "Decode Bottleneck",
      "severity": "warning",
      "deployment_id": "vllm-prod-01",
      "detected_at": "2024-06-01T12:00:00Z",
      "cleared_at": null,
      "supporting_metrics": {
        "decode_throughput_tps": 120.5,
        "threshold_tps": 300.0,
        "gpu_compute_utilization_pct": 94.2
      },
      "description": "Decode throughput (120.5 t/s) is below threshold (300 t/s) with high GPU compute (94.2%).",
      "plugin_name": "decode_bottleneck_analyzer"
    }
  ]
}
```

#### GET `/api/v1/recommendations`

Query parameters:
- `deployment_id` (optional)
- `status` — `open | acknowledged | applied | dismissed` (optional)
- `issue_type` (optional)

Response:
```json
{
  "count": 1,
  "items": [
    {
      "rec_id": "rec-abc123",
      "issue_id": "decode_bottleneck",
      "deployment_id": "vllm-prod-01",
      "plugin_name": "batch_size_recommender",
      "target_parameter": "max_num_seqs",
      "current_value": 64,
      "recommended_value": 128,
      "reasoning": "Batch fill rate is 38%; doubling max_num_seqs allows more concurrent requests.",
      "estimated_impact": "20–40% throughput increase",
      "engine_config_snippet": "--max-num-seqs 128",
      "rank": 1,
      "status": "open",
      "created_at": "2024-06-01T12:01:00Z"
    }
  ]
}
```

#### PATCH `/api/v1/recommendations/{rec_id}`

Request body:
```json
{ "status": "applied" }
```

Response: updated `Recommendation` object.

#### POST `/api/v1/copilot/chat`

Request body:
```json
{
  "session_id": "sess-xyz",
  "message": "Why is my TTFT increasing on vllm-prod-01?"
}
```

Response:
```json
{
  "session_id": "sess-xyz",
  "reply": "Based on the last 30 minutes of data, TTFT p99 has risen from 340ms to 890ms...",
  "citations": [
    { "metric": "ttft_ms.p99", "value": 890.2, "timestamp": "2024-06-01T12:05:00Z" },
    { "issue": "queue_saturation", "detected_at": "2024-06-01T12:03:00Z" }
  ],
  "reply_type": "factual"
}
```

---

## 6. Storage Layer

### 6.1 StorageBackend ABC

```python
from abc import ABC, abstractmethod
from datetime import datetime
from infersight.schema import CanonicalMetric
from infersight.plugins.base import Issue, Recommendation


class StorageBackend(ABC):

    @abstractmethod
    async def write_metrics(self, metrics: list[CanonicalMetric]) -> None: ...

    @abstractmethod
    async def query_metrics(
        self,
        deployment_ids: list[str] | None,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[CanonicalMetric]: ...

    @abstractmethod
    async def write_issues(self, issues: list[Issue]) -> None: ...

    @abstractmethod
    async def query_issues(
        self,
        deployment_ids: list[str] | None,
        severity: list[str] | None,
        active_only: bool,
    ) -> list[Issue]: ...

    @abstractmethod
    async def write_recommendations(self, recs: list[Recommendation]) -> None: ...

    @abstractmethod
    async def update_recommendation(self, rec_id: str, status: str) -> Recommendation: ...

    @abstractmethod
    async def query_recommendations(
        self,
        deployment_ids: list[str] | None,
        status: list[str] | None,
    ) -> list[Recommendation]: ...
```

Concrete implementations: `SQLiteBackend`, `PrometheusBackend`, `InfluxBackend`.
`SQLiteBackend` is the default for single-node deployments.

### 6.2 SQLite DDL

```sql
-- Metrics are stored as JSON blobs for schema flexibility;
-- key scalar fields are indexed for fast range queries.

CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deployment_id TEXT NOT NULL,
    engine      TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    captured_at TEXT NOT NULL,  -- ISO-8601
    payload     TEXT NOT NULL   -- full CanonicalMetric as JSON
);

CREATE INDEX IF NOT EXISTS idx_metrics_deployment_time
    ON metrics (deployment_id, captured_at);

CREATE INDEX IF NOT EXISTS idx_metrics_engine_time
    ON metrics (engine, captured_at);

-- TTL enforcement: a daily job deletes rows older than retention_days
-- DELETE FROM metrics WHERE captured_at < datetime('now', '-30 days');

CREATE TABLE IF NOT EXISTS issues (
    issue_id      TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    detected_at   TEXT NOT NULL,
    cleared_at    TEXT,
    severity      TEXT NOT NULL,
    payload       TEXT NOT NULL,
    PRIMARY KEY (issue_id, deployment_id, detected_at)
);

CREATE TABLE IF NOT EXISTS recommendations (
    rec_id        TEXT PRIMARY KEY,
    issue_id      TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open',
    rank          INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    applied_at    TEXT,
    payload       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS copilot_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,  -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
```

---

## 7. UI Structure

### 7.1 Page Layout

```
/                   → redirect to /dashboard
/dashboard          → Fleet Overview (all deployments, health indicators)
/deployments/:id    → Deployment Detail (metric charts, issues, recommendations)
/compare            → Multi-deployment comparison side-by-side
/issues             → Issue list with filters
/recommendations    → Recommendation list; apply/dismiss actions
/copilot            → AI Copilot chat interface
/advisor            → Infrastructure Advisor manifest upload + results
/settings           → API keys, OIDC config, notification channels, thresholds
```

### 7.2 Component Tree

```
<App>
  <AuthGuard>                        ← checks api-key / OIDC token
    <Layout>
      <Sidebar />                    ← nav links, deployment quick-list
      <TopBar />                     ← global time-range picker, search
      <Outlet />                     ← React Router outlet

      /* /dashboard */
      <DashboardPage>
        <FleetHealthBanner />        ← aggregate green/yellow/red
        <DeploymentGrid>
          <DeploymentCard />         ← per-deployment summary tile
        </DeploymentGrid>
      </DashboardPage>

      /* /deployments/:id */
      <DeploymentDetailPage>
        <MetricPanel title="Latency">
          <LineChart />              ← Recharts, TanStack Query polling
        </MetricPanel>
        <MetricPanel title="Throughput">
          <LineChart />
        </MetricPanel>
        <MetricPanel title="GPU">
          <BarChart />               ← per-device utilization
        </MetricPanel>
        <MetricPanel title="KV Cache">
          <GaugeChart />
        </MetricPanel>
        <IssueList />
        <RecommendationList />
      </DeploymentDetailPage>

      /* /compare */
      <ComparePage>
        <DeploymentSelector />       ← Zustand: selectedDeployments[]
        <CompareGrid>
          <MetricColumn />           ← one column per selected deployment
        </CompareGrid>
      </ComparePage>

      /* /copilot */
      <CopilotPage>
        <ChatHistory />
        <CitationBadge />            ← inline metric citations
        <MessageInput />
      </CopilotPage>

      /* /advisor */
      <AdvisorPage>
        <ManifestDropzone />
        <FindingsList>
          <FindingRow />             ← severity badge, file:line, description, fix
        </FindingsList>
      </AdvisorPage>
    </Layout>
  </AuthGuard>
</App>
```

### 7.3 State Management Strategy

- **Server state** (metrics, issues, recommendations): TanStack Query with 15s polling interval matching the collection interval.
- **UI state** (selected deployments, time range, filter values): Zustand store, persisted to `localStorage` for page-reload resilience.
- **WebSocket** connection for real-time issue/alert push: managed in a single global context provider.

---

## 8. Deployment

### 8.1 Python Module Layout

```
infersight/
├── __main__.py              ← entry point: uvicorn app startup
├── app.py                   ← FastAPI application factory
├── config.py                ← Pydantic Settings v2 config model
├── schema.py                ← CanonicalMetric and related models
├── scheduler.py             ← APScheduler setup, collection jobs
├── plugins/
│   ├── base.py              ← ABCs: CollectorPlugin, AnalyzerPlugin, etc.
│   ├── registry.py          ← PluginRegistry, discovery logic
│   ├── collectors/
│   │   ├── vllm.py
│   │   ├── sglang.py
│   │   ├── tgi.py
│   │   ├── triton.py
│   │   ├── kserve.py
│   │   └── ray_serve.py
│   ├── analyzers/
│   │   ├── decode_bottleneck.py
│   │   ├── batch_efficiency.py
│   │   ├── gpu_utilization.py
│   │   ├── memory_fragmentation.py
│   │   ├── queue_saturation.py
│   │   ├── kv_cache_effectiveness.py
│   │   └── scheduling.py
│   ├── recommenders/
│   │   ├── prefix_cache.py
│   │   ├── batch_size.py
│   │   ├── scheduler_config.py
│   │   ├── tensor_parallelism.py
│   │   └── scaling.py
│   └── notifications/
│       ├── slack.py
│       ├── pagerduty.py
│       └── email.py
├── storage/
│   ├── base.py              ← StorageBackend ABC
│   ├── sqlite.py
│   ├── prometheus.py
│   └── influx.py
├── api/
│   ├── routes/
│   │   ├── metrics.py
│   │   ├── issues.py
│   │   ├── recommendations.py
│   │   ├── copilot.py
│   │   └── advisor.py
│   └── middleware.py        ← auth, request logging
├── copilot/
│   ├── agent.py             ← tool-calling loop
│   ├── tools.py             ← 6 tool definitions
│   └── prompts.py           ← system prompt template
└── advisor/
    ├── k8s.py
    ├── helm.py
    ├── terraform.py
    └── ray.py
```

### 8.2 Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /build/dist/*.whl .
RUN pip install --no-cache-dir *.whl && rm -f *.whl

# Frontend static files (pre-built in CI)
COPY ui/dist /app/static

ENV INFERSIGHT_CONFIG=/config/infersight.yaml
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["python", "-m", "infersight"]
```

Build args:
- `INFERSIGHT_VERSION` — injected by CI, written to `schema.py` as `__version__`

### 8.3 Helm Chart Structure

```
helm/infersight/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml      ← InferSight server pod
│   ├── service.yaml         ← ClusterIP + optional LoadBalancer
│   ├── ingress.yaml
│   ├── configmap.yaml       ← infersight.yaml mounted as volume
│   ├── secret.yaml          ← API keys and credentials
│   ├── serviceaccount.yaml
│   ├── pvc.yaml             ← persistent volume for SQLite data
│   └── hpa.yaml             ← optional horizontal pod autoscaler
└── charts/                  ← optional sub-charts (prometheus-stack)
```

Key `values.yaml` fields:

```yaml
replicaCount: 1

image:
  repository: ghcr.io/piyushdaftary/infersight
  tag: "latest"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: false
  className: nginx
  host: infersight.example.com
  tls: []

persistence:
  enabled: true
  storageClass: ""
  size: 10Gi
  mountPath: /data

config:
  # Inline infersight.yaml — see Section 11
  collectionInterval: 15
  retentionDays: 30

secrets:
  # Kubernetes Secret keys injected as env vars
  apiKey: ""
  llmApiKey: ""

resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: "2"
    memory: 2Gi

podAnnotations: {}
nodeSelector: {}
tolerations: []
affinity: {}
```

---

## 9. Security

### 9.1 API Key Authentication

When `auth.api_key_enabled: true` in config, all `/api/v1/*` and WebSocket endpoints
require the header `Authorization: Bearer <key>`. The key is compared using a
constant-time comparison (`hmac.compare_digest`) to prevent timing attacks.
Multiple keys can be configured (e.g., one per team) as a list.

The `/health` and `/ready` endpoints are always unauthenticated.

### 9.2 OIDC Authentication

When `auth.oidc_enabled: true`, the web UI redirects unauthenticated browser sessions
to the OIDC provider's authorization endpoint. The callback handler exchanges the code
for tokens, validates the `id_token` signature and `aud` claim, then issues a
short-lived session cookie (httpOnly, Secure, SameSite=Strict).

Required config fields:
- `auth.oidc.issuer_url` — e.g. `https://accounts.google.com`
- `auth.oidc.client_id`
- `auth.oidc.client_secret` — injected via environment variable, never in YAML

API requests from CI/CD pipelines continue to use API key auth even when OIDC is enabled.

### 9.3 TLS

All outbound HTTP connections (engine scraping, LLM API calls, notification webhooks)
use `httpx.AsyncClient` with `verify=True` by default.

Custom CA bundles are supported via `http.ca_bundle_path` in config.
TLS verification can be disabled per-deployment with `tls_verify: false` for self-signed
certs in dev/test environments — this setting is logged as a WARNING on startup.

Inbound TLS termination is handled by the ingress controller (Kubernetes) or a reverse
proxy (single-node). InferSight itself does not terminate TLS.

### 9.4 Secret Handling

Sensitive values are never written to log output. `structlog` processors include a
`ScrubSensitiveProcessor` that redacts fields matching a configurable deny-list
(default: `api_key`, `password`, `token`, `secret`, `credential`).

Secrets are loaded from environment variables or a secrets file path, not from the
main `infersight.yaml`. In Kubernetes the Helm chart creates a `Secret` object and
injects values as env vars:

```yaml
env:
  - name: INFERSIGHT_AUTH_API_KEY
    valueFrom:
      secretKeyRef:
        name: infersight-secrets
        key: api-key
```

---

## 10. AI Copilot

### 10.1 Architecture Overview

The copilot is a tool-calling LLM agent. It does not have direct database access;
instead it calls well-typed tools that proxy into the Storage Layer. This keeps the
LLM grounded in real data and makes audit logging straightforward.

```
User Message
    │
    ▼
CopilotAgent.chat()
    │
    ├── Build messages: [system_prompt] + history + user_message
    │
    ├── LiteLLM.completion(model, messages, tools=[...])
    │       ↓
    │   LLM decides to call tool(s)
    │       ↓
    ├── dispatch_tool_call(tool_name, args)
    │       ↓
    │   Tool queries StorageBackend → returns typed result
    │       ↓
    ├── Append tool result to messages
    │       ↓
    └── LiteLLM.completion() again → final text response
            │
            ▼
    Extract citations from tool results
            │
            ▼
    Return CopilotResponse(reply, citations, reply_type)
```

### 10.2 Tool Definitions

Six tools are registered. All return JSON-serializable dicts; the LLM never receives
raw Pydantic objects.

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_latest_metrics",
            "description": (
                "Returns the most recent metric snapshot for one or more deployments. "
                "Use this to answer questions about current latency, throughput, GPU "
                "utilization, KV cache, queue depth, and batch efficiency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deployment_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of deployment IDs. Pass empty list for all."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_metric_history",
            "description": (
                "Returns a time-series of metric snapshots for a deployment over a given "
                "time range. Use this to identify trends, correlate events, or answer "
                "questions about historical behavior."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deployment_id": {"type": "string"},
                    "metric_field":  {
                        "type": "string",
                        "description": "Dot-path into CanonicalMetric, e.g. 'ttft_ms.p99'"
                    },
                    "start_iso":     {"type": "string", "description": "ISO-8601 datetime"},
                    "end_iso":       {"type": "string", "description": "ISO-8601 datetime"}
                },
                "required": ["deployment_id", "metric_field"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_issues",
            "description": (
                "Returns currently active detected issues. Use this to answer questions "
                "about what is wrong, why a metric is behaving unexpectedly, or to "
                "identify root causes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deployment_id": {"type": "string", "description": "Optional filter"},
                    "severity":      {
                        "type": "array",
                        "items": {"type": "string", "enum": ["info", "warning", "critical"]}
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": (
                "Returns open optimization recommendations ranked by estimated impact. "
                "Use this to answer questions about what to do, what the highest-value "
                "optimization is, or how to reduce cost or latency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deployment_id": {"type": "string"},
                    "status":        {
                        "type": "string",
                        "enum": ["open", "acknowledged", "applied", "dismissed"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_deployments",
            "description": (
                "Compares a specific metric across multiple deployments and returns a "
                "ranked table. Use for questions like 'which deployment has the best "
                "throughput?' or 'which model has the lowest TTFT?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deployment_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "metric_field":   {"type": "string"}
                },
                "required": ["metric_field"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_deployment_config",
            "description": (
                "Returns the last-known configuration metadata for a deployment "
                "(batch size settings, parallelism, cache settings collected from "
                "the engine's /info or /config endpoint)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "deployment_id": {"type": "string"}
                },
                "required": ["deployment_id"]
            }
        }
    }
]
```

### 10.3 System Prompt Template

```python
SYSTEM_PROMPT = """\
You are the InferSight AI Copilot — an expert assistant for AI inference infrastructure
observability, optimization, and troubleshooting.

## Your Role
- Answer questions about inference deployments monitored by InferSight.
- Ground every factual claim in data retrieved via the available tools.
- Distinguish clearly between FACTUAL answers (backed by collected data) and
  GUIDANCE (general knowledge about inference optimization).

## Rules
1. NEVER fabricate metric values, issue descriptions, or recommendation details.
2. If data is unavailable, say so explicitly — do not estimate.
3. Do NOT suggest executing infrastructure changes directly; provide instructions only.
4. Always cite the tool results that support your answer. Use the format:
   [metric: ttft_ms.p99 = 890ms @ 2024-06-01T12:05Z] or [issue: queue_saturation].
5. If a question is outside the scope of InferSight data, say so and offer general
   guidance labeled as "(general guidance, not based on your specific deployment data)".
6. Keep responses concise. Use bullet points for lists of findings or recommendations.

## Available Deployments
{deployment_list}

## Current Time
{current_time_iso}
"""
```

### 10.4 Citation Extraction

After the LLM returns its final text response, the agent post-processes it to extract
structured citations:

```python
import re

CITATION_PATTERN = re.compile(
    r'\[(?:metric|issue|recommendation): ([^\]]+)\]'
)

def extract_citations(reply: str, tool_results: list[dict]) -> list[dict]:
    """
    Parse inline citation markers from the reply and resolve them against
    the tool_results accumulated during the tool-calling loop.
    Returns a list of structured citation dicts for the API response.
    """
    citations = []
    for match in CITATION_PATTERN.finditer(reply):
        ref = match.group(1)
        # resolve ref against tool_results (fuzzy match on metric names,
        # issue_ids, rec_ids)
        resolved = _resolve_citation(ref, tool_results)
        if resolved:
            citations.append(resolved)
    return citations
```

---

## 11. Configuration Reference

Full `infersight.yaml` with all supported fields and defaults:

```yaml
# infersight.yaml — Full configuration reference
# Environment variable overrides use the prefix INFERSIGHT_
# e.g. INFERSIGHT_SERVER__PORT=9000

server:
  host: "0.0.0.0"
  port: 8000
  log_level: "info"          # debug | info | warning | error
  log_format: "json"         # json | console
  static_dir: "./static"     # path to pre-built React SPA

collection:
  interval_seconds: 15       # how often to scrape each engine
  timeout_seconds: 10        # per-request scrape timeout
  retry_max_attempts: 3
  retry_backoff_seconds: 5

storage:
  backend: "sqlite"          # sqlite | prometheus | influx
  sqlite:
    path: "./data/infersight.db"
    retention_days: 30
    vacuum_interval_hours: 24
  prometheus:
    remote_write_url: ""
    remote_read_url: ""
  influx:
    url: ""
    token: ""                # use env var: INFERSIGHT_STORAGE__INFLUX__TOKEN
    org: ""
    bucket: "infersight"

auth:
  api_key_enabled: false
  # api_keys:                # injected via env var as comma-separated list
  #   - "key1"
  oidc_enabled: false
  oidc:
    issuer_url: ""
    client_id: ""
    # client_secret via env var: INFERSIGHT_AUTH__OIDC__CLIENT_SECRET
    redirect_uri: "http://localhost:8000/auth/callback"
    scopes: ["openid", "email", "profile"]

http:
  tls_verify: true
  ca_bundle_path: ""
  proxy: ""

deployments:
  - id: "vllm-prod-01"
    engine: "vllm"
    name: "Production vLLM (Llama-3-70B)"
    endpoint: "http://vllm-prod-01:8000"
    tls_verify: true
    labels:
      team: "ml-platform"
      env: "production"
    engine_config:
      max_num_seqs: 64         # used by analyzers as baseline

  # Additional deployments follow the same structure

plugin_dirs:
  - "./plugins"

analyzers:
  decode_bottleneck:
    enabled: true
    throughput_threshold_tps: 300
    gpu_utilization_threshold_pct: 85
    window_seconds: 120
  batch_efficiency:
    enabled: true
    fill_rate_threshold: 0.60
    window_seconds: 300
  gpu_underutilization:
    enabled: true
    utilization_threshold_pct: 40
    window_seconds: 600
  memory_fragmentation:
    enabled: true
  queue_saturation:
    enabled: true
    depth_multiplier: 2        # threshold = max_batch_size * multiplier
    window_seconds: 120
  kv_cache_effectiveness:
    enabled: true
    hit_rate_threshold: 0.30
  scheduling_inefficiency:
    enabled: true

alerting:
  deduplication_window_seconds: 300
  channels:
    slack:
      enabled: false
      webhook_url: ""          # env: INFERSIGHT_ALERTING__CHANNELS__SLACK__WEBHOOK_URL
      severity_threshold: "warning"
    pagerduty:
      enabled: false
      routing_key: ""          # env: INFERSIGHT_ALERTING__CHANNELS__PAGERDUTY__ROUTING_KEY
      severity_threshold: "critical"
    email:
      enabled: false
      smtp_host: ""
      smtp_port: 587
      smtp_user: ""
      smtp_password: ""        # env: INFERSIGHT_ALERTING__CHANNELS__EMAIL__SMTP_PASSWORD
      from_address: "infersight@example.com"
      to_addresses: []
      severity_threshold: "warning"

copilot:
  enabled: false
  provider: "openai"           # openai | anthropic | azure_openai | custom
  model: "gpt-4o"
  api_key: ""                  # env: INFERSIGHT_COPILOT__API_KEY
  base_url: ""                 # for OpenAI-compatible endpoints
  azure_deployment: ""         # Azure OpenAI deployment name
  max_context_messages: 20
  max_tokens: 2048
  temperature: 0.2

grafana:
  dashboards_export_path: "./dashboards"

prometheus:
  exposition_enabled: true
  exposition_path: "/metrics"  # Prometheus scrape path
```

---

## 12. Requirements Traceability

| Requirement | Design Section | Notes |
|-------------|---------------|-------|
| REQ-1.1.1 — Collect from vLLM, SGLang, TGI, Triton, KServe, HyperPod, Ray Serve | §8.1 `plugins/collectors/` | One module per engine |
| REQ-1.1.2 — CollectorPlugin interface | §4.2 CollectorPlugin ABC | Documented ABC with health_check + collect |
| REQ-1.1.3 — Configurable collection interval | §11 `collection.interval_seconds` | Default 15s |
| REQ-1.1.4 — Graceful failure with backoff | §8.1 scheduler.py; §11 `collection.retry_*` | APScheduler job isolation |
| REQ-1.1.5 — Pull and push collection | §1.2 Collector Scheduler | HTTP scrape = pull; webhook endpoint = push |
| REQ-1.2.1 — TTFT histogram (p50/p90/p95/p99) | §3.1 `HistogramBuckets`, `CanonicalMetric.ttft_ms` | Configurable bucket list |
| REQ-1.2.2 — Decode throughput | §3.1 `CanonicalMetric.decode_throughput_tps` | Per-request and aggregate |
| REQ-1.2.3 — Queue depth and wait time | §3.1 `CanonicalMetric.queue_depth`, `.queue_wait_ms` | — |
| REQ-1.2.4 — GPU compute utilization per device | §3.1 `GPUDeviceMetrics.compute_utilization_pct` | Per-device list |
| REQ-1.2.5 — GPU memory utilization per device | §3.1 `GPUDeviceMetrics.memory_used_bytes` | `memory_utilization_pct` property |
| REQ-1.2.6 — KV cache metrics | §3.1 `KVCacheMetrics` | Optional; None when engine doesn't expose |
| REQ-1.2.7 — Batch efficiency metrics | §3.1 `BatchMetrics` | fill_rate, prefill_decode_ratio |
| REQ-1.2.8 — Request metadata | §3.1 `CanonicalMetric.total_requests`, `.error_count`, etc. | Aggregated per window |
| REQ-1.3.1–1.3.5 — Canonical schema + versioning | §3 Canonical Metric Schema | `SCHEMA_VERSION` constant; Pydantic v2 |
| REQ-1.4.1 — Configurable storage backend | §6 Storage Layer | `StorageBackend` ABC; SQLite, Prometheus, InfluxDB |
| REQ-1.4.2 — Configurable retention | §11 `storage.sqlite.retention_days` | Daily TTL job |
| REQ-1.4.3 — Prometheus exposition format | §11 `prometheus.exposition_enabled` | `/metrics` endpoint |
| REQ-1.4.4 — Grafana dashboards | §11 `grafana.dashboards_export_path` | Pre-built JSON definitions |
| REQ-1.5.1–1.5.5 — Web dashboard | §7 UI Structure | React SPA; auth optional |
| REQ-2.1 — Decode bottleneck detection | §8.1 `analyzers/decode_bottleneck.py`; §11 analyzers config | Threshold + window configurable |
| REQ-2.2 — Inefficient batching detection | §8.1 `analyzers/batch_efficiency.py` | fill_rate_threshold default 0.60 |
| REQ-2.3 — GPU underutilization detection | §8.1 `analyzers/gpu_utilization.py` | utilization_threshold_pct default 40 |
| REQ-2.4 — Memory fragmentation detection | §8.1 `analyzers/memory_fragmentation.py` | KV cache vs. memory cross-correlation |
| REQ-2.5 — Queue saturation detection | §8.1 `analyzers/queue_saturation.py` | depth_multiplier configurable |
| REQ-2.6 — Low KV cache effectiveness | §8.1 `analyzers/kv_cache_effectiveness.py` | hit_rate_threshold default 0.30 |
| REQ-2.7 — Scheduling inefficiency | §8.1 `analyzers/scheduling.py` | Engine-specific baselines |
| REQ-2.8 — Analysis REST API | §5.1 `/api/v1/issues` | Filtering by deployment, severity, type |
| REQ-3.1.1–3.1.5 — Recommendation generation | §4.4 RecommenderPlugin ABC; §8.1 `plugins/recommenders/` | Ranked by `rank` field |
| REQ-3.2.1–3.2.7 — Specific recommendation types | §8.1 `plugins/recommenders/` | One module per recommendation type |
| REQ-3.3 — Recommendation history and feedback | §6.2 SQLite DDL `recommendations` table; §5.2 PATCH endpoint | Post-apply monitoring window |
| REQ-3.4 — Recommendation export | §5.2 GET `/recommendations/{id}/export` | `engine_config_snippet` field |
| REQ-4.1 — Kubernetes manifest analysis | §8.1 `advisor/k8s.py`, `advisor/helm.py` | CLI `infersight advisor analyze` |
| REQ-4.2 — Terraform + SageMaker analysis | §8.1 `advisor/terraform.py` | HCL parsing |
| REQ-4.3 — Ray cluster analysis | §8.1 `advisor/ray.py` | — |
| REQ-4.4 — Advisor output + CI integration | §5.1 POST `/advisor/analyze`; §11 | JSON + markdown output; `--threshold` flag |
| REQ-5.1 — Conversational interface | §7.1 `/copilot` page; §10 AI Copilot | Web UI + CLI |
| REQ-5.2 — Supported query types | §10.2 Tool Definitions | 6 tools cover all query categories |
| REQ-5.3 — LLM backend configuration | §11 `copilot.*`; §10.1 LiteLLM | Multi-provider via LiteLLM |
| REQ-5.4 — Copilot safety | §10.3 System Prompt; §10.4 Citations | No fabrication; audit log via copilot_history |
| REQ-6.1 — CollectorPlugin | §4.2 CollectorPlugin ABC | Plugin discovery via PluginRegistry |
| REQ-6.2 — AnalyzerPlugin | §4.3 AnalyzerPlugin ABC | Custom analyzers appear alongside built-in |
| REQ-6.3 — RecommenderPlugin | §4.4 RecommenderPlugin ABC | `plugin_name` field on Recommendation |
| REQ-6.4 — NotificationPlugin | §4.5 NotificationPlugin ABC; §11 `alerting.*` | Slack, PagerDuty, Email built-in |
| REQ-7.1.1 — Single binary / Docker | §8.2 Dockerfile | Single-container image |
| REQ-7.1.2 — Helm chart | §8.3 Helm Chart | `helm/infersight/` |
| REQ-7.1.3 — YAML config + env overrides | §11 Configuration Reference | `INFERSIGHT_` prefix for all env overrides |
| REQ-7.1.4 — `/health` and `/ready` endpoints | §5.1 Endpoint Table | Always unauthenticated |
| REQ-7.1.5 — Structured JSON logs | §2.1 structlog | `log_format: json` default |
| REQ-7.2.1 — API key auth | §9.1 API Key Authentication | `auth.api_key_enabled` |
| REQ-7.2.2 — OIDC auth | §9.2 OIDC Authentication | `auth.oidc_enabled` |
| REQ-7.2.3 — TLS for outbound connections | §9.3 TLS | `httpx` with `verify=True` default |
| REQ-7.2.4 — Secrets not in logs | §9.4 Secret Handling | `ScrubSensitiveProcessor` in structlog pipeline |
| REQ-7.3.1–7.3.4 — Performance and reliability | §1.3 Data Flow; §6.1 StorageBackend | Collection job isolation; async httpx; <100ms overhead target |
| REQ-7.4.1–7.4.4 — Documentation | Out of scope for design doc | Quickstart, API ref, plugin guide, engine guides |
