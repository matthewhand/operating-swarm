"""#1703 — the host-CLI detection tip reads this payload; no second scanner.

The chat-side tip (``webui/frontend/src/lib/hostCliTip.ts``) is driven purely by
the ``GET /v1/cli-agents/`` body: ``discovered`` (PATH seed) minus ``configured``
(opt-in names). ``CliAgentsView.get`` is a thin wrapper over
``cli_catalog.cli_agents_catalog_payload``, so these tests pin the payload the
tip consumes — keeping them free of the Django test client, which cannot import
on Windows (``fcntl`` in ``operator_plane``).

They also pin that detection stays PATH/stat-only (no subprocess, no network),
so the tip can never cause a CLI to be executed.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

import pytest

from swarm.core import cli_catalog

FAKE_CLIS = ("echo", "fake", "dummy", "mock", "testcli", "placeholder")

FRONTEND_TIP_MODULES = (
    "webui/frontend/src/lib/hostCliTip.ts",
    "webui/frontend/src/components/HostCliTip.tsx",
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def on_path(*names: str) -> Callable[[pytest.MonkeyPatch], pytest.MonkeyPatch]:
    """Patch the one discovery seam so only *names* resolve on PATH."""
    wanted = set(names)

    def apply(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
        monkeypatch.setattr(
            cli_catalog,
            "which_cli",
            lambda exe: "/usr/local/bin/" + exe if exe in wanted else None,
        )
        return monkeypatch

    return apply


@pytest.fixture
def only_opencode(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """`opencode` on PATH, nothing else — the #1703 example host."""
    on_path("opencode")(monkeypatch)
    return monkeypatch


@pytest.fixture
def nothing_on_path(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    on_path()(monkeypatch)
    return monkeypatch


@pytest.fixture
def every_cli_on_path(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    on_path(*cli_catalog.catalog_names())(monkeypatch)
    return monkeypatch


def payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return cli_catalog.cli_agents_catalog_payload(config or {"cli_agents": {}})


def test_detected_but_unconfigured_cli_is_discovered_and_suggested(only_opencode):
    """`opencode` on PATH and not configured → the tip has something to announce."""
    data = payload()
    # The exact three fields the tip consumes.
    assert data["discovered"] == ["opencode"]
    assert data["configured"] == []
    assert "opencode" in data["suggestions"]
    assert data["suggestions"]["opencode"]["cmd"][0] == "opencode"


def test_no_tip_trigger_when_nothing_is_on_path(nothing_on_path):
    """Success #4: with an empty PATH seed the tip has nothing to announce."""
    data = payload()
    assert data["discovered"] == []
    assert data["configured"] == []
    assert (data.get("suggestions") or {}) == {}
    assert data["paths"] == {}


def test_configured_cli_leaves_nothing_for_the_tip_to_offer(every_cli_on_path):
    """Success #4: a CLI the user already added is not announced again."""
    data = payload({"cli_agents": {"opencode": {"cmd": ["opencode", "-p", "{prompt}"]}}})
    assert set(data["discovered"]) >= {"opencode"}
    assert "opencode" in data["configured"]
    assert "opencode" not in data["suggestions"]


def test_mixed_host_offers_only_the_unconfigured_cli(every_cli_on_path):
    data = payload({"cli_agents": {"claude": {"cmd": ["claude", "-p", "{prompt}"]}}})
    assert "claude" not in data["suggestions"]
    assert "opencode" in data["suggestions"]


def test_detected_names_never_include_placeholders(only_opencode):
    data = payload()
    for fake in FAKE_CLIS:
        assert fake not in data["discovered"]
        assert fake not in (data.get("suggestions") or {})


def test_tip_reuses_cli_agents_payload_instead_of_a_second_scanner():
    """The tip must not add another PATH walk or a new detection endpoint."""
    tip = (REPO_ROOT / FRONTEND_TIP_MODULES[0]).read_text(encoding="utf-8")
    assert "discoveredCliNames" in tip
    assert "configuredCliNames" in tip
    assert "shutil" not in tip
    assert "child_process" not in tip and "execSync" not in tip
    assert "apiGet" not in tip and "fetch(" not in tip

    urls = (REPO_ROOT / "src" / "swarm" / "urls.py").read_text(encoding="utf-8")
    assert "cli-detect" not in urls
    assert "detected-clis" not in urls
    # The endpoint the tip reads is still the single discovery surface.
    assert "v1/cli-agents" in urls


def test_cli_discovery_stays_path_only_for_the_tip():
    """Guards the constraint: detection never executes the CLI."""
    for rel in ("src/swarm/core/cli_catalog.py", "src/swarm/utils/cli_path.py"):
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert not (
                    node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in {"subprocess", "os"}
                ), f"{rel} executes a subprocess; the tip must stay PATH/stat only"
