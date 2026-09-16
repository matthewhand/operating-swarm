"""REQ-863 / #253 — bare-metal host execution, env inheritance, tool attach."""

from __future__ import annotations

import pytest

from swarm.core.sandbox import (
    LocalSubprocessSandbox,
    SandboxConfig,
    SandboxManager,
    sandbox_function_tools,
)
from swarm.core.sandbox.disabled_sandbox import DisabledSandbox


class TestBareMetalExecution:
    def test_python_and_bash_in_workspace(self, tmp_path):
        cfg = SandboxConfig(
            backend_type="local",
            work_dir=str(tmp_path),
            unrestricted_host=True,
            inherit_env=True,
            sanitize_env=False,
        )
        sandbox = LocalSubprocessSandbox(cfg)
        py = sandbox.execute_python("print('bare-metal-ok')")
        assert py.success
        assert "bare-metal-ok" in py.stdout
        sh = sandbox.execute_bash("echo host-shell")
        assert sh.success
        assert "host-shell" in sh.stdout

    def test_unrestricted_paths_allow_sibling_workspace(self, tmp_path):
        work = tmp_path / "workspace"
        sibling = tmp_path / "sibling"
        work.mkdir()
        sibling.mkdir()
        target = sibling / "notes.txt"
        target.write_text("outside-work-dir", encoding="utf-8")
        sandbox = LocalSubprocessSandbox(
            SandboxConfig(
                backend_type="local",
                work_dir=str(work),
                unrestricted_host=True,
            )
        )
        assert sandbox.read_file(str(target)) == "outside-work-dir"
        other = sibling / "written.txt"
        assert sandbox.write_file(str(other), "from-bare-metal")
        assert other.read_text(encoding="utf-8") == "from-bare-metal"

    def test_jailed_local_still_blocks_outside_paths(self, tmp_path):
        work = tmp_path / "workspace"
        work.mkdir()
        forbidden = tmp_path / "secret.txt"
        forbidden.write_text("nope", encoding="utf-8")
        sandbox = LocalSubprocessSandbox(
            SandboxConfig(backend_type="local", work_dir=str(work))
        )
        with pytest.raises(PermissionError):
            sandbox.read_file(str(forbidden))

    def test_full_env_inheritance_includes_developer_cli_secrets(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("GH_TOKEN", "ghp_test_token")
        monkeypatch.setenv("GITHUB_TOKEN", "ghs_test_token")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-kept-on-bare-metal")
        sandbox = LocalSubprocessSandbox(
            SandboxConfig(
                backend_type="local",
                work_dir=str(tmp_path),
                unrestricted_host=True,
                inherit_env=True,
                sanitize_env=False,
            )
        )
        code = (
            "import os;"
            "print('GH:' + str(os.getenv('GH_TOKEN')));"
            "print('OPENAI:' + str(os.getenv('OPENAI_API_KEY')))"
        )
        res = sandbox.execute_python(code)
        assert res.success
        assert "GH:ghp_test_token" in res.stdout
        assert "OPENAI:sk-kept-on-bare-metal" in res.stdout

    def test_audit_log_at_info(self, tmp_path, monkeypatch):
        records: list[str] = []

        def _capture(msg, *args, **_kwargs):
            records.append(msg % args if args else str(msg))

        monkeypatch.setattr("swarm.core.sandbox.local_sandbox.logger.info", _capture)
        sandbox = LocalSubprocessSandbox(
            SandboxConfig(
                backend_type="local",
                work_dir=str(tmp_path),
                unrestricted_host=True,
            )
        )
        sandbox.execute_bash("echo audited")
        joined = "\n".join(records)
        assert "bare_metal" in joined
        assert "bash" in joined
        assert "echo audited" in joined


class TestBareMetalManager:
    def test_from_config_provider_bare_metal_is_unrestricted(self, tmp_path):
        manager = SandboxManager.from_config(
            {"provider": "bare_metal", "work_dir": str(tmp_path)}
        )
        assert isinstance(manager.backend, LocalSubprocessSandbox)
        assert manager.config.unrestricted_host is True
        assert manager.config.sanitize_env is False
        assert manager.config.inherit_env is True
        assert manager.tools_enabled() is True
        names = [
            getattr(t, "name", getattr(t, "__name__", ""))
            for t in manager.as_function_tools()
        ]
        for expected in (
            "sandbox_run_python",
            "sandbox_run_bash",
            "sandbox_read_file",
            "sandbox_write_file",
        ):
            assert expected in names

    def test_from_settings_default_is_none(self):
        manager = SandboxManager.from_settings({"settings": {}})
        assert isinstance(manager.backend, DisabledSandbox)
        assert manager.tools_enabled() is False
        assert sandbox_function_tools(config={"settings": {}}) == []

    def test_from_settings_bare_metal_attaches_tools(self, tmp_path):
        config = {
            "settings": {
                "sandbox": {
                    "provider": "bare_metal",
                    "dangerous_confirmed": True,
                    "work_dir": str(tmp_path),
                }
            }
        }
        tools = sandbox_function_tools(config=config)
        names = [getattr(t, "name", getattr(t, "__name__", "")) for t in tools]
        assert "sandbox_run_bash" in names
        assert "sandbox_run_python" in names

    def test_make_agent_bare_metal_attaches_tools(self, monkeypatch):
        import agents
        import swarm.core.blueprint_base as bb

        captured = {}

        class FakeAgent:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(agents, "Agent", FakeAgent)

        class _ConcreteBP(bb.BlueprintBase):
            async def run(self, *a, **k):  # pragma: no cover
                yield {}

        bp = _ConcreteBP.__new__(_ConcreteBP)
        bp._config = {
            "llm": {},
            "settings": {"sandbox": {"provider": "bare_metal", "dangerous_confirmed": True}},
        }
        bp._resolve_llm_profile = lambda *a, **k: "stub-profile"
        bp._get_model_instance = lambda profile=None: object()
        bp._get_memory_instance = lambda *a, **k: None
        bp.make_agent(name="t", instructions="i", tools=[])
        assert "sandbox_run_python" in str(captured.get("tools", []))
        assert "sandbox_run_bash" in str(captured.get("tools", []))

    def test_make_agent_none_ignores_legacy_toggle(self, monkeypatch):
        import agents
        import swarm.core.blueprint_base as bb

        captured = {}

        class FakeAgent:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(agents, "Agent", FakeAgent)

        class _ConcreteBP(bb.BlueprintBase):
            async def run(self, *a, **k):  # pragma: no cover
                yield {}

        bp = _ConcreteBP.__new__(_ConcreteBP)
        bp._config = {
            "llm": {},
            "settings": {
                "sandbox": {"provider": "none"},
                "enable_sandbox_tools": True,
            },
        }
        bp._resolve_llm_profile = lambda *a, **k: "stub-profile"
        bp._get_model_instance = lambda profile=None: object()
        bp._get_memory_instance = lambda *a, **k: None
        bp.make_agent(name="t", instructions="i", tools=[])
        assert "sandbox_run_python" not in str(captured.get("tools", []))

    def test_api_kind_base_attaches_sandbox_tools(self):
        from types import SimpleNamespace

        from swarm.core.kind_bases import ApiKindBase
        from swarm.core.sandbox import attach_sandbox_tools_to_agent

        agent = SimpleNamespace(tools=[])
        attach_sandbox_tools_to_agent(
            agent,
            config={"settings": {"sandbox": {"provider": "bare_metal"}}},
        )
        names = [getattr(t, "name", getattr(t, "__name__", "")) for t in agent.tools]
        assert "sandbox_run_bash" in names
        assert ApiKindBase.kind == "api"
