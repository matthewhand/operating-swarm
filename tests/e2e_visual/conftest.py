"""Fixtures for the opt-in golden-journey visual-regression suite.

These tests exist because a "green build" has shipped an unstyled UI twice:

1. Tailwind v4 misconfiguration emitted a ~2kB CSS file (no utilities), and
2. DaisyUI 5 renamed ``card-bordered`` to ``card-border``, silently dropping
   card borders.

Unit tests and HTTP-status smoke tests cannot catch either class of bug, so
this suite drives a real Chromium against a real dev server (daphne-aware
``runserver``, so websockets work) and asserts on *computed styles*.

The whole package is skipped unless ``RUN_E2E_VISUAL=1`` to keep the default
suite fast and free of browser/node dependencies. CI runs it from
``.github/workflows/visual-regression.yml`` after building the frontend.

Server-start pattern mirrors ``scripts/capture_user_journey.py`` (build-aware
dev server with DJANGO_DEBUG=true / ENABLE_WEBUI=true, migrations, a
throwaway superuser, dedicated port) but is factored as fixtures here.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "webui" / "frontend" / "dist"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

PORT = 8326  # dedicated; journey-capture script owns 8321
BASE_URL = f"http://127.0.0.1:{PORT}"
VIEWPORT = {"width": 1280, "height": 800}

# Throwaway credentials (local-only; the e2e database is a tempfile).
ADMIN_USER = "e2e-visual-admin"
ADMIN_PASS = "e2e-visual-pass-8326"

ENABLED = os.environ.get("RUN_E2E_VISUAL") == "1"
SKIP_REASON = (
    "e2e visual suite is opt-in: set RUN_E2E_VISUAL=1 (needs a built "
    "webui/frontend/dist and `playwright install chromium`)"
)
_HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    """Skip everything in this directory unless explicitly enabled, so the
    default suite stays fast and free of browser/node dependencies."""
    if ENABLED:
        return
    skip = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if Path(str(item.fspath)).resolve().is_relative_to(_HERE):
            item.add_marker(skip)


def _server_env(db_path: str) -> dict[str, str]:
    return {
        **os.environ,
        "DJANGO_DEBUG": "true",   # dev mode; relaxes SECRET_KEY requirement
        "ENABLE_WEBUI": "true",   # /teams/ et al. 404 without this
        "DJANGO_DB_NAME": db_path,
    }


@pytest.fixture(scope="session")
def frontend_dist() -> Path:
    """Fail fast (not skip!) if the SPA bundle is missing.

    Skipping here would recreate the very failure mode this suite guards
    against: a green run with no styled UI ever exercised.
    """
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        pytest.fail(
            f"{index} not found. Build the frontend first:\n"
            "  cd webui/frontend && npm ci && npm run build"
        )
    return FRONTEND_DIST


@pytest.fixture(scope="session")
def live_server_url(frontend_dist: Path) -> str:
    """Migrate a throwaway sqlite DB, create a superuser, and run the
    daphne-aware dev server (serves the SPA fallback + websockets)."""
    with tempfile.TemporaryDirectory(prefix="e2e-visual-db-") as tmp:
        env = _server_env(str(Path(tmp) / "db.sqlite3"))
        manage = [sys.executable, str(REPO_ROOT / "manage.py")]
        subprocess.run(
            [*manage, "migrate", "-v", "0"],
            cwd=REPO_ROOT, env=env, check=True, capture_output=True,
        )
        superuser_code = (
            "from django.contrib.auth import get_user_model; "
            "U = get_user_model(); "
            f"u, _ = U.objects.get_or_create(username='{ADMIN_USER}'); "
            "u.is_staff = True; u.is_superuser = True; "
            f"u.set_password('{ADMIN_PASS}'); u.save()"
        )
        subprocess.run(
            [*manage, "shell", "-c", superuser_code],
            cwd=REPO_ROOT, env=env, check=True, capture_output=True,
        )
        proc = subprocess.Popen(
            [*manage, "runserver", str(PORT), "--noreload"],
            cwd=REPO_ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 90
            while True:
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"dev server exited early (rc={proc.returncode})"
                    )
                try:
                    urllib.request.urlopen(BASE_URL + "/v1/models", timeout=2)
                    break
                except Exception:
                    if time.time() > deadline:
                        proc.terminate()
                        raise RuntimeError(
                            "dev server not ready within 90s"
                        ) from None
                    time.sleep(0.5)
            yield BASE_URL
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="session")
def browser():
    # Imported lazily so the default (skipped) run never needs playwright
    # at collection time.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def auth_state(browser, live_server_url: str, tmp_path_factory) -> Path:
    """Log in once through the real form and persist the session cookie as a
    Playwright storage state, so every test gets an authenticated context
    without repeating the login flow."""
    state_path = tmp_path_factory.mktemp("e2e-visual-auth") / "state.json"
    context = browser.new_context(viewport=VIEWPORT)
    page = context.new_page()
    page.goto(f"{live_server_url}/accounts/login/", wait_until="domcontentloaded")
    page.locator("input[name='username'], input[type='text']").first.fill(ADMIN_USER)
    page.locator("input[name='password'], input[type='password']").first.fill(ADMIN_PASS)
    page.locator("button[type='submit'], input[type='submit']").first.click()
    # #1029: networkidle never settles on this SPA (react-query polling keeps
    # the wire busy) — wait for the post-login redirect instead.
    page.wait_for_url(lambda url: "/accounts/login/" not in url, timeout=15_000)
    page.wait_for_load_state("domcontentloaded", timeout=15_000)
    assert "login" not in page.url, (
        f"form login with the throwaway superuser failed; still on {page.url}"
    )
    context.storage_state(path=str(state_path))
    context.close()
    return state_path


@pytest.fixture
def page(browser, live_server_url: str, auth_state: Path, request):
    """Authenticated page; captures a screenshot artifact on test failure."""
    context = browser.new_context(
        viewport=VIEWPORT, storage_state=str(auth_state)
    )
    page = context.new_page()
    yield page
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.node.name)
        try:
            page.screenshot(
                path=str(ARTIFACT_DIR / f"{slug}.png"), full_page=True
            )
        except Exception:
            pass  # never let artifact capture mask the real failure
    context.close()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose each phase's report on the item so the ``page`` fixture's
    teardown can tell whether the test body failed."""
    rep = yield
    setattr(item, f"rep_{rep.when}", rep)
    return rep
