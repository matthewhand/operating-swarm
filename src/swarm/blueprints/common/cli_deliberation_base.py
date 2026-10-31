"""Shared base class for multi-CLI deliberation strategy blueprints.

Provides shared parameter handling, prompt rendering, CLI adapter overrides,
workdir isolation and escape handling, and configuration fallback across the
deliberation strategy family (cli_map, cli_orchestrator, cli_pipeline,
cli_planner, cli_recurse, cli_roundtable).
"""

from __future__ import annotations

import logging
from typing import Any

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.kind_bases import CliKindBase
from swarm.core.workdir import WorkdirEscapeError

logger = logging.getLogger(__name__)


class CliDeliberationBase(CliKindBase):
    """Common base class for multi-CLI deliberation blueprints."""

    def __init__(self, blueprint_id: str, config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        """Store per-request parameters."""
        self._params = dict(params or {})

    def get_fusion_config(self) -> dict[str, Any]:
        """Convenience accessor for fallback cli_fusion configuration."""
        return (self._config or {}).get("cli_fusion") or {}

    def get_strategy_config(self, key: str | None = None) -> dict[str, Any]:
        """Convenience accessor for strategy-specific configuration."""
        lookup_key = key or getattr(self, "blueprint_id", "")
        return (self._config or {}).get(lookup_key) or {}

    def get_fusion_preset(self) -> dict[str, Any]:
        """Convenience accessor for default fusion preset."""
        fusion = self.get_fusion_config()
        return (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}

    def get_default_cli(self) -> str | None:
        """Convenience accessor for default fallback CLI."""
        return self.get_fusion_config().get("default_cli")

    def bounded_int(
        self,
        params: dict[str, Any],
        key: str,
        default: int,
        max_val: int,
        min_val: int = 1,
        config_key: str | None = None,
    ) -> int:
        """Safely extract an integer parameter within [min_val, max_val]."""
        cfg = self.get_strategy_config(config_key)
        raw = params.get(key, cfg.get(key, default))
        try:
            return max(min_val, min(int(raw), max_val))
        except (TypeError, ValueError):
            return default

    def prepare_deliberation(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, CliAdapterRegistry, str, None] | tuple[None, None, None, dict[str, Any]]:
        """Validate input prompt, construct adapter registry with overrides, and resolve workdir.

        Returns (prompt, registry, workdir, None) on success, or
        (None, None, None, error_chunk) if a precondition fails.
        """
        params = dict(self._params)
        prompt = support.render_prompt(messages)
        if not prompt:
            return None, None, None, support.message_chunk("No prompt provided.", final=True)

        registry = support.apply_overrides(support.build_registry(self._config), params)

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            return None, None, None, support.message_chunk(str(e), final=True)

        return prompt, registry, workdir, None
