"""#728 / #740 — Herdr chat send ergonomics.

#728: a chat send to the ``herdr`` remote without an explicit target used to
die with ``target is required (Herdr pane / CLI id, e.g. w3:p1 or grok)`` —
correct refusal, zero help. When the workspace runs exactly one member, the
send can safely auto-target it; when several exist the error must list them
so the user can pick.

#740: a blocked pane (CLI sitting at an approval/question prompt) must
surface WHAT it is asking (the pane's recent text) and how to answer, not a
bare ``submit rejected``.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from swarm.core import remotes as remotes_core


def _runner_single(pane: str):
    """Fake herdr CLI runner: one member, answers prompts with HERDR_PONG."""

    def runner(argv, timeout=None):
        import subprocess

        del timeout
        if "list" in argv:
            payload = {"result": {"agents": [{"name": "grok", "target": pane}]}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
        if "get" in argv:
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"result": {"state": "idle"}}), ""
            )
        if "read" in argv:
            return subprocess.CompletedProcess(argv, 0, "HERDR_PONG", "")
        return subprocess.CompletedProcess(argv, 0, '{"type":"agent_prompted"}', "")

    return runner


CFG = {"remotes": {"herdr": {"herdr_mode": "local"}}}


def _setup(monkeypatch, runner):
    from swarm.herdr.remote import herdr_client_from_spec as real_factory

    def spy(spec=None, **kwargs):
        kwargs.setdefault("runner", runner)
        return real_factory(spec, **kwargs)

    monkeypatch.setattr(
        "swarm.herdr.remote.herdr_client_from_spec", staticmethod(spy)
    )
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)


def test_send_without_target_auto_selects_the_single_member(monkeypatch):
    """#728: one member in the workspace → the send targets it automatically."""
    _setup(monkeypatch, _runner_single("w3:p1"))
    sent = remotes_core.operate("herdr", "send", prompt="ping", config=CFG, timeout=1.0)
    assert sent.ok is True
    assert sent.data["text"] == "HERDR_PONG"
    assert sent.data.get("target") == "w3:p1"


def test_send_without_target_lists_members_when_ambiguous(monkeypatch):
    """#728: several members → honest error naming the choices, no send."""

    def runner(argv, timeout=None):
        import subprocess

        del timeout
        if "list" in argv:
            payload = {
                "result": {
                    "agents": [
                        {"name": "grok", "target": "w3:p1"},
                        {"name": "aider", "target": "w4:p2"},
                    ]
                }
            }
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
        raise AssertionError("no other CLI call should happen before a target exists")

    _setup(monkeypatch, runner)
    sent = remotes_core.operate("herdr", "send", prompt="ping", config=CFG, timeout=1.0)
    assert sent.ok is False
    assert "w3:p1" in sent.detail and "w4:p2" in sent.detail
    # #787: rows carry friendly display labels — 'Grok', not the raw CLI id.
    assert "Grok" in sent.detail and "Aider" in sent.detail


def test_blocked_pane_surfces_the_pending_prompt_and_unblock_hint(monkeypatch):
    """#740: blocked → show what the agent is asking + how to answer."""

    def runner(argv, timeout=None):
        import subprocess

        del timeout
        if "list" in argv:
            payload = {"result": {"agents": [{"name": "grok", "target": "w3:p1"}]}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
        if "get" in argv:
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"result": {"state": "blocked"}}), ""
            )
        if "read" in argv:
            return subprocess.CompletedProcess(
                argv, 0, "Allow write access to ./src? [y/N]", ""
            )
        raise AssertionError("prompt must not be sent to a blocked pane")

    _setup(monkeypatch, runner)
    sent = remotes_core.operate("herdr", "send", prompt="go on", config=CFG, timeout=1.0)
    assert sent.ok is False
    assert "blocked" in sent.detail.lower()
    assert "Allow write access to ./src? [y/N]" in sent.detail, (
        "the pending question text must be surfaced so the user knows what to answer"
    )
    assert "w3:p1" in sent.detail, "the unblock target must be named"
