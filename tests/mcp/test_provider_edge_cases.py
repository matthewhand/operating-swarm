"""Edge case tests for MCP provider and integration modules.

Covers:
- Invalid/partial server configs
- Tool schema validation failures
- Provider execute error propagation + redaction
- Timeouts / subprocess failures (mocked)
- Empty tool lists / empty resources
"""
import importlib
import sys
from types import ModuleType
from unittest.mock import AsyncMock, Mock, patch

import pytest

# ============================================================================
# Provider Edge Cases: Invalid/Partial Server Configs
# ============================================================================


def test_start_mcp_server_missing_config(monkeypatch):
    """Test _start_required_mcp_servers when server config is missing."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    # Create provider with empty MCP config
    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    p._mcp_config = {}  # Empty config

    with pytest.raises(ValueError, match="MCP server config 'nonexistent' not found"):
        p._start_required_mcp_servers(["nonexistent"])


def test_start_mcp_server_missing_command(monkeypatch):
    """Test _start_required_mcp_servers when server config lacks command."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    # Config with no command
    p._mcp_config = {"broken_server": {"name": "broken_server", "args": []}}

    with pytest.raises(ValueError, match="missing required 'command'"):
        p._start_required_mcp_servers(["broken_server"])


def test_start_mcp_server_subprocess_failure_all_retries(monkeypatch):
    """Test _start_required_mcp_servers when subprocess fails all retry attempts."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    p._mcp_config = {"failing_server": {"name": "failing_server", "command": "false", "args": []}}

    # Mock subprocess.Popen to simulate immediate process death
    mock_process = Mock()
    mock_process.poll.return_value = 1  # Process exited immediately
    mock_process.wait.return_value = 1
    mock_process.pid = 12345

    # Mock time.sleep to avoid delays
    with patch("swarm.mcp.provider.subprocess.Popen", return_value=mock_process), \
         patch("swarm.mcp.provider.time.sleep"):
        with pytest.raises(RuntimeError, match="Failed to start MCP server 'failing_server' after 3 attempts"):
            p._start_required_mcp_servers(["failing_server"])


def test_start_mcp_server_subprocess_exception(monkeypatch):
    """Test _start_required_mcp_servers when subprocess.Popen raises exception."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    p._mcp_config = {"error_server": {"name": "error_server", "command": "badcmd", "args": []}}

    with patch("swarm.mcp.provider.subprocess.Popen", side_effect=OSError("Command not found")), \
         patch("swarm.mcp.provider.time.sleep"):
        with pytest.raises(RuntimeError, match="Failed to start MCP server 'error_server' after 3 attempts"):
            p._start_required_mcp_servers(["error_server"])


# ============================================================================
# Provider Edge Cases: Stop Server Timeouts
# ============================================================================


def test_stop_mcp_server_timeout_kill(monkeypatch):
    """Test _stop_started_servers when terminate times out and kill is needed."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    import subprocess

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    # Mock process that times out on terminate
    mock_process = Mock()
    mock_process.pid = 12345
    mock_process.poll.return_value = None  # still running
    mock_process.stdin = mock_process.stdout = mock_process.stderr = None
    mock_process.terminate = Mock()
    mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]  # First call times out, second succeeds
    mock_process.kill = Mock()

    started_servers = [{"name": "stubborn_server", "process": mock_process, "pid": 12345}]

    p._stop_started_servers(started_servers)

    mock_process.terminate.assert_called_once()
    mock_process.kill.assert_called_once()


def test_stop_mcp_server_closes_pipes(monkeypatch):
    """Stop path must close stdout/stderr so unread PIPE data cannot block wait()."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    stdout = Mock()
    stderr = Mock()
    mock_process = Mock()
    mock_process.pid = 12345
    mock_process.poll.return_value = None
    mock_process.stdin = None
    mock_process.stdout = stdout
    mock_process.stderr = stderr
    mock_process.terminate = Mock()
    mock_process.wait.return_value = 0

    p._stop_started_servers([{"name": "pipe_server", "process": mock_process, "pid": 12345}])

    stdout.close.assert_called()
    stderr.close.assert_called()
    mock_process.terminate.assert_called_once()


