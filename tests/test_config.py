"""Tests for the InferSight config model."""

import os
import tempfile

import pytest
import yaml

from infersight.config import InferSightConfig, load_config


def test_defaults() -> None:
    """Config loads with all defaults when no file or env vars present."""
    config = InferSightConfig()
    assert config.server.port == 8000
    assert config.server.log_level == "info"
    assert config.collection.interval_seconds == 15
    assert config.storage.backend == "sqlite"
    assert config.auth.api_key_enabled is False
    assert config.copilot.enabled is False


def test_secrets_excluded_from_dump() -> None:
    """SecretStr fields must not appear as plaintext in model_dump()."""
    os.environ["INFERSIGHT_AUTH__API_KEY"] = "super-secret"
    try:
        config = InferSightConfig()
        dump = config.model_dump()
        # The value should be a SecretStr, not a plain string
        assert dump["auth"]["api_key"] != "super-secret"
    finally:
        del os.environ["INFERSIGHT_AUTH__API_KEY"]


def test_yaml_file_loading(tmp_path: pytest.TempPathFactory) -> None:
    """Config values are loaded from a YAML file."""
    config_file = tmp_path / "infersight.yaml"  # type: ignore[operator]
    config_data = {
        "server": {"port": 9090, "log_level": "debug"},
        "collection": {"interval_seconds": 30},
    }
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))
    assert config.server.port == 9090
    assert config.server.log_level == "debug"
    assert config.collection.interval_seconds == 30


def test_env_override_takes_precedence(tmp_path: pytest.TempPathFactory) -> None:
    """Environment variables override YAML file values."""
    config_file = tmp_path / "infersight.yaml"  # type: ignore[operator]
    config_file.write_text(yaml.dump({"server": {"port": 9090}}))

    os.environ["INFERSIGHT_SERVER__PORT"] = "7777"
    try:
        config = load_config(str(config_file))
        assert config.server.port == 7777
    finally:
        del os.environ["INFERSIGHT_SERVER__PORT"]


def test_missing_yaml_uses_defaults() -> None:
    """Missing YAML file does not raise; defaults apply."""
    config = load_config("/nonexistent/path/infersight.yaml")
    assert config.server.port == 8000
