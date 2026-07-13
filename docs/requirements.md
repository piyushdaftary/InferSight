# InferSight Requirements Document

## Overview

InferSight is an open-source intelligence layer for AI inference infrastructure. It sits on top of existing model serving systems and makes them observable, understandable, and optimizable — without serving models itself.

**Repository:** https://github.com/piyushdaftary/InferSight

---

## Guiding Principles

- **Vendor neutral** — supports multiple inference engines (vLLM, SGLang, TGI, Triton, KServe, SageMaker HyperPod, etc.) and deployment platforms without lock-in
- **Explainable recommendations** — every recommendation includes the supporting metrics, the reasoning chain, and an estimated impact range
- **Production first** — optimizes for reliability, measurable cost/latency/throughput improvements, not benchmark-only scenarios
- **Extensible** — modular plugin architecture so new analyzers, collectors, and integrations can be added without modifying core code

---

## Success Criteria

InferSight is considered successful when users can:

1. Reduce inference latency (TTFT, inter-token latency)
2. Improve throughput (tokens/sec, requests/sec)
3. Increase GPU utilization toward capacity limits
4. Lower infrastructure cost per token/request
5. Identify root causes of performance regressions faster than manual investigation
6. Apply optimization best practices with confidence backed by data

---

## Phase 1 — Observability

### Goal

Collect, normalize, and present metrics from heterogeneous inference systems in a unified view.

### REQ-1.1: Multi-Engine Metric Collection

**User Story:** As an ML infrastructure engineer, I want to collect metrics from any inference engine I use so I have a single place to monitor all deployments.

**Acceptance Criteria:**
- 1.1.1 The system SHALL collect metrics from vLLM, SGLang, TGI (Text Generation Inference), NVIDIA Triton Inference Server, KServe, Amazon SageMaker HyperPod, and Ray Serve deployments.
- 1.1.2 The system SHALL expose a collector plugin interface so that metrics from additional inference engines can be added without modifying core code.
- 1.1.3 The system SHALL poll or scrape metrics at a configurable interval (default: 15 seconds).
- 1.1.4 The system SHALL handle collection failures gracefully, logging errors and retrying with backoff, without crashing or dropping existing data.
- 1.1.5 The system SHALL support both pull-based (HTTP scrape) and push-based (webhook/agent) collection modes.

### REQ-1.2: Core Metric Coverage

**User Story:** As an ML infrastructure engineer, I want to see all the key inference metrics in one place so I can understand system health at a glance.

**Acceptance Criteria:**
- 1.2.1 The system SHALL collect Time to First Token (TTFT) per request, as a histogram with configurable percentile buckets (p50, p90, p95, p99).
- 1.2.2 The system SHALL collect decode throughput in tokens per second, both per-request and aggregated.
- 1.2.3 The system SHALL collect request queue depth and queue wait time at each engine instance.
- 1.2.4 The system SHALL collect GPU utilization (compute %) per GPU device.
- 1.2.5 The system SHALL collect GPU memory utilization (used/total) per GPU device.
- 1.2.6 The system SHALL collect KV cache utilization (hit rate, eviction rate, size used/total) where the engine exposes it.
- 1.2.7 The system SHALL collect batch efficiency metrics including batch size distribution, batch fill rate, and prefill vs. decode token ratio.
- 1.2.8 The system SHALL collect request-level metadata: model name, request length (prompt tokens), output length, finish reason, and error codes.

### REQ-1.3: Unified Metric Schema

**User Story:** As a developer building on InferSight, I want a consistent metric schema regardless of which engine produced the data so I can write engine-agnostic analysis code.

**Acceptance Criteria:**
- 1.3.1 The system SHALL normalize all collected metrics into a canonical schema with consistent field names, units, and types.
- 1.3.2 The canonical schema SHALL include an `engine` field indicating the source engine and version.
- 1.3.3 The canonical schema SHALL include a `deployment_id` field linking metrics to a specific deployment or replica.
- 1.3.4 The system SHALL document the canonical schema and publish a schema version with each release.
- 1.3.5 Breaking schema changes SHALL increment a major schema version.

### REQ-1.4: Metric Storage and Retention

**User Story:** As an ML infrastructure engineer, I want metrics stored so I can analyze trends and correlate incidents with historical data.

