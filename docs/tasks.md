# InferSight — Implementation Task List

> Phases are ordered for incremental delivery. Complete each phase before starting the next.
> Complexity: **S** = Small (< 1 day) · **M** = Medium (1–3 days) · **L** = Large (3–5 days)

---

## Phase 0 — Project Scaffolding

### Task 0.1 — Repository Structure
- Create top-level directories: `infersight/`, `ui/`, `helm/`, `docs/`, `tests/`, `.github/workflows/`
- Add `README.md`, `LICENSE`, `.gitignore`, and `.editorconfig`
- Verify `git init` + initial commit succeeds with no untracked noise
- **Complexity:** S

### Task 0.2 — Python Project Config (`pyproject.toml`)
- Define project metadata, `[build-system]` (hatchling or setuptools), and `[project.scripts]` entry point for `infersight`
- Pin all runtime dependencies to exact versions matching the design tech stack (FastAPI 0.111.x, Pydantic 2.7.x, APScheduler 3.10.x, LiteLLM 1.40.x, httpx 0.27.x, structlog 24.x, Typer 0.12.x, uvicorn 0.29.x)
- Include `[project.optional-dependencies]` groups for `dev`, `test`, and `docs`
- **Complexity:** S

### Task 0.3 — Ruff + Mypy Configuration
- Add `[tool.ruff]` section to `pyproject.toml` with `select = ["E","F","I","UP"]` and `line-length = 100`
- Add `[tool.mypy]` with `strict = true`, `python_version = "3.11"`, and per-module overrides for third-party stubs
- Confirm `ruff check .` and `mypy infersight/` both exit 0 on an empty package
- **Complexity:** S

### Task 0.4 — Pre-commit Hooks
- Add `.pre-commit-config.yaml` with hooks: `ruff`, `ruff-format`, `mypy`, `check-yaml`, `end-of-file-fixer`, `trailing-whitespace`
- Verify `pre-commit run --all-files` passes on the scaffolded repo
- Document hook setup in `CONTRIBUTING.md`
- **Complexity:** S

### Task 0.5 — GitHub Actions CI Skeleton
- Create `.github/workflows/ci.yml` with jobs: `lint` (ruff + mypy), `test` (pytest), `build` (Docker build --no-push)
- Each job runs on `ubuntu-latest` with Python 3.11 and caches pip/npm as appropriate
- CI must pass on the main branch before any feature branch is merged
- **Complexity:** S

### Task 0.6 — Dockerfile Skeleton
- Implement the multi-stage Dockerfile from design §8.2: `builder` stage (pip wheel build) + `runtime` stage
- Expose port 8000; add `HEALTHCHECK` using the `/health` endpoint
- Verify `docker build -t infersight:dev .` completes without errors on an empty `infersight/` package
- **Complexity:** S

### Task 0.7 — Vite/React Project Init
- Run `npm create vite@latest ui -- --template react-ts` and commit the output
- Install and configure Tailwind CSS 3.x, shadcn/ui, TanStack Query 5.x, React Router 6.x, Recharts 2.x, Zustand 4.x
- Verify `npm run build` produces a `dist/` folder with no TypeScript errors
- **Complexity:** S


---

# Phase 1 — Core Infrastructure (In Progress)

### Task 1.1 — Config Model (`infersight/config.py`) ✅ COMPLETE
- Implement `InferSightConfig` using Pydantic Settings v2 with `INFERSIGHT_` env-variable prefix and YAML file loading
- Cover all top-level sections from design §11: `server`, `collection`, `storage`, `auth`, `http`, `deployments`, `plugin_dirs`, `analyzers`, `alerting`, `copilot`, `grafana`, `prometheus`
- Sensitive fields (`api_key`, `smtp_password`, `routing_key`) must not appear in `model_dump()` output by default (use `exclude` or `SecretStr`)
- **Complexity:** M
- _Requirements: REQ-7.1.3, REQ-7.2.4_
- **Status:** Complete. Full YAML + env var loading with 5 passing unit tests.

### Task 1.2 — StorageBackend ABC (`infersight/storage/base.py`) ✅ COMPLETE
- Define the abstract `StorageBackend` class with all seven abstract methods from design §6.1: `write_metrics`, `query_metrics`, `write_issues`, `query_issues`, `write_recommendations`, `update_recommendation`, `query_recommendations`
- All methods must be `async`; type signatures must use the canonical models
- Add a `write_copilot_message` / `query_copilot_history` pair to support the `copilot_history` table
- **Complexity:** S
- _Requirements: REQ-1.4.1, REQ-3.3.1_
- **Status:** Complete. StorageBackend ABC with all methods defined.

### Task 1.3 — SQLite Storage Backend (`infersight/storage/sqlite.py`) ✅ COMPLETE
- Implement `SQLiteBackend(StorageBackend)` using Python's stdlib `sqlite3` (via `aiosqlite` for async)
- Create all four tables from design §6.2 DDL on first connection: `metrics`, `issues`, `recommendations`, `copilot_history`; create all specified indexes
- Implement a daily TTL cleanup job that deletes metrics rows older than `retention_days`
- **Complexity:** M
- _Requirements: REQ-1.4.1, REQ-1.4.2, REQ-3.3.1_
- **Status:** Complete. Full SQLite backend with async context manager, all CRUD operations, TTL cleanup.

