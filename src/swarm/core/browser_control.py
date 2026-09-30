"""Local Playwright browser control (this machine).

Operating Swarm is a harness-of-harnesses. The **default** browser target is
Playwright launching or attaching Chrome on the machine that runs the agent
(CLI, API, or remote seat — same module). OMB/Rakazo Docker sandboxes and
SaaS browsers are future providers (UI rows stay grey TODO). Desktop/OS
automation is out of scope.

Missing Playwright or Chrome is a structured error. Callers must not crash
and must not fake a successful navigation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from swarm.core.browser_tools import BROWSER_UNAVAILABLE, browser_unavailable_error

TARGET_THIS_MACHINE = "this_machine"
TARGET_SANDBOX = "sandbox"
TARGET_SAAS = "saas"
DEFAULT_BROWSER_TARGET = TARGET_THIS_MACHINE

BROWSER_CHROME_MISSING = "browser automation unavailable: Chrome not found on this machine"
BROWSER_PLAYWRIGHT_MISSING = "browser automation unavailable: Playwright is not installed"
BROWSER_TARGET_TODO = "browser provider is TODO — not wired"

ENV_CHROME_CDP = "SWARM_CHROME_CDP"


class BrowserControlError(Exception):
    """Safe-to-surface browser-control failure."""


class BrowserUnavailable(BrowserControlError):
    """Playwright or Chrome is missing / unreachable."""


class BrowserTargetNotImplemented(BrowserControlError):
    """Sandbox / SaaS provider row — clickable WIP, not implemented."""


class BrowserDriver(Protocol):
    def navigate(self, url: str) -> dict[str, Any]: ...
    def snapshot(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


def browser_targets() -> list[dict[str, Any]]:
    """UI/API catalog. Only ``this_machine`` is wired."""
    return [
        {
            "id": TARGET_THIS_MACHINE,
            "label": "Browser (this machine)",
            "wired": True,
            "default": True,
            "todo": False,
            "detail": "Playwright launches or attaches local Chrome. Navigate + snapshot.",
        },
        {
            "id": TARGET_SANDBOX,
            "label": "Sandbox / Docker",
            "wired": False,
            "default": False,
            "todo": True,
            "detail": "OMB/Rakazo-style sandboxed browser. Future — not wired.",
        },
        {
            "id": TARGET_SAAS,
            "label": "SaaS",
            "wired": False,
            "default": False,
            "todo": True,
            "detail": "Hosted browser. Future — not wired. No live paid checkout.",
        },
    ]


def target_not_implemented(target: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": BROWSER_TARGET_TODO,
        "target": target,
        "detail": f"{target} browser provider is TODO — not wired.",
    }


def _safe_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise BrowserControlError("url is required")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise BrowserControlError("url must be http or https")
    if not parsed.netloc:
        raise BrowserControlError("url host is required")
    return raw


@dataclass
class StubBrowser:
    """In-memory browser for tests. Never talks to Chrome."""

    current_url: str = "about:blank"
    title: str = ""
    text: str = ""
    closed: bool = False

    def navigate(self, url: str) -> dict[str, Any]:
        if self.closed:
            raise BrowserUnavailable("stub browser is closed")
        target = _safe_url(url)
        self.current_url = target
        self.title = f"stub:{parsed_host(target)}"
        self.text = f"Stub page at {target}"
        return {"ok": True, "url": self.current_url, "title": self.title}

    def snapshot(self) -> dict[str, Any]:
        if self.closed:
            raise BrowserUnavailable("stub browser is closed")
        return {
            "ok": True,
            "url": self.current_url,
            "title": self.title,
            "text": self.text,
        }

    def close(self) -> None:
        self.closed = True


def parsed_host(url: str) -> str:
    return urlparse(url).netloc or "page"


class PlaywrightChrome:
    """Thin Playwright wrapper. Constructed via :func:`open_this_machine`."""

    def __init__(self, playwright: Any, browser: Any, page: Any) -> None:
        self._playwright = playwright
        self._browser = browser
        self._page = page

    def navigate(self, url: str) -> dict[str, Any]:
        target = _safe_url(url)
        self._page.goto(target, wait_until="domcontentloaded")
        return {
            "ok": True,
            "url": getattr(self._page, "url", target),
            "title": _page_title(self._page),
        }

    def snapshot(self) -> dict[str, Any]:
        page = self._page
        text = ""
        try:
            text = page.inner_text("body")
        except Exception:
            text = ""
        if len(text) > 8000:
            text = text[:8000] + "…"
        return {
            "ok": True,
            "url": getattr(page, "url", ""),
            "title": _page_title(page),
            "text": text,
        }

    def close(self) -> None:
        for closer in (self._page, self._browser, self._playwright):
            stop = getattr(closer, "close", None) or getattr(closer, "stop", None)
            if not callable(stop):
                continue
            try:
                stop()
            except Exception:
                continue


def _page_title(page: Any) -> str:
    getter = getattr(page, "title", None)
    if callable(getter):
        try:
            return str(getter() or "")
        except Exception:
            return ""
    return str(getter or "")


def open_this_machine(
    *,
    cdp_url: str | None = None,
    driver: BrowserDriver | None = None,
    playwright_factory: Any | None = None,
) -> BrowserDriver:
    """Launch or attach local Chrome. Inject ``driver`` in tests.

    ``playwright_factory`` is a zero-arg callable returning a started
    Playwright instance (tests pass a fake). Real path uses
    ``sync_playwright().start()``.
    """
    if driver is not None:
        return driver

    attach = (cdp_url or os.environ.get(ENV_CHROME_CDP) or "").strip() or None
    factory = playwright_factory or _start_sync_playwright
    try:
        playwright = factory()
    except BrowserUnavailable:
        raise
    except Exception as exc:
        raise BrowserUnavailable(BROWSER_PLAYWRIGHT_MISSING) from exc

    try:
        browser = _launch_or_attach(playwright, attach)
        page = browser.new_page()
        return PlaywrightChrome(playwright, browser, page)
    except BrowserUnavailable:
        _stop_playwright(playwright)
        raise
    except Exception as exc:
        _stop_playwright(playwright)
        raise BrowserUnavailable(BROWSER_CHROME_MISSING) from exc


def _start_sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailable(BROWSER_PLAYWRIGHT_MISSING) from exc
    return sync_playwright().start()


def _launch_or_attach(playwright: Any, cdp_url: str | None) -> Any:
    chromium = getattr(playwright, "chromium", None)
    if chromium is None:
        raise BrowserUnavailable(BROWSER_PLAYWRIGHT_MISSING)
    if cdp_url:
        try:
            return chromium.connect_over_cdp(cdp_url)
        except Exception as exc:
            raise BrowserUnavailable(BROWSER_CHROME_MISSING) from exc
    last_error: Exception | None = None
    for kwargs in ({"channel": "chrome"}, {}):
        try:
            return chromium.launch(headless=True, **kwargs)
        except Exception as exc:
            last_error = exc
            continue
    raise BrowserUnavailable(BROWSER_CHROME_MISSING) from last_error


def _stop_playwright(playwright: Any) -> None:
    stop = getattr(playwright, "stop", None)
    if callable(stop):
        try:
            stop()
        except Exception:
            return


def run_navigate(
    url: str,
    *,
    target: str = DEFAULT_BROWSER_TARGET,
    driver: BrowserDriver | None = None,
    cdp_url: str | None = None,
    playwright_factory: Any | None = None,
) -> dict[str, Any]:
    """Navigate. Returns a structured dict; never raises to the caller."""
    if target != TARGET_THIS_MACHINE:
        return target_not_implemented(target)
    session: BrowserDriver | None = None
    own_session = driver is None
    try:
        session = open_this_machine(
            cdp_url=cdp_url,
            driver=driver,
            playwright_factory=playwright_factory,
        )
        result = session.navigate(url)
        result.setdefault("target", TARGET_THIS_MACHINE)
        return result
    except BrowserUnavailable as exc:
        payload = browser_unavailable_error(str(exc))
        payload["error"] = str(exc) or BROWSER_UNAVAILABLE
        payload["target"] = TARGET_THIS_MACHINE
        return payload
    except BrowserControlError as exc:
        return {"ok": False, "error": str(exc), "target": TARGET_THIS_MACHINE}
    finally:
        if own_session and session is not None:
            try:
                session.close()
            except Exception:
                pass


def run_snapshot(
    *,
    target: str = DEFAULT_BROWSER_TARGET,
    driver: BrowserDriver | None = None,
    cdp_url: str | None = None,
) -> dict[str, Any]:
    """Snapshot the current page. Same honesty contract as :func:`run_navigate`."""
    if target != TARGET_THIS_MACHINE:
        return target_not_implemented(target)
    if driver is None:
        return {
            "ok": False,
            "error": "no open browser session",
            "target": TARGET_THIS_MACHINE,
            "detail": "Open a this-machine session (navigate first) or pass a stub driver.",
        }
    try:
        result = driver.snapshot()
        result.setdefault("target", TARGET_THIS_MACHINE)
        return result
    except BrowserUnavailable as exc:
        payload = browser_unavailable_error(str(exc))
        payload["error"] = str(exc) or BROWSER_UNAVAILABLE
        payload["target"] = TARGET_THIS_MACHINE
        return payload
    except BrowserControlError as exc:
        return {"ok": False, "error": str(exc), "target": TARGET_THIS_MACHINE}


def catalog_payload() -> dict[str, Any]:
    return {
        "default": DEFAULT_BROWSER_TARGET,
        "targets": browser_targets(),
        "driver": "playwright",
        "desktop_os": "out_of_scope",
    }