**Acceptance Criteria:**
- 1.4.1 The system SHALL persist collected metrics to a configurable time-series backend (Prometheus, InfluxDB, or an embedded store for single-node deployments).
- 1.4.2 The system SHALL support configurable retention windows (default: 30 days).
- 1.4.3 The system SHALL support exporting metrics in Prometheus exposition format so existing Prometheus/Grafana stacks can consume them.
- 1.4.4 The system SHALL provide pre-built Grafana dashboard definitions (JSON) for the canonical metric schema.

### REQ-1.5: Unified Dashboard

**User Story:** As an ML infrastructure engineer, I want a web UI that shows all inference deployments in one view so I can spot problems quickly.

**Acceptance Criteria:**
- 1.5.1 The system SHALL provide a web-based dashboard showing real-time and historical values for all REQ-1.2 metrics.
- 1.5.2 The dashboard SHALL allow filtering by engine type, deployment, model name, and time range.
- 1.5.3 The dashboard SHALL support multi-deployment comparison views side by side.
- 1.5.4 The dashboard SHALL display health indicators (green/yellow/red) derived from configurable thresholds for each metric.
- 1.5.5 The dashboard SHALL be accessible without login by default, with optional authentication (API key or OIDC) configurable in settings.

---

## Phase 2 — Analysis

### Goal

Automatically detect common inference performance issues and surface them with supporting evidence.

### REQ-2.1: Decode Bottleneck Detection

**User Story:** As an ML infrastructure engineer, I want to know when my deployment is decode-bound so I can take targeted action.

**Acceptance Criteria:**
- 2.1.1 The system SHALL flag a deployment as decode-bottlenecked WHEN the decode token throughput is consistently below an engine-specific threshold AND GPU compute utilization is high.
- 2.1.2 The detection SHALL include the observed throughput value, the threshold used, and the time window analyzed.
- 2.1.3 The system SHALL suppress repeated alerts for the same ongoing condition; re-alerting SHALL occur only after the condition clears and recurs.

### REQ-2.2: Inefficient Batching Detection

**User Story:** As an ML infrastructure engineer, I want to be alerted when batches are consistently under-filled so I know I'm leaving throughput on the table.

**Acceptance Criteria:**
- 2.2.1 The system SHALL flag inefficient batching WHEN the average batch fill rate falls below a configurable threshold (default: 60%) over a sustained window (default: 5 minutes).
- 2.2.2 The detection SHALL report the observed fill rate, batch size distribution histogram, and the time window analyzed.
- 2.2.3 The analysis SHALL distinguish between genuine low-traffic conditions and misconfiguration.

### REQ-2.3: GPU Underutilization Detection

**User Story:** As an ML platform engineer, I want to know when GPUs are idle or underused so I can resize or consolidate deployments to reduce cost.

**Acceptance Criteria:**
- 2.3.1 The system SHALL flag GPU underutilization WHEN average GPU compute utilization remains below a configurable threshold (default: 40%) for a sustained period (default: 10 minutes).
- 2.3.2 The detection SHALL include per-GPU breakdowns and the aggregated average.
- 2.3.3 The system SHALL correlate underutilization with low request volume to distinguish workload gaps from configuration issues.

### REQ-2.4: Memory Fragmentation Detection

**User Story:** As an ML infrastructure engineer, I want to detect GPU memory fragmentation so I can understand unexpected OOM errors and inefficient KV cache usage.

**Acceptance Criteria:**
- 2.4.1 The system SHALL flag memory fragmentation WHEN GPU memory utilization is high but effective KV cache occupancy is low relative to the allocated memory, indicating fragmentation.
- 2.4.2 The detection SHALL report memory utilization, KV cache hit rate, and eviction rate as supporting evidence.

### REQ-2.5: Queue Saturation Detection

**User Story:** As an ML infrastructure engineer, I want to be alerted when request queues are backing up so I can scale before latency degrades significantly.

**Acceptance Criteria:**
- 2.5.1 The system SHALL flag queue saturation WHEN queue depth exceeds a configurable threshold (default: engine_max_batch_size * 2) for more than a configurable duration (default: 2 minutes).
- 2.5.2 The detection SHALL include current queue depth, p99 queue wait time, and request arrival rate.

### REQ-2.6: Low KV Cache Effectiveness Detection

