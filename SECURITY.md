# Security Policy

## Supported Versions

InferSight is currently pre-release. Security fixes are applied to the `main` branch and included in the next release.

| Version | Supported |
|---------|-----------|
| `main` (pre-release) | ✅ Active |
| Older snapshots | ❌ Not supported |

Once stable releases begin (v0.1+), this table will be updated to reflect the supported version window.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please use [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) to report issues confidentially:

1. Go to the [InferSight Security Advisories](https://github.com/infersight/InferSight/security/advisories/new) page.
2. Click **Report a vulnerability**.
3. Fill in the details: affected component, steps to reproduce, potential impact, and any suggested fix.

### Response SLA

| Milestone | Target |
|-----------|--------|
| Acknowledgment | 48 hours |
| Initial triage and severity assessment | 5 business days |
| Fix or mitigation plan communicated | 30 days |
| Public disclosure | 90 days after report (coordinated with reporter) |

We follow responsible disclosure. If you need to disclose sooner for any reason, please let us know in your report.

---

## Security Considerations

InferSight is a read-only observability and analysis tool. It does not serve models or execute inference workloads. Key security properties:

**No credential logging** — InferSight never logs API keys, tokens, or secrets passed through configuration. Configuration values are referenced by key name in logs, not by value.

**Read-only metric collection** — Collector plugins use read-only HTTP endpoints (metrics, health, stats). They do not send write requests to inference engines.

**TLS recommended** — When collecting metrics from remote endpoints in production, configure TLS on both the InferSight server and the target engine endpoints. Plaintext HTTP is supported only for local development.

**AI Copilot data handling** — The AI Copilot sends anonymized metric snapshots to the configured LLM provider (via LiteLLM). Raw prompt content and model weights are never transmitted. Review your LLM provider's data handling policy before enabling the copilot in sensitive environments.

**Infrastructure Advisor** — Static analysis of Kubernetes, Helm, Terraform, and Ray configurations is performed locally. Config files are never uploaded to external services.

**Authentication** — The InferSight REST API does not include authentication by default in early releases. Do not expose the API port on untrusted networks without adding an authentication proxy (e.g., OAuth2 Proxy, API gateway).

---

## Out of Scope

The following are considered out of scope for security reports:

- Vulnerabilities in inference engines themselves (vLLM, SGLang, TGI, etc.) — report those to the respective upstream projects.
- Issues requiring physical access to the host machine.
- Social engineering attacks targeting maintainers or contributors.
- Theoretical vulnerabilities with no practical exploit path.
- Vulnerabilities in dependencies that have already been publicly disclosed and are awaiting an upstream fix.

---

## Security-Related Configuration

When deploying InferSight, consider the following hardening steps:

- Run InferSight as a non-root user.
- Bind the API server to `localhost` unless external access is required.
- Use a reverse proxy (nginx, Caddy) with TLS termination in front of the API and dashboard.
- Rotate any API keys used for the AI Copilot on a regular schedule.
- Review collector plugin permissions — plugins only need read access to engine metric endpoints.

---

*This security policy is reviewed and updated with each release.*