### Task 1.4 — Plugin Registry (`infersight/plugins/registry.py`) ⏳ PENDING
- Implement `PluginRegistry` that scans directories listed in `config.plugin_dirs` using `importlib` and auto-discovers subclasses of `CollectorPlugin`, `AnalyzerPlugin`, `RecommenderPlugin`, and `NotificationPlugin`
- A plugin that raises during `__init__` must be isolated — log the error, skip the plugin, continue loading others
- Expose `registry.collectors`, `registry.analyzers`, `registry.recommenders`, `registry.notifiers` typed lists
- **Complexity:** M
- _Requirements: REQ-6.1.2, REQ-6.1.3_

### Task 1.5 — Canonical Metric Schema (`infersight/schema.py`)
- Implement all Pydantic v2 models from design §3.1: `HistogramBuckets`, `GPUDeviceMetrics`, `KVCacheMetrics`, `BatchMetrics`, `CanonicalMetric`
- Include the `rates_sum_to_one` model validator on `KVCacheMetrics` and the `memory_utilization_pct` computed property on `GPUDeviceMetrics`
- Export `SCHEMA_VERSION = "1.0"` constant; write unit tests asserting all validators fire correctly
- **Complexity:** M
- _Requirements: REQ-1.3.1–1.3.5_

### Task 1.6 — Domain Models (`infersight/plugins/base.py`)
- Implement `Severity` enum, `Issue` model, and `Recommendation` model as specified in design §4.1
- Implement all four plugin ABCs: `CollectorPlugin` (§4.2), `AnalyzerPlugin` (§4.3), `RecommenderPlugin` (§4.4), `NotificationPlugin` (§4.5)
- All ABCs must use `abc.ABC` + `@abstractmethod`; add docstrings matching the design
- **Complexity:** S
- _Requirements: REQ-6.1.1, REQ-6.2.1, REQ-6.3.1, REQ-6.4.5_

### Task 1.7 — FastAPI App Factory + Health Endpoints (`infersight/app.py`)
- Implement `create_app()` factory that wires up the FastAPI instance, mounts routers, and applies auth middleware (disabled by default)
- Implement `GET /health` returning `{"status": "ok"}` (always unauthenticated, REQ-7.1.4)
- Implement `GET /ready` that checks `StorageBackend` connectivity and returns `{"status": "ready"}` or 503
- **Complexity:** S
- _Requirements: REQ-7.1.4_

### Task 1.8 — APScheduler Setup (`infersight/scheduler.py`)
- Configure `AsyncIOScheduler` with an `IntervalTrigger` using `config.collection.interval_seconds`
- For each configured deployment, create an isolated job that calls `CollectorPlugin.collect()` → writes to storage → triggers analyzer engine
- Implement exponential backoff on `CollectionError` using `config.collection.retry_max_attempts` and `retry_backoff_seconds`
- **Complexity:** M
- _Requirements: REQ-1.1.3, REQ-1.1.4_


---

## Phase 2 — Collector Plugins

> Each collector lives in `infersight/plugins/collectors/`. All must subclass `CollectorPlugin`, implement `engine_name`, `health_check`, and `collect`, and return a fully populated `CanonicalMetric`.

### Task 2.1 — vLLM Collector (`collectors/vllm.py`)
- Scrape the vLLM Prometheus `/metrics` endpoint via `httpx.AsyncClient` and map metrics to `CanonicalMetric` fields
- Populate `ttft_ms`, `decode_throughput_tps`, `queue_depth`, `gpu_devices`, `kv_cache`, and `batch` from standard vLLM metric names
- Return `engine_name = "vllm"`; handle missing optional metrics gracefully (set to `None`)
- **Complexity:** M
- _Requirements: REQ-1.1.1, REQ-1.2.1–1.2.8_

### Task 2.2 — SGLang Collector (`collectors/sglang.py`)
- Scrape SGLang's Prometheus-compatible metrics endpoint and map to `CanonicalMetric`
- Handle SGLang-specific metric name differences from vLLM (document mapping in module docstring)
- Return `engine_name = "sglang"`; add integration test with a mock HTTP server
- **Complexity:** M
- _Requirements: REQ-1.1.1_

### Task 2.3 — TGI Collector (`collectors/tgi.py`)
- Scrape HuggingFace Text Generation Inference metrics endpoint and map to `CanonicalMetric`
- Map TGI-specific fields: `tgi_request_mean_time_per_token_duration`, `tgi_batch_current_size`, etc.
- Return `engine_name = "tgi"`; gracefully handle TGI versions that omit KV cache metrics
- **Complexity:** M
- _Requirements: REQ-1.1.1_

### Task 2.4 — NVIDIA Triton Collector (`collectors/triton.py`) ✅ COMPLETE
- Query Triton's HTTP statistics endpoint (`/v2/models/stats`) and Prometheus metrics to populate `CanonicalMetric`
- Map per-model throughput, queue depth, and GPU metrics from Triton's response format
- Return `engine_name = "triton"`; handle multi-model Triton instances by aggregating or per-model `deployment_id`
- **Complexity:** M
- _Requirements: REQ-1.1.1_
- **Status:** Complete. Aggregates Triton model statistics, queue depth, and exposed GPU gauges.

### Task 2.5 — KServe Collector (`collectors/kserve.py`) ✅ COMPLETE
- Query KServe's model metadata and Prometheus sidecar metrics to build `CanonicalMetric`
- Map KServe InferenceService-level metrics: request latency, throughput, and queue depth
- Return `engine_name = "kserve"`; support both v1 and v2 inference protocol endpoints
- **Complexity:** M
- _Requirements: REQ-1.1.1_
- **Status:** Complete. Supports KServe V1/V2 metadata APIs and normalizes sidecar metrics.

