"""Dynamic discovery and loading of InferSight plugins."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Any

from infersight.config import InferSightConfig
from infersight.plugins.base import (
    AnalyzerPlugin,
    CollectorPlugin,
    NotificationPlugin,
    RecommenderPlugin,
)

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Discover and instantiate concrete plugins from Python source directories.

    Invalid plugin modules and constructors are isolated: their failures are
    logged, and discovery continues with the remaining modules.
    """

    def __init__(self, plugin_dirs: Iterable[str] = ()) -> None:
        self.collectors: list[CollectorPlugin] = []
        self.analyzers: list[AnalyzerPlugin] = []
        self.recommenders: list[RecommenderPlugin] = []
        self.notifiers: list[NotificationPlugin] = []
        self.load(plugin_dirs)

    @classmethod
    def from_config(cls, config: InferSightConfig) -> PluginRegistry:
        """Build a registry using plugin directories in application configuration."""
        return cls(config.plugins.plugin_dirs)

    def load(self, plugin_dirs: Iterable[str]) -> None:
        """Discover plugins from directories, appending successfully loaded instances."""
        for directory in plugin_dirs:
            directory_path = Path(directory).expanduser()
            if not directory_path.is_dir():
                logger.warning("Plugin directory does not exist: %s", directory_path)
                continue
            for module_path in directory_path.rglob("*.py"):
                if module_path.name == "__init__.py":
                    continue
                module = self._load_module(module_path)
                if module is not None:
                    self._load_module_plugins(module, module_path)

    def _load_module(self, module_path: Path) -> ModuleType | None:
        module_name = self._module_name(module_path)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            logger.warning("Could not create an import specification for plugin: %s", module_path)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            logger.exception("Could not import plugin module: %s", module_path)
            return None
        return module

    def _load_module_plugins(self, module: ModuleType, module_path: Path) -> None:
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate.__module__ != module.__name__ or inspect.isabstract(candidate):
                continue
            self._register(candidate, module_path)

    def _register(self, candidate: type[Any], module_path: Path) -> None:
        try:
            if issubclass(candidate, CollectorPlugin):
                self.collectors.append(candidate())
            elif issubclass(candidate, AnalyzerPlugin):
                self.analyzers.append(candidate())
            elif issubclass(candidate, RecommenderPlugin):
                self.recommenders.append(candidate())
            elif issubclass(candidate, NotificationPlugin):
                self.notifiers.append(candidate())
        except Exception:
            logger.exception(
                "Could not initialize plugin %s from %s", candidate.__name__, module_path
            )

    @staticmethod
    def _module_name(module_path: Path) -> str:
        digest = hashlib.sha256(str(module_path.resolve()).encode()).hexdigest()
        return f"infersight_external_plugin_{digest}"
