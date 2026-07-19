"""InferSight configuration model.

Loaded from a YAML file (default: infersight.yaml) with full override
support via environment variables prefixed with INFERSIGHT_.

Nested keys use double-underscore: INFERSIGHT_SERVER__PORT=9000
Secrets must be provided via environment variables, never in the YAML file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ServerConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = Field(default="info", pattern="^(debug|info|warning|error)$")
    log_format: str = Field(default="json", pattern="^(json|console)$")
    static_dir: str = ""


class CollectionConfig(BaseSettings):
    interval_seconds: int = Field(default=15, ge=1)
    timeout_seconds: int = Field(default=10, ge=1)
    retry_max_attempts: int = Field(default=3, ge=0)
    retry_backoff_seconds: int = Field(default=5, ge=1)


class SqliteConfig(BaseSettings):
    path: str = "~/.infersight/infersight.db"
    retention_days: int = Field(default=30, ge=1)
    wal_mode: bool = True


class PrometheusStorageConfig(BaseSettings):
    remote_write_url: str = ""
    remote_read_url: str = ""


class InfluxConfig(BaseSettings):
    url: str = ""
    token: SecretStr = SecretStr("")
    org: str = ""
    bucket: str = "infersight"


class StorageConfig(BaseSettings):
    backend: str = Field(default="sqlite", pattern="^(sqlite|prometheus|influx)$")
    sqlite: SqliteConfig = Field(default_factory=SqliteConfig)
    prometheus: PrometheusStorageConfig = Field(default_factory=PrometheusStorageConfig)
    influx: InfluxConfig = Field(default_factory=InfluxConfig)


class OidcConfig(BaseSettings):
    issuer_url: str = ""
    client_id: str = ""
    client_secret: SecretStr = SecretStr("")
    redirect_uri: str = "http://localhost:8000/auth/callback"
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])


class AuthConfig(BaseSettings):
    api_key_enabled: bool = False
    api_key: SecretStr = SecretStr("")
    oidc_enabled: bool = False
    oidc: OidcConfig = Field(default_factory=OidcConfig)


class HttpConfig(BaseSettings):
    tls_verify: bool = True
    ca_bundle_path: str = ""
    proxy: str = ""


class DeploymentConfig(BaseSettings):
    id: str
    engine: str
    name: str = ""
    endpoint: str
    collection_mode: str = Field(default="pull", pattern="^(pull|push)$")
    interval_seconds: int = Field(default=15, ge=1)
    tls_verify: bool = True
    labels: dict[str, str] = Field(default_factory=dict)
    engine_config: dict[str, Any] = Field(default_factory=dict)


class DecodeBottleneckConfig(BaseSettings):
    enabled: bool = True
    throughput_threshold_tps: float = 300.0
    gpu_utilization_threshold_pct: float = 85.0
    window_seconds: int = 120


class BatchEfficiencyConfig(BaseSettings):
    enabled: bool = True
    fill_rate_threshold: float = 0.60
    window_seconds: int = 300


class GpuUnderutilizationConfig(BaseSettings):
    enabled: bool = True
    utilization_threshold_pct: float = 40.0
    window_seconds: int = 600


class MemoryFragmentationConfig(BaseSettings):
    enabled: bool = True


class QueueSaturationConfig(BaseSettings):
    enabled: bool = True
    depth_multiplier: float = 2.0
    window_seconds: int = 120


class KvCacheEffectivenessConfig(BaseSettings):
    enabled: bool = True
    hit_rate_threshold: float = 0.30


class SchedulingInefficiencyConfig(BaseSettings):
    enabled: bool = True


class AnalyzersConfig(BaseSettings):
    decode_bottleneck: DecodeBottleneckConfig = Field(
        default_factory=DecodeBottleneckConfig
    )
    batch_efficiency: BatchEfficiencyConfig = Field(
        default_factory=BatchEfficiencyConfig
    )
    gpu_underutilization: GpuUnderutilizationConfig = Field(
        default_factory=GpuUnderutilizationConfig
    )
    memory_fragmentation: MemoryFragmentationConfig = Field(
        default_factory=MemoryFragmentationConfig
    )
    queue_saturation: QueueSaturationConfig = Field(
        default_factory=QueueSaturationConfig
    )
    kv_cache_effectiveness: KvCacheEffectivenessConfig = Field(
        default_factory=KvCacheEffectivenessConfig
    )
    scheduling_inefficiency: SchedulingInefficiencyConfig = Field(
        default_factory=SchedulingInefficiencyConfig
    )


class SlackConfig(BaseSettings):
    enabled: bool = False
    webhook_url: SecretStr = SecretStr("")
    severity_threshold: str = "warning"


class PagerdutyConfig(BaseSettings):
    enabled: bool = False
    routing_key: SecretStr = SecretStr("")
    severity_threshold: str = "critical"


class EmailConfig(BaseSettings):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)
    severity_threshold: str = "warning"


class AlertingConfig(BaseSettings):
    deduplication_window_seconds: int = 300
    min_severity: str = "warning"
    slack: SlackConfig = Field(default_factory=SlackConfig)
    pagerduty: PagerdutyConfig = Field(default_factory=PagerdutyConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)


class CopilotConfig(BaseSettings):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: SecretStr = SecretStr("")
    base_url: str = ""
    azure_deployment: str = ""
    max_context_messages: int = 20
    max_tokens: int = 2048
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    audit_log_enabled: bool = True


class PrometheusExpositionConfig(BaseSettings):
    exposition_enabled: bool = True
    exposition_path: str = "/metrics"


class PluginsConfig(BaseSettings):
    plugin_dirs: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class InferSightConfig(BaseSettings):
    """Root configuration model for InferSight.

    Loaded from infersight.yaml, with environment variable overrides
    using the INFERSIGHT_ prefix and double-underscore nesting.
    Sensitive fields use SecretStr and are excluded from model_dump().
    """

    model_config = {  # type: ignore[assignment]
        "env_prefix": "INFERSIGHT_",
        "env_nested_delimiter": "__",
        "extra": "ignore",
    }

    server: ServerConfig = Field(default_factory=ServerConfig)
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    deployments: list[DeploymentConfig] = Field(default_factory=list)
    analyzers: AnalyzersConfig = Field(default_factory=AnalyzersConfig)
    alerting: AlertingConfig = Field(default_factory=AlertingConfig)
    copilot: CopilotConfig = Field(default_factory=CopilotConfig)
    prometheus: PrometheusExpositionConfig = Field(
        default_factory=PrometheusExpositionConfig
    )
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, _YamlConfigSource(settings_cls))


class _YamlConfigSource(PydanticBaseSettingsSource):
    """Load config values from a YAML file.

    The file path is resolved from the INFERSIGHT_CONFIG environment
    variable, falling back to ./infersight.yaml, then ~/infersight.yaml.
    Missing files are silently ignored — defaults apply.
    """

    def get_field_value(
        self, field: Any, field_name: str  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        import os

        candidates = [
            os.environ.get("INFERSIGHT_CONFIG", ""),
            "infersight.yaml",
            str(Path.home() / "infersight.yaml"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                with open(candidate) as fh:
                    data = yaml.safe_load(fh) or {}
                return data  # type: ignore[return-value]
        return {}


def load_config(config_path: str | None = None) -> InferSightConfig:
    """Load and return the InferSightConfig.

    Args:
        config_path: Optional explicit path to a YAML config file.
                     If provided, sets the INFERSIGHT_CONFIG env var
                     before initialising the settings model.

    Returns:
        A fully validated InferSightConfig instance.
    """
    import os

    if config_path:
        os.environ["INFERSIGHT_CONFIG"] = config_path
    return InferSightConfig()
