"""REQ-100 SSH transport — stub only. No live LAN. No private keys."""

from __future__ import annotations

import subprocess

import pytest
from helpers.private_net import assert_no_private_ip

from swarm.herdr.ssh import (
    SSH_NOT_CONFIGURED,
    SSHNotConfiguredError,
    SSHTarget,
    SSHTransport,
    looks_like_key_material,
    remote_command_from_ssh_argv,
    require_ssh_target,
    resolve_identity_path,
    stub_ssh_transport,
)


def _ok(argv, stdout="{}"):
    return subprocess.CompletedProcess(argv, 0, stdout, "")


def test_require_ssh_target_missing_host_or_user():
    with pytest.raises(SSHNotConfiguredError, match="SSH-shaped"):
        require_ssh_target(host="", user="herdr")
    with pytest.raises(SSHNotConfiguredError, match="ssh_host"):
        require_ssh_target(host="herdr.example.test", user="")
    assert_no_private_ip(SSH_NOT_CONFIGURED)
    assert "OpenMousBot" in SSH_NOT_CONFIGURED


def test_build_ssh_argv_user_host_and_port():
    transport = SSHTransport(SSHTarget(host="herdr.example.test", user="herdr", port=2222))
    argv = transport.build_ssh_argv(["herdr", "agent", "list"])
    assert argv[0] == "ssh"
    assert "-o" in argv and "BatchMode=yes" in argv
    assert argv[argv.index("-p") + 1] == "2222"
    assert "herdr@herdr.example.test" in argv
    assert remote_command_from_ssh_argv(argv) == ["herdr", "agent", "list"]
    assert "--remote" not in argv


def test_identity_env_is_path_not_key(tmp_path, monkeypatch):
    key_path = tmp_path / "id_ed25519"
    key_path.write_text("not-a-real-key\n", encoding="utf-8")
    monkeypatch.setenv("HERDR_SSH_IDENTITY", str(key_path))
    transport = SSHTransport(
        SSHTarget(
            host="herdr.example.test",
            user="herdr",
            identity_env="HERDR_SSH_IDENTITY",
            use_agent=False,
        )
    )
    argv = transport.build_ssh_argv(["herdr", "workspace", "list"])
    assert "-i" in argv
    assert str(key_path) in argv
    assert "BEGIN" not in " ".join(argv)
    assert "PRIVATE KEY" not in " ".join(argv)


def test_identity_env_unset_is_clear_error(monkeypatch):
    monkeypatch.delenv("HERDR_SSH_IDENTITY", raising=False)
    with pytest.raises(SSHNotConfiguredError, match="empty"):
        resolve_identity_path("HERDR_SSH_IDENTITY")


def test_identity_env_key_material_refused():
    with pytest.raises(SSHNotConfiguredError, match="key material"):
        resolve_identity_path(
            "HERDR_SSH_IDENTITY",
            environ={"HERDR_SSH_IDENTITY": "-----BEGIN OPENSSH PRIVATE KEY-----\nbogus\n"},
        )
    assert looks_like_key_material("-----BEGIN OPENSSH PRIVATE KEY-----\nx\n")
    assert looks_like_key_material("ssh-ed25519 AAAA fake")
    assert not looks_like_key_material("/home/herdr/.ssh/id_ed25519")


def test_stub_transport_never_opens_ssh():
    seen: list[list[str]] = []

    def handler(argv):
        seen.append(list(argv))
        return _ok(argv, '{"ok":true}')

    transport = stub_ssh_transport(handler)
    result = transport.run(["herdr", "agent", "list"])
    assert result.returncode == 0
    assert seen[0][0] == "ssh"
    assert remote_command_from_ssh_argv(seen[0]) == ["herdr", "agent", "list"]
    assert_no_private_ip(" ".join(seen[0]))


def test_no_agent_and_no_identity_is_clear_error():
    transport = SSHTransport(
        SSHTarget(host="herdr.example.test", user="herdr", use_agent=False)
    )
    with pytest.raises(SSHNotConfiguredError, match="ssh_identity_env"):
        transport.build_ssh_argv(["herdr", "agent", "list"])
