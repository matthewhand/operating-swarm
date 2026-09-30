"""#1200 — sandbox browser/computer-control tools (hermetic)."""

from __future__ import annotations

import json

from swarm.core.sandbox.base import SandboxBackend, SandboxConfig, SandboxExecutionResult
from swarm.core.sandbox.browser import BROWSER_TOOL_NAMES, browser_tools
from swarm.core.sandbox.manager import SandboxManager


class FakeBackend(SandboxBackend):
    def __init__(self, *, browser: bool = True) -> None:
        self.config = SandboxConfig()
        self.browser = browser
        self.bash_calls: list[str] = []
        self.py_calls: list[str] = []
        self.written: dict[str, str] = {}
        self.next_stdout = '{"ok": true, "url": "https://example.test", "title": "Example"}'

    @property
    def browser_supported(self) -> bool:
        return self.browser

    def execute_python(self, code, timeout=None):
        self.py_calls.append(code)
        return SandboxExecutionResult(stdout=self.next_stdout, success=True)

    def execute_bash(self, command, timeout=None):
        self.bash_calls.append(command)
        return SandboxExecutionResult(stdout="", success=True)

    def read_file(self, path):
        return ""

    def write_file(self, path, content):
        self.written[path] = content
        return True

    def is_available(self):
        return True


def test_browser_tools_absent_for_unsupported_backend():
    assert browser_tools(FakeBackend(browser=False)) == {}


def test_browser_tools_present_for_capable_backend():
    tools = browser_tools(FakeBackend(browser=True))
    assert set(tools) == set(BROWSER_TOOL_NAMES)
    assert len(BROWSER_TOOL_NAMES) == 7


def test_navigate_runs_cdp_action_and_installs_helper():
    backend = FakeBackend()
    tools = browser_tools(backend)
    out = tools["sandbox_browser_navigate"]("https://example.test")
    assert "Example" in out and "https://example.test" in out
    assert backend.written, "helper script should be written into the sandbox"
    assert any("connect_over_cdp" in c for c in backend.written.values())
    assert any("navigate" in c for c in backend.py_calls)


def test_screenshot_returns_data_url():
    backend = FakeBackend()
    backend.next_stdout = json.dumps({"ok": True, "url": "u", "png_b64": "QUJD"})
    out = browser_tools(backend)["sandbox_browser_screenshot"]()
    assert out == "data:image/png;base64,QUJD"


def test_action_error_degrades_honestly():
    backend = FakeBackend()
    backend.next_stdout = json.dumps({"ok": False, "error": "TimeoutError: nope"})
    out = browser_tools(backend)["sandbox_browser_click"]("#a")
    assert out.startswith("[Browser Error:")
    assert "nope" in out


def test_manager_exposes_browser_tools_only_when_capable():
    capable = SandboxManager(config=SandboxConfig(backend_type="daytona"), backend=FakeBackend())
    names = set(capable.get_raw_tools())
    assert set(BROWSER_TOOL_NAMES) <= names

    plain = SandboxManager(config=SandboxConfig(), backend=FakeBackend(browser=False))
    plain_names = set(plain.get_raw_tools())
    assert not (set(BROWSER_TOOL_NAMES) & plain_names)


def test_ensure_script_still_installs_playwright_when_probe_fails(tmp_path):
    """Regression: ``set -e`` must not abort before the lazy installer runs.

    The readiness probe deliberately exits non-zero when Playwright is absent.
    The old ``python ... ; if [ $? -ne 0 ]`` form tripped ``set -e`` at the
    probe, so Playwright/Chromium were never installed and every browser call
    failed with ``[Execution Error: exit 3]``.
    """
    import subprocess

    from swarm.core.sandbox.browser import _ensure_script

    marker = tmp_path / "pip-ran"
    wrapper = (
        "python() {\n"
        '  case "$1" in -m) cat >/dev/null; return 0;; esac\n'
        "  cat >/dev/null; return 3\n"
        "}\n"
        f"pip() {{ touch {marker}; return 0; }}\n"
        "curl() { return 0; }\n"
    )
    result = subprocess.run(
        ["bash", "-c", wrapper + _ensure_script()],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert marker.is_file(), "lazy Playwright installer did not run"


def test_snapshot_render_returns_aria_text_verbatim():
    """Modern Playwright returns a YAML-ish aria snapshot string, not a dict."""
    from swarm.core.sandbox.browser import BrowserController

    out = BrowserController._render("snapshot", {"snapshot": '- heading "Example Domain"'})
    assert 'heading "Example Domain"' in out
    assert not out.startswith('"')


def test_helper_prefers_aria_snapshot_with_legacy_fallback():
    """Playwright dropped ``page.accessibility``; pin the dual-path helper."""
    from swarm.core.sandbox.browser import _HELPER_SRC

    assert 'page.locator("body").aria_snapshot()' in _HELPER_SRC
    assert "page.accessibility.snapshot()" in _HELPER_SRC
