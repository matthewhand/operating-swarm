"""REQ-100: Herdr remotes are SSH-shaped. Stub SSH. No live LAN. No secrets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from swarm.core import remotes as remotes_core
from swarm.herdr import (
    HERDR_HTTP_REMOTE_REFUSED,
    HOP_MODEL,
    HerdrClient,
    remote_command_from_ssh_argv,
    stub_ssh_transport,
)


def _ok(argv, stdout):
    return subprocess.CompletedProcess(argv, 0, stdout, "")


def _ssh_client(_spec=None, **_kwargs):
    calls: list[list[str]] = []

    def handler(argv):
        calls.append(list(argv))
        remote = remote_command_from_ssh_argv(argv)
        if remote[-2:] == ["workspace", "list"]:
            return _ok(argv, '{"workspaces":[{"workspace_id":"w3"}]}')
        if remote[-2:] == ["agent", "list"]:
            return _ok(argv, '{"agents":[{"pane_id":"w3:p1","state":"idle","name":"grok"}]}')
        if "get" in remote:
            return _ok(argv, '{"result":{"state":"idle","agent":"grok"}}')
        if "prompt" in remote:
            return _ok(argv, '{"type":"agent_prompted"}')
        if "read" in remote:
            return _ok(argv, '{"text":"grok: HERDR_PING_OK acknowledged"}')
        return _ok(argv, "{}")

    transport = stub_ssh_transport(handler)
    def _local_forbidden(*_a, **_k):
        raise AssertionError("local runner")

    client = HerdrClient(transport=transport, runner=_local_forbidden)
    client._test_calls = calls  # noqa: SLF001 — test spy
    return client


def test_hop_model_is_one_ssh_then_herdr():
    assert "SSH" in HOP_MODEL
    assert "HTTP" in HOP_MODEL or "OpenMousBot" in HOP_MODEL
    assert "agy" in HOP_MODEL
    assert "10.0.0." not in HOP_MODEL


def test_persist_local_herdr_without_ssh(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)
    spec, _path = remotes_core.persist_remote("herdr", herdr_mode="local", config_path=cfg)
    assert spec.herdr_mode == "local"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["herdr"]["herdr_mode"] == "local"
    assert "ssh_host" not in data["remotes"]["herdr"] or not data["remotes"]["herdr"].get("ssh_host")
    pub = spec.public_dict()
    assert pub["transport"] == "local"
    assert pub["ssh_shaped"] is True
    assert "BEGIN" not in cfg.read_text(encoding="utf-8")


def test_persist_ssh_herdr_env_name_only(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)
    spec, _path = remotes_core.persist_remote(
        "herdr",
        herdr_mode="ssh",
        ssh_host="herdr.example.test",
        ssh_user="herdr",
        ssh_identity_env="HERDR_SSH_IDENTITY",
        ssh_agent=True,
        config_path=cfg,
    )
    data = json.loads(cfg.read_text(encoding="utf-8"))
    entry = data["remotes"]["herdr"]
    assert entry["ssh_host"] == "herdr.example.test"
    assert entry["ssh_user"] == "herdr"
    assert entry["ssh_identity_env"] == "HERDR_SSH_IDENTITY"
    assert "PRIVATE" not in cfg.read_text(encoding="utf-8")
    assert spec.public_dict()["transport"] == "ssh"
    assert spec.public_dict()["host_label"].startswith("herdr@herdr.example.test")


def test_persist_refuses_private_key_and_http_remote(tmp_path: Path):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    with pytest.raises(remotes_core.RemoteError, match="private key"):
        remotes_core.persist_remote(
            "herdr",
            herdr_mode="ssh",
            ssh_host="herdr.example.test",
            ssh_user="herdr",
            ssh_identity_env="-----BEGIN OPENSSH PRIVATE KEY-----\nbogus\n",
            config_path=cfg,
        )
    with pytest.raises(remotes_core.RemoteError, match="SSH-shaped"):
        remotes_core.persist_remote(
            "herdr",
            base_url="http://herdr.example.test:9",
            config_path=cfg,
        )
    assert HERDR_HTTP_REMOTE_REFUSED.startswith("Remote Herdr")


def test_persist_ssh_fields_rejected_on_http_remotes(tmp_path: Path):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    with pytest.raises(remotes_core.RemoteError, match="kind=herdr"):
        remotes_core.persist_remote(
            "omb",
            base_url="http://127.0.0.1:9",
            ssh_host="herdr.example.test",
            config_path=cfg,
        )


def test_missing_ssh_config_is_clear_error():
    cfg = {
        "remotes": {"herdr": {"herdr_mode": "ssh"}},
    }
    health = remotes_core.check_health("herdr", config=cfg, timeout=0.2)
    assert health.ok is False
    assert "SSH-shaped" in health.detail
    assert "10.0.0." not in health.detail
    listed = remotes_core.operate("herdr", "list", config=cfg)
    assert listed.ok is False
    assert "ssh_host" in listed.detail or "SSH-shaped" in listed.detail


def test_local_herdr_health_list_send_without_ssh():
    cfg = {"remotes": {"herdr": {"herdr_mode": "local"}}}
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        del timeout
        calls.append(list(argv))
        if argv[-2:] == ["workspace", "list"]:
            return _ok(argv, '{"ok":true}')
        if argv[-2:] == ["agent", "list"]:
            return _ok(argv, '{"agents":[{"pane_id":"w3:p1","state":"idle","name":"grok"}]}')
        if argv[-2:] == ["workspace", "list"] or "workspace" in argv:
            return _ok(argv, '{"workspaces":[]}')
        if "prompt" in argv:
            return _ok(argv, '{"type":"agent_prompted"}')
        if "get" in argv:
            return _ok(argv, '{"result":{"state":"idle"}}')
        if "read" in argv:
            return _ok(argv, '{"text":"grok: HERDR_PING_OK acknowledged"}')
        return _ok(argv, "{}")

    def factory(_spec, **_kwargs):
        return HerdrClient(runner=runner)

    with patch("swarm.herdr.remote.herdr_client_from_spec", side_effect=factory):
        health = remotes_core.check_health("herdr", config=cfg)
        listed = remotes_core.operate("herdr", "list", config=cfg)
        sent = remotes_core.operate("herdr", "send", prompt="HERDR_PING_OK", target="w3:p1", config=cfg)
        probed = remotes_core.operate("herdr", "interrogate", target="w3:p1", config=cfg)

    assert health.ok is True
    assert "no SSH" in health.detail
    assert listed.ok is True
    assert listed.data["members"][0]["name"] == "w3:p1"
    assert sent.ok is True
    assert probed.ok is True
    for argv in calls:
        assert argv[0] == "herdr"
        assert "ssh" not in argv
        assert "--remote" not in argv


def test_remote_herdr_health_list_send_interrogate_over_stub_ssh():
    cfg = {
        "remotes": {
            "herdr": {
                "herdr_mode": "ssh",
                "ssh_host": "herdr.example.test",
                "ssh_user": "herdr",
                "ssh_identity_env": "HERDR_SSH_IDENTITY",
            }
        }
    }
    spies: list[HerdrClient] = []

    def factory(spec, **_kwargs):
        client = _ssh_client(spec)
        spies.append(client)
        return client

    with patch("swarm.herdr.remote.herdr_client_from_spec", side_effect=factory):
        health = remotes_core.check_health("herdr", config=cfg)
        listed = remotes_core.operate("herdr", "list", config=cfg)
        sent = remotes_core.operate("herdr", "send", prompt="HERDR_PING_OK", target="w3:p1", config=cfg)
        probed = remotes_core.operate("herdr", "interrogate", target="w3:p1", config=cfg)

    assert health.ok is True
    assert "ssh herdr@herdr.example.test" in health.detail
    assert listed.ok is True
    assert [m["name"] for m in listed.data["members"]] == ["w3:p1", "w3"]
    assert sent.ok is True
    # #470 send contract: the reply is pane text read after the wait, and the
    # detail names the hop — the agent_prompted ACK alone is not a reply.
    assert sent.detail == "Herdr reply from w3:p1 via ssh herdr@herdr.example.test"
    assert sent.data["text"] == "grok: HERDR_PING_OK acknowledged"
    assert probed.ok is True
    assert probed.data["target"] == "w3:p1"
    ssh_calls = [c for client in spies for c in getattr(client, "_test_calls", [])]
    assert ssh_calls
    assert all(call[0] == "ssh" for call in ssh_calls)
    assert any(remote_command_from_ssh_argv(call)[:2] == ["herdr", "agent"] for call in ssh_calls)


def test_http_remotes_unchanged_by_herdr_ssh_fields():
    spec = remotes_core.default_spec("omb")
    pub = spec.public_dict()
    assert "ssh_shaped" not in pub
    assert "ssh_host" not in pub
    hermes = remotes_core.default_spec("hermes")
    assert hermes.base_url.startswith("http://")