**User Story:** As an ML infrastructure engineer, I want to know when my KV cache hit rate is low so I understand whether prefix caching could reduce latency.

**Acceptance Criteria:**
- 2.6.1 The system SHALL flag low KV cache effectiveness WHEN the KV cache hit rate falls below a configurable threshold (default: 30%) on engines where prefix caching is available.
- 2.6.2 The detection SHALL report hit rate, miss rate, eviction rate, and whether prefix caching is currently enabled.

### REQ-2.7: Scheduling Inefficiency Detection

**User Story:** As an ML infrastructure engineer, I want to detect scheduling inefficiencies so I can tune scheduler parameters.

**Acceptance Criteria:**
- 2.7.1 The system SHALL flag scheduling inefficiencies WHEN prefill queue stalls, preemption rates, or context-switch overhead metrics exceed engine-specific baselines.
- 2.7.2 Detection results SHALL identify the specific scheduling metric that crossed threshold and suggest related configuration parameters.

### REQ-2.8: Analysis API

**User Story:** As a developer integrating InferSight into CI/CD or alerting pipelines, I want a programmatic API to retrieve analysis results.

**Acceptance Criteria:**
- 2.8.1 The system SHALL expose a REST API endpoint that returns the current set of detected issues for a given deployment.
- 2.8.2 Each issue in the API response SHALL include: issue type, severity (info/warning/critical), affected deployment, supporting metrics, and timestamp.
- 2.8.3 The API SHALL support filtering by deployment, severity level, and issue type.
- 2.8.4 The API SHALL be documented with an OpenAPI 3.x specification.

---

## Phase 3 — Recommendations

### Goal

Translate detected issues into actionable, evidence-backed optimization guidance with estimated impact.

### REQ-3.1: Recommendation Generation

**User Story:** As an ML infrastructure engineer, I want to receive specific optimization recommendations tied to detected issues so I know what to do next and why.

**Acceptance Criteria:**
- 3.1.1 The system SHALL generate at least one recommendation for each detected issue category from Phase 2.
- 3.1.2 Every recommendation SHALL include: the target configuration parameter or action, the current observed value, the recommended value or range, the reasoning for the recommendation, and an estimated impact range (e.g., "expected 15–30% reduction in TTFT").
- 3.1.3 Recommendations SHALL be engine-specific where configuration syntax differs across engines.
- 3.1.4 Recommendations SHALL be ranked by estimated impact so the highest-value action appears first.
- 3.1.5 The system SHALL NOT recommend changes that could violate safety constraints (e.g., exceeding physical GPU memory) without explicitly flagging the risk.

### REQ-3.2: Specific Recommendation Types

**User Story:** As an ML infrastructure engineer, I want recommendations across the full range of common tuning levers.

**Acceptance Criteria:**
- 3.2.1 The system SHALL provide prefix caching enablement recommendations WHEN KV cache effectiveness is low and the engine supports it.
- 3.2.2 The system SHALL provide batch size tuning recommendations WHEN batch fill rate is low or decode is bottlenecked.
- 3.2.3 The system SHALL provide scheduler configuration recommendations (e.g., `max_num_batched_tokens`, scheduling policy) WHEN scheduling inefficiencies are detected.
- 3.2.4 The system SHALL provide tensor parallelism tuning recommendations WHEN GPU utilization patterns suggest sub-optimal parallelism configuration.
- 3.2.5 The system SHALL provide KV cache size recommendations WHEN cache eviction rates are high or memory allocation is imbalanced.
- 3.2.6 The system SHALL provide chunked prefill enablement recommendations WHEN long-prompt workloads cause prefill stalls.
- 3.2.7 The system SHALL provide scaling recommendations (add/remove replicas) WHEN queue saturation or GPU underutilization persists.

### REQ-3.3: Recommendation History and Feedback

**User Story:** As an ML infrastructure engineer, I want to track which recommendations I've applied and see their measured impact so I can validate improvements.

**Acceptance Criteria:**
- 3.3.1 The system SHALL maintain a recommendation history log with timestamp, recommendation content, and status (open/acknowledged/applied/dismissed).
- 3.3.2 Users SHALL be able to mark a recommendation as applied, which triggers a post-application monitoring window.
- 3.3.3 After a recommendation is marked applied, the system SHALL compare relevant metrics before and after and report the measured impact.
- 3.3.4 Feedback (applied/dismissed) SHALL be usable to improve future recommendation ranking.

