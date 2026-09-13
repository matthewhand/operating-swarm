"""Comprehensive unit tests for the LangChain sandbox harness and sandbox manager."""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, create_autospec

from swarm.core.sandbox import (
    LangChainSandboxHarness,
    LocalSubprocessSandbox,
    MockSandbox,
    SandboxBackend,
    SandboxConfig,
    SandboxExecutionResult,
    SandboxManager,
    get_default_sandbox_manager,
    reset_default_sandbox_manager,
)


class TestMockSandbox:
    def test_python_eval_and_exec(self):
        sandbox = MockSandbox()
        # Expression
        res = sandbox.execute_python("1 + 1")
        assert res.success
        assert "2" in res.stdout

        # Statement
        res2 = sandbox.execute_python("x = 42\nprint(f'val={x}')")
        assert res2.success
        assert "val=42" in res2.stdout

    def test_python_syntax_error(self):
        sandbox = MockSandbox()
        res = sandbox.execute_python("def broken(")
        assert not res.success
        assert res.error is not None

    def test_bash_simulations(self):
        sandbox = MockSandbox()
        res = sandbox.execute_bash("echo 'hello world'")
        assert res.success
        assert "hello world" in res.stdout

        pwd_res = sandbox.execute_bash("pwd")
        assert pwd_res.success

    def test_files_and_cat(self):
        sandbox = MockSandbox()
        sandbox.write_file("test.txt", "mock content")
        assert sandbox.read_file("test.txt") == "mock content"

        cat_res = sandbox.execute_bash("cat test.txt")
        assert cat_res.success
        assert "mock content" in cat_res.stdout

        missing_cat = sandbox.execute_bash("cat missing.txt")
        assert not missing_cat.success

    def test_registered_response(self):
        sandbox = MockSandbox()
        canned = SandboxExecutionResult(stdout="custom output", exit_code=0, success=True)
        sandbox.register_response("special_command", canned)
        res = sandbox.execute_bash("special_command")
        assert res.stdout == "custom output"

    def test_cleanup(self):
        sandbox = MockSandbox()
        sandbox.write_file("a.txt", "foo")
        sandbox.cleanup()
        assert sandbox.closed
        res = sandbox.execute_bash("echo hi")
        assert not res.success
        assert "closed" in (res.error or "")


