"""REQ-863 / #253 — Daytona SaaS lifecycle, cleanup, lazy degradation."""

from __future__ import annotations

from types import SimpleNamespace

from swarm.core.sandbox import SandboxManager
from swarm.core.sandbox.daytona_sandbox import (
    DAYTONA_SDK_INSTALL_HINT,
    DaytonaSandbox,
)
from swarm.core.sandbox.disabled_sandbox import DisabledSandbox


class _FakeFS:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def upload_file(self, data, path):
        self.files[path] = data if isinstance(data, bytes) else str(data).encode()

    def set_file(self, path, content):
        self.files[path] = content.encode() if isinstance(content, str) else content

    def get_file(self, path):
        return self.files[path]


class _FakeProcess:
    def exec(self, command, timeout=None):
        return SimpleNamespace(exit_code=0, result="ok", stderr="")


class _FakeSandbox:
    def __init__(self, sandbox_id="sb-1"):
        self.id = sandbox_id
        self.fs = _FakeFS()
        self.process = _FakeProcess()
        self.deleted = False
        self.stopped = False

    def delete(self):
        self.deleted = True

    def stop(self):
        self.stopped = True


class _FakeDaytona:
    def __init__(self):
        self.created = []
        self.deleted = []
        self.stopped = []
        self.create_kwargs = []

    def create(self, params=None, **kwargs):
        self.create_kwargs.append((params, kwargs))
        sandbox = _FakeSandbox(f"sb-{len(self.created) + 1}")
        self.created.append(sandbox)
        return sandbox

    def delete(self, sandbox):
        self.deleted.append(sandbox)
        sandbox.deleted = True

    def remove(self, sandbox):
        self.deleted.append(sandbox)
        sandbox.deleted = True

    def stop(self, sandbox):
        self.stopped.append(sandbox)
        sandbox.stopped = True


def test_from_config_provider_daytona():
    manager = SandboxManager.from_config({"provider": "daytona"})
    assert isinstance(manager.backend, DaytonaSandbox)
    assert manager.tools_enabled() is True


def test_from_settings_none_is_disabled():
    manager = SandboxManager.from_settings({"settings": {"sandbox": {"provider": "none"}}})
    assert isinstance(manager.backend, DisabledSandbox)