### REQ-3.4: Recommendation Export

**User Story:** As an ML infrastructure engineer, I want to export recommendations as config file diffs or runbooks so I can apply them through my normal change management process.

**Acceptance Criteria:**
- 3.4.1 The system SHALL be able to export a recommendation as a configuration snippet or diff in the engine's native format (e.g., vLLM CLI flags, YAML patch).
- 3.4.2 Exported recommendations SHALL include a human-readable explanation suitable for inclusion in a change request.

---

## Phase 4 — Infrastructure Advisor

### Goal

Analyze deployment manifests and infrastructure configuration files to identify architecture improvements before workloads reach production.

### REQ-4.1: Manifest Analysis

**User Story:** As an ML platform engineer, I want InferSight to analyze my Kubernetes manifests and Helm charts and flag infrastructure issues before I deploy to production.

**Acceptance Criteria:**
- 4.1.1 The system SHALL accept Kubernetes YAML manifests (Deployment, StatefulSet, DaemonSet, Service, ConfigMap, HPA) and analyze them for inference-specific misconfigurations.
- 4.1.2 The system SHALL accept Helm chart directories (including `values.yaml` and templates) and render them before analysis.
- 4.1.3 The system SHALL detect missing or incorrect GPU resource requests/limits (`nvidia.com/gpu`).
- 4.1.4 The system SHALL detect missing liveness/readiness probes on inference serving containers.
- 4.1.5 The system SHALL detect missing anti-affinity rules that could co-locate multiple large model replicas on the same node.
- 4.1.6 The system SHALL detect insufficient memory requests relative to model size hints (e.g., from annotations or environment variables).
- 4.1.7 The system SHALL detect missing or misconfigured HPA policies for inference workloads.

### REQ-4.2: Terraform and Cloud Config Analysis

**User Story:** As an ML platform engineer, I want InferSight to review my Terraform configs and SageMaker deployment definitions for infrastructure-level issues.

**Acceptance Criteria:**
- 4.2.1 The system SHALL accept Terraform HCL files and analyze them for GPU instance type selection, count, and networking configuration issues relevant to inference.
- 4.2.2 The system SHALL analyze SageMaker endpoint configuration files for instance type, scaling policy, and model parallelism settings.
- 4.2.3 The system SHALL flag instance types that are likely insufficient for the indicated model size or throughput target.
- 4.2.4 The system SHALL detect missing autoscaling policies for production deployments.

### REQ-4.3: Ray Cluster Analysis

**User Story:** As an ML infrastructure engineer using Ray Serve, I want InferSight to check my Ray cluster configuration for inference-specific issues.

**Acceptance Criteria:**
- 4.3.1 The system SHALL accept Ray cluster YAML configuration and analyze it for resource allocation, placement group configuration, and deployment replica settings.
- 4.3.2 The system SHALL flag imbalanced GPU allocation across Ray worker nodes.
- 4.3.3 The system SHALL flag missing `ray_actor_options` GPU resource declarations in Ray Serve deployment definitions.

### REQ-4.4: Infrastructure Advisor Output

**User Story:** As an ML platform engineer, I want infrastructure analysis results to be actionable, structured, and easy to incorporate into code review or CI checks.

**Acceptance Criteria:**
- 4.4.1 Every infrastructure finding SHALL include: severity (info/warning/critical), the file and line range where the issue was found, a plain-language description, and a recommended remediation.
- 4.4.2 The system SHALL provide a CLI command that exits with a non-zero code WHEN critical findings are present, enabling CI/CD gate integration.
- 4.4.3 The system SHALL support outputting findings as JSON for machine consumption and as a human-readable text/markdown report.
- 4.4.4 The system SHALL support a `--threshold` flag to configure which severity levels cause a non-zero exit code.

---

## Phase 5 — AI Copilot

### Goal

Enable conversational, natural language troubleshooting and optimization guidance grounded in the user's actual deployment metrics and configurations.

### REQ-5.1: Conversational Interface

**User Story:** As an ML infrastructure engineer, I want to ask questions in plain English about my deployments and get informed answers so I don't have to manually correlate data across dashboards.

