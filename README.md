# InferSight

> The open-source intelligence layer for AI inference infrastructure.

🚧 **Early Development** — Architecture complete, implementation underway.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

Serving tells you what is running.
InferSight tells you **why it is slow** and **how to improve it**.

InferSight collects telemetry from LLM inference systems, identifies performance bottlenecks, recommends optimizations, validates deployment configurations, and provides an AI copilot for troubleshooting.

InferSight does not serve models — it helps teams operate inference systems efficiently.

---

## The Pipeline

```text
  Collect        Analyze        Recommend       Validate        Explain
     │              │               │               │              │
     ▼              ▼               ▼               ▼              ▼
vLLM/SGLang   Detect issues   Ranked config   K8s/Helm/TF/   AI Copilot
TGI/Triton    with evidence   changes with    Ray static     grounded in
KServe/Ray    & thresholds    impact ranges   analysis       inference
                                                             telemetry
```

---

## Example

```bash
$ infersight analyze --engine vllm --endpoint localhost:8000
```

```
Health Score: 81/100

Issues Detected
  ⚠  GPU utilization:   38%   (threshold: 60%)
  ⚠  KV cache hit rate: 14%   (prefix caching disabled)

Recommendations  (ranked by estimated impact)
  1. Enable prefix caching           --enable-prefix-caching
  2. Increase max_num_batched_tokens  --max-num-batched-tokens 4096
  3. Tune scheduler policy           --scheduling-policy fcfs

Estimated Improvement
  TTFT        -24%
  Throughput  +18%
  Cost        -11%
```

---

## Dashboard

> 🚧 Screenshot coming soon — dashboard implementation is in progress.

---

## Who Is This For?

- ML Platform Engineers managing inference fleets at scale
- AI Infrastructure Teams deploying LLMs in production
- MLOps Engineers optimizing cost and latency
- Kubernetes Operators running GPU workloads
- GPU Cluster Operators maximizing hardware utilization

---

## Features

| Phase | Capability | Status |
|-------|-----------|--------|
| 📊 Observability | Unified metrics from 7 engines; Prometheus & Grafana export | ⏳ Planned |
| 🔍 Analysis | 7 automated issue detectors with configurable thresholds | ⏳ Planned |
| 💡 Recommendations | Ranked guidance with impact estimates & engine-native config snippets | ⏳ Planned |
| 🏗️ Infra Advisor | Static analysis of K8s, Helm, Terraform, Ray configs — CI/CD ready | ⏳ Planned |
| 🤖 AI Copilot | Conversational troubleshooting grounded in inference telemetry and operational context | ⏳ Planned |

[Full requirements →](docs/requirements.md)

---

## Development Status

| Component | Status |
|-----------|--------|
| Specification | ✅ Complete |
| Architecture | ✅ Complete |
| Plugin Framework | ⏳ Planned |
| vLLM Collector | ⏳ Planned |
| SGLang Collector | ⏳ Planned |
| Analyzer Engine (7 detectors) | ⏳ Planned |
| Recommendation Engine | ⏳ Planned |
| Infrastructure Advisor | ⏳ Planned |
| React Dashboard | ⏳ Planned |
| AI Copilot | ⏳ Planned |

InferSight is in active development. The spec and architecture are complete; implementation begins with Phase 0 scaffolding. See [tasks.md](docs/tasks.md) for the full implementation plan.

---

## Supported Engines

| Engine | Status |
|--------|--------|
| [vLLM](https://github.com/vllm-project/vllm) | ⏳ Planned |
| [SGLang](https://github.com/sgl-project/sglang) | ⏳ Planned |
| [HuggingFace TGI](https://github.com/huggingface/text-generation-inference) | ⏳ Planned |
| [NVIDIA Triton](https://github.com/triton-inference-server/server) | ⏳ Planned |
| [KServe](https://github.com/kserve/kserve) | ⏳ Planned |
| [Amazon SageMaker HyperPod](https://aws.amazon.com/sagemaker/hyperpod/) | ⏳ Planned |
| [Ray Serve](https://docs.ray.io/en/latest/serve/index.html) | ⏳ Planned |

Want to add an engine? [Write a collector plugin →](CONTRIBUTING.md)

---

## Architecture

```text
               Inference Engine Fleet
    ┌────────┬─────────┬──────┬────────┬────────┐
    │  vLLM  │ SGLang  │ TGI  │ Triton │ KServe │
    └────────┴─────────┴──────┴────────┴────────┘
                          │
                  Collector Plugins
                  (pull or push)
                          │
                          ▼
                 Canonical Metric Schema
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        Analyzer Engine         Infra Advisor
        (7 detectors)           (K8s/Helm/TF/Ray)
              │
              ▼
       Recommendation Engine
       (ranked by estimated impact)
              │
     ┌────────┴──────────────┐
     ▼                       ▼
  Storage              Notification Engine
  (SQLite /            (issues + recommendations)
  Prometheus/                  │
  InfluxDB)            ┌───────┴───────┐
     │                 ▼               ▼
     ▼               Slack         PagerDuty
  REST API +                        Email
  WebSocket
     │
  ┌──┴────────────────────┐
  ▼                       ▼
Dashboard             AI Copilot
(React 18)            (LiteLLM)
```

[Full design doc →](docs/design.md)

---

## Quick Start

> InferSight is not yet installable — implementation is in progress.
> The steps below reflect the intended UX once Phase 1 ships.

```bash
pip install infersight
```

```yaml
# infersight.yaml
server:
  port: 8000

deployments:
  - id: my-vllm
    engine: vllm
    endpoint: http://localhost:8000
```

```bash
infersight serve --config infersight.yaml
# Dashboard: http://localhost:8000
# API docs:  http://localhost:8000/docs
```

---

## Future Integrations

Community contributions welcome:

- [ ] llama.cpp
- [ ] TensorRT-LLM
- [ ] OpenShift AI
- [ ] Amazon EKS managed auth
- [ ] Google Kubernetes Engine (GKE)
- [ ] Vertex AI
- [ ] Azure Machine Learning

---

## Documentation

| Document | Description |
|----------|-------------|
| [Requirements](docs/requirements.md) | Product requirements with acceptance criteria |
| [Design](docs/design.md) | Architecture, schemas, plugin ABCs, API reference |
| [Tasks](docs/tasks.md) | 76-task implementation plan across 12 phases |
| [Roadmap](ROADMAP.md) | Phase timeline and community wishlist |
| [Contributing](CONTRIBUTING.md) | How to contribute code, plugins, and docs |
| [Changelog](CHANGELOG.md) | Release history |

---

## Contributing

InferSight is built to be extended. The plugin architecture makes it straightforward to add new inference engine collectors, custom analyzers, and recommendation logic without touching core code.

See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

*Built for the ML infrastructure community. Inspired by the operational challenges of running LLMs at scale.*