def test_start_and_stop_chatty_subprocess_no_pipe_deadlock(monkeypatch):
    """Chatty child must not deadlock: start uses DEVNULL; stop closes/terminates cleanly."""
    import sys
    import time as real_time

    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)
    # Shorten the 1s startup probe without skipping process spawn.
    orig_sleep = real_time.sleep
    monkeypatch.setattr(prov.time, "sleep", lambda s: orig_sleep(min(float(s), 0.05)))

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    # Python that floods stdout/stderr then sleeps until signaled.
    p._mcp_config = {
        "chatty": {
            "name": "chatty",
            "command": sys.executable,
            "args": [
                "-c",
                "import sys,time\n"
                "for _ in range(20000):\n"
                "    sys.stdout.write('x'*100); sys.stderr.write('y'*100)\n"
                "sys.stdout.flush(); sys.stderr.flush()\n"
                "time.sleep(30)\n",
            ],
            "env": {},
        }
    }

    started = p._start_required_mcp_servers(["chatty"])
    assert len(started) == 1
    proc = started[0]["process"]
    assert proc.poll() is None
    # Would hang forever with undrained PIPE once OS pipe buffer fills.
    p._stop_started_servers(started)
    assert proc.poll() is not None


def test_stop_mcp_server_exception_during_stop(monkeypatch):
    """Test _stop_started_servers handles exceptions gracefully."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    # Mock process that raises exception
    mock_process = Mock()
    mock_process.pid = 12345
    mock_process.poll.return_value = None
    mock_process.stdin = mock_process.stdout = mock_process.stderr = None
    mock_process.terminate = Mock(side_effect=PermissionError("Access denied"))

    started_servers = [{"name": "protected_server", "process": mock_process, "pid": 12345}]

    # Should not raise, just log error
    p._stop_started_servers(started_servers)
    mock_process.terminate.assert_called_once()


# ============================================================================
# Provider Edge Cases: Tool Schema Validation
# ============================================================================


def test_call_tool_empty_instruction(monkeypatch):
    """Test call_tool with empty instruction raises ValueError."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    with pytest.raises(ValueError, match="'instruction' must be a non-empty string"):
        p.call_tool("test_bp", {"instruction": ""})

    with pytest.raises(ValueError, match="'instruction' must be a non-empty string"):
        p.call_tool("test_bp", {"instruction": "   "})


def test_call_tool_non_string_instruction(monkeypatch):
    """Test call_tool with non-string instruction raises ValueError."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    with pytest.raises(ValueError, match="'instruction' must be a non-empty string"):
        p.call_tool("test_bp", {"instruction": 123})

    with pytest.raises(ValueError, match="'instruction' must be a non-empty string"):
        p.call_tool("test_bp", {"instruction": None})


def test_call_tool_unknown_tool(monkeypatch):
    """Test call_tool with unknown tool name raises ValueError."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    with pytest.raises(ValueError, match="Unknown tool: nonexistent"):
        p.call_tool("nonexistent", {"instruction": "test"})


