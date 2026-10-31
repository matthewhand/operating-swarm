"""Unit tests for Phase 2 container and microVM sandboxes (DockerSandbox and E2BSandbox)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from swarm.core.sandbox import (
    DockerSandbox,
    E2BSandbox,
    SandboxConfig,
    SandboxManager,
)


class TestDockerSandbox:
    def test_init_defaults(self, tmp_path):
        cfg = SandboxConfig(backend_type="docker", work_dir=str(tmp_path))
        sbx = DockerSandbox(cfg)
        assert sbx.image == "python:3.12-slim"
        assert sbx.network == "none"
        assert sbx.cpus == "1.0"
        assert sbx.memory == "512m"
        assert sbx.work_dir == tmp_path.resolve()

    def test_is_available_when_missing_binary(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        sbx = DockerSandbox()
        assert not sbx.is_available()

    def test_is_available_when_daemon_responding(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/docker")
        mock_proc = MagicMock(returncode=0)
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_proc)
        sbx = DockerSandbox()
        assert sbx.is_available()

    def test_execute_bash_unavailable(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        sbx = DockerSandbox()
        res = sbx.execute_bash("echo hi")
        assert not res.success
        assert res.exit_code == 127
        assert "unavailable" in res.error.lower()

    def test_execute_bash_success(self, monkeypatch, tmp_path):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/docker")
        mock_info = MagicMock(returncode=0)
        mock_run = MagicMock(returncode=0, stdout="hello from container\n", stderr="")

        def fake_run(cmd, *args, **kwargs):
            if "info" in cmd:
                return mock_info
            return mock_run

        monkeypatch.setattr("subprocess.run", fake_run)
        sbx = DockerSandbox(SandboxConfig(backend_type="docker", work_dir=str(tmp_path)))
        res = sbx.execute_bash("echo 'hello from container'")
        assert res.success
        assert "hello from container" in res.stdout
        assert res.metadata.get("backend") == "docker"

    def test_execute_python(self, monkeypatch, tmp_path):
        sbx = DockerSandbox(SandboxConfig(backend_type="docker", work_dir=str(tmp_path)))
        executed_cmds = []

        def fake_execute_bash(cmd, timeout=None):
            executed_cmds.append(cmd)
            return MagicMock(success=True)

        monkeypatch.setattr(sbx, "execute_bash", fake_execute_bash)
        sbx.execute_python("print(1 + 1)")
        assert len(executed_cmds) == 1
        assert "python3 -c" in executed_cmds[0]

    def test_file_read_write_and_path_escape(self, tmp_path):
        sbx = DockerSandbox(SandboxConfig(backend_type="docker", work_dir=str(tmp_path)))
        assert sbx.write_file("test.txt", "content")
        assert sbx.read_file("test.txt") == "content"

        with pytest.raises(PermissionError):
            sbx.read_file("../escape.txt")

        with pytest.raises(PermissionError):
            sbx.write_file("../escape.txt", "evil")


class TestE2BSandbox:
    def test_is_available_without_key(self, monkeypatch):
        monkeypatch.delenv("E2B_API_KEY", raising=False)
        sbx = E2BSandbox(SandboxConfig(backend_type="e2b"))
        assert not sbx.is_available()

    def test_execute_when_unavailable(self, monkeypatch):
        monkeypatch.delenv("E2B_API_KEY", raising=False)
        sbx = E2BSandbox(SandboxConfig(backend_type="e2b"))
        res_py = sbx.execute_python("print(1)")
        assert not res_py.success
        assert "unavailable" in res_py.error.lower()

        res_sh = sbx.execute_bash("ls")
        assert not res_sh.success
        assert "unavailable" in res_sh.error.lower()

    def test_execute_python_with_mocked_instance(self, monkeypatch):
        sbx = E2BSandbox(SandboxConfig(backend_type="e2b", e2b_api_key="e2b_test_key"))
        monkeypatch.setattr(sbx, "is_available", lambda: True)

        mock_execution = MagicMock()
        mock_execution.logs.stdout = ["e2b output"]
        mock_execution.logs.stderr = []
        mock_execution.error = None

        mock_inst = MagicMock()
        mock_inst.run_code.return_value = mock_execution
        sbx._sandbox_instance = mock_inst

        res = sbx.execute_python("print('e2b output')")
        assert res.success
        assert "e2b output" in res.stdout
        assert res.metadata.get("backend") == "e2b"

    def test_cleanup(self):
        sbx = E2BSandbox(SandboxConfig(backend_type="e2b", e2b_api_key="e2b_test_key"))
        mock_inst = MagicMock()
        sbx._sandbox_instance = mock_inst
        sbx.cleanup()
        assert mock_inst.close.called
        assert sbx._sandbox_instance is None


class TestSandboxManagerContainerWiring:
    def test_manager_instantiates_docker(self, tmp_path):
        mgr = SandboxManager.from_config({"provider": "docker", "work_dir": str(tmp_path)})
        assert isinstance(mgr.backend, DockerSandbox)

    def test_manager_instantiates_e2b(self):
        mgr = SandboxManager.from_config({"provider": "e2b", "e2b_api_key": "dummy"})
        assert isinstance(mgr.backend, E2BSandbox)
