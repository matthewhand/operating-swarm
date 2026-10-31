import importlib
import sys
from types import ModuleType
from unittest.mock import AsyncMock, Mock


def test_register_blueprints_with_mcp_legacy(monkeypatch):
    """Test backwards-compatibility with legacy mcp_server.registry.register_tool."""
    # Fake discovery with one blueprint
    fake_discovered = {
        "suggestion": {
            "metadata": {"name": "Suggestion", "description": "Provide suggestions"},
            "class_type": Mock
        },
    }

    # Stub registry module
    reg_pkg = ModuleType("mcp_server")
    reg_mod = ModuleType("mcp_server.registry")
    calls = []

    def register_tool(name, parameters, description, handler):  # noqa: D401
        calls.append({"name": name, "parameters": parameters, "description": description, "handler": handler})

    # Add the register_tool function to the module's namespace
    reg_mod.register_tool = register_tool  # type: ignore
    reg_pkg.registry = reg_mod  # type: ignore
    monkeypatch.setitem(sys.modules, "mcp_server", reg_pkg)
    monkeypatch.setitem(sys.modules, "mcp_server.registry", reg_mod)

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    # Create a mock blueprint class for the test
    mock_blueprint_cls = Mock()
    fake_discovered["suggestion"]["class_type"] = mock_blueprint_cls

    # Mock the blueprint instance and its run method
    mock_blueprint_instance = Mock()
    mock_blueprint_cls.return_value = mock_blueprint_instance

    async def mock_run(messages, mcp_servers_override=None):
        return [{"messages": [{"role": "assistant", "content": "Hi there! How can I help with your instruction?"}]}]

    mock_blueprint_instance.run = AsyncMock(side_effect=mock_run)

    from swarm.mcp import integration as integ
    importlib.reload(integ)
    count = integ.register_blueprints_with_mcp()

    assert count == 1
    assert calls and calls[0]["name"] == "suggestion"
    # Call handler to ensure it wires through to provider
    result = calls[0]["handler"]({"instruction": "Hi"})
    assert "instruction" in result["content"].lower()


def test_register_blueprints_with_mcp_server_add_tool(monkeypatch):
    """Test modern registration via mcp_server.mcp_server.add_tool (mcp_server >= 0.5.0)."""
    fake_discovered = {
        "codey": {
            "metadata": {"name": "Codey", "description": "Expert coding assistant"},
            "class_type": Mock,
        },
    }

    server_pkg = ModuleType("mcp_server")
    mock_server = Mock()
    tools_registered = []

    def add_tool(fn, name=None, description=None, **kwargs):
        tools_registered.append({"fn": fn, "name": name, "description": description})

    mock_server.add_tool = add_tool
    server_pkg.mcp_server = mock_server
    monkeypatch.setitem(sys.modules, "mcp_server", server_pkg)

    from swarm.mcp import provider as prov
    monkeypatch.setattr(prov, "discover_blueprints", lambda _: fake_discovered)

    mock_blueprint_cls = Mock()
    fake_discovered["codey"]["class_type"] = mock_blueprint_cls
    mock_blueprint_instance = Mock()
    mock_blueprint_cls.return_value = mock_blueprint_instance

    async def mock_run(messages, mcp_servers_override=None):
        return [{"messages": [{"role": "assistant", "content": "Code generated successfully"}]}]

    mock_blueprint_instance.run = AsyncMock(side_effect=mock_run)

    from swarm.mcp import integration as integ
    importlib.reload(integ)
    count = integ.register_blueprints_with_mcp()

    assert count == 1
    assert len(tools_registered) == 1
    reg = tools_registered[0]
    assert reg["name"] == "codey"
    assert "Expert coding" in reg["description"]
    # Execute the generated tool callable
    tool_fn = reg["fn"]
    result_str = tool_fn(instruction="Write a hello world function")
    assert "Code generated successfully" in result_str


def test_register_blueprints_missing_mcp_server_package(monkeypatch, caplog):
    """When mcp_server is absent, register_blueprints_with_mcp returns 0 without raising."""
    monkeypatch.setitem(sys.modules, "mcp_server", None)

    from swarm.mcp import integration as integ
    importlib.reload(integ)
    count = integ.register_blueprints_with_mcp()
    assert count == 0
    assert any("bridge unavailable: cannot import mcp_server" in rec.message for rec in caplog.records)


def test_register_blueprints_no_registration_api(monkeypatch, caplog):
    """When mcp_server is present but lacks add_tool or register_tool, return 0."""
    empty_pkg = ModuleType("mcp_server")
    monkeypatch.setitem(sys.modules, "mcp_server", empty_pkg)

    from swarm.mcp import integration as integ
    importlib.reload(integ)
    count = integ.register_blueprints_with_mcp()
    assert count == 0
    assert any("neither mcp_server.add_tool nor registry.register_tool" in rec.message for rec in caplog.records)