### Task 2.6 — Amazon SageMaker HyperPod Collector (`collectors/hyperpod.py`)
- Collect metrics from SageMaker HyperPod via CloudWatch API or the HyperPod monitoring endpoint using `boto3`/`httpx`
- Map SageMaker endpoint invocation metrics (latency, error rate, throughput) to `CanonicalMetric`
- Return `engine_name = "hyperpod"`; document required IAM permissions in module docstring
- **Complexity:** L
- _Requirements: REQ-1.1.1_

### Task 2.7 — Ray Serve Collector (`collectors/ray_serve.py`)
- Query Ray Serve's Prometheus metrics endpoint and `/api/serve/applications` for deployment-level stats
- Map Ray Serve replica metrics: request latency, queue depth, and replica utilization to `CanonicalMetric`
- Return `engine_name = "ray_serve"`; handle multi-deployment Ray Serve applications
- **Complexity:** M
- _Requirements: REQ-1.1.1_


---

## Phase 3 — Analyzer Plugins

> Each analyzer lives in `infersight/plugins/analyzers/`. All must subclass `AnalyzerPlugin`, implement `analyzer_name`, `required_metrics`, and `analyze(metrics: list[CanonicalMetric]) -> list[Issue]`. Analyzers must be stateless.

### Task 3.1 — Decode Bottleneck Analyzer (`analyzers/decode_bottleneck.py`)
- Flag an issue when `decode_throughput_tps` is consistently below `config.analyzers.decode_bottleneck.throughput_threshold_tps` AND average `gpu_devices[*].compute_utilization_pct` exceeds the GPU threshold over the configured `window_seconds`
- Include `decode_throughput_tps`, threshold, and GPU utilization in `supporting_metrics`
- Suppress re-alerting for an ongoing condition; re-alert only after it clears and recurs (design §2.1.3)
- **Complexity:** M
- _Requirements: REQ-2.1_

### Task 3.2 — Batch Efficiency Analyzer (`analyzers/batch_efficiency.py`)
- Flag an issue when `batch.fill_rate` averages below `config.analyzers.batch_efficiency.fill_rate_threshold` (default 0.60) over the sustained window (default 5 minutes)
- Include observed fill rate, `batch.avg_batch_size`, and `batch.max_batch_size` distribution in `supporting_metrics`
- Distinguish genuine low-traffic (low `request_throughput_rps`) from misconfiguration and set severity accordingly
- **Complexity:** M
- _Requirements: REQ-2.2_

### Task 3.3 — GPU Underutilization Analyzer (`analyzers/gpu_utilization.py`)
- Flag an issue when average `compute_utilization_pct` across all `gpu_devices` stays below threshold (default 40%) for the sustained window (default 10 minutes)
- Include per-GPU breakdowns and the aggregated average in `supporting_metrics`
- Correlate with `request_throughput_rps` to distinguish workload gaps from config issues; set severity to `info` for low traffic vs. `warning` for suspected misconfiguration
- **Complexity:** M
- _Requirements: REQ-2.3_

