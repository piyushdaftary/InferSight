"""Tests for external plugin discovery."""

from pathlib import Path

from infersight.config import InferSightConfig
from infersight.plugins.registry import PluginRegistry


def write_plugin(directory: Path, name: str, source: str) -> None:
    """Write a plugin fixture module to the supplied temporary directory."""
    (directory / f"{name}.py").write_text(source)


def test_registry_discovers_each_plugin_type(tmp_path: Path) -> None:
    """All concrete plugin interfaces are discovered from configured directories."""
    write_plugin(
        tmp_path,
        "plugins",
        """
from infersight.plugins.base import AnalyzerPlugin, CollectorPlugin, NotificationPlugin, RecommenderPlugin

class Collector(CollectorPlugin):
    @property
    def engine_name(self): return "test"
    async def health_check(self): return True
    async def collect(self): raise NotImplementedError

class Analyzer(AnalyzerPlugin):
    @property
    def analyzer_name(self): return "test"
    @property
    def required_metrics(self): return []
    async def analyze(self, metrics): return []

class Recommender(RecommenderPlugin):
    @property
    def recommender_name(self): return "test"
    @property
    def handles_issue_types(self): return []
    async def recommend(self, issue): return []

class Notifier(NotificationPlugin):
    @property
    def channel_name(self): return "test"
    async def notify(self, issue): pass
""",
    )

    registry = PluginRegistry([str(tmp_path)])

    assert [plugin.engine_name for plugin in registry.collectors] == ["test"]
    assert [plugin.analyzer_name for plugin in registry.analyzers] == ["test"]
    assert [plugin.recommender_name for plugin in registry.recommenders] == ["test"]
    assert [plugin.channel_name for plugin in registry.notifiers] == ["test"]


def test_registry_isolates_broken_plugin_constructors(tmp_path: Path) -> None:
    """A broken constructor is skipped without preventing other plugin discovery."""
    write_plugin(
        tmp_path,
        "broken",
        """
from infersight.plugins.base import CollectorPlugin

class Broken(CollectorPlugin):
    def __init__(self): raise RuntimeError("broken")
    @property
    def engine_name(self): return "broken"
    async def health_check(self): return True
    async def collect(self): raise NotImplementedError
""",
    )
    write_plugin(
        tmp_path,
        "working",
        """
from infersight.plugins.base import CollectorPlugin

class Working(CollectorPlugin):
    @property
    def engine_name(self): return "working"
    async def health_check(self): return True
    async def collect(self): raise NotImplementedError
""",
    )

    registry = PluginRegistry([str(tmp_path)])

    assert [plugin.engine_name for plugin in registry.collectors] == ["working"]


def test_registry_loads_directories_from_configuration(tmp_path: Path) -> None:
    """The configuration helper reads the nested plugin directory setting."""
    registry = PluginRegistry.from_config(
        InferSightConfig(plugins={"plugin_dirs": [str(tmp_path)]})
    )

    assert registry.collectors == []