**Acceptance Criteria:**
- 5.1.1 The system SHALL provide a chat interface (web UI and CLI) for natural language queries about inference deployments.
- 5.1.2 The system SHALL answer questions about current metric values, detected issues, and recommendations using live data from the InferSight data store.
- 5.1.3 The system SHALL answer questions about historical trends using stored metric history.
- 5.1.4 Responses SHALL cite the specific metrics and data points used to generate the answer.
- 5.1.5 The system SHALL distinguish between factual answers (grounded in collected data) and general guidance (from knowledge base), labeling each clearly.

### REQ-5.2: Supported Query Types

**User Story:** As an ML infrastructure engineer, I want the copilot to answer the most common operational questions without me having to look anything up manually.

**Acceptance Criteria:**
- 5.2.1 The system SHALL answer latency root-cause questions (e.g., "Why is my TTFT increasing?") by correlating metric changes with detected issues.
- 5.2.2 The system SHALL answer cost optimization questions (e.g., "How can I reduce cost per token?") by referencing utilization data and applicable recommendations.
- 5.2.3 The system SHALL answer comparison questions (e.g., "Which deployment has the best throughput?") by querying and ranking metric data.
- 5.2.4 The system SHALL answer optimization priority questions (e.g., "Which optimization gives the biggest improvement?") by ranking open recommendations by estimated impact.
- 5.2.5 The system SHALL answer configuration questions (e.g., "What is my current batch size setting?") by reading from collected configuration metadata.

### REQ-5.3: LLM Backend Configuration

**User Story:** As an operator deploying InferSight, I want to configure which LLM powers the copilot so I can use a model that fits my privacy and cost requirements.

**Acceptance Criteria:**
- 5.3.1 The system SHALL support configuring the copilot to use any OpenAI-compatible API endpoint (OpenAI, Azure OpenAI, locally-hosted models via vLLM or Ollama).
- 5.3.2 The system SHALL support configuring the copilot to use Anthropic Claude via their API.
- 5.3.3 API credentials SHALL be configurable via environment variables or a secrets file and SHALL NOT be stored in plaintext in configuration files committed to version control.
- 5.3.4 The system SHALL function in a degraded mode (no copilot) when no LLM backend is configured, without crashing other phases.

### REQ-5.4: Copilot Context and Safety

**User Story:** As an operator, I want the copilot to stay grounded in InferSight's data and avoid hallucinating metrics or recommendations.

**Acceptance Criteria:**
- 5.4.1 The system SHALL only surface metric values retrieved from the InferSight data store, never fabricate numerical data.
- 5.4.2 WHEN data is unavailable for a query, the system SHALL state that data is unavailable rather than estimating.
- 5.4.3 The system SHALL not execute infrastructure changes directly; it SHALL only provide recommendations and instructions.
- 5.4.4 The system SHALL log all copilot queries and responses for audit and debugging purposes.

---

## Phase 6 — Plugin and Extensibility Architecture

### REQ-6.1: Collector Plugin Interface

**User Story:** As a developer, I want to add support for a new inference engine without modifying InferSight's core code.

**Acceptance Criteria:**
- 6.1.1 The system SHALL define a documented `CollectorPlugin` interface with methods for: engine identification, health check, and metric collection returning the canonical schema.
- 6.1.2 Plugins SHALL be loadable from a configurable plugin directory at startup without recompilation.
- 6.1.3 A failing plugin SHALL not affect the operation of other plugins or core InferSight components.
- 6.1.4 The system SHALL provide a reference collector plugin implementation and a developer guide.

### REQ-6.2: Analyzer Plugin Interface

**User Story:** As a developer, I want to add custom analysis rules for organization-specific performance heuristics.

**Acceptance Criteria:**
- 6.2.1 The system SHALL define a documented `AnalyzerPlugin` interface with methods for: analyzer identification, input metric requirements, and issue detection returning the canonical issue schema.
- 6.2.2 Custom analyzers SHALL be registerable alongside built-in analyzers.
- 6.2.3 Custom analyzer findings SHALL appear in the API and UI alongside built-in findings, labeled with the plugin name.

### REQ-6.3: Recommendation Plugin Interface

**User Story:** As a developer, I want to add custom recommendation logic that accounts for our internal deployment patterns.

**Acceptance Criteria:**
- 6.3.1 The system SHALL define a documented `RecommenderPlugin` interface that takes issue findings and returns recommendations in the canonical recommendation schema.
- 6.3.2 Custom recommendations SHALL appear alongside built-in recommendations and be labeled with the plugin source.

