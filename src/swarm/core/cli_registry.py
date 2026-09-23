"""Dynamic registry for BaseCliAgent drivers.

REQ-889: Manages built-in protocol drivers and dynamically discovers custom
drivers generated or registered by the Support Agent.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from typing import Any

from swarm.core.cli_driver import (
    AgyCliAgent,
    BaseCliAgent,
    ClaudeCliAgent,
    CodexCliAgent,
    GeminiCliAgent,
    GrokCliAgent,
    HermesCliAgent,
    KiloCodeCliAgent,
    OpenCodeCliAgent,
    PiCliAgent,
    QwenCliAgent,
    find_cli_candidates,
    test_cli_binary,
)

logger = logging.getLogger(__name__)

BUILT_IN_DRIVERS: tuple[type[BaseCliAgent], ...] = (
    ClaudeCliAgent,
    GrokCliAgent,
    GeminiCliAgent,
    CodexCliAgent,
    AgyCliAgent,
    OpenCodeCliAgent,
    KiloCodeCliAgent,
    PiCliAgent,
    QwenCliAgent,
    HermesCliAgent,
)


class CliRegistry:
    """Singleton registry holding registered BaseCliAgent drivers."""

    def __init__(self) -> None:
        self._drivers: dict[str, BaseCliAgent] = {}
        self._init_builtins()

    def _init_builtins(self) -> None:
        for driver_cls in BUILT_IN_DRIVERS:
            instance = driver_cls()
            if instance.name:
                self._drivers[instance.name] = instance

    def register(self, driver: BaseCliAgent) -> None:
        """Register or override a CLI driver instance."""
        if not driver.name:
            raise ValueError("Driver name cannot be empty")
        self._drivers[driver.name] = driver

    def get(self, name: str) -> BaseCliAgent | None:
        """Look up a driver by name."""
        return self._drivers.get(name)

    def names(self) -> list[str]:
        """All registered driver names (sorted)."""
        return sorted(self._drivers.keys())

    def all_drivers(self) -> dict[str, BaseCliAgent]:
        """Copy of all registered driver instances."""
        return dict(self._drivers)

    def load_custom_drivers(self, directory: str | None = None) -> int:
        """Dynamically load any BaseCliAgent subclasses from custom drivers directory.

        Returns the number of newly discovered drivers.
        """
        if directory is None:
            # Default to custom_cli_agents adjacent to swarm package
            directory = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "custom_cli_agents",
            )

        if not os.path.isdir(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                init_file = os.path.join(directory, "__init__.py")
                if not os.path.exists(init_file):
                    with open(init_file, "w", encoding="utf-8") as f:
                        f.write('"""Custom agentic CLI drivers registered by Support Agent."""\n')
            except OSError:
                return 0

        loaded = 0
        for fname in os.listdir(directory):
            if not fname.endswith(".py") or fname.startswith(("_", ".")):
                continue
            fpath = os.path.join(directory, fname)
            mod_name = f"swarm.custom_cli_agents.{fname[:-3]}"
            try:
                spec = importlib.util.spec_from_file_location(mod_name, fpath)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    for attr_name in dir(mod):
                        val = getattr(mod, attr_name)
                        if (
                            isinstance(val, type)
                            and issubclass(val, BaseCliAgent)
                            and val is not BaseCliAgent
                        ):
                            driver = val()
                            if driver.name:
                                self.register(driver)
                                loaded += 1
            except Exception:
                logger.exception("Failed to load custom CLI driver from %s", fpath)

        return loaded


_REGISTRY: CliRegistry | None = None


def get_cli_registry() -> CliRegistry:
    """Get the global CliRegistry singleton with built-in and custom drivers loaded."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CliRegistry()
        _REGISTRY.load_custom_drivers()
    return _REGISTRY


def get_driver(name: str) -> BaseCliAgent | None:
    """Convenience helper to retrieve a driver by name."""
    return get_cli_registry().get(name)


def registered_cli_names() -> list[str]:
    """List of all registered driver names."""
    return get_cli_registry().names()


def driver_catalog_descriptors() -> list[dict[str, Any]]:
    """Serialisable descriptor list for frontend driver selection in Settings."""
    registry = get_cli_registry()
    out = []
    for name in registry.names():
        driver = registry.get(name)
        if not driver:
            continue
        out.append({
            "name": driver.name,
            "display_name": driver.display_name or driver.name,
            "default_binary": driver.default_binary,
            "list_capability": driver.list_capability,
            "candidates": find_cli_candidates(driver.default_binary or driver.name),
        })
    return out
