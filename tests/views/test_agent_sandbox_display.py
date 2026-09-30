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

import importlib.util
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


@pytest.mark.skipif(
    importlib.util.find_spec("daytona") is None,
    reason="requires the daytona SDK (optional `sandbox` extra); without it the "
    "probe reports sdk_missing, whose operator hint does not name the env var",
)
def test_resolver_daytona_reports_credential_path_and_preflight(monkeypatch):
    """#720: an unreachable Daytona reports the env-var NAME (never a value)
    and an honest offline preflight classification + operator hint."""
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    payload = resolve_sandbox_display(
        {"settings": {"sandbox": {"provider": "daytona", "daytona_api_key_env": "MY_DAYTONA_KEY"}}}
    )
    assert payload["provider"] == "daytona"
    assert payload["display"] is None
    assert payload["reason"] == "no_active_sandbox"
    assert payload["available"] is False
    assert payload["sandbox"] is None
    assert payload["credential"] == {"env_var": "MY_DAYTONA_KEY", "set": False}
    assert payload["probe"]["ok"] is False
    assert payload["probe"]["classification"] in {"sdk_missing", "env_name_unset"}
    assert "MY_DAYTONA_KEY" in payload["probe"]["operator_hint"]


def test_resolver_reports_live_sandbox_state_and_status(monkeypatch):
    """#720: a live sandbox exposes its id/status without recreating a VM."""
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    sandbox = MockSandbox()
    sandbox.preview_url = "https://example.invalid/preview/"  # type: ignore[attr-defined]
    sandbox.sandbox_id = "vm-42"  # type: ignore[attr-defined]
    sandbox.sandbox_status = "started"  # type: ignore[attr-defined]
    manager = SandboxManager(backend=sandbox)
    payload = resolve_sandbox_display(
        {"settings": {"sandbox": {"provider": "daytona"}}},
        manager=manager,
    )
    assert payload["available"] is True
    assert payload["sandbox"] == {"id": "vm-42", "status": "started"}
    assert payload["display"] == {
        "kind": "iframe",
        "url": "https://example.invalid/preview/",
    }


def test_resolver_uses_registered_live_sandbox():
    """#720: the display finds a VM created by a different request's manager."""
    from swarm.core.sandbox.registry import clear_live_sandboxes, register_live_sandbox

    clear_live_sandboxes()
    live = MockSandbox()
    live.preview_url = "https://example.invalid/live/"  # type: ignore[attr-defined]
    live.sandbox_id = "vm-registry"  # type: ignore[attr-defined]
    register_live_sandbox(live)
    try:
        # A fresh manager (its backend has no live sandbox) must still resolve
        # the registered VM rather than falling back to an empty state.
        manager = SandboxManager(backend=MockSandbox())
        payload = resolve_sandbox_display(
            {"settings": {"sandbox": {"provider": "daytona"}}},
            manager=manager,
        )
        assert payload["sandbox"]["id"] == "vm-registry"
        assert payload["display"]["url"] == "https://example.invalid/live/"
    finally:
        clear_live_sandboxes()


def test_resolver_sandbox_without_preview_is_honest(monkeypatch):
    """A live VM with no preview URL is ``no_preview_url``, not fabricated."""
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    sandbox = MockSandbox()
    sandbox.sandbox_id = "vm-nopreview"  # type: ignore[attr-defined]
    manager = SandboxManager(backend=sandbox)
    payload = resolve_sandbox_display(
        {"settings": {"sandbox": {"provider": "daytona"}}},
        manager=manager,
    )
    assert payload["display"] is None
    assert payload["reason"] == "no_preview_url"
    assert payload["sandbox"] == {"id": "vm-nopreview", "status": None}



# --- endpoint ---------------------------------------------------------------


def test_endpoint_returns_display_payload(api_client):
    url = reverse("agent-sandbox-display", kwargs={"agent_id": "example_api_minimal"})
    response = api_client.get(url)
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"agent_id", "provider", "display"}
    # Default config has no daytona provider — must be an honest empty state,
    # never a fabricated screenshot.
    assert body["display"] is None
    assert body["reason"] in {"provider_not_daytona", "no_active_sandbox"}
