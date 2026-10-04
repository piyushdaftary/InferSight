# InferSight Roadmap

This roadmap reflects the current planning horizon. Dates are targets, not commitments. Community contributions can accelerate any phase.

---

## v0.1 — Foundation (Q3 2025)

**Goal**: Runnable skeleton with the first working collector and end-to-end analysis pipeline.

- [x] Phase 0: Project scaffolding (pyproject.toml, package structure, CI)
- [x] Phase 1: Core infrastructure (Config model ✅, StorageBackend ABC ✅, SQLite backend ✅)
- [x] Phase 2: Canonical metric schema (`EngineSnapshot`, `Issue`, `Recommendation`)
- [x] Phase 3: vLLM collector (pull-based, `/metrics` endpoint)
- [x] Phase 4: Analyzer detectors (7 implemented)
- [ ] Phase 5: CLI (`infersight analyze`) with JSON and human-readable output
- [x] Basic test suite (unit + mock end-to-end pipeline)

**Definition of done**: `infersight analyze --engine vllm --endpoint localhost:8000` produces a health score, issues, and recommendations.

---

## v0.2 — Observability (Q4 2025)

**Goal**: Multi-engine support and persistent metric storage.

- [x] SGLang collector
- [x] HuggingFace TGI collector
- [x] Analyzer detectors (7 implemented)
- [ ] Prometheus remote-write storage backend (SQLite default is implemented)
- [ ] Grafana dashboard JSON export
- [x] Scheduled collection with configurable intervals
- [x] Alerting: Slack and PagerDuty webhooks

---

## v0.3 — Recommendations & Infra Advisor (Q1 2026)

**Goal**: Ranked recommendations and static infrastructure analysis.

- [x] Recommendation engine with ranked engine-aware guidance
- [x] Engine-native configuration snippet generation
- [ ] Infrastructure Advisor: Kubernetes manifest analysis
- [ ] Infrastructure Advisor: Helm values analysis
- [ ] Infrastructure Advisor: Terraform plan analysis
- [ ] Infrastructure Advisor: Ray Serve config analysis
- [ ] CI/CD integration (`infersight validate --config k8s/deployment.yaml`)

---

## v0.4 — Dashboard (Q2 2026)

**Goal**: React dashboard with real-time metrics and drill-down views.

- [ ] FastAPI REST API + WebSocket for live metric streaming
- [ ] React 18 dashboard (fleet overview, per-engine detail, issue timeline)
- [ ] Recommendation panel with one-click config snippet copy
- [ ] Infra Advisor results view
- [ ] Dark mode and responsive layout
- [x] NVIDIA Triton collector
- [x] KServe collector

---

## v0.5 — AI Copilot (Q3 2026)

**Goal**: Conversational troubleshooting grounded in live metrics.

- [ ] LiteLLM integration (supports OpenAI, Anthropic, Bedrock, local models)
- [ ] Metric-grounded context injection (copilot sees your live data)
- [ ] Structured troubleshooting workflows
- [ ] Amazon SageMaker HyperPod collector
- [ ] Ray Serve collector
- [ ] Multi-tenant support (namespace isolation)
- [ ] Role-based access control (RBAC) for API and dashboard

---

## Beyond v1.0 — Community Wishlist

These are ideas from early discussions. No timeline yet — contributions welcome.

- **llama.cpp collector** — local inference on CPU/GPU
- **TensorRT-LLM collector** — NVIDIA optimized serving
- **OpenShift AI integration** — Red Hat ML platform support
- **GKE and EKS managed auth** — cloud-native Kubernetes auth flows
- **Vertex AI and Azure ML collectors** — managed cloud inference
- **Cost attribution** — per-request cost modeling across GPU instance types
- **Autoscaling recommendations** — HPA/KEDA tuning based on observed load patterns
- **Anomaly detection** — ML-based detection beyond threshold rules
- **Multi-cluster federation** — aggregate metrics across Kubernetes clusters
- **Plugin marketplace** — community-published collector and analyzer plugins
- **Notification routing** — fine-grained alert routing by engine, severity, team
- **Historical trending** — week-over-week regression detection

---

## Community Input

Have a feature you'd like to see? Open a [GitHub Discussion](https://github.com/infersight/InferSight/discussions) with the `roadmap` label. The most-requested community features are reviewed during each quarterly planning cycle.

If you want to build something from the wishlist, open an issue first to coordinate — we'll help you design the approach so it fits the architecture cleanly.

---

*Last updated: 2026. Roadmap is subject to change based on community feedback and contributor availability.*
