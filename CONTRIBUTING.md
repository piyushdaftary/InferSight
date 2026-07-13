# Contributing to InferSight

Thanks for your interest in contributing. InferSight is built to be extended — the plugin architecture means you can add a new inference engine collector or custom analyzer without touching core code. Every contribution helps the ML infrastructure community run LLMs more efficiently.

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it. Report unacceptable behavior to the maintainers via GitHub's private reporting.

---

## Ways to Contribute

**Bug reports** — open a GitHub issue using the bug report template. Include your InferSight version, Python version, engine type, and a minimal reproducer.

**Feature requests** — open a GitHub issue using the feature request template. Describe the use case before proposing a solution.

**Collector plugins** — add support for a new inference engine by implementing the `CollectorPlugin` ABC (see below).

**Analyzer plugins** — add a new issue detector by implementing the `AnalyzerPlugin` ABC (see below).

**Documentation** — fix typos, improve examples, translate docs, or add tutorials.

**Tests** — improve coverage, add property-based tests, or write integration fixtures.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+ (for the React dashboard in `ui/`)
- Git

### Steps

```bash
# 1. Fork and clone
git clone https://github.com/<your-fork>/InferSight.git
cd InferSight

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Install pre-commit hooks
pre-commit install

# 5. Install frontend dependencies (when ui/ exists)
# npm install --prefix ui

# 6. Run the test suite
pytest
```

All tests must pass before opening a pull request.

---

## Project Structure

```text
InferSight/
├── infersight/               # Core Python package
│   ├── collectors/           # CollectorPlugin implementations
│   │   ├── base.py           # CollectorPlugin ABC
│   │   ├── vllm.py
│   │   └── sglang.py
│   ├── analyzers/            # AnalyzerPlugin implementations
│   │   ├── base.py           # AnalyzerPlugin ABC
│   │   └── gpu_utilization.py
│   ├── recommenders/         # Recommendation engine
│   ├── infra/                # Infrastructure Advisor
│   ├── api/                  # FastAPI routes
│   ├── copilot/              # AI Copilot (LiteLLM)
│   └── storage/              # Storage backends
├── ui/                       # React 18 dashboard
├── tests/                    # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/                     # Specification documents
├── pyproject.toml
└── pre-commit-config.yaml
```

---

## Coding Standards

- **Formatter / linter**: `ruff` (configured in `pyproject.toml`). Run `ruff check . --fix` before committing.
- **Type checking**: `mypy --strict`. All public functions must have fully typed signatures.
- **Docstrings**: Google-style docstrings on all public classes and functions.
- **No `Any` unless unavoidable**: use `TypeVar`, `Generic`, or `Protocol` instead.
- **Tests required**: every new module needs a corresponding test file under `tests/`.

Pre-commit runs `ruff`, `mypy`, and `pytest` automatically on staged files.

---

## Writing a CollectorPlugin

A collector pulls (or receives) metrics from one inference engine and normalizes them into InferSight's canonical `EngineSnapshot` schema.

### Step 1 — Subclass `CollectorPlugin`

```python
# infersight/collectors/my_engine.py
from infersight.collectors.base import CollectorPlugin
from infersight.schema import EngineSnapshot, CollectorConfig


class MyEngineCollector(CollectorPlugin):
    """Collector for MyEngine inference server."""

    engine_id: str = "my_engine"
```

### Step 2 — Implement the three required methods

```python
    def validate_config(self, config: CollectorConfig) -> None:
        """Raise ValueError if required config keys are missing."""
        if not config.endpoint:
            raise ValueError("endpoint is required for MyEngineCollector")

    async def collect(self, config: CollectorConfig) -> EngineSnapshot:
        """Fetch metrics and return a canonical EngineSnapshot."""
        raw = await self._fetch_metrics(config.endpoint)
        return EngineSnapshot(
            engine=self.engine_id,
            timestamp=raw["timestamp"],
            gpu_utilization_pct=raw["gpu_util"],
            kv_cache_hit_rate=raw["cache_hit"],
            # ... map remaining fields
        )

    def health_check(self, config: CollectorConfig) -> bool:
        """Return True if the engine endpoint is reachable."""
        try:
            response = httpx.get(f"{config.endpoint}/health", timeout=2)
            return response.status_code == 200
        except httpx.RequestError:
            return False
```

### Step 3 — Register the plugin

Add an entry point in `pyproject.toml`:

