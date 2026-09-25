"""#1144 — a herdr seat bound to a pane that no longer exists.

The 2026-09-25 incident: seat target ``w3:p7`` was deleted from the herdr
workspace; every send dumped raw CLI JSON into the chat
(``herdr send: FAIL — Herdr send failed: {"error":{"code":"agent_not_found",...}}``).

Contracts:
- The client distinguishes ``agent_not_found`` (``HerdrAgentMissingError``)
  from generic CLI errors.
- The send path answers with a friendly, actionable detail (rebind hint,
  which live panes exist) and structured ``missing: True`` data — never a
  raw JSON blob.
- Other CLI failures keep the existing ``Herdr send failed: …`` shape.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from swarm.core import remotes as remotes_core
from swarm.herdr.client import HerdrAgentMissingError, HerdrClient

CFG = {"remotes": {"herdr": {"herdr_mode": "local"}}}
GONE = "w3:p7"
LIVE = "w3:p2"


def _runner_missing_pane(pane: str):
    """herdr CLI stub: the target pane is gone; one other pane is live."""

    def runner(argv, timeout=None):
        import subprocess

        del timeout
        missing = json.dumps(
            {"error": {"code": "agent_not_found", "message": f"agent target {pane} not found"}}
        )
        if "list" in argv:
            payload = {"result": {"agents": [{"name": "omp", "target": LIVE}]}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
        if "get" in argv or "prompt" in argv:
            return subprocess.CompletedProcess(argv, 1, missing, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    return runner


def test_client_raises_missing_error_for_agent_not_found():
    """agent get on a deleted pane raises HerdrAgentMissingError, not CLIError."""

    def runner(argv, timeout=None):
        import subprocess

        del timeout
        body = json.dumps(
            {"error": {"code": "agent_not_found", "message": f"agent target {GONE} not found"}}
        )
        return subprocess.CompletedProcess(argv, 1, body, "")

    client = HerdrClient(runner=runner)
    with pytest.raises(HerdrAgentMissingError) as excinfo:
        client.agent_get(GONE)
    assert excinfo.value.target == GONE


def test_send_to_missing_pane_is_friendly_and_actionable():
    """The chat detail names the rebind path and live panes — no raw JSON."""

    def runner(argv, timeout=None):
        import subprocess

        del timeout
        missing = json.dumps(
            {"error": {"code": "agent_not_found", "message": f"agent target {GONE} not found"}}
        )
        if "list" in argv:
            payload = {"result": {"agents": [{"name": "omp", "target": LIVE}]}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
        if "get" in argv or "prompt" in argv:
            return subprocess.CompletedProcess(argv, 1, missing, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with patch(
        "swarm.herdr.remote.herdr_client_from_spec",
        side_effect=lambda spec=None, **kw: HerdrClient(runner=runner),
    ):
        sent = remotes_core.operate(
            "herdr", "send", prompt="ping", target=GONE, config=CFG, timeout=1.0
        )

    assert sent.ok is False
    assert "no longer exists" in sent.detail
    assert "Rebind" in sent.detail
    assert '{"error"' not in sent.detail
    assert sent.data.get("missing") is True
    assert sent.data.get("target") == GONE
    assert LIVE in (sent.data.get("available") or [])


def test_other_cli_failures_keep_the_existing_shape():
    """Non-missing CLI errors still render the classic ``Herdr send failed``."""

    def runner(argv, timeout=None):
        import subprocess

        del timeout
        if "get" in argv or "prompt" in argv:
            return subprocess.CompletedProcess(argv, 1, "boom", "explosion")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with patch(
        "swarm.herdr.remote.herdr_client_from_spec",
        side_effect=lambda spec=None, **kw: HerdrClient(runner=runner),
    ):
        sent = remotes_core.operate(
            "herdr", "send", prompt="ping", target=GONE, config=CFG, timeout=1.0
        )

    assert sent.ok is False
    assert "Herdr send failed" in sent.detail
