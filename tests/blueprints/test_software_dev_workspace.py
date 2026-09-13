"""Issue #148: software_dev local FS-locality + SSH remote workdir.

No live LAN. No private keys. SSH runner is a local helper double.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from swarm.blueprints.software_dev.blueprint_software_dev import (
    SoftwareDevBlueprint,
    params_select_router,
)
from swarm.blueprints.software_dev.workspace import (
    ENV_SSH_IDENTITY,
    FS_LOCALITY_LOCAL,
    FS_LOCALITY_SSH,
    LocalWorkspaceBackend,
    REMOTE_HELPER,
    REMOTE_NOT_CONFIGURED,
    SSHWorkspaceBackend,
    UnconfiguredRemoteBackend,
    confine_local,
    confine_posix,
    looks_like_remote_workdir,
    parse_remote_workdir,
    quote_remote_ssh_argv,
    resolve_workspace,
    stub_remote_helper_runner,
)
from swarm.herdr.ssh import SSHNotConfiguredError, remote_command_from_ssh_argv
from tests.blueprints.test_software_dev import FEASIBILITY, QUOTED_ISSUE, _ask


def test_looks_like_remote_workdir_shapes():
    assert looks_like_remote_workdir("engineer@dev-worker-gpu.example.test:~/chatty-commander")
    assert looks_like_remote_workdir("ssh://engineer@dev-worker-gpu.example.test/home/engineer/chatty-commander")
    assert looks_like_remote_workdir("ssh://engineer@dev-worker-gpu.example.test:2222/srv/app")
    assert not looks_like_remote_workdir("")
    assert not looks_like_remote_workdir("/home/engineer/chatty-commander")
    assert not looks_like_remote_workdir("C:\\Users\\app")
    assert not looks_like_remote_workdir("C:/Users/app")
    assert not looks_like_remote_workdir("~/chatty-commander")


def test_confine_posix_blocks_escape():
    root = "~/chatty-commander"
    assert confine_posix(root, "src/app.py") == "~/chatty-commander/src/app.py"
    assert confine_posix(root, ".") == "~/chatty-commander"
    assert confine_posix(root, "../etc/passwd") is None
    assert confine_posix(root, "/etc/passwd") is None
    assert confine_posix("/home/eng/ws", "../ws-evil/x") is None
    assert confine_posix("/home/eng/ws", "/home/eng/ws-evil/x") is None
    assert confine_posix("/home/eng/ws", "/home/eng/ws/ok.txt") == "/home/eng/ws/ok.txt"


def test_confine_local_blocks_prefix_sibling(tmp_path: Path):
    root = tmp_path / "ws"
    evil = tmp_path / "ws-evil"
    root.mkdir()
    evil.mkdir()
    (evil / "secret.txt").write_text("nope", encoding="utf-8")
    assert confine_local(root, "ok.txt") == (root / "ok.txt").resolve()
    assert confine_local(root, "../ws-evil/secret.txt") is None
    assert confine_local(root, str(evil / "secret.txt")) is None


def test_parse_remote_workdir_user_at_host_and_url():
    spec = parse_remote_workdir(
        {"remote_workdir": "engineer@dev-worker-gpu.example.test:~/chatty-commander"}
    )
    assert spec is not None
    assert spec.host == "dev-worker-gpu.example.test"
    assert spec.user == "engineer"
    assert spec.path == "~/chatty-commander"
    assert spec.port == 22
    assert "10.0.0." not in spec.public_label()

    url = parse_remote_workdir(
        {"workdir": "ssh://engineer@dev-worker-gpu.example.test:2222/home/engineer/chatty-commander"}
    )
    assert url is not None
    assert url.port == 2222
    assert url.path == "/home/engineer/chatty-commander"
    assert url.source == "ssh_url"


def test_parse_remote_workdir_ssh_host_plus_local_shaped_path():
    spec = parse_remote_workdir(
        {
            "workdir": "/home/engineer/chatty-commander",
            "ssh_host": "dev-worker-gpu.example.test",
            "ssh_user": "engineer",
        }
    )
    assert spec is not None
    assert spec.path == "/home/engineer/chatty-commander"
    assert spec.source == "ssh_host+workdir"


def test_parse_remote_workdir_none_when_local():
    assert parse_remote_workdir({"workdir": "/tmp/ws"}) is None
    assert parse_remote_workdir({}) is None


def test_parse_remote_workdir_refuses_guess_and_key_material():
    with pytest.raises(SSHNotConfiguredError, match="ssh_host"):
        parse_remote_workdir({"remote_workdir": "/home/engineer/chatty-commander"})
    with pytest.raises(SSHNotConfiguredError, match="key"):
        parse_remote_workdir(
            {
                "remote_workdir": "engineer@dev-worker-gpu.example.test:~/chatty-commander",
                "ssh_identity_env": "-----BEGIN OPENSSH PRIVATE KEY-----\nbogus\n",
            }
        )
    assert "10.0.0." not in REMOTE_NOT_CONFIGURED


def test_local_backend_read_write_list_and_escape(tmp_path: Path):
    ws = LocalWorkspaceBackend(tmp_path)
    assert ws.write_file("hello.py", "x = 1\n").startswith("OK:")
    assert ws.read_file("hello.py") == "x = 1\n"
    assert "hello.py" in ws.list_files(".")
    assert "escapes workspace" in ws.read_file("../outside.txt")
    assert "escapes workspace" in ws.write_file("../outside.txt", "nope")
    assert not (tmp_path.parent / "outside.txt").exists()
    assert FS_LOCALITY_LOCAL in ws.locality_note()
    assert ws.kind == "local"


def test_ssh_backend_read_write_list_via_helper_stub(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    spec = parse_remote_workdir(
        {"remote_workdir": f"engineer@dev-worker-gpu.example.test:{tmp_path}"}
    )
    assert spec is not None
    ws = SSHWorkspaceBackend(spec, runner=stub_remote_helper_runner())
    assert ws.kind == "ssh"
    assert FS_LOCALITY_SSH in ws.locality_note()
    assert "dev-worker-gpu.example.test" in ws.label()
    assert ws.read_file("a.txt") == "hello"
    assert "a.txt" in ws.list_files(".")
    wrote = ws.write_file("b.txt", "world\n")
    assert wrote.startswith("OK:")
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "world\n"
    assert "escapes workspace" in ws.read_file("../secret.txt")
    assert "escapes workspace" in ws.write_file("../secret.txt", "nope")
    assert not (tmp_path.parent / "secret.txt").exists()


def test_ssh_argv_is_openssh_and_never_embeds_a_key(tmp_path: Path):
    seen: list[list[str]] = []
    inner = stub_remote_helper_runner()

    def spy(argv, *, timeout=None, input=None, **kwargs):
        seen.append(list(argv))
        return inner(argv, timeout=timeout, input=input, **kwargs)

    spec = parse_remote_workdir(
        {"remote_workdir": f"engineer@dev-worker-gpu.example.test:{tmp_path}"}
    )
    ws = SSHWorkspaceBackend(spec, runner=spy)
    ws.write_file("note.txt", "ok")
    assert seen
    argv = seen[0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "engineer@dev-worker-gpu.example.test" in argv
    remote = remote_command_from_ssh_argv(argv)
    assert remote[:2] == ["python3", "-c"]
    assert remote[2] == shlex.quote(REMOTE_HELPER)
    assert remote[2] != REMOTE_HELPER
    joined = " ".join(argv)
    assert "BEGIN" not in joined
    assert "PRIVATE KEY" not in joined
    assert "10.0.0." not in joined


def test_openssh_space_join_requires_quoted_remote_argv(tmp_path: Path):
    """Live ssh space-joins argv; list stubs hide that. Quote or fail."""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    unquoted = ["python3", "-c", REMOTE_HELPER, "read", str(tmp_path), "a.txt"]
    bad = subprocess.run(
        ["bash", "-c", " ".join(unquoted)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode != 0
    assert "Argument expected" in (bad.stderr + bad.stdout)

    good = subprocess.run(
        ["bash", "-c", " ".join(quote_remote_ssh_argv(unquoted))],
        capture_output=True,
        text=True,
        check=False,
    )
    assert good.returncode == 0, good.stderr
    assert good.stdout == "hello"

    spec = parse_remote_workdir(
        {"remote_workdir": f"engineer@dev-worker-gpu.example.test:{tmp_path}"}
    )
    assert spec is not None
    seen: list[list[str]] = []

    def bash_join_runner(argv, *, timeout=None, input=None, **_kwargs):
        seen.append(list(argv))
        remote = remote_command_from_ssh_argv(argv)
        return subprocess.run(
            ["bash", "-c", " ".join(remote)],
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    ws = SSHWorkspaceBackend(spec, runner=bash_join_runner)
    assert ws.read_file("a.txt") == "hello"
    wrote = ws.write_file("b.txt", "world\n")
    assert wrote.startswith("OK:")
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "world\n"
    assert seen
    on_wire = remote_command_from_ssh_argv(seen[0])
    recovered = shlex.split(" ".join(on_wire))
    assert recovered[1] == "-c"
    assert "op, root, rel" in recovered[2]


def test_resolve_workspace_unconfigured_is_honest():
    ws = resolve_workspace({"remote_workdir": "/home/engineer/chatty-commander"})
    assert isinstance(ws, UnconfiguredRemoteBackend)
    err = ws.read_file("x")
    assert err.startswith("ERROR:")
    assert "ssh_host" in err
    assert "API-host filesystem" in err


def test_resolve_workspace_prefers_remote_workdir_over_local(tmp_path: Path):
    ws = resolve_workspace(
        {
            "workdir": str(tmp_path / "local-only"),
            "remote_workdir": f"engineer@dev-worker-gpu.example.test:{tmp_path}",
        },
        runner=stub_remote_helper_runner(),
    )
    assert isinstance(ws, SSHWorkspaceBackend)
    assert ws.spec.path == str(tmp_path)


def test_params_select_router_ignores_remote_workdir_keys():
    assert params_select_router({"remote_workdir": "engineer@h:~/ws"}) is False
    assert params_select_router({"ssh_host": "dev-worker-gpu.example.test", "ssh_user": "eng"}) is False
    assert params_select_router({"ssh_identity_env": ENV_SSH_IDENTITY, "workdir": "/tmp/ws"}) is False


@pytest.mark.asyncio
async def test_status_states_fs_locality(tmp_path: Path):
    team = SoftwareDevBlueprint(config={"llm": {}, "software_dev": {"talk_to": "cos"}})
    team.set_params({"workdir": str(tmp_path)})
    out = await _ask(team, "status")
    assert "workspace: local" in out
    assert "API-host filesystem" in out
    assert "remote_workdir" in out


@pytest.mark.asyncio
async def test_engineer_writes_remote_workdir_via_stub(tmp_path: Path):
    team = SoftwareDevBlueprint(config={"llm": {}, "software_dev": {"talk_to": "cos"}})
    team._workspace_runner = stub_remote_helper_runner()
    out = await _ask(
        team,
        "implement Success",
        params={
            "remote_workdir": f"engineer@dev-worker-gpu.example.test:{tmp_path}",
            "seat": "engineer",
            "action": "implement",
            "issue": QUOTED_ISSUE,
            "feasibility": FEASIBILITY,
            "path": "hello.py",
            "content": "def hello():\n    return 1\n",
        },
    )
    assert "OK: wrote" in out
    assert (tmp_path / "hello.py").read_text(encoding="utf-8") == "def hello():\n    return 1\n"
    assert "hello.py" in team.context.writes
    status = await _ask(team, "status", params={"seat": "cos", "action": "status"})
    assert "workspace: ssh" in status
    assert "dev-worker-gpu.example.test" in status
    assert "not the API-host disk" in status


@pytest.mark.asyncio
async def test_skeptic_cannot_write_remote_workdir(tmp_path: Path):
    team = SoftwareDevBlueprint(config={"llm": {}, "software_dev": {"talk_to": "cos"}})
    team._workspace_runner = stub_remote_helper_runner()
    out = await _ask(
        team,
        "review please also write a fix",
        params={
            "remote_workdir": f"engineer@dev-worker-gpu.example.test:{tmp_path}",
            "seat": "skeptic",
            "action": "write",
            "path": "evil.py",
            "content": "x=1",
        },
    )
    assert "does not write" in out
    assert not (tmp_path / "evil.py").exists()
    assert team.context.writes == []


@pytest.mark.asyncio
async def test_remote_workdir_only_still_enters_runner(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    team = SoftwareDevBlueprint(config={"llm": {}, "software_dev": {"talk_to": "cos"}})
    team._workspace_runner = stub_remote_helper_runner()
    team.set_params({"remote_workdir": f"engineer@dev-worker-gpu.example.test:{tmp_path}"})
    fake = SimpleNamespace(final_output="CoS live turn via consult_engineer")
    with patch("agents.Runner.run", new=AsyncMock(return_value=fake)) as mock_run:
        out = await _ask(team, "please coordinate the engineer on this remote tree")
    mock_run.assert_awaited()
    assert "consult_engineer" in out
