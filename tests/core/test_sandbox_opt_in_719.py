"""#719 — optional per-agent Daytona sandbox tools: opt-in, degrade, tools.

Contracts:
- ``normalize_sandbox_param`` validates the per-agent ``sandbox`` param:
  provider allow-list, env-var *name* only (never key material), never a
  bare token.
- ``make_agent`` honours the per-agent opt-in from ``self._params``: a
  ``sandbox`` param wins over an absent/``none`` settings block (opt-in),
  and ``{"provider": "none"}`` opts *out* even when settings enable tools.
- The tool surface degrades honestly: a Daytona backend with no key returns
  an explicit ``not configured`` message, never a raised exception.
- Toolset completeness: upload/download round-trip through the manager.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from swarm.core.sandbox.manager import SandboxManager
from swarm.core.sandbox.opt_in import normalize_sandbox_param

pytestmark = pytest.mark.django_db


# --- param validation --------------------------------------------------------


def test_normalize_accepts_daytona_opt_in():
    out = normalize_sandbox_param({"provider": "daytona"})
    assert out == {"provider": "daytona"}


def test_normalize_accepts_env_name_and_clamps_extras():
    out = normalize_sandbox_param(
        {"provider": "daytona", "daytona_api_key_env": "MY_DAYTONA_KEY", "timeout_seconds": 45}
    )
    assert out["provider"] == "daytona"
    assert out["daytona_api_key_env"] == "MY_DAYTONA_KEY"
    assert out["timeout_seconds"] == 45


def test_normalize_rejects_unknown_provider():
    with pytest.raises(ValueError, match="provider"):
        normalize_sandbox_param({"provider": "hyperion"})


def test_normalize_rejects_key_material():
    with pytest.raises(ValueError, match="env"):
        normalize_sandbox_param(
            {"provider": "daytona", "daytona_api_key_env": "-----BEGIN RSA PRIVATE KEY-----"}
        )
    with pytest.raises(ValueError, match="env"):
        normalize_sandbox_param({"provider": "daytona", "daytona_api_key": "sk-live-xyz"})


def test_normalize_rejects_non_dict():
    with pytest.raises(ValueError):
        normalize_sandbox_param("daytona")  # type: ignore[arg-type]


# --- make_agent per-agent opt-in ---------------------------------------------


def _bare_blueprint(settings_block, monkeypatch):
    from tests.views.test_sandbox_settings import _bare_blueprint as factory

    return factory(settings_block, monkeypatch)


def test_params_opt_in_attaches_tools_when_settings_none(monkeypatch):
    bp, captured = _bare_blueprint({"sandbox": {"provider": "none"}}, monkeypatch)
    bp._params = {"sandbox": {"provider": "daytona"}}
    bp.make_agent(name="t", instructions="i", tools=[])
    assert "sandbox_run_python" in str(captured.get("tools", []))


def test_params_opt_out_beats_settings_enabled(monkeypatch):
    bp, captured = _bare_blueprint(
        {"sandbox": {"provider": "daytona", "enable_sandbox_tools": True}}, monkeypatch
    )
    bp._params = {"sandbox": {"provider": "none"}}
    bp.make_agent(name="t", instructions="i", tools=[])
    assert "sandbox_run_python" not in str(captured.get("tools", []))


def test_params_invalid_sandbox_is_ignored_not_fatal(monkeypatch):
    bp, captured = _bare_blueprint({"sandbox": {"provider": "none"}}, monkeypatch)
    bp._params = {"sandbox": {"provider": "sk-live-xyz"}}
    bp.make_agent(name="t", instructions="i", tools=[])
    assert "sandbox_run_python" not in str(captured.get("tools", []))


# --- honest degrade + toolset completeness ------------------------------------


def test_daytona_tools_without_key_degrade_to_explicit_message(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    manager = SandboxManager.from_config({"provider": "daytona"})
    tools = manager.get_raw_tools()
    out = tools["sandbox_run_python"]("print('hi')")
    # Honest degrade: names the actual cause (no key, or SDK absent) and never raises.
    assert (
        "not configured" in out.lower()
        or "api key" in out.lower()
        or "not installed" in out.lower()
    )
    # and it never raises
    out2 = tools["sandbox_run_bash"]("ls")
    assert isinstance(out2, str)


def test_upload_download_tools_round_trip(tmp_path):
    import base64

    manager = SandboxManager.from_config({"backend_type": "local", "work_dir": str(tmp_path)})
    tools = manager.get_raw_tools()
    assert "sandbox_upload_file" in tools
    assert "sandbox_download_file" in tools
    payload = base64.b64encode(b"hi from swarm").decode("ascii")
    ok = tools["sandbox_upload_file"]("notes/hello.txt", payload)
    assert ok.lower().startswith("uploaded")
    got = tools["sandbox_download_file"]("notes/hello.txt")
    assert "hi from swarm" in base64.b64decode(got).decode("utf-8")
    missing = tools["sandbox_download_file"]("nope/missing.txt")
    assert "error" in missing.lower()


def test_daytona_upload_download_without_key_degrade(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    manager = SandboxManager.from_config({"provider": "daytona"})
    tools = manager.get_raw_tools()
    assert "not configured" in tools["sandbox_upload_file"]("a.txt", "eHg=").lower()
    assert "not configured" in tools["sandbox_download_file"]("a.txt").lower()


# --- persistence surface -------------------------------------------------------


def test_custom_blueprint_patch_persists_sandbox_param():
    from swarm.views.api_views import _custom_blueprints_registry

    if not _custom_blueprints_registry:
        pytest.skip("no custom seats in test registry")
    seat_id = _custom_blueprints_registry[0]["id"]
    client = APIClient()
    url = reverse("custom-blueprint-detail", kwargs={"blueprint_id": seat_id})
    response = client.patch(url, {"sandbox": {"provider": "daytona"}}, format="json")
    assert response.status_code == 200
    assert response.json()["sandbox"] == {"provider": "daytona"}
    bad = client.patch(url, {"sandbox": {"provider": "daytona", "daytona_api_key": "sk-x"}}, format="json")
    assert bad.status_code == 400