def test_missing_sdk_is_honest(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    backend = DaytonaSandbox()
    result = backend.execute_python("print('hi')")
    assert result.success is False
    assert "daytona" in (result.error or "").lower() or "daytona" in (result.stderr or "").lower()
    assert "pip install" in (result.error or result.stderr or "") or "api key" in (
        result.error or result.stderr or ""
    ).lower()


def test_missing_key_is_honest_when_sdk_present(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "daytona", SimpleNamespace())
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    backend = DaytonaSandbox()
    # Force the import path to succeed then fail on the key.
    monkeypatch.setattr(
        "swarm.core.sandbox.daytona_sandbox.DaytonaSandbox._get_sandbox",
        lambda self: (_ for _ in ()).throw(RuntimeError("Daytona API key missing — set DAYTONA_API_KEY")),
    )
    result = backend.execute_bash("echo hi")
    assert result.success is False
    assert "api key" in (result.error or "").lower()


def test_cleanup_is_noop_without_sandbox():
    backend = DaytonaSandbox()
    backend.cleanup()  # must not raise
    backend.cleanup()


def test_cleanup_deletes_remote_sandbox():
    client = _FakeDaytona()
    sandbox = _FakeSandbox()
    backend = DaytonaSandbox()
    backend._client = client
    backend._sandbox = sandbox
    backend.cleanup()
    assert sandbox in client.deleted
    assert sandbox.deleted is True
    assert backend._sandbox is None
    backend.cleanup()  # idempotent
    assert len(client.deleted) == 1


def test_cleanup_falls_back_to_sandbox_delete_when_client_lacks_api():
    sandbox = _FakeSandbox()
    backend = DaytonaSandbox()
    backend._client = SimpleNamespace()  # no delete/remove/stop
    backend._sandbox = sandbox
    backend.cleanup()
    assert sandbox.deleted is True


def test_cleanup_falls_back_to_stop():
    sandbox = SimpleNamespace(id="sb-stop", stop=lambda: setattr(sandbox, "stopped", True))
    sandbox.stopped = False
    backend = DaytonaSandbox()
    backend._client = SimpleNamespace()
    backend._sandbox = sandbox
    backend.cleanup()
    assert sandbox.stopped is True


def test_create_passes_auto_stop_interval(monkeypatch):
    fake = _FakeDaytona()

    class _Daytona:
        def __init__(self, *_a, **_k):
            pass

        def create(self, params=None, **kwargs):
            return fake.create(params, **kwargs)

    class _Params:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setitem(
        __import__("sys").modules,
        "daytona",
        SimpleNamespace(
            Daytona=_Daytona,
            DaytonaConfig=lambda **k: k,
            CreateSandboxFromSnapshotParams=_Params,
        ),
    )
    monkeypatch.setenv("DAYTONA_API_KEY", "dt_test")
    backend = DaytonaSandbox()
    backend.config.auto_stop_interval = 15
    backend.config.extra_options["auto_stop_interval"] = 15
    created = backend._create_remote(_Daytona())
    assert created is not None
    params, kwargs = fake.create_kwargs[0]
    if params is not None:
        assert getattr(params, "kwargs", {}).get("auto_stop_interval") == 15
    else:
        assert kwargs.get("auto_stop_interval") == 15


def test_sync_workspace_uploads_project_files(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored", encoding="utf-8")
    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "mod.py").write_text("x = 1\n", encoding="utf-8")
    backend = DaytonaSandbox()
    backend._sandbox = _FakeSandbox()
    backend.config.work_dir = str(tmp_path)
    count = backend.sync_workspace()
    assert count == 2
    uploaded = set(backend._sandbox.fs.files)
    assert any(p.endswith("hello.py") for p in uploaded)
    assert any(p.endswith("pkg/mod.py") for p in uploaded)
    assert not any(".git" in p for p in uploaded)


def test_manager_cleanup_destroys_daytona_backend():
    manager = SandboxManager.from_config({"provider": "daytona"})
    fake = _FakeSandbox()
    manager.backend._sandbox = fake
    manager.backend._client = SimpleNamespace()
    manager.cleanup()
    assert fake.deleted is True


def test_probe_daytona_cleans_up(monkeypatch):
    cleaned = {"n": 0}

    class _Mgr:
        def execute_bash(self, command):
            return SimpleNamespace(success=False, stdout="", stderr="Daytona API key missing")

        def cleanup(self):
            cleaned["n"] += 1

    monkeypatch.setattr(
        SandboxManager,
        "from_config",
        classmethod(lambda cls, raw=None: _Mgr()),
    )
    from swarm.views.sandbox_settings_api import probe_sandbox_provider

    result = probe_sandbox_provider("daytona")
    assert result["ok"] is False
    assert cleaned["n"] == 1


def test_install_hint_mentions_pip():
    assert "pip install daytona" in DAYTONA_SDK_INSTALL_HINT


def test_pyproject_declares_sandbox_extra():
    from pathlib import Path

    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "sandbox = [" in text
    assert "daytona>=0.5.0" in text


def test_attach_sandbox_tools_to_agent_daytona():
    from swarm.core.sandbox import attach_sandbox_tools_to_agent

    agent = SimpleNamespace(tools=[])
    attach_sandbox_tools_to_agent(
        agent,
        config={"settings": {"sandbox": {"provider": "daytona"}}},
    )
    names = [getattr(t, "name", getattr(t, "__name__", "")) for t in agent.tools]
    assert "sandbox_run_python" in names
