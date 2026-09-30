"""#1201 — probe failure classification + operator path for Daytona keys.

The probe used to say only "Daytona API key missing" — it never told the
operator *which side* failed or that the env var must live in the **server's**
environment (not their shell). The probe now classifies its own failure and
returns a copyable operator hint:

- ``sdk_missing``    → the ``daytona`` package is not installed in the server venv
- ``env_name_unset`` → the configured env-var name (default DAYTONA_API_KEY) is
  not set in the server process environment; hint names it and shows the
  systemd operator path
- ``auth``           → the key reached Daytona but was rejected (401/403)
- ``network``        → DNS/connect/timeout reaching the Daytona API
- ``unknown``        → anything else (detail still shown verbatim)
"""

from __future__ import annotations

import pytest

from swarm.views import sandbox_settings_api as mod
from swarm.views.sandbox_settings_api import probe_sandbox_provider


import importlib.util

import pytest

# Daytona probe classification. These tests exercise
# _classify_daytona_failure, whose first branch keys on the probe error
# "no module named 'daytona'" -> "sdk_missing". Without the SDK that branch
# always wins and "env_name_unset" is unreachable, so assertions about the
# env-var-specific operator hint cannot hold. The SDK ships in the optional
# `sandbox` extra and is legitimately absent from CI and from a barebones
# install, so skip rather than assert something unreachable.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("daytona") is None,
    reason="requires the daytona SDK (optional `sandbox` extra); without it the "
    "sdk_missing classification always wins and env_name_unset is unreachable",
)
def _scrub_env(monkeypatch):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    monkeypatch.delenv("DAYTONA_API_URL", raising=False)


def test_probe_daytona_classifies_env_name_unset_with_hint(monkeypatch):
    _scrub_env(monkeypatch)
    result = probe_sandbox_provider("daytona")
    assert result["ok"] is False
    assert result["classification"] == "env_name_unset"
    # The hint names the env var AND the server-side operator path.
    assert "DAYTONA_API_KEY" in result["operator_hint"]
    assert "systemctl" in result["operator_hint"]


def test_probe_daytona_env_unset_names_configured_env(monkeypatch):
    _scrub_env(monkeypatch)
    block = {
        "provider": "daytona",
        "enable_sandbox_tools": True,
        "timeout_seconds": 30,
        "daytona_api_key_env": "MY_DAYTONA_KEY",
        "daytona_api_url": "",
        "dangerous_confirmed": False,
        "inherit_env": False,
        "auto_stop_interval": 15,
        "sync_workspace": False,
    }
    monkeypatch.setattr(mod, "sandbox_settings_block", lambda: block)
    result = probe_sandbox_provider("daytona")
    assert result["classification"] == "env_name_unset"
    assert "MY_DAYTONA_KEY" in result["operator_hint"]


def test_probe_daytona_classifies_sdk_missing(monkeypatch):
    _scrub_env(monkeypatch)
    monkeypatch.setenv("DAYTONA_API_KEY", "k")
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "daytona" or name.startswith("daytona."):
            raise ImportError("No module named 'daytona'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = probe_sandbox_provider("daytona")
    assert result["ok"] is False
    assert result["classification"] == "sdk_missing"
    assert "pip install daytona" in result["operator_hint"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Daytona API rejected the key: 401 Unauthorized", "auth"),
        ("403 Forbidden from api", "auth"),
        ("connect ECONNREFUSED 1.2.3.4:443", "network"),
        ("request timed out after 30s", "network"),
        ("Name or service not known", "network"),
        ("weird planner failure", "unknown"),
    ],
)
def test_probe_daytona_classifies_execution_failures(monkeypatch, message, expected):
    _scrub_env(monkeypatch)
    monkeypatch.setenv("DAYTONA_API_KEY", "k")
    from swarm.core.sandbox import SandboxManager
    from swarm.core.sandbox.base import SandboxExecutionResult

    def fake_exec(self, command, timeout=None):
        return SandboxExecutionResult(
            stdout="", stderr="", exit_code=1, success=False, error=message
        )

    monkeypatch.setattr(SandboxManager, "execute_bash", fake_exec)
    result = probe_sandbox_provider("daytona")
    assert result["ok"] is False
    assert result["classification"] == expected