class TestLocalSubprocessSandbox:
    def test_bare_metal_python_execution(self, tmp_path):
        cfg = SandboxConfig(backend_type="local", work_dir=str(tmp_path))
        sandbox = LocalSubprocessSandbox(cfg)

        res = sandbox.execute_python("print('bare-metal-ok')")
        assert res.success
        assert "bare-metal-ok" in res.stdout
        assert res.exit_code == 0

    def test_bare_metal_bash_execution(self, tmp_path):
        cfg = SandboxConfig(backend_type="local", work_dir=str(tmp_path))
        sandbox = LocalSubprocessSandbox(cfg)

        res = sandbox.execute_bash("echo test-bash")
        assert res.success
        assert "test-bash" in res.stdout

    def test_environment_sanitization(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-secret-key")
        monkeypatch.setenv("SAFE_VAR", "visible-safe-var")

        cfg = SandboxConfig(
            backend_type="local",
            work_dir=str(tmp_path),
            inherit_env=True,
            sanitize_env=True,
        )
        sandbox = LocalSubprocessSandbox(cfg)

        code = "import os; print('OPENAI:' + str(os.getenv('OPENAI_API_KEY'))); print('SAFE:' + str(os.getenv('SAFE_VAR')))"
        res = sandbox.execute_python(code)
        assert res.success
        assert "OPENAI:None" in res.stdout
        assert "SAFE:visible-safe-var" in res.stdout

    def test_timeout_enforcement(self, tmp_path):
        cfg = SandboxConfig(backend_type="local", work_dir=str(tmp_path), timeout_seconds=1)
        sandbox = LocalSubprocessSandbox(cfg)

        # Python sleep longer than timeout
        res = sandbox.execute_python("import time; time.sleep(3)", timeout=1)
        assert not res.success
        assert res.exit_code == 124
        assert "TimeoutExpired" in (res.error or "")

    def test_path_confinement_and_file_ops(self, tmp_path):
        work_dir = tmp_path / "workspace"
        work_dir.mkdir()
        cfg = SandboxConfig(backend_type="local", work_dir=str(work_dir))
        sandbox = LocalSubprocessSandbox(cfg)

        # Allowed write and read
        sandbox.write_file("hello.txt", "data123")
        assert sandbox.read_file("hello.txt") == "data123"

        # Disallowed out-of-bounds access
        forbidden_file = tmp_path / "forbidden.txt"
        with pytest.raises(PermissionError):
            sandbox.write_file(str(forbidden_file), "malicious")

        with pytest.raises(PermissionError):
            sandbox.read_file(str(forbidden_file))

        sandbox.cleanup()


class TestLangChainSandboxHarness:
    def test_fallback_when_langchain_missing(self):
        # Default fallback is MockSandbox
        cfg = SandboxConfig(backend_type="langchain_repl", fallback_to_mock=True)
        harness = LangChainSandboxHarness(cfg)
        assert harness.is_available()

        res = harness.execute_python("2 + 2")
        assert res.success
        assert "4" in res.stdout

    def test_fallback_to_local_when_requested(self, tmp_path):
        cfg = SandboxConfig(
            backend_type="langchain_repl",
            work_dir=str(tmp_path),
            fallback_to_mock=False,
        )
        harness = LangChainSandboxHarness(cfg)
        assert harness.is_available()

        res = harness.execute_python("print('from-local-fallback')")
        assert res.success
        assert "from-local-fallback" in res.stdout

    def test_mocked_langchain_tools_injection(self):
        class DummyReplTool:
            def run(self, code: str) -> str:
                return f"REPL-RESULT: {code}"

        class DummyShellTool:
            def run(self, command: str) -> str:
                return f"SHELL-RESULT: {command}"

        harness = LangChainSandboxHarness(
            config=SandboxConfig(backend_type="langchain_repl"),
            repl_tool=DummyReplTool(),
            shell_tool=DummyShellTool(),
        )

        res_py = harness.execute_python("x = 10")
        assert res_py.success
        assert res_py.stdout == "REPL-RESULT: x = 10"

        res_sh = harness.execute_bash("ls -la")
        assert res_sh.success
        assert res_sh.stdout == "SHELL-RESULT: ls -la"

    def test_langchain_tool_exception_handling(self):
        class BrokenReplTool:
            def run(self, code: str) -> str:
                raise RuntimeError("REPL syntax crash")

        harness = LangChainSandboxHarness(
            config=SandboxConfig(backend_type="langchain_repl"),
            repl_tool=BrokenReplTool(),
        )

        res = harness.execute_python("crash_now()")
        assert not res.success
        assert res.exit_code == 1
        assert "REPL syntax crash" in (res.error or "")


class TestSandboxManagerAndTools:
    def test_manager_from_config(self, tmp_path):
        raw_cfg = {
            "backend": "mock",
            "timeout": 15,
            "workspace": str(tmp_path),
            "inherit_env": False,
        }
        manager = SandboxManager.from_config(raw_cfg)
        assert isinstance(manager.backend, MockSandbox)
        assert manager.config.timeout_seconds == 15
        assert manager.config.work_dir == str(tmp_path)

    def test_manager_delegation(self):
        manager = SandboxManager(config=SandboxConfig(backend_type="mock"))
        res = manager.execute_python("print('mgr-test')")
        assert res.success
        assert "mgr-test" in res.stdout

        manager.write_file("doc.txt", "abc")
        assert manager.read_file("doc.txt") == "abc"

    def test_get_raw_tools(self):
        manager = SandboxManager(config=SandboxConfig(backend_type="mock"))
        raw = manager.get_raw_tools()

        assert "sandbox_run_python" in raw
        assert "sandbox_run_bash" in raw
        assert "sandbox_read_file" in raw
        assert "sandbox_write_file" in raw

        out_py = raw["sandbox_run_python"]("5 * 5")
        assert "25" in out_py

        out_sh = raw["sandbox_run_bash"]("echo test-tool")
        assert "test-tool" in out_sh

        write_res = raw["sandbox_write_file"]("note.txt", "tool-written")
        assert "successfully" in write_res

        read_res = raw["sandbox_read_file"]("note.txt")
        assert read_res == "tool-written"

        missing_res = raw["sandbox_read_file"]("nonexistent.txt")
        assert "[Read Error:" in missing_res

    def test_as_function_tools_schema(self):
        manager = SandboxManager(config=SandboxConfig(backend_type="mock"))
        tools = manager.as_function_tools()
        assert len(tools) == 4

        tool_names = [getattr(t, "name", getattr(t, "__name__", None)) for t in tools]
        assert "sandbox_run_python" in tool_names
        assert "sandbox_run_bash" in tool_names
        assert "sandbox_read_file" in tool_names
        assert "sandbox_write_file" in tool_names

        # Each tool has a valid description
        for t in tools:
            desc = getattr(t, "description", getattr(t, "__doc__", ""))
            assert desc is not None and len(desc) > 0

    def test_global_manager_helpers(self):
        reset_default_sandbox_manager()
        m1 = get_default_sandbox_manager()
        m2 = get_default_sandbox_manager()
        assert m1 is m2
        reset_default_sandbox_manager()

    def test_integration_with_openai_agent(self):
        try:
            from agents import Agent
        except ImportError:
            pytest.skip("openai-agents SDK not installed")

        manager = SandboxManager(config=SandboxConfig(backend_type="mock"))
        tools = manager.as_function_tools()
        agent = Agent(
            name="SandboxWorker",
            instructions="You are a worker with isolated sandbox tools.",
            tools=tools,
        )
        assert agent.name == "SandboxWorker"
        assert len(agent.tools) == 4
