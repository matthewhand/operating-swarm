"""#720 — per-agent sandbox display endpoint for the computer pane.

GET /v1/agents/<id>/sandbox-display/ returns an honest, secret-free display
payload for the agent's effective sandbox:

- provider != daytona (incl. ``none``) → ``{"display": None, "reason":
  "provider_not_daytona", "provider": <name>}``
- provider == daytona but no live sandbox → ``{"display": None, "reason":
  "no_active_sandbox", "provider": "daytona"}``
- live sandbox with preview port → ``{"display": {"kind": "iframe",
  "url": <preview link>}, "provider": "daytona"}``

Never echoes API keys or tokens. The resolver lives in
``swarm.core.sandbox.display`` so the endpoint stays a thin shell.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from swarm.core.sandbox.display import resolve_sandbox_display
from swarm.core.sandbox.manager import SandboxManager
from swarm.core.sandbox.mock_sandbox import MockSandbox

pytestmark = pytest.mark.django_db


# --- resolver ---------------------------------------------------------------


def test_resolver_none_provider_is_honest_empty():
    payload = resolve_sandbox_display({"settings": {"sandbox": {"provider": "none"}}})
    assert payload["display"] is None
    assert payload["reason"] == "provider_not_daytona"
    assert payload["provider"] == "none"


def test_resolver_daytona_without_key_reports_no_active_sandbox(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    payload = resolve_sandbox_display({"settings": {"sandbox": {"provider": "daytona"}}})
    assert payload["display"] is None
    assert payload["reason"] == "no_active_sandbox"
    assert payload["provider"] == "daytona"


def test_resolver_surfaces_preview_url_from_live_sandbox():
    sandbox = MockSandbox()
    sandbox.preview_url = "https://example.invalid/preview/"  # type: ignore[attr-defined]
    manager = SandboxManager(backend=sandbox)
    payload = resolve_sandbox_display(
        {"settings": {"sandbox": {"provider": "daytona"}}},
        manager=manager,
    )
    assert payload["display"] == {
        "kind": "iframe",
        "url": "https://example.invalid/preview/",
    }
    assert payload["provider"] == "daytona"


def test_resolver_never_echoes_secrets(monkeypatch):
    monkeypatch.setenv("DAYTONA_API_KEY", "sk-super-secret")
    payload = resolve_sandbox_display({"settings": {"sandbox": {"provider": "daytona"}}})
    blob = repr(payload)
    assert "sk-super-secret" not in blob


# --- endpoint ---------------------------------------------------------------


def test_endpoint_returns_display_payload():
    client = APIClient()
    url = reverse("agent-sandbox-display", kwargs={"agent_id": "example_api_minimal"})
    response = client.get(url)
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"agent_id", "provider", "display"}
    # Default config has no daytona provider — must be an honest empty state,
    # never a fabricated screenshot.
    assert body["display"] is None
    assert body["reason"] in {"provider_not_daytona", "no_active_sandbox"}
