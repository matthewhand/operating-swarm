"""REQ-860 / #227 — Sandboxes settings: providers, honesty, persistence."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from swarm.core.sandbox import SandboxManager
from swarm.core.sandbox.daytona_sandbox import DaytonaSandbox
from swarm.core.sandbox.disabled_sandbox import DisabledSandbox
from swarm.core.sandbox.local_sandbox import LocalSubprocessSandbox

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _restore_app_config():
    """persist_sandbox_settings() refreshes the global AppConfig.config.

    Snapshot and restore it around every test so these view tests (which
    point the persist path at tmp configs) cannot poison later suites.
    """
    try:
        from django.apps import apps

        app = apps.get_app_config("swarm") if apps.ready else None
    except Exception:
        app = None
    saved = getattr(app, "config", None)
    yield
    if app is not None:
        app.config = saved


# --- provider → backend selection ------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected_cls"),
    [
        ({"backend_type": "none"}, DisabledSandbox),
        ({"backend_type": "mock"}, __import__("swarm.core.sandbox", fromlist=["MockSandbox"]).MockSandbox),
        ({"backend_type": "local"}, LocalSubprocessSandbox),
        ({"backend_type": "bare_metal"}, LocalSubprocessSandbox),  # alias
        ({"backend_type": "daytona"}, DaytonaSandbox),
        ({}, LocalSubprocessSandbox),  # legacy default
    ],
)
def test_provider_selection(raw, expected_cls):
    manager = SandboxManager.from_config(raw)
    assert isinstance(manager.backend, expected_cls)


def test_disabled_backend_is_honest():
    manager = SandboxManager.from_config({"backend_type": "none"})
    result = manager.execute_python("print('hi')")
    assert result.success is False
    assert "disabled" in (result.stderr or "").lower()
    assert result.exit_code != 0


def test_daytona_without_sdk_is_honest(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    manager = SandboxManager.from_config({"backend_type": "daytona"})
    result = manager.execute_python("print('hi')")
    assert result.success is False
    assert "daytona" in (result.error or "").lower()
    assert "pip install" in (result.error or "") or "api key" in (result.error or "").lower()


def test_daytona_env_name_resolution(monkeypatch):
    monkeypatch.setenv("MY_DAYTONA_KEY", "secret-token")
    backend = DaytonaSandbox()
    backend.config.extra_options["daytona_api_key_env"] = "MY_DAYTONA_KEY"
    assert backend._api_key() == "secret-token"
    monkeypatch.delenv("MY_DAYTONA_KEY")
    assert backend._api_key() == ""  # missing key → empty, honest failure later


# --- make_agent attachment gating ------------------------------------------


def _make_agent_config(settings_block):
    return {"llm": {}, "settings": settings_block}


def _bare_blueprint(settings_block, monkeypatch):
    """Bare BlueprintBase whose Agent() constructor is captured hermetically."""
    import agents

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    # make_agent does `from agents import Agent` at call time — patch the
    # attribute on the source module so the local import sees the fake.
    monkeypatch.setattr(agents, "Agent", FakeAgent)
    import swarm.core.blueprint_base as bb

    class _ConcreteBP(bb.BlueprintBase):
        async def run(self, *a, **k):  # pragma: no cover — never invoked
            yield {}

    bp = _ConcreteBP.__new__(_ConcreteBP)
    bp._config = _make_agent_config(settings_block)
    bp._resolve_llm_profile = lambda *a, **k: "stub-profile"
    bp._get_model_instance = lambda profile=None: object()
    bp._get_memory_instance = lambda *a, **k: None
    return bp, captured


def test_make_agent_none_provider_attaches_no_sandbox_tools(monkeypatch):
    bp, captured = _bare_blueprint(
        {"sandbox": {"provider": "none"}, "enable_sandbox_tools": True}, monkeypatch
    )
    bp.make_agent(name="t", instructions="i", tools=[])
    assert "sandbox_run_python" not in str(captured.get("tools", []))


def test_make_agent_daytona_provider_attaches_tools(monkeypatch):
    bp, captured = _bare_blueprint(
        {"sandbox": {"provider": "daytona", "enable_sandbox_tools": True}}, monkeypatch
    )
    bp.make_agent(name="t", instructions="i", tools=[])
    assert "sandbox_run_python" in str(captured.get("tools", []))


# --- settings view ----------------------------------------------------------


def test_settings_get_defaults():
    client = APIClient()
    url = reverse("sandbox-settings")
    response = client.get(url)
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "none"
    assert [p["id"] for p in body["providers"]] == ["none", "bare_metal", "daytona"]
    assert body["providers"][1]["dangerous"] is True


def test_settings_put_bare_metal_requires_confirm(tmp_path, monkeypatch):
    from swarm.views.sandbox_settings_api import persist_sandbox_settings

    cfg = tmp_path / "swarm_config.json"
    cfg.write_text('{"llm": {}, "settings": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="dangerous"):
        persist_sandbox_settings(provider="bare_metal", config_path=str(cfg))
    block, _ = persist_sandbox_settings(
        provider="bare_metal", confirm_dangerous=True, config_path=str(cfg)
    )
    assert block["provider"] == "bare_metal"
    assert block["dangerous_confirmed"] is True
    # Switching away clears the confirmation.
    block2, _ = persist_sandbox_settings(provider="none", config_path=str(cfg))
    assert block2["dangerous_confirmed"] is False


def test_settings_put_rejects_unknown_provider(tmp_path):
    from swarm.views.sandbox_settings_api import persist_sandbox_settings

    cfg = tmp_path / "swarm_config.json"
    cfg.write_text('{"llm": {}, "settings": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown sandbox provider"):
        persist_sandbox_settings(provider="chaos", config_path=str(cfg))


def test_settings_put_rejects_plaintext_key(tmp_path):
    from swarm.views.sandbox_settings_api import persist_sandbox_settings

    cfg = tmp_path / "swarm_config.json"
    cfg.write_text('{"llm": {}, "settings": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="env-var NAME"):
        persist_sandbox_settings(daytona_api_key_env="dt_abc123secret", config_path=str(cfg))


def test_settings_put_round_trip(tmp_path):
    import json

    from swarm.views.sandbox_settings_api import persist_sandbox_settings

    cfg = tmp_path / "swarm_config.json"
    cfg.write_text('{"llm": {}, "settings": {}}', encoding="utf-8")
    block, _ = persist_sandbox_settings(
        provider="daytona",
        enable_sandbox_tools=True,
        timeout_seconds=45,
        daytona_api_key_env="DAYTONA_API_KEY",
        daytona_api_url="https://app.daytona.io/api",
        config_path=str(cfg),
    )
    assert block["provider"] == "daytona"
    on_disk = json.loads(cfg.read_text(encoding="utf-8"))
    saved = on_disk["settings"]["sandbox"]
    assert saved["provider"] == "daytona"
    assert saved["daytona_api_key_env"] == "DAYTONA_API_KEY"
    assert "token" not in json.dumps(saved)  # no secrets on disk
    assert saved["timeout_seconds"] == 45


# --- test-probe endpoint -----------------------------------------------------


def test_probe_none_is_disabled_note():
    from swarm.views.sandbox_settings_api import probe_sandbox_provider

    result = probe_sandbox_provider("none")
    assert result["ok"] is True
    assert "disabled" in result["detail"].lower()


def test_probe_bare_metal_executes_python():
    from swarm.views.sandbox_settings_api import probe_sandbox_provider

    result = probe_sandbox_provider("bare_metal")
    assert result["ok"] is True
    assert "ok" in result["detail"]


def test_probe_daytona_honest_without_sdk(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    from swarm.views.sandbox_settings_api import probe_sandbox_provider

    result = probe_sandbox_provider("daytona")
    assert result["ok"] is False
    assert "daytona" in result["detail"].lower()


def test_view_put_and_test_round_trip(tmp_path, monkeypatch):
    from django.test import override_settings

    from swarm.core import remotes as remotes_core

    monkeypatch.setattr(remotes_core, "resolve_config_path", lambda explicit=None: tmp_path / "cfg.json")
    client = APIClient()
    url = reverse("sandbox-settings")
    response = client.put(
        url,
        {"provider": "bare_metal", "confirm_dangerous": True, "enable_sandbox_tools": True},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["provider"] == "bare_metal"
    probe = client.post(reverse("sandbox-settings-test"), {"provider": "bare_metal"}, format="json")
    assert probe.status_code == 200
    assert probe.json()["ok"] is True