### Task 3.4 — Memory Fragmentation Analyzer (`analyzers/memory_fragmentation.py`)
- Flag an issue when GPU memory utilization is high (e.g., > 85%) but `kv_cache.hit_rate` is low (e.g., < 0.3), indicating fragmentation
- Include `memory_utilization_pct`, `kv_cache.hit_rate`, and `kv_cache.eviction_rate` in `supporting_metrics`
- Skip gracefully when `kv_cache` is `None` (engine doesn't expose KV cache metrics)
- **Complexity:** M
- _Requirements: REQ-2.4_

### Task 3.5 — Queue Saturation Analyzer (`analyzers/queue_saturation.py`)
- Flag an issue when `queue_depth` exceeds `batch.max_batch_size * config.analyzers.queue_saturation.depth_multiplier` (default 2×) for more than `window_seconds` (default 120s)
- Include `queue_depth`, `queue_wait_ms.p99`, and `request_throughput_rps` in `supporting_metrics`
- Set severity to `warning` at threshold and `critical` at 3× threshold
- **Complexity:** M
- _Requirements: REQ-2.5_

### Task 3.6 — KV Cache Effectiveness Analyzer (`analyzers/kv_cache_effectiveness.py`)
- Flag an issue when `kv_cache.hit_rate` is below `config.analyzers.kv_cache_effectiveness.hit_rate_threshold` (default 0.30) on deployments where the engine supports prefix caching
- Include `hit_rate`, `miss_rate`, `eviction_rate`, and `prefix_caching_enabled` in `supporting_metrics`
- Skip gracefully when `kv_cache` is `None`
- **Complexity:** S
- _Requirements: REQ-2.6_

### Task 3.7 — Scheduling Inefficiency Analyzer (`analyzers/scheduling.py`)
- Flag an issue when prefill stalls, preemption rates, or context-switch overhead metrics exceed engine-specific baselines configured in `config.analyzers.scheduling_inefficiency`
- Include the specific scheduling metric that crossed threshold in `supporting_metrics`; populate `description` with the related configuration parameters to investigate
- Fall back gracefully when engine does not expose scheduling metrics
- **Complexity:** M
- _Requirements: REQ-2.7_


---

## Phase 4 — Recommender Plugins

> Each recommender lives in `infersight/plugins/recommenders/`. All must subclass `RecommenderPlugin`, declare `handles_issue_types`, and implement `recommend(issue: Issue) -> list[Recommendation]`.

### Task 4.1 — Prefix Cache Recommender (`recommenders/prefix_cache.py`)
- Generate a recommendation to enable prefix caching when `issue_type == "low_kv_cache_effectiveness"` and `kv_cache.prefix_caching_enabled == False`
- Include `target_parameter` = engine-specific flag (e.g., `--enable-prefix-caching` for vLLM), `reasoning`, and `estimated_impact` derived from the hit-rate gap
- Provide `engine_config_snippet` in native engine format; mark `rank = 1` as highest priority
- **Complexity:** S
- _Requirements: REQ-3.1, REQ-3.2.1_

### Task 4.2 — Batch Size Recommender (`recommenders/batch_size.py`)
- Generate a recommendation to increase `max_num_seqs` (or equivalent) when `issue_type` is `batch_efficiency` or `decode_bottleneck`
- Compute `recommended_value` as `current_value * 2` capped at a safety maximum (document the formula); include fill-rate evidence in `reasoning`
- Provide engine-specific CLI flag snippet in `engine_config_snippet`
- **Complexity:** S
- _Requirements: REQ-3.1, REQ-3.2.2_

### Task 4.3 — Scheduler Config Recommender (`recommenders/scheduler_config.py`)
- Generate recommendations for `max_num_batched_tokens` and scheduling policy parameters when `issue_type == "scheduling_inefficiency"`
- Reference the specific scheduling metric that triggered the issue in the `reasoning` field
- Provide config snippet for the identified engine's scheduler config format
- **Complexity:** M
- _Requirements: REQ-3.1, REQ-3.2.3_

### Task 4.4 — Tensor Parallelism Recommender (`recommenders/tensor_parallelism.py`)
- Analyze `gpu_devices` utilization imbalance patterns and recommend adjusting `tensor_parallel_size` when GPU utilization is consistently uneven across devices
- Validate that the recommended TP value is a valid divisor of the model's attention heads (document the constraint)
- Flag the risk of exceeding memory if TP is reduced; set `estimated_impact` to a conservative range
- **Complexity:** M
- _Requirements: REQ-3.1, REQ-3.2.4_

### Task 4.5 — KV Cache Size Recommender (`recommenders/kv_cache_size.py`)
- Generate a recommendation to increase KV cache allocation when `kv_cache.eviction_rate` is high or memory allocation is imbalanced (high eviction with available GPU memory headroom)
- Compute `recommended_value` as a percentage of GPU memory (e.g., `gpu_memory_utilization = 0.90`) and flag if it approaches physical limits
- Reference design §3.1.5 safety constraint: never recommend exceeding physical GPU memory without an explicit risk flag
- **Complexity:** S
- _Requirements: REQ-3.1, REQ-3.2.5_

### Task 4.6 — Chunked Prefill Recommender (`recommenders/chunked_prefill.py`)
- Recommend enabling chunked prefill when `avg_prompt_tokens` is high and scheduling stall metrics indicate prefill dominance
- Set `target_parameter` to engine-specific flag (e.g., `--enable-chunked-prefill` for vLLM)
- Include `prefill_decode_ratio` and `avg_prompt_tokens` values in `reasoning`
- **Complexity:** S
- _Requirements: REQ-3.1, REQ-3.2.6_

### Task 4.7 — Scaling Recommender (`recommenders/scaling.py`)
- Generate scale-up recommendations (add replicas) when `issue_type == "queue_saturation"` persists beyond the alert window
- Generate scale-down recommendations (remove replicas) when `issue_type == "gpu_underutilization"` persists beyond the alert window
- `estimated_impact` must state expected latency or cost change; include a note that actual scaling requires user action via their orchestrator
- **Complexity:** M
- _Requirements: REQ-3.1, REQ-3.2.7_


---

## Phase 5 — Notification Plugins

> Each notification plugin lives in `infersight/plugins/notifications/`. All must subclass `NotificationPlugin`. Failures must be logged but must NOT propagate exceptions (design §4.5).

### Task 5.1 — Slack Notification Plugin (`notifications/slack.py`)
- Implement `SlackNotificationPlugin` that posts issue alerts to a Slack webhook URL configured via `alerting.channels.slack.webhook_url`
- Format the message with severity emoji, deployment ID, issue description, and a link to the dashboard `/issues` page
- Implement deduplication: track `(issue_id, deployment_id)` tuples and suppress re-notification within `alerting.deduplication_window_seconds`
- **Complexity:** S
- _Requirements: REQ-6.4.1, REQ-6.4.4_

### Task 5.2 — PagerDuty Notification Plugin (`notifications/pagerduty.py`)
- Implement `PagerDutyNotificationPlugin` using PagerDuty Events API v2 (`POST https://events.pagerduty.com/v2/enqueue`)
- Map InferSight `Severity` to PagerDuty severity levels; use `issue_id + deployment_id` as the `dedup_key` for automatic PagerDuty deduplication
- Send a `resolve` event when `issue.cleared_at` is set; handle API errors gracefully (log, don't raise)
- **Complexity:** S
- _Requirements: REQ-6.4.2_

### Task 5.3 — Email (SMTP) Notification Plugin (`notifications/email.py`)
- Implement `EmailNotificationPlugin` using Python's `smtplib` / `aiosmtplib` with TLS support
- Render a structured HTML email body with issue details; support `to_addresses` list from config
- Respect `alerting.channels.email.severity_threshold`; handle SMTP auth errors gracefully and log them without exposing credentials
- **Complexity:** S
- _Requirements: REQ-6.4.3_

### Task 5.4 — Alert Routing + Deduplication Logic
- Implement a central `AlertRouter` that dispatches `Issue` objects to configured `NotificationPlugin` instances based on severity thresholds and deployment filters from `alerting.channels.*`
- Maintain an in-memory (and SQLite-persisted) deduplication state keyed on `(issue_id, deployment_id)` with TTL = `alerting.deduplication_window_seconds`
- Write unit tests covering: correct routing by severity, deduplication within window, and re-alerting after window expiry
- **Complexity:** M
- _Requirements: REQ-6.4.4_


---

## Phase 6 — REST API

> All routes mount under `/api/v1`. Auth middleware (API key) wraps all `/api/v1/*` routes; `/health` and `/ready` are always public (design §9.1).

### Task 6.1 — Deployments Endpoints (`api/routes/deployments.py`)
- Implement `GET /api/v1/deployments` returning the list of configured deployments with last-known health status
- Implement `GET /api/v1/deployments/{id}` returning deployment detail including current metric snapshot and open issue count
- Return `404` with a structured error body when the deployment ID is not found
- **Complexity:** S
- _Requirements: REQ-1.5.1, REQ-2.8.1_

### Task 6.2 — Metrics Query Endpoints (`api/routes/metrics.py`)
- Implement `GET /api/v1/metrics` with query parameters: `deployment_id`, `engine`, `model_name`, `start`, `end`, `limit` (design §5.2)
- Implement `GET /api/v1/metrics/latest` returning the most recent `CanonicalMetric` per deployment
- Implement `GET /metrics` (Prometheus exposition format) by serializing the latest snapshot into Prometheus text format; controlled by `prometheus.exposition_enabled`
- **Complexity:** M
- _Requirements: REQ-1.4.3, REQ-2.8.1_

### Task 6.3 — Issues Endpoints (`api/routes/issues.py`)
- Implement `GET /api/v1/issues` with filters: `deployment_id`, `severity` (repeatable), `issue_type`, `active_only` (design §5.2)
- Implement `GET /api/v1/issues/{issue_id}` returning a single issue with full `supporting_metrics`
- Response shape must match the example from design §5.2; write a test asserting the schema
- **Complexity:** S
- _Requirements: REQ-2.8.1–2.8.4_

### Task 6.4 — Recommendations Endpoints (`api/routes/recommendations.py`)
- Implement `GET /api/v1/recommendations` with filters: `deployment_id`, `status`, `issue_type`
- Implement `PATCH /api/v1/recommendations/{rec_id}` accepting `{"status": "applied" | "acknowledged" | "dismissed"}` and triggering post-apply monitoring when status = `applied`
- Implement `GET /api/v1/recommendations/{rec_id}/export` returning the `engine_config_snippet` as plain text with a human-readable explanation header
- **Complexity:** M
- _Requirements: REQ-3.3, REQ-3.4_

### Task 6.5 — WebSocket Live Metric Stream
- Implement a WebSocket endpoint at `ws://host/api/v1/ws/metrics` that pushes new `CanonicalMetric` snapshots to connected clients as they are written to storage
- Implement a WebSocket endpoint at `ws://host/api/v1/ws/issues` that pushes new and resolved `Issue` objects
- Apply the same API key auth check on WebSocket upgrade handshake when auth is enabled
- **Complexity:** M
- _Requirements: REQ-1.5.1_

### Task 6.6 — Plugins Listing Endpoint
- Implement `GET /api/v1/plugins` returning a list of all loaded plugins grouped by type (collector, analyzer, recommender, notification), including `plugin_name` and `engine_name`/`analyzer_name` as applicable
- Used for debugging plugin discovery issues; always returns 200 even if plugin list is empty
- **Complexity:** S
- _Requirements: REQ-6.1.2_


---

## Phase 7 — Infrastructure Advisor

> Advisor logic lives in `infersight/advisor/`. Analysis is triggered via CLI or REST API. Output is structured `FindingsList` with severity, file reference, description, and remediation.

### Task 7.1 — Kubernetes Manifest Analyzer (`advisor/k8s.py`)
- Parse YAML manifests (Deployment, StatefulSet, DaemonSet, Service, ConfigMap, HPA) using `pyyaml` and check for: missing/incorrect `nvidia.com/gpu` resource requests, missing liveness/readiness probes, missing anti-affinity rules, insufficient memory requests, missing/misconfigured HPA
- Emit a `Finding` object per issue with `severity`, `file`, `line_range`, `description`, and `remediation`
- Write unit tests using fixture YAML files for each check (both passing and failing cases)
- **Complexity:** L
- _Requirements: REQ-4.1.1–4.1.7_

### Task 7.2 — Helm Chart Analyzer (`advisor/helm.py`)
- Accept a Helm chart directory, invoke `helm template` via `subprocess` to render manifests, then feed rendered YAML into the Kubernetes analyzer from Task 7.1
- Handle `helm` binary not found gracefully: return a `Finding(severity=WARNING, description="helm binary not found — cannot render chart")` rather than raising
- Support `--set key=value` overrides passed through from the CLI/API
- **Complexity:** M
- _Requirements: REQ-4.1.2_

### Task 7.3 — Terraform HCL Analyzer (`advisor/terraform.py`)
- Parse Terraform HCL files using `python-hcl2` and check for: GPU instance type selection (flag non-GPU types for inference workloads), autoscaling policy presence, and networking configuration issues
- Flag instance types from a configurable deny-list of known insufficient types for inference workloads (e.g., `t3.*`, `m5.*`)
- Emit structured `Finding` objects with file and line range references
- **Complexity:** M
- _Requirements: REQ-4.2.1, REQ-4.2.3, REQ-4.2.4_

### Task 7.4 — Ray Cluster Analyzer (`advisor/ray.py`)
- Parse Ray cluster YAML config and Ray Serve deployment definitions, checking for: imbalanced GPU allocation across worker nodes, missing `ray_actor_options` GPU resource declarations, placement group misconfiguration
- Emit `Finding` objects with severity appropriate to the issue (missing GPU declaration = `critical`)
- **Complexity:** M
- _Requirements: REQ-4.3_

### Task 7.5 — CLI `infersight advisor analyze` Command
- Add `infersight advisor analyze <path>` Typer subcommand that accepts a file or directory path and dispatches to the appropriate analyzer based on file extension/structure
- Support `--format json|text` and `--threshold info|warning|critical` flags; exit with code 1 when any finding at or above threshold is present
- Print human-readable findings table to stdout for `--format text`; print JSON array for `--format json`
- **Complexity:** S
- _Requirements: REQ-4.4.2, REQ-4.4.3, REQ-4.4.4_

### Task 7.6 — `POST /advisor/analyze` API Endpoint (`api/routes/advisor.py`)
- Accept multipart file upload(s) or a JSON body with file contents; dispatch to the appropriate advisor module
- Return a JSON response with the `findings` array matching the `Finding` schema; include `file`, `line_range`, `severity`, `description`, `remediation`
- Apply auth middleware; document the endpoint in OpenAPI with a request body example
- **Complexity:** S
- _Requirements: REQ-4.4.1, REQ-4.4.3_


---

## Phase 8 — AI Copilot

> Copilot logic lives in `infersight/copilot/`. The system runs in degraded mode (503 responses) when no LLM backend is configured (REQ-5.3.4).

### Task 8.1 — CopilotAgent Tool-Calling Loop (`copilot/agent.py`)
- Implement `CopilotAgent.chat(session_id, message)` following the architecture in design §10.1: build messages array → call LiteLLM → dispatch tool calls → append results → call LiteLLM again for final response
- Limit conversation history to `config.copilot.max_context_messages` to bound token usage
- Log all queries and responses to `copilot_history` table via `StorageBackend`; never log raw LLM API keys
- **Complexity:** L
- _Requirements: REQ-5.1, REQ-5.4.4_

### Task 8.2 — Copilot Tool Implementations (`copilot/tools.py`)
- Implement all six tools from design §10.2: `get_latest_metrics`, `get_metric_history`, `get_active_issues`, `get_recommendations`, `compare_deployments`, `get_deployment_config`
- All tools must proxy into `StorageBackend`; return JSON-serializable dicts (no raw Pydantic objects to the LLM)
- Each tool must handle the case where no data is available and return `{"available": false, "reason": "..."}` rather than raising
- **Complexity:** M
- _Requirements: REQ-5.2, REQ-5.4.1, REQ-5.4.2_

### Task 8.3 — System Prompt Template (`copilot/prompts.py`)
- Implement the system prompt from design §10.3 with `{deployment_list}` and `{current_time_iso}` interpolation
- Include the "NEVER fabricate" and "cite tool results" rules exactly as specified
- Expose a `build_system_prompt(deployments: list[str]) -> str` function used by the agent
- **Complexity:** S
- _Requirements: REQ-5.4.1, REQ-5.4.3_

### Task 8.4 — Citation Extraction (`copilot/agent.py`)
- Implement `extract_citations(reply, tool_results)` using the regex pattern from design §10.4
- Resolve citation references against the accumulated tool results from the tool-calling loop
- Return a `list[dict]` of structured citation objects included in the API response
- **Complexity:** S
- _Requirements: REQ-5.1.4_

### Task 8.5 — Copilot REST Endpoints (`api/routes/copilot.py`)
- Implement `POST /api/v1/copilot/chat` accepting `{"session_id": str, "message": str}` and returning `{"reply": str, "citations": [...], "reply_type": "factual" | "guidance"}`
- Implement `GET /api/v1/copilot/history` returning paginated chat history for a session
- Return `503 Service Unavailable` with `{"error": "copilot not configured"}` when `config.copilot.enabled == False`
- **Complexity:** S
- _Requirements: REQ-5.1.1, REQ-5.3.4_

### Task 8.6 — Degraded Mode + LiteLLM Multi-Provider Config
- Configure LiteLLM via `config.copilot.provider` to support: `openai`, `anthropic`, `azure_openai`, and `custom` (OpenAI-compatible base URL)
- Validate that the LLM connection is reachable at startup and log a clear `WARNING` when not configured; do not crash other phases
- Write an integration test using a mock LiteLLM response to verify the full chat → tool call → response flow
- **Complexity:** M
- _Requirements: REQ-5.3.1, REQ-5.3.2, REQ-5.3.4_


---

## Phase 9 — React Frontend

> All frontend code lives in `ui/src/`. Use TanStack Query for server state with 15s polling. Use Zustand for UI state. See design §7 for page layout and component tree.

### Task 9.1 — Project Setup + API Client
- Configure Vite proxy (`/api` → `http://localhost:8000`) for local development
- Implement a typed API client (`ui/src/api/client.ts`) with functions for each backend endpoint using `fetch` + TanStack Query hooks
- Set up a `QueryClientProvider` root and a global WebSocket context provider for live updates
- **Complexity:** S
- _Requirements: REQ-1.5.1_

### Task 9.2 — Dashboard Page (Fleet Overview)
- Implement `DashboardPage` with `FleetHealthBanner` showing aggregate green/yellow/red status and `DeploymentGrid` with one `DeploymentCard` per deployment
- `DeploymentCard` shows: deployment name, engine type, model name, health indicator, latest TTFT p99, throughput, and open issue count
- Wire to `GET /api/v1/deployments` and `GET /api/v1/metrics/latest` via TanStack Query with 15s refetch
- **Complexity:** M
- _Requirements: REQ-1.5.1, REQ-1.5.4_

### Task 9.3 — Deployment Detail Page (Metric Charts)
- Implement `DeploymentDetailPage` with four `MetricPanel` sections: Latency (LineChart), Throughput (LineChart), GPU (BarChart per device), KV Cache (GaugeChart)
- Use Recharts for all charts; data comes from `GET /api/v1/metrics` with the deployment filter and a time-range picker
- Include `IssueList` and `RecommendationList` sections at the bottom of the page; wire apply/dismiss actions to `PATCH /recommendations/{id}`
- **Complexity:** L
- _Requirements: REQ-1.5.1, REQ-1.5.2, REQ-1.5.3_

### Task 9.4 — Issues Page (Filterable Table)
- Implement `IssuesPage` with a filterable table of all active issues; filters: engine type, deployment, severity, issue type
- Each row shows: severity badge, issue type, affected deployment, detected time, and a "View Details" link to the deployment detail page
- Wire filters to URL query params so the filtered view is bookmarkable
- **Complexity:** M
- _Requirements: REQ-1.5.2, REQ-2.8.3_

### Task 9.5 — Recommendations Page
- Implement `RecommendationsPage` with a ranked list of open recommendations; each card shows: issue type, target parameter, current vs. recommended value, estimated impact, and Apply/Dismiss/Acknowledge buttons
- Implement an "Export Snippet" button per recommendation that fetches `GET /recommendations/{id}/export` and shows the snippet in a code block modal
- Optimistically update recommendation status in the UI on button click while the PATCH request is in-flight
- **Complexity:** M
- _Requirements: REQ-3.4, REQ-3.3_

### Task 9.6 — Infrastructure Advisor Page
- Implement `AdvisorPage` with a drag-and-drop file upload zone (accept `.yaml`, `.yml`, `.tf`, `.json`) that POSTs to `POST /api/v1/advisor/analyze`
- Display findings in a sortable table with columns: severity, file, line, description, remediation
- Color-code rows by severity (red = critical, yellow = warning, blue = info); show a summary banner with counts per severity
- **Complexity:** M
- _Requirements: REQ-4.4.1, REQ-4.4.3_

### Task 9.7 — Copilot Chat Page
- Implement `CopilotPage` with a message thread view, citation chips rendered as inline badges, and a message input with send button
- Render `reply_type` labels: "Factual (based on your data)" vs. "General Guidance"
- Show a disabled state with a banner message "Copilot not configured" when the backend returns 503
- **Complexity:** M
- _Requirements: REQ-5.1.1, REQ-5.1.4, REQ-5.1.5_

### Task 9.8 — Settings Page
- Implement `SettingsPage` with sections: API key configuration, OIDC setup, notification channel toggles (Slack/PagerDuty/Email), analyzer thresholds, and copilot LLM provider selection
- Settings changes POST to a `PATCH /api/v1/config` endpoint (or save to `localStorage` for frontend-only preferences)
- Mask sensitive field values (API keys, webhooks) in the UI after initial entry
- **Complexity:** M
- _Requirements: REQ-7.2.1, REQ-7.2.2_

### Task 9.9 — WebSocket Integration for Live Updates
- Connect the global WebSocket context provider to `ws://host/api/v1/ws/issues`; update the TanStack Query cache with incoming issue events via `queryClient.setQueryData`
- Show a real-time notification toast when a new `critical` issue arrives
- Reconnect automatically with exponential backoff on WebSocket disconnect
- **Complexity:** M
- _Requirements: REQ-1.5.1_


---

## Phase 10 — Kubernetes / Helm

### Task 10.1 — Helm Chart (`helm/infersight/`)
- Create `Chart.yaml` with `apiVersion: v2`, `name: infersight`, and semantic version matching the app version
- Implement all eight templates from design §8.3: `deployment.yaml`, `service.yaml`, `configmap.yaml`, `secret.yaml`, `serviceaccount.yaml`, `pvc.yaml`, `ingress.yaml`, `hpa.yaml`
- Write `values.yaml` with all fields from design §8.3 including `replicaCount`, `image`, `service`, `ingress`, `persistence`, `config`, `secrets`, `resources`, `podAnnotations`, `nodeSelector`, `tolerations`, `affinity`
- **Complexity:** L
- _Requirements: REQ-7.1.2_

### Task 10.2 — Grafana Dashboard JSON
- Export a Grafana dashboard JSON definition covering all REQ-1.2 metrics: TTFT histograms, throughput, queue depth, GPU utilization per device, KV cache hit rate, batch fill rate
- Use the Prometheus data source with metric names matching the Prometheus exposition output from Task 6.2
- Save to `dashboards/infersight.json`; document import steps in a README
- **Complexity:** M
- _Requirements: REQ-1.4.4_

### Task 10.3 — Multi-Stage Dockerfile Finalization
- Finalize the Dockerfile to copy pre-built `ui/dist/` into `/app/static` and verify FastAPI serves it at `/`
- Add `INFERSIGHT_VERSION` build arg wired to `pyproject.toml` version field
- Publish a `linux/amd64` and `linux/arm64` manifest list from the CI build job; verify `docker run` produces a working health check
- **Complexity:** M
- _Requirements: REQ-7.1.1_


---

## Phase 11 — Docs + CI/CD

### Task 11.1 — Quickstart Guide (`docs/quickstart.md`)
- Write a step-by-step guide covering: installation via `pip install infersight`, creating a minimal `infersight.yaml` pointing at a vLLM deployment, running `infersight`, and viewing the dashboard
- Include a Docker Compose example for single-node evaluation
- Verify all commands in the guide work against the latest release build
- **Complexity:** S
- _Requirements: REQ-7.4.1_

### Task 11.2 — Plugin Development Guide (`docs/plugin-guide.md`)
- Document all three plugin ABCs (`CollectorPlugin`, `AnalyzerPlugin`, `RecommenderPlugin`) with annotated example implementations
- Explain the plugin discovery mechanism (directory scanning, `plugin_dirs` config) and how to package a plugin as a separate Python module
- Include a "Testing your plugin" section using pytest fixtures and the mock `CanonicalMetric` builder
- **Complexity:** M
- _Requirements: REQ-7.4.3_

### Task 11.3 — Engine-Specific Integration Guides
- Write one integration guide per supported engine: vLLM, SGLang, TGI, Triton, KServe, SageMaker HyperPod, Ray Serve
- Each guide covers: enabling metrics endpoints on the engine, the minimal `infersight.yaml` deployment block, any engine-specific gotchas, and expected metrics populated
- Save as `docs/engines/{engine_name}.md`
- **Complexity:** M
- _Requirements: REQ-7.4.4_

### Task 11.4 — OpenAPI Reference (Auto-Generated)
- Configure FastAPI to export `openapi.json` at `/openapi.json` and a Swagger UI at `/docs`; ensure all routes have `summary`, `description`, and response schema annotations
- Add a CI step that exports `openapi.json` and fails if it differs from the committed copy (`make update-openapi`)
- Publish the generated reference to the project `docs/` folder or a dedicated docs site
- **Complexity:** S
- _Requirements: REQ-2.8.4, REQ-7.4.2_

### Task 11.5 — GitHub Actions: Test + Lint
- Finalize the `ci.yml` `lint` job to run `ruff check`, `ruff format --check`, and `mypy`; fail fast on first error
- Finalize the `test` job to run `pytest tests/ --cov=infersight --cov-report=xml` and upload coverage to Codecov
- Add a `frontend` job running `npm run lint` and `npm run build` in `ui/`
- **Complexity:** S
- _Requirements: REQ-7.4.1_

### Task 11.6 — GitHub Actions: Docker Build + Publish
- Add a `docker` workflow triggered on tag push (`v*.*.*`) that builds the multi-arch image and pushes to `ghcr.io/piyushdaftary/infersight:{tag}` and `:latest`
- Use `docker/buildx-action` and `docker/login-action`; sign the image with `cosign` if available
- Add a `publish-helm` job that packages the Helm chart and pushes it to a GitHub Pages OCI registry or chart museum
- **Complexity:** M
- _Requirements: REQ-7.1.1, REQ-7.1.2_


---

## Task Summary

| Phase | Tasks | Estimated Effort |
|-------|-------|-----------------|
| 0 — Scaffolding | 0.1–0.7 (7 tasks) | ~3–4 days |
| 1 — Core Infrastructure | 1.1–1.8 (8 tasks) | ~5–7 days |
| 2 — Collector Plugins | 2.1–2.7 (7 tasks) | ~6–8 days |
| 3 — Analyzer Plugins | 3.1–3.7 (7 tasks) | ~5–7 days |
| 4 — Recommender Plugins | 4.1–4.7 (7 tasks) | ~4–6 days |
| 5 — Notification Plugins | 5.1–5.4 (4 tasks) | ~2–3 days |
| 6 — REST API | 6.1–6.6 (6 tasks) | ~4–6 days |
| 7 — Infrastructure Advisor | 7.1–7.6 (6 tasks) | ~5–7 days |
| 8 — AI Copilot | 8.1–8.6 (6 tasks) | ~5–7 days |
| 9 — React Frontend | 9.1–9.9 (9 tasks) | ~8–12 days |
| 10 — Kubernetes / Helm | 10.1–10.3 (3 tasks) | ~3–4 days |
| 11 — Docs + CI/CD | 11.1–11.6 (6 tasks) | ~3–5 days |
| **Total** | **76 tasks** | **~53–76 days** |

> Parallel execution across frontend/backend and plugin development will compress wall-clock time significantly.