```toml
[project.entry-points."infersight.collectors"]
my_engine = "infersight.collectors.my_engine:MyEngineCollector"
```

### Step 4 — Write tests

```python
# tests/unit/collectors/test_my_engine.py
import pytest
from infersight.collectors.my_engine import MyEngineCollector

def test_validate_config_raises_without_endpoint():
    collector = MyEngineCollector()
    with pytest.raises(ValueError, match="endpoint"):
        collector.validate_config(CollectorConfig(endpoint=""))
```

---

## Writing an AnalyzerPlugin

An analyzer receives an `EngineSnapshot` and emits zero or more `Issue` objects when a problem is detected.

### Step 1 — Subclass `AnalyzerPlugin`

```python
# infersight/analyzers/my_detector.py
from infersight.analyzers.base import AnalyzerPlugin
from infersight.schema import EngineSnapshot, Issue, Severity


class MyDetector(AnalyzerPlugin):
    """Detects when something specific is wrong."""

    detector_id: str = "my_detector"
    default_threshold: float = 0.5
```

### Step 2 — Implement the three required methods

```python
    def configure(self, threshold: float | None = None) -> None:
        """Accept optional user-supplied threshold override."""
        self.threshold = threshold or self.default_threshold

    def analyze(self, snapshot: EngineSnapshot) -> list[Issue]:
        """Return a list of Issues found in the snapshot."""
        issues: list[Issue] = []
        if snapshot.some_metric < self.threshold:
            issues.append(Issue(
                detector=self.detector_id,
                severity=Severity.WARNING,
                metric="some_metric",
                observed=snapshot.some_metric,
                threshold=self.threshold,
                message="some_metric is below threshold",
            ))
        return issues

    def explain(self, issue: Issue) -> str:
        """Return a human-readable explanation for an Issue."""
        return (
            f"some_metric is {issue.observed:.1%}, below the "
            f"{issue.threshold:.1%} threshold. Consider tuning X."
        )
```

### Step 3 — Write tests with fixtures

```python
# tests/unit/analyzers/test_my_detector.py
import pytest
from infersight.analyzers.my_detector import MyDetector
from tests.fixtures import make_snapshot

def test_no_issue_above_threshold():
    detector = MyDetector()
    detector.configure(threshold=0.5)
    snapshot = make_snapshot(some_metric=0.8)
    assert detector.analyze(snapshot) == []

def test_issue_below_threshold():
    detector = MyDetector()
    detector.configure(threshold=0.5)
    snapshot = make_snapshot(some_metric=0.2)
    issues = detector.analyze(snapshot)
    assert len(issues) == 1
    assert issues[0].detector == "my_detector"
```

---

## Pull Request Process

### Branch naming

```
feat/<short-description>       # new feature
fix/<short-description>        # bug fix
docs/<short-description>       # documentation only
test/<short-description>       # tests only
chore/<short-description>      # tooling, deps, CI
```

### Checklist before opening a PR

- [ ] `ruff check . --fix` passes with no remaining errors
- [ ] `mypy --strict` passes
- [ ] `pytest` passes (all existing + new tests)
- [ ] New public APIs have docstrings and type annotations
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] PR description explains **what** changed and **why**

### Review SLA

Maintainers aim to provide initial feedback within **2 business days**. If you haven't heard back in 3 days, ping the thread.

---

## Commit Message Convention

InferSight uses [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<optional scope>): <short summary>

<optional body>

<optional footer>
```

**Types**: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `ci`

**Examples**:

```
feat(collectors): add SGLang collector plugin
fix(analyzer): correct KV cache hit rate threshold check
docs(contributing): add AnalyzerPlugin authoring guide
test(recommender): add property tests for impact ranking
chore(deps): bump httpx to 0.27.0
```

Breaking changes: append `!` after the type and add a `BREAKING CHANGE:` footer.

---

## Reporting Bugs

Open a [GitHub issue](https://github.com/infersight/InferSight/issues/new?template=bug_report.md) and include:

1. InferSight version (`infersight --version`)
2. Python version and OS
3. Inference engine and version
4. Minimal config that reproduces the issue
5. Full error traceback

For security vulnerabilities, **do not open a public issue** — see [SECURITY.md](SECURITY.md).

---

## Getting Help

- **GitHub Discussions** — questions, ideas, show-and-tell
- **GitHub Issues** — confirmed bugs and feature requests
- **Pull Requests** — code, docs, and tests

When asking for help, include your setup details and what you've already tried.