### REQ-6.4: Notification and Alerting Integration

**User Story:** As an ML infrastructure engineer, I want InferSight alerts to appear in my existing alerting channels (PagerDuty, Slack, email) without running a separate pipeline.

**Acceptance Criteria:**
- 6.4.1 The system SHALL support sending issue alerts to Slack via webhook.
- 6.4.2 The system SHALL support sending issue alerts to PagerDuty via Events API v2.
- 6.4.3 The system SHALL support sending issue alerts via email (SMTP).
- 6.4.4 Alert routing rules SHALL be configurable: severity thresholds, deployment filters, and deduplication windows.
- 6.4.5 The system SHALL define a `NotificationPlugin` interface for adding additional alert destinations.

---

## Phase 7 — Cross-Cutting Requirements

### REQ-7.1: Deployment and Operations

**Acceptance Criteria:**
- 7.1.1 InferSight SHALL be deployable as a single binary or Docker container for single-node use.
- 7.1.2 InferSight SHALL provide a Helm chart for Kubernetes deployment.
- 7.1.3 All configuration SHALL be manageable via a single YAML config file and environment variable overrides.
- 7.1.4 The system SHALL expose a `/health` and `/ready` HTTP endpoint for liveness and readiness probing.
- 7.1.5 The system SHALL produce structured (JSON) logs with configurable log levels.

### REQ-7.2: Security

**Acceptance Criteria:**
- 7.2.1 The web UI and REST API SHALL support optional API key authentication.
- 7.2.2 The web UI SHALL support optional OIDC-based authentication.
- 7.2.3 All external HTTP connections (to inference engine endpoints, LLM APIs) SHALL use TLS by default with certificate verification enabled.
- 7.2.4 Sensitive configuration values (API keys, credentials) SHALL not appear in log output.

### REQ-7.3: Performance and Reliability

**Acceptance Criteria:**
- 7.3.1 The metric collection loop SHALL not add more than 100ms of overhead to the inference engines it monitors, measured as the duration of the scrape request.
- 7.3.2 The InferSight server process SHALL use less than 2 GB RAM in a typical deployment monitoring up to 50 engine replicas.
- 7.3.3 The REST API SHALL respond to analysis and recommendation queries within 2 seconds under normal load.
- 7.3.4 The system SHALL tolerate a monitored engine being unavailable without losing data from other engines.

### REQ-7.4: Documentation

**Acceptance Criteria:**
- 7.4.1 The project SHALL provide a quickstart guide covering installation, connecting to a first inference engine, and viewing the dashboard.
- 7.4.2 The project SHALL provide API reference documentation (auto-generated from the OpenAPI spec).
- 7.4.3 The project SHALL provide a plugin development guide for all three plugin interfaces (collector, analyzer, recommender).
- 7.4.4 The project SHALL provide engine-specific integration guides for each supported engine.

---

## Supported Integrations Summary

| Category | Supported Systems |
|---|---|
| Inference Engines | vLLM, SGLang, HuggingFace TGI, NVIDIA Triton, KServe, Ray Serve |
| Cloud / Orchestration | Amazon SageMaker HyperPod, Kubernetes (raw manifests + Helm), Terraform, Ray |
| Metric Backends | Prometheus, InfluxDB, embedded (single-node) |
| Visualization | Grafana (pre-built dashboards), built-in web UI |
| Alerting | Slack, PagerDuty, Email (SMTP) |
| LLM Backends (Copilot) | OpenAI, Azure OpenAI, Anthropic Claude, any OpenAI-compatible endpoint |

---

## Requirements Traceability

| Phase | Requirements |
|---|---|
| Phase 1 — Observability | REQ-1.1 through REQ-1.5 |
| Phase 2 — Analysis | REQ-2.1 through REQ-2.8 |
| Phase 3 — Recommendations | REQ-3.1 through REQ-3.4 |
| Phase 4 — Infrastructure Advisor | REQ-4.1 through REQ-4.4 |
| Phase 5 — AI Copilot | REQ-5.1 through REQ-5.4 |
| Phase 6 — Extensibility | REQ-6.1 through REQ-6.4 |
| Phase 7 — Cross-Cutting | REQ-7.1 through REQ-7.4 |
