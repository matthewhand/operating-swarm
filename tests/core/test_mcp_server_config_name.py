"""MCP server dicts use the map key as name (swarm_config.example.json)."""

import pytest
from pydantic import ValidationError

from swarm.core.mcp_server_config import MCPServerConfig


def test_from_named_dict_fills_key():
    cfg = MCPServerConfig.from_named_dict(
        "playwright", {"command": "npx", "args": ["-y", "playwright"]}
    )
    assert cfg.name == "playwright"
    assert cfg.command == "npx"


def test_from_named_dict_keeps_explicit_name():
    cfg = MCPServerConfig.from_named_dict(
        "key", {"name": "explicit", "command": "npx"}
    )
    assert cfg.name == "explicit"


def test_validation_error_does_not_dump_env_secret():
    with pytest.raises(ValidationError) as ei:
        MCPServerConfig(command=123, env={"SECRET": "should-not-appear"})  # type: ignore[arg-type]
    assert "should-not-appear" not in str(ei.value)
