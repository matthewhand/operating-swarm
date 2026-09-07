"""API tests for /v1/cli-agents/runs/ (REQ-114)."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from rest_framework.test import APIClient

from swarm.core.cli_run_registry import register_cli_run, reset_cli_run_registry

PY = sys.executable


@pytest.fixture
def api_client():
    from django.conf import settings
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_cli_run_registry()
    yield
    reset_cli_run_registry()


def _looping_child() -> subprocess.Popen:
    return subprocess.Popen(
        [PY, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_idle_status_and_terminate(api_client):
    status = api_client.get("/v1/cli-agents/runs/?agent=cli_agent")
    assert status.status_code == 200
    body = status.json()
    assert body["object"] == "cli_run_status"
    assert body["running"] is False

    stopped = api_client.post(
        "/v1/cli-agents/runs/terminate/",
        {"agent": "cli_agent"},
        format="json",
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "not_running"


def test_api_agent_rejected(api_client):
    response = api_client.post(
        "/v1/cli-agents/runs/terminate/",
        {"agent": "api_agent"},
        format="json",
    )
    assert response.status_code == 400
    assert "CLI" in response.json()["error"]

    status = api_client.get("/v1/cli-agents/runs/?agent=api_agent")
    assert status.status_code == 400


def test_team_and_remote_rejected(api_client):
    for agent in ("team:research", "remote:omb"):
        response = api_client.post(
            "/v1/cli-agents/runs/terminate/",
            {"agent": agent},
            format="json",
        )
        assert response.status_code == 400, agent


def test_terminate_looping_cli_leaves_agent(api_client):
    child = _looping_child()
    register_cli_run(
        user_key="u0",
        agent_id="cli_agent",
        conversation_id="conv-loop",
        pid=child.pid,
        pgid=os.getpgid(child.pid),
    )
    try:
        running = api_client.get("/v1/cli-agents/runs/?agent=cli_agent")
        assert running.status_code == 200
        assert running.json()["running"] is True

        stopped = api_client.post(
            "/v1/cli-agents/runs/terminate/",
            {"agent": "cli_agent", "conversation_id": "conv-loop"},
            format="json",
        )
        assert stopped.status_code == 200
        assert stopped.json()["status"] == "terminated"
        child.wait(timeout=5)
        assert child.poll() is not None
        assert _wait_dead(child.pid)

        idle = api_client.get("/v1/cli-agents/runs/?agent=cli_agent")
        assert idle.json()["running"] is False
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
