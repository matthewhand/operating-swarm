"""Unit tests for CLI MCP argv / mcp.json construction (no live MCP servers)."""

from pathlib import Path

from swarm.core.cli_mcp import (
    inject_mcp_argv,
    normalize_mcp_servers,
    parse_mcp_help_flags,
    write_mcp_config_file,
    cleanup_mcp_config_file,
)

SERVERS = {
    "basic-memory": {
        "command": "uvx",
        "args": ["basic-memory", "mcp"],
        "env": {"API_KEY": "secret-token"},
    }
}


def test_normalize_skips_disabled_and_empty():
    out = normalize_mcp_servers({
        "ok": {"command": "uvx", "args": ["x"]},
        "off": {"command": "uvx", "enabled": False},
        "off-text": {"command": "uvx", "enabled": " false "},
        "http": {"url": "https://example/mcp", "transport": "http", "headers": {"Authorization": "Bearer t"}},
        "bad": True,
    })
    assert "ok" in out and "off" not in out and "off-text" not in out
    assert out["http"]["url"] == "https://example/mcp"
    assert out["http"]["headers"]["Authorization"] == "Bearer t"


def test_help_flags_mcp_config_vs_acp_only():
    assert parse_mcp_help_flags("Usage: grok [--mcp-config FILE]")["mcp_config"] is True
    acp = parse_mcp_help_flags("ACP session/new mcpServers list")
    assert acp["acp"] is True
    assert acp["mcp_config"] is False


def test_claude_writes_mcp_json_and_keeps_secrets_off_argv():
    argv, path = inject_mcp_argv("claude", ["claude", "-p", "hi"], SERVERS)
    try:
        assert path and Path(path).is_file()
        assert argv[-2:] == ["--mcp-config", path]
        assert "secret-token" not in argv
        assert "API_KEY" not in argv
        payload = Path(path).read_text(encoding="utf-8")
        assert "secret-token" in payload
        assert '"basic-memory"' in payload
    finally:
        cleanup_mcp_config_file(path)


def test_grok_injects_when_help_has_mcp_config():
    argv, path = inject_mcp_argv(
        "grok",
        ["grok", "-p", "hi"],
        SERVERS,
        help_text="  --mcp-config PATH   Load MCP servers",
    )
    try:
        assert argv[-2:] == ["--mcp-config", path]
    finally:
        cleanup_mcp_config_file(path)


def test_grok_falls_back_when_acp_only_or_unknown():
    argv, path = inject_mcp_argv(
        "grok",
        ["grok", "-p", "hi"],
        SERVERS,
        help_text="session/new mcpServers (ACP)",
    )
    assert path is None
    assert argv == ["grok", "-p", "hi"]

    argv, path = inject_mcp_argv(
        "agy",
        ["agy", "-p=hi"],
        SERVERS,
        help_text="no mcp flags here",
    )
    assert path is None
    assert argv == ["agy", "-p=hi"]


def test_empty_servers_or_unknown_cli_is_noop():
    argv, path = inject_mcp_argv("claude", ["claude", "-p", "x"], {})
    assert path is None and argv == ["claude", "-p", "x"]
    argv, path = inject_mcp_argv("gemini", ["gemini", "-p", "x"], SERVERS)
    assert path is None


def test_write_mcp_config_file_mode():
    path = write_mcp_config_file(normalize_mcp_servers(SERVERS))
    try:
        mode = Path(path).stat().st_mode & 0o777
        assert mode == 0o600
    finally:
        cleanup_mcp_config_file(path)
