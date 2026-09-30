"""#1200 — browser / computer control tools for sandbox backends.

Adds a first-class ``sandbox_browser_*`` toolset (navigate, click, type, press,
screenshot, accessibility snapshot) backed by Playwright + Chromium running
**inside** the sandbox microVM. The browser is launched once with a remote
debugging port; every tool call connects over CDP, acts, and disconnects —
the browser process (and its cookies/page state) persists between calls.

Backends opt in via ``SandboxBackend.browser_supported``. Backends that do not
opt in expose no browser tools (honest degrade, never a fabricated tool).

Playwright/Chromium are installed lazily on first use unless the sandbox image
already provides them (a prebuilt snapshot is the recommended path). No secrets
are read or logged here.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import SandboxBackend, SandboxExecutionResult

logger = logging.getLogger(__name__)

# Chromium remote-debugging endpoint inside the VM.
_CDP_PORT = 9222
_CDP_URL = f"http://127.0.0.1:{_CDP_PORT}"
_HELPER_DIR = "/tmp/swarm-browser"
_HELPER_PATH = f"{_HELPER_DIR}/swarm_browser.py"

BROWSER_TOOL_NAMES: tuple[str, ...] = (
    "sandbox_browser_navigate",
    "sandbox_browser_snapshot",
    "sandbox_browser_click",
    "sandbox_browser_type",
    "sandbox_browser_press",
    "sandbox_browser_screenshot",
    "sandbox_browser_back",
)

# In-VM helper. Connects over CDP, reuses the live page, never closes the
# browser (os._exit skips Playwright teardown so the process/state survives).
_HELPER_SRC = r'''
import json, os, sys
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
action = json.loads(sys.argv[1])

def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()
    os._exit(0)

try:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        kind = action.get("action")
        if kind == "navigate":
            page.goto(action["url"], wait_until="domcontentloaded", timeout=30000)
            emit({"ok": True, "url": page.url, "title": page.title()})
        elif kind == "snapshot":
            # Playwright >=1.49 exposes the canonical text aria snapshot;
            # <1.49 (and <1.56) still have the legacy dict API. Support both.
            try:
                snap = page.locator("body").aria_snapshot()
            except Exception:
                snap = page.accessibility.snapshot() or {}
                snap = json.dumps(snap, indent=2)
            emit({"ok": True, "url": page.url, "snapshot": snap})
        elif kind == "click":
            page.click(action["selector"], timeout=15000)
            page.wait_for_timeout(500)
            emit({"ok": True, "url": page.url, "title": page.title()})
        elif kind == "type":
            sel = action.get("selector")
            if sel:
                page.fill(sel, action.get("text", ""), timeout=15000)
            else:
                page.keyboard.type(action.get("text", ""))
            if action.get("submit"):
                page.keyboard.press("Enter")
                page.wait_for_timeout(500)
            emit({"ok": True, "url": page.url})
        elif kind == "press":
            page.keyboard.press(action["key"])
            page.wait_for_timeout(300)
            emit({"ok": True, "url": page.url})
        elif kind == "screenshot":
            full = bool(action.get("full_page"))
            png = page.screenshot(full_page=full, type="png")
            import base64
            emit({"ok": True, "url": page.url, "png_b64": base64.b64encode(png).decode("ascii")})
        elif kind == "back":
            page.go_back(timeout=15000)
            page.wait_for_timeout(500)
            emit({"ok": True, "url": page.url, "title": page.title()})
        else:
            emit({"ok": False, "error": f"unknown action {kind!r}"})
except Exception as exc:
    emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
'''


def _ensure_script() -> str:
    """Bash that guarantees Playwright + Chromium and a live CDP browser.

    Idempotent: installs only when missing, starts Chromium only when the
    debugging port is not already answering. Safe to run before every call.
    """
    return f"""
set -e
mkdir -p {_HELPER_DIR}
if ! python - <<'PY'
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec('playwright') else 3)
PY
then
  pip install --quiet playwright >/dev/null 2>&1 || pip install --quiet --break-system-packages playwright
  python -m playwright install --with-deps chromium >/dev/null 2>&1 || python -m playwright install chromium >/dev/null 2>&1
fi
if ! curl -sf {_CDP_URL}/json/version >/dev/null 2>&1; then
  nohup chromium --headless --no-sandbox --disable-dev-shm-usage \
    --remote-debugging-port={_CDP_PORT} --remote-debugging-address=127.0.0.1 \
    about:blank >/tmp/swarm-browser/chromium.log 2>&1 &
  for i in $(seq 1 30); do
    if curl -sf {_CDP_URL}/json/version >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