def test_call_tool_missing_class_type(monkeypatch):
    """Test call_tool when blueprint has no class_type."""
    fake_discovered = {
        "broken_bp": {
            "metadata": {"name": "Broken", "description": "Blueprint without class"},
            "class_type": None
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    p._index["broken_bp"]["class_type"] = None  # Explicitly set to None

    result = p.call_tool("broken_bp", {"instruction": "test"})
    assert "[Blueprint:broken_bp] Execution error:" in result["content"]
    assert "Blueprint class not found" in result["content"]


# ============================================================================
# Provider Edge Cases: Executor Error Propagation
# ============================================================================


def test_executor_returns_non_dict(monkeypatch):
    """Test executor that returns non-dict result."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    # Set executor that returns a string
    p.set_executor(lambda cls, instr, args: "plain string result")

    result = p.call_tool("test_bp", {"instruction": "test"})
    assert result["content"] == "plain string result"


def test_executor_raises_exception(monkeypatch):
    """Test executor that raises exception - error should be caught and returned."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    # Set executor that raises
    p.set_executor(lambda cls, instr, args: 1/0)

    result = p.call_tool("test_bp", {"instruction": "test"})
    assert "[Blueprint:test_bp] Execution error:" in result["content"]
    assert "division by zero" in result["content"]


# ============================================================================
# Provider Edge Cases: Empty Tool Lists
# ============================================================================


def test_list_tools_empty_discovery(monkeypatch):
    """Test list_tools when no blueprints are discovered."""
    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: {})

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    tools = p.list_tools()

    assert tools == []


def test_list_tools_blueprint_without_metadata(monkeypatch):
    """Test list_tools handles blueprints with missing metadata gracefully."""
    fake_discovered = {
        "minimal_bp": {},  # No metadata at all
        "partial_bp": {"metadata": {}},  # Empty metadata
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    tools = p.list_tools()

    assert len(tools) == 2
    names = {t["name"] for t in tools}
    assert "minimal_bp" in names
    assert "partial_bp" in names


# ============================================================================
# Provider Edge Cases: Blueprint Metadata Without required_mcp_servers
# ============================================================================


def test_blueprint_metadata_not_dict(monkeypatch):
    """Test blueprint with non-dict metadata attribute."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    # Mock blueprint class with non-dict metadata
    mock_blueprint_cls = Mock()
    mock_blueprint_cls.metadata = "invalid metadata"  # Not a dict
    p._index["test_bp"]["class_type"] = mock_blueprint_cls

    mock_instance = Mock()
    mock_instance.run = AsyncMock(return_value=[{"messages": [{"role": "assistant", "content": "ok"}]}])
    mock_blueprint_cls.return_value = mock_instance

    result = p.call_tool("test_bp", {"instruction": "test"})
    assert "ok" in result["content"]


def test_blueprint_no_metadata_attribute(monkeypatch):
    """Test blueprint without metadata attribute."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    # Mock blueprint class without metadata attribute
    mock_blueprint_cls = Mock(spec=[])  # No metadata attribute
    p._index["test_bp"]["class_type"] = mock_blueprint_cls

    mock_instance = Mock()
    mock_instance.run = AsyncMock(return_value=[{"messages": [{"role": "assistant", "content": "no metadata"}]}])
    mock_blueprint_cls.return_value = mock_instance

    result = p.call_tool("test_bp", {"instruction": "test"})
    assert "no metadata" in result["content"]


# ============================================================================
# Provider Edge Cases: _run_blueprint_sync Variations
# ============================================================================


def test_run_blueprint_sync_with_exception(monkeypatch):
    """Test _run_blueprint_sync when blueprint.run raises exception."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    mock_instance = Mock()
    # Create an async generator that raises
    async def failing_run(messages, mcp_servers_override=None):
        raise RuntimeError("Blueprint failed")
        yield  # pragma: no cover

    mock_instance.run = failing_run

    result = p._run_blueprint_sync(mock_instance, [{"role": "user", "content": "test"}], [], "test_bp")
    assert "[Blueprint:test_bp] Execution error:" in result["content"]
    assert "Blueprint failed" in result["content"]


def test_run_blueprint_sync_with_dict_result(monkeypatch):
    """Test _run_blueprint_sync with dict result (not list)."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    mock_instance = Mock()
    # Mock that returns a dict directly (mock case)
    async def mock_run(messages, mcp_servers_override=None):
        return {"messages": [{"role": "assistant", "content": "dict result"}]}

    mock_instance.run = AsyncMock(side_effect=mock_run)
    # Make it look like a mock
    mock_instance.run.__name__ = "AsyncMock_mock"

    result = p._run_blueprint_sync(mock_instance, [{"role": "user", "content": "test"}], [], "test_bp")
    assert "dict result" in result["content"]


def test_run_blueprint_sync_with_string_result(monkeypatch):
    """Test _run_blueprint_sync with string result (unexpected format)."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    mock_instance = Mock()
    # Mock that returns a string directly
    async def mock_run(messages, mcp_servers_override=None):
        return "plain string result"

    mock_instance.run = AsyncMock(side_effect=mock_run)
    mock_instance.run.__name__ = "AsyncMock_mock"

    result = p._run_blueprint_sync(mock_instance, [{"role": "user", "content": "test"}], [], "test_bp")
    assert "plain string result" in result["content"]


# ============================================================================
# Integration Edge Cases
# ============================================================================


def test_register_blueprints_missing_mcp_server(monkeypatch, caplog):
    """Missing mcp_server → 0 tools and a loud logger.error (not silent)."""
    import logging

    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)
    monkeypatch.setattr(logging.getLogger("swarm"), "propagate", True)

    # Mask mcp_server in sys.modules so import raises hermetically
    for mod in list(sys.modules.keys()):
        if mod.startswith("mcp_server"):
            del sys.modules[mod]
    monkeypatch.setitem(sys.modules, "mcp_server", None)

    from swarm.mcp import integration as integ
    importlib.reload(integ)

    with caplog.at_level(logging.ERROR, logger="swarm.mcp.integration"):
        count = integ.register_blueprints_with_mcp()
    assert count == 0
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("blueprint→tool bridge unavailable" in msg for msg in messages), messages
    assert any("NOT MCP tools" in msg for msg in messages), messages


def test_register_blueprints_no_register_tool_api(monkeypatch, caplog):
    """mcp_server≥0.5-style registry without register_tool → loud no-op."""
    import logging

    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)
    monkeypatch.setattr(logging.getLogger("swarm"), "propagate", True)

    reg_pkg = ModuleType("mcp_server")
    reg_mod = ModuleType("mcp_server.registry")
    # Intentionally no register_tool — MCPToolset-era API gap
    reg_pkg.registry = reg_mod
    sys.modules["mcp_server"] = reg_pkg
    sys.modules["mcp_server.registry"] = reg_mod

    from swarm.mcp import integration as integ
    importlib.reload(integ)

    with caplog.at_level(logging.ERROR, logger="swarm.mcp.integration"):
        count = integ.register_blueprints_with_mcp()
    assert count == 0
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("blueprint→tool bridge no-op" in msg for msg in messages), messages
    assert any("NOT MCP tools" in msg for msg in messages), messages


def test_register_blueprints_registration_error(monkeypatch, caplog):
    """Per-tool registry.register_tool failure logs error; others still register."""
    import logging

    fake_discovered = {
        "bad_bp": {
            "metadata": {"name": "Bad", "description": "Bad blueprint"},
            "class_type": Mock()
        },
        "good_bp": {
            "metadata": {"name": "Good", "description": "Good blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)
    monkeypatch.setattr(logging.getLogger("swarm"), "propagate", True)

    # Create stub registry that fails for one tool
    reg_pkg = ModuleType("mcp_server")
    reg_mod = ModuleType("mcp_server.registry")
    calls = []

    def register_tool(name, parameters, description, handler):
        if name == "bad_bp":
            raise ValueError("Registration failed")
        calls.append(name)

    reg_mod.register_tool = register_tool
    reg_pkg.registry = reg_mod
    sys.modules["mcp_server"] = reg_pkg
    sys.modules["mcp_server.registry"] = reg_mod

    from swarm.mcp import integration as integ
    importlib.reload(integ)

    with caplog.at_level(logging.ERROR, logger="swarm.mcp.integration"):
        count = integ.register_blueprints_with_mcp()

    # Only good_bp should be registered
    assert count == 1
    assert calls == ["good_bp"]
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("Failed to register blueprint 'bad_bp'" in msg for msg in messages), messages


def test_register_blueprints_handler_execution(monkeypatch):
    """Test that registered handlers work correctly."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    # Mock blueprint
    mock_blueprint_cls = Mock()
    fake_discovered["test_bp"]["class_type"] = mock_blueprint_cls
    mock_instance = Mock()
    mock_instance.run = AsyncMock(return_value=[{"messages": [{"role": "assistant", "content": "Handler result"}]}])
    mock_blueprint_cls.return_value = mock_instance

    # Create stub registry
    reg_pkg = ModuleType("mcp_server")
    reg_mod = ModuleType("mcp_server.registry")
    registered_handler = None

    def register_tool(name, parameters, description, handler):
        nonlocal registered_handler
        registered_handler = handler

    reg_mod.register_tool = register_tool
    reg_pkg.registry = reg_mod
    sys.modules["mcp_server"] = reg_pkg
    sys.modules["mcp_server.registry"] = reg_mod

    from swarm.mcp import integration as integ
    importlib.reload(integ)

    count = integ.register_blueprints_with_mcp()
    assert count == 1

    # Execute the handler
    result = registered_handler({"instruction": "test"})
    assert "Handler result" in result["content"]


# ============================================================================
# Provider Edge Cases: Refresh
# ============================================================================


def test_provider_refresh(monkeypatch):
    """Test refresh method rebuilds index."""
    initial_discovered = {
        "bp1": {"metadata": {"name": "BP1", "description": "First"}}
    }
    updated_discovered = {
        "bp1": {"metadata": {"name": "BP1", "description": "First"}},
        "bp2": {"metadata": {"name": "BP2", "description": "Second"}}
    }

    from swarm.mcp import provider as prov

    call_count = [0]

    def fake_discover(_):
        result = initial_discovered if call_count[0] == 0 else updated_discovered
        call_count[0] += 1
        return result

    monkeypatch.setattr(prov, "discover_blueprints", fake_discover)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    assert len(p.list_tools()) == 1

    # Update discovery and refresh
    p.refresh()
    assert len(p.list_tools()) == 2


# ============================================================================
# Provider Edge Cases: Successful Server Start
# ============================================================================


def test_start_mcp_server_success(monkeypatch):
    """Test _start_required_mcp_servers when process starts successfully."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)
    # Ambient secret must not be forwarded to the MCP stdio child.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    p._mcp_config = {"good_server": {"name": "good_server", "command": "test-cmd", "args": ["--port", "8080"], "env": {"FOO": "bar"}, "cwd": "/tmp"}}

    # Mock subprocess.Popen to simulate successful process start
    mock_process = Mock()
    mock_process.poll.return_value = None  # Process is running
    mock_process.pid = 54321

    with patch("swarm.mcp.provider.subprocess.Popen", return_value=mock_process) as mock_popen, \
         patch("swarm.mcp.provider.time.sleep"):
        started = p._start_required_mcp_servers(["good_server"])

        assert len(started) == 1
        assert started[0]["name"] == "good_server"
        assert started[0]["pid"] == 54321

        # Verify Popen was called with correct args (DEVNULL — never undrained PIPE)
        import subprocess
        call_args = mock_popen.call_args
        assert call_args[0][0] == ["test-cmd", "--port", "8080"]
        assert call_args[1]["cwd"] == "/tmp"
        assert call_args[1]["env"]["FOO"] == "bar"
        assert "OPENAI_API_KEY" not in call_args[1]["env"]
        assert call_args[1]["stdin"] is subprocess.DEVNULL
        assert call_args[1]["stdout"] is subprocess.DEVNULL
        assert call_args[1]["stderr"] is subprocess.DEVNULL


def test_start_mcp_server_retry_then_success(monkeypatch):
    """Test _start_required_mcp_servers succeeds after retry."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    p._mcp_config = {"retry_server": {"name": "retry_server", "command": "test", "args": []}}

    # First call fails, second succeeds
    fail_process = Mock()
    fail_process.poll.return_value = 1
    fail_process.wait.return_value = 1

    success_process = Mock()
    success_process.poll.return_value = None
    success_process.pid = 99999

    with patch("swarm.mcp.provider.subprocess.Popen", side_effect=[fail_process, success_process]) as mock_popen, \
         patch("swarm.mcp.provider.time.sleep"):
        started = p._start_required_mcp_servers(["retry_server"])

        assert len(started) == 1
        assert started[0]["pid"] == 99999
        assert mock_popen.call_count == 2


# ============================================================================
# Provider Edge Cases: Non-Mock Blueprint Run (Async Generator)
# ============================================================================


def test_run_blueprint_sync_async_generator(monkeypatch):
    """Test _run_blueprint_sync with real async generator (non-mock)."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    mock_instance = Mock()

    # Create a real async generator (not a mock)
    async def real_async_gen(messages, mcp_servers_override=None):
        yield {"messages": [{"role": "assistant", "content": "chunk 1"}]}
        yield {"messages": [{"role": "assistant", "content": "chunk 2"}]}

    # Don't make it look like a mock
    mock_instance.run = real_async_gen

    result = p._run_blueprint_sync(mock_instance, [{"role": "user", "content": "test"}], [], "test_bp")
    assert "chunk 1" in result["content"]
    assert "chunk 2" in result["content"]


def test_run_blueprint_sync_async_generator_exception(monkeypatch):
    """Test _run_blueprint_sync when async generator raises exception."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    mock_instance = Mock()

    # Create an async generator that raises after yielding
    async def failing_async_gen(messages, mcp_servers_override=None):
        yield {"messages": [{"role": "assistant", "content": "before error"}]}
        raise RuntimeError("Generator error")

    mock_instance.run = failing_async_gen

    result = p._run_blueprint_sync(mock_instance, [{"role": "user", "content": "test"}], [], "test_bp")
    assert "[Blueprint:test_bp] Execution error:" in result["content"]
    assert "Generator error" in result["content"]


def test_run_blueprint_sync_async_generator_empty_chunks(monkeypatch):
    """Test _run_blueprint_sync when async generator yields no chunks."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    mock_instance = Mock()

    # Empty async generator
    async def empty_async_gen(messages, mcp_servers_override=None):
        return
        yield  # pragma: no cover

    mock_instance.run = empty_async_gen

    result = p._run_blueprint_sync(mock_instance, [{"role": "user", "content": "test"}], [], "test_bp")
    assert result["content"] == ""


def test_run_blueprint_sync_non_coroutine_mock_result(monkeypatch):
    """Test _run_blueprint_sync when mock returns non-coroutine result."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")

    mock_instance = Mock()

    # Mock that returns a list directly (not a coroutine)
    def sync_run(messages, mcp_servers_override=None):
        return [{"messages": [{"role": "assistant", "content": "sync result"}]}]

    mock_instance.run = Mock(side_effect=sync_run)
    mock_instance.run.__name__ = "Mock_mock"

    result = p._run_blueprint_sync(mock_instance, [{"role": "user", "content": "test"}], [], "test_bp")
    assert "sync result" in result["content"]


# ============================================================================
# Provider Edge Cases: Process None Edge Case
# ============================================================================


def test_start_mcp_server_process_none_after_loop(monkeypatch):
    """Test _start_required_mcp_servers when process is None after loop (defensive)."""
    fake_discovered = {
        "test_bp": {
            "metadata": {"name": "Test", "description": "Test blueprint"},
            "class_type": Mock()
        }
    }

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    p = prov.BlueprintMCPProvider(blueprint_dir="ignored")
    p._mcp_config = {"weird_server": {"name": "weird_server", "command": "test", "args": []}}

    # Mock Popen to return None (very unusual but possible in theory)
    with patch("swarm.mcp.provider.subprocess.Popen", return_value=None), \
         patch("swarm.mcp.provider.time.sleep"):
        with pytest.raises(RuntimeError, match="Failed to start MCP server 'weird_server'"):
            p._start_required_mcp_servers(["weird_server"])