fi
"""


class BrowserController:
    """Drive a persistent headless Chromium inside a sandbox backend."""

    def __init__(self, backend: SandboxBackend) -> None:
        self._backend = backend
        self._prepared = False

    @staticmethod
    def supported(backend: SandboxBackend) -> bool:
        return bool(getattr(backend, "browser_supported", False))

    def _run_bash(self, command: str, timeout: int) -> SandboxExecutionResult:
        return self._backend.execute_bash(command, timeout=timeout)

    def _ensure(self, timeout: int) -> str | None:
        """Ensure browser is up; return an error string, or None on success."""
        if self._prepared:
            return None
        res = self._run_bash(_ensure_script(), timeout)
        if not res.success:
            return res.output or "browser preparation failed"
        try:
            self._backend.write_file(_HELPER_PATH, _HELPER_SRC)
        except Exception as exc:  # backend write is best-effort/honest
            return f"could not install browser helper: {exc}"
        self._prepared = True
        return None

    def _action(self, action: dict[str, Any], timeout: int) -> str:
        err = self._ensure(timeout)
        if err is not None:
            return f"[Browser Error: {err}]"
        payload = json.dumps(action)
        res = self._backend.execute_python(
            f"import runpy, sys; sys.argv = ['swarm_browser', {payload!r}]; "
            f"runpy.run_path({_HELPER_PATH!r}, run_name='__main__')",
            timeout=timeout or 60,
        )
        text = (res.stdout or "").strip()
        if not res.success and not text:
            return f"[Browser Error: {res.output}]"
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError:
            return f"[Browser Error: unexpected output: {text[:200]}]"
        if not data.get("ok"):
            return f"[Browser Error: {data.get('error', 'unknown')}]"
        return self._render(action.get("action", ""), data)

    @staticmethod
    def _render(kind: str, data: dict[str, Any]) -> str:
        if kind == "screenshot":
            return f"data:image/png;base64,{data.get('png_b64', '')}"
        if kind == "snapshot":
            snap = data.get("snapshot", {})
            if isinstance(snap, str):
                return snap[:20000]
            return json.dumps(snap, indent=2)[:20000]
        url = data.get("url", "")
        title = data.get("title", "")
        return f"{title}\n{url}".strip() if title else url

    # -- public actions ----------------------------------------------------

    def navigate(self, url: str, *, timeout: int = 60) -> str:
        return self._action({"action": "navigate", "url": url}, timeout)

    def snapshot(self, *, timeout: int = 60) -> str:
        return self._action({"action": "snapshot"}, timeout)

    def click(self, selector: str, *, timeout: int = 60) -> str:
        return self._action({"action": "click", "selector": selector}, timeout)

    def type_text(
        self, text: str, selector: str = "", submit: bool = False, *, timeout: int = 60
    ) -> str:
        return self._action(
            {"action": "type", "text": text, "selector": selector, "submit": submit},
            timeout,
        )

    def press(self, key: str, *, timeout: int = 60) -> str:
        return self._action({"action": "press", "key": key}, timeout)

    def screenshot(self, full_page: bool = False, *, timeout: int = 60) -> str:
        return self._action({"action": "screenshot", "full_page": full_page}, timeout)

    def back(self, *, timeout: int = 60) -> str:
        return self._action({"action": "back"}, timeout)


def browser_tools(backend: SandboxBackend) -> dict[str, Any]:
    """``sandbox_browser_*`` callables for a browser-capable backend, else {}."""
    if not BrowserController.supported(backend):
        return {}
    ctrl = BrowserController(backend)

    def sandbox_browser_navigate(url: str) -> str:
        """Open a URL in the sandbox browser. Returns the page title and URL."""
        return ctrl.navigate(url)

    def sandbox_browser_snapshot() -> str:
        """Return the accessibility tree of the current page (for inspection/click targets)."""
        return ctrl.snapshot()

    def sandbox_browser_click(selector: str) -> str:
        """Click the first element matching a CSS/Playwright selector."""
        return ctrl.click(selector)

    def sandbox_browser_type(text: str, selector: str = "", submit: bool = False) -> str:
        """Type text (into ``selector`` when given). ``submit`` presses Enter after."""
        return ctrl.type_text(text, selector=selector, submit=submit)

    def sandbox_browser_press(key: str) -> str:
        """Press a keyboard key (e.g. ``Enter``, ``Escape``, ``Control+A``)."""
        return ctrl.press(key)

    def sandbox_browser_screenshot(full_page: bool = False) -> str:
        """Capture a PNG screenshot as a data URL the chat can render."""
        return ctrl.screenshot(full_page=full_page)

    def sandbox_browser_back() -> str:
        """Navigate the sandbox browser back one history entry."""
        return ctrl.back()

    return {
        "sandbox_browser_navigate": sandbox_browser_navigate,
        "sandbox_browser_snapshot": sandbox_browser_snapshot,
        "sandbox_browser_click": sandbox_browser_click,
        "sandbox_browser_type": sandbox_browser_type,
        "sandbox_browser_press": sandbox_browser_press,
        "sandbox_browser_screenshot": sandbox_browser_screenshot,
        "sandbox_browser_back": sandbox_browser_back,
    }


__all__ = ["BROWSER_TOOL_NAMES", "BrowserController", "browser_tools"]
