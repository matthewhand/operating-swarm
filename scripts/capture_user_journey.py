#!/usr/bin/env python
"""Capture screenshots for docs/USER_JOURNEY.md + GUIDED_TOUR.md.

Idempotent and re-runnable:

1. Starts the Django dev server itself on a dedicated port (8321) with the
   env it needs (DJANGO_DEBUG=true, ENABLE_WEBUI=true,
   isolated SWARM_RESPONSES_DIR), waits for readiness.
2. Visits each page in the user journey with Playwright (Chromium,
   1280x800) and saves full-page PNGs to docs/screenshots/<kebab>.png,
   overwriting any previous capture. With --mobile, emulates an iPhone-14
   class device (390x844, dpr 2, touch) and writes to
   docs/screenshots/mobile/<kebab>.png instead.
3. After the empty ``sessions`` list capture, seeds a minimal
   ``responses_store`` fixture (``resp_journey_seed``) so
   ``session-detail`` can screenshot ``/sessions/<id>/`` honestly.
   Also isolates ``SWARM_USER_DATA_DIR`` so My Blueprints ignores host
   custom agents under ``~/.local/share/OpenSwarm/…/blueprints/``.
4. If a page redirects to a login form, creates a throwaway superuser via
   `manage.py shell -c` and logs in through the form, then retries.
5. Writes a JSON capture manifest (status, final URL, PNG path) when
   ``CAPTURE_MANIFEST`` is set, or to ``--manifest PATH``.
6. Kills the server and prints a captured/skipped summary.

Pages that return 4xx/5xx are skipped and reported -- never faked.

Usage:
    .venv/bin/python scripts/capture_user_journey.py [--mobile]
    CAPTURE_MANIFEST=/path/manifest.json .venv/bin/python scripts/capture_user_journey.py

Requires: `.venv/bin/pip install playwright && .venv/bin/playwright install chromium`

Canonical operator UI is Django trailing-slash routes (ADR-001). SPA mounts
only ``/`` and ``/chat``. Bare ``/teams``, ``/blueprints``, ``/settings``,
and ``/agent-creator`` 302 to Django; spa-* stems still capture those entry
URLs so the tour can document the redirect honestly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python")
PORT = int(os.environ.get("CAPTURE_PORT", "8321"))
BASE_URL = f"http://127.0.0.1:{PORT}"
SCREENSHOT_DIR = REPO_ROOT / "docs" / "screenshots"
FRONTEND_DIST_INDEX = REPO_ROOT / "webui" / "frontend" / "dist" / "index.html"
VIEWPORT = {"width": 1280, "height": 800}
# iPhone 14-class emulation for --mobile runs.
MOBILE_VIEWPORT = {"width": 390, "height": 844}
# Match e2e_visual chat WS wait — 8s was flaky under load (Connecting… → capture).
SPA_CHAT_STATUS_TIMEOUT_MS = 20_000
# Bare SPA entry paths that Django RedirectView sends to trailing-slash operator UI.
SPA_REDIRECT_STEMS = frozenset(
    {"spa-teams", "spa-blueprints", "spa-settings", "spa-agent-creator"}
)
# ADR-001: only these stems are real SPA destinations (not redirect documentation).
SPA_ROUTE_STEMS = frozenset({"landing", "spa-chat"})

# Throwaway credentials for the dev-server superuser (local only, never
# committed anywhere; the dev db is throwaway state).
ADMIN_USER = "journey-admin"
ADMIN_PASS = "journey-pass-8321"

# Isolated responses store so capture never pollutes ~/.local/share/swarm/responses
# and so `sessions` stays empty until we seed for session-detail.
CAPTURE_RESPONSES_DIR = Path(
    os.environ.get(
        "CAPTURE_RESPONSES_DIR",
        str(Path(tempfile.gettempdir()) / f"open-swarm-capture-responses-{PORT}"),
    )
)
# Isolate XDG user data so My Blueprints does not pick up host custom agents
# under ~/.local/share/OpenSwarm/swarm/blueprints/ (SWARM_USER_DATA_DIR).
CAPTURE_USER_DATA_DIR = Path(
    os.environ.get(
        "CAPTURE_USER_DATA_DIR",
        str(Path(tempfile.gettempdir()) / f"open-swarm-capture-user-data-{PORT}"),
    )
)
# Fixed id matching responses_store._ID_RE; owner must be user:<ADMIN_USER>.
SESSION_DETAIL_ID = "resp_journey_seed"

# (output filename stem, path, human name)
# SCREENSHOTS.md tracks every capture produced here.
# `sessions` is captured against an empty store; `session-detail` is seeded
# mid-run (after the list PNG) so /sessions/<id>/ shows real Graph/timeline UI.
PAGES = [
    # Landing remains the React SPA shell (demoted operator chrome → Django hrefs).
    ("landing", "/", "Landing page (React SPA dashboard)"),
    # SPA-only routes still served by React (no Django twin).
    ("spa-chat", "/chat", "Chat (React SPA)"),
    # Bare paths that redirect to canonical Django operator UI (document redirect).
    ("spa-teams", "/teams", "Bare /teams → Django Team Launcher (redirect)"),
    ("spa-blueprints", "/blueprints", "Bare /blueprints → Django Blueprint Library (redirect)"),
    ("spa-settings", "/settings", "Bare /settings → Django Settings Dashboard (redirect)"),
    ("spa-agent-creator", "/agent-creator", "Bare /agent-creator → Django Agent Creator (redirect)"),
    ("login", "/accounts/login/", "Login page"),
    ("teams", "/teams/", "Teams admin / registry (Django)"),
    ("teams-launch", "/teams/launch/", "Team launcher (Django)"),
    ("blueprint-library", "/blueprint-library/", "Blueprint library (Django)"),
    ("my-blueprints", "/blueprint-library/my-blueprints/", "My blueprints (Django)"),
    ("agent-creator", "/agent-creator/", "Agent creator (Django)"),
    ("settings", "/settings/", "Settings dashboard (Django)"),
    ("sessions", "/sessions/", "Session explorer (Django)"),
    (
        "session-detail",
        f"/sessions/{SESSION_DETAIL_ID}/",
        "Session explorer detail (seeded fixture)",
    ),
    ("profiles", "/profiles/", "LLM profiles (Django)"),
]

SERVER_ENV = {
    "DJANGO_DEBUG": "true",       # dev mode; also relaxes SECRET_KEY requirement
    "ENABLE_WEBUI": "true",       # /teams/ et al. 404 without this
    "DJANGO_SECRET_KEY": os.environ.get("DJANGO_SECRET_KEY", "journey-capture-secret"),
    "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
    "SWARM_TEST_MODE": "1",
    "SWARM_RESPONSES_DIR": str(CAPTURE_RESPONSES_DIR),
    "SWARM_USER_DATA_DIR": str(CAPTURE_USER_DATA_DIR),
    "DJANGO_DB_NAME": str(CAPTURE_USER_DATA_DIR / "capture.sqlite3"),
    # Uncomment to exercise token auth instead of open dev access:
    # "API_AUTH_TOKEN": "local-journey-token",
}

# Host DATABASE_URL / POSTGRES_* would otherwise bind capture to a down
# Postgres and hang the 60s ready wait.
_CAPTURE_DB_POP = (
    "DATABASE_URL",
    "POSTGRES_HOST",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DJANGO_DATABASE",
)


def capture_env() -> dict[str, str]:
    CAPTURE_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **SERVER_ENV}
    for key in _CAPTURE_DB_POP:
        env.pop(key, None)
    return env


def require_frontend_dist() -> None:
    """ADR-001 SPA captures need a built ``webui/frontend/dist`` (gitignored)."""
    if FRONTEND_DIST_INDEX.is_file():
        return
    raise SystemExit(
        f"Missing {FRONTEND_DIST_INDEX.relative_to(REPO_ROOT)}. "
        "Build the SPA first (ADR-001 `/` + `/chat`):\n"
        "  make frontend\n"
        "  # or: cd webui/frontend && npm ci && npm run build"
    )


def assert_pages_adr001_contract() -> None:
    """Guard PAGES drift: SPA destinations stay `/` + `/chat` only."""
    by_stem = {stem: path for stem, path, _name in PAGES}
    assert by_stem["landing"] == "/" and by_stem["spa-chat"] == "/chat"
    assert {"landing", "spa-chat"} == SPA_ROUTE_STEMS
    assert {
        "spa-teams",
        "spa-blueprints",
        "spa-settings",
        "spa-agent-creator",
    } == SPA_REDIRECT_STEMS
    for stem in SPA_REDIRECT_STEMS:
        assert stem in by_stem and not by_stem[stem].endswith("/"), stem


def start_server() -> subprocess.Popen:
    env = capture_env()
    log_path = Path(tempfile.gettempdir()) / f"open-swarm-capture-server-{PORT}.log"
    log_f = open(log_path, "wb")
    proc = subprocess.Popen(
        [PYTHON, "manage.py", "runserver", str(PORT), "--noreload"],
        cwd=REPO_ROOT,
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            log_f.close()
            tail = log_path.read_text(errors="replace")[-2000:]
            raise RuntimeError(
                f"Django server exited early (rc={proc.returncode}); log {log_path}:\n{tail}"
            )
        try:
            urllib.request.urlopen(BASE_URL + "/v1/models", timeout=2)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    log_f.close()
    tail = log_path.read_text(errors="replace")[-2000:]
    raise RuntimeError(
        f"Django server did not become ready within 60s; log {log_path}:\n{tail}"
    )


def ensure_superuser() -> None:
    """Create (or reset) a throwaway superuser for form login."""
    code = (
        "from django.contrib.auth import get_user_model; "
        "U = get_user_model(); "
        f"u, _ = U.objects.get_or_create(username='{ADMIN_USER}'); "
        "u.is_staff = True; u.is_superuser = True; "
        f"u.set_password('{ADMIN_PASS}'); u.save(); "
        "print('superuser ready')"
    )
    env = capture_env()
    # Fresh checkouts/dbs have no tables yet — make auth_user exist first.
    subprocess.run(
        [PYTHON, "manage.py", "migrate", "-v", "0"],
        cwd=REPO_ROOT, env=env, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [PYTHON, "manage.py", "shell", "-c", code],
        cwd=REPO_ROOT, env=env, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def reset_capture_responses_dir() -> None:
    """Start each run with an empty isolated responses store (empty list PNG)."""
    if CAPTURE_RESPONSES_DIR.exists():
        shutil.rmtree(CAPTURE_RESPONSES_DIR)
    CAPTURE_RESPONSES_DIR.mkdir(parents=True, exist_ok=True)


def reset_capture_user_data_dir() -> None:
    """Empty isolated SWARM_USER_DATA_DIR so My Blueprints ignores host customs."""
    if CAPTURE_USER_DATA_DIR.exists():
        shutil.rmtree(CAPTURE_USER_DATA_DIR)
    CAPTURE_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def seed_session_detail_fixture() -> None:
    """Persist a minimal hybrid_team-shaped record for /sessions/<id>/ capture.

    Must run *after* the empty ``sessions`` list screenshot so that PNG stays
    an honest empty-state capture. Owner matches the throwaway login principal
    (``user:journey-admin``); Session Explorer always filters via owner_allows.
    """
    # Progress shape mirrors live hybrid_team async progress (role/status/
    # model_used/task/result) so Graph + Delegation timeline tabs render.
    code = f"""
from swarm.core import responses_store
import time
rid = {SESSION_DETAIL_ID!r}
owner = "user:{ADMIN_USER}"
responses_store.save({{
    "id": rid,
    "object": "response",
    "owner": owner,
    "response": {{
        "id": rid,
        "model": "hybrid_team",
        "status": "completed",
        "created_at": int(time.time()) - 90,
        "output_text": (
            "Seeded capture fixture: orchestration finished; "
            "agent + auxiliary delegations completed."
        ),
        "execution_ms": 1842,
        "usage": {{"total_tokens": 1280}},
        "progress": [
            {{
                "role": "orchestration",
                "status": "completed",
                "model_used": "claude -p",
                "task": "Plan and route sub-tasks",
                "result": "Delegated to agent + auxiliary",
            }},
            {{
                "role": "agent",
                "status": "completed",
                "model_used": "gpt-4o",
                "task": "Implement the feature",
                "result": "Patch applied",
            }},
            {{
                "role": "auxiliary",
                "status": "completed",
                "model_used": "gpt-4o-mini",
                "task": "Summarize findings",
                "result": "Summary ready",
            }},
        ],
    }},
    "messages": [
        {{
            "role": "user",
            "content": "Ship a small hybrid_team demo for the Session Explorer screenshot.",
        }},
        {{
            "role": "assistant",
            "content": (
                "Seeded capture fixture: orchestration finished; "
                "agent + auxiliary delegations completed."
            ),
        }},
    ],
}})
print("seeded", rid)
"""
    env = capture_env()
    subprocess.run(
        [PYTHON, "manage.py", "shell", "-c", code],
        cwd=REPO_ROOT, env=env, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def login_if_needed(page) -> bool:
    """If the current page is a login form, log in with the throwaway
    superuser. Returns True if a login was performed."""
    if "login" not in page.url:
        return False
    user_box = page.locator(
        "input[name='username'], input[type='text']").first
    pass_box = page.locator("input[name='password'], input[type='password']").first
    if user_box.count() == 0 or pass_box.count() == 0:
        return False
    ensure_superuser()
    user_box.fill(ADMIN_USER)
    pass_box.fill(ADMIN_PASS)
    page.locator("button[type='submit'], input[type='submit']").first.click()
    page.wait_for_load_state("networkidle", timeout=15000)
    return True


def _spa_chat_status_is_terminal(text: str) -> bool:
    """True when chat is ready (silent healthy) or a failure is on screen.

    Healthy connection no longer shows a standing Connected badge. Terminal
    means the composer is enabled, or the empty-state / toast names a failure.
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    if t == "ready":
        return True
    return bool(
        re.search(
            r"websocket not connected|sign in required|unreachable|disconnected",
            t,
            flags=re.I,
        )
    )


def capture(
    page,
    slug: str,
    path: str,
    name: str,
    screenshot_dir: Path,
    *,
    allow_connecting: bool = False,
) -> dict:
    """Visit path, screenshot, return a manifest entry."""
    entry: dict = {
        "stem": slug,
        "path": path,
        "name": name,
        "ok": False,
    }
    url = BASE_URL + path
    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    status = response.status if response else 0
    entry["status"] = status
    if status >= 400:
        entry["error"] = f"HTTP {status}"
        return entry
    # Follow a login redirect if auth hardening kicked in.
    if "login" in page.url and path not in ("/accounts/login/", "/login/"):
        if login_if_needed(page):
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = response.status if response else 0
            entry["status"] = status
            if status >= 400 or "login" in page.url:
                entry["error"] = f"auth-blocked (HTTP {status})"
                return entry
        else:
            entry["error"] = "redirected to login; no login form found"
            return entry
    # Let the SPA / async widgets settle.
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass  # busy pages (polling) never go idle; capture anyway
    # spa-chat: wait for a *terminal* WS state so Connecting… is not captured
    # as ready. Healthy is silent (composer enabled). Failure surfaces as
    # "Websocket not connected" / toast. Default: FAIL (skip PNG) if still
    # connecting; pass --allow-connecting to soft-accept.
    if slug == "spa-chat":
        try:
            page.wait_for_function(
                """() => {
                  const composer = document.querySelector('[aria-label="Chat message"]');
                  if (composer && !composer.disabled) return true;
                  const body = (document.body && document.body.innerText) || '';
                  return /Websocket not connected|sign in required|websocket unreachable|disconnected/i.test(body);
                }""",
                timeout=SPA_CHAT_STATUS_TIMEOUT_MS,
            )
        except Exception:
            pass  # read status below; may still hard-fail
        try:
            enabled = page.evaluate(
                """() => {
                  const el = document.querySelector('[aria-label="Chat message"]');
                  return Boolean(el && !el.disabled);
                }"""
            )
            if enabled:
                entry["connection_status"] = "ready"
            else:
                entry["connection_status"] = (
                    page.locator("body").inner_text(timeout=2000)[:240]
                )
        except Exception:
            entry["connection_status"] = ""
        status_text = entry.get("connection_status") or ""
        if not _spa_chat_status_is_terminal(status_text):
            if allow_connecting:
                entry["connection_status_soft"] = True
            else:
                shown = status_text or "(empty)"
                entry["error"] = (
                    f"spa-chat not terminal after "
                    f"{SPA_CHAT_STATUS_TIMEOUT_MS}ms: {shown!r} "
                    f"(want ready composer or Websocket not connected; "
                    f"pass --allow-connecting to soft-accept Connecting…)"
                )
                return entry
    page.wait_for_timeout(750)
    final_url = page.url
    entry["final_url"] = final_url
    # Compare path only (keep trailing-slash differences): /settings → /settings/
    # is still a redirect for bare SPA entry documentation.
    final_path = urlparse(final_url).path or "/"
    entry["redirected"] = final_path != path and path not in (
        "/accounts/login/",
        "/login/",
    )
    try:
        entry["title"] = page.title()
        entry["body_snip"] = page.locator("body").inner_text(timeout=5000)[:350].replace("\n", " ")
        entry["nav_sample"] = [
            t.strip()
            for t in page.locator("nav a, .navbar a, .os-bottom-nav a").all_inner_texts()
            if t.strip()
        ][:16]
    except Exception as exc:
        entry["dom_error"] = str(exc)
    # When this slug documents a bare SPA path that redirected, inject a
    # capture-only banner so spa-* redirect PNGs are not pixel twins of the
    # canonical Django page. Insert at body start (above sticky header).
    entry["banner_injected"] = False
    if entry.get("redirected") and slug in SPA_REDIRECT_STEMS:
        try:
            from_path = path
            to_path = final_url.replace(BASE_URL, "") or final_url
            page.evaluate(
                """([fromPath, toPath]) => {
                  if (document.getElementById('os-capture-redirect-banner')) return;
                  const b = document.createElement('div');
                  b.id = 'os-capture-redirect-banner';
                  b.setAttribute('role', 'status');
                  b.setAttribute(
                    'style',
                    [
                      'position:sticky','top:0','z-index:2000','padding:0.55rem 1rem',
                      'background:#1e3a5f','color:#e2e8f0','font:600 0.9rem/1.35 system-ui,sans-serif',
                      'border-bottom:2px solid #3b82f6','box-shadow:0 4px 12px rgba(0,0,0,.35)'
                    ].join(';')
                  );
                  b.textContent = 'Redirected: ' + fromPath + ' → ' + toPath
                    + '  ·  canonical Django operator UI (bare SPA path is not a separate product)';
                  document.body.insertBefore(b, document.body.firstChild);
                }""",
                [from_path, to_path],
            )
            entry["banner_injected"] = bool(
                page.locator("#os-capture-redirect-banner").count()
            )
        except Exception:
            entry["banner_injected"] = False

    # Full-page PNGs paint *fixed* bottom bars over content in Chromium stitch
    # (Django `.os-bottom-nav` and SPA `nav.fixed.bottom-0` / Daisy dock).
    # Park only *visible* docks as static so desktop `lg:hidden` bars stay hidden.
    try:
        page.evaluate(
            """() => {
              const nodes = document.querySelectorAll(
                '.os-bottom-nav, nav.fixed.bottom-0, nav[class*="fixed"][class*="bottom-0"], nav[aria-label="Mobile primary"]'
              );
              nodes.forEach((n) => {
                if (getComputedStyle(n).display === 'none') return;
                n.style.position = 'static';
                n.style.boxShadow = 'none';
                n.style.inset = 'auto';
              });
              document.body.style.paddingBottom = '0';
              const app = document.querySelector('.min-h-screen.pb-20, .min-h-screen');
              if (app && app.classList) {
                app.classList.remove('pb-20');
                app.style.paddingBottom = '0';
              }
            }"""
        )
    except Exception:
        pass
    out = screenshot_dir / f"{slug}.png"
    page.screenshot(path=str(out), full_page=True)
    entry["ok"] = True
    entry["screenshot"] = str(out.relative_to(REPO_ROOT))
    entry["bytes"] = out.stat().st_size if out.is_file() else 0
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mobile", action="store_true",
        help="emulate an iPhone-14 class device (390x844, dpr 2, touch) and "
             "write captures to docs/screenshots/mobile/ instead",
    )
    parser.add_argument(
        "--manifest",
        default=os.environ.get("CAPTURE_MANIFEST", ""),
        help="write JSON capture manifest to this path (or set CAPTURE_MANIFEST)",
    )
    parser.add_argument(
        "--allow-connecting",
        action="store_true",
        help="soft-accept spa-chat while the badge still says Connecting… "
             "(default: fail/skip that stem so docs never claim Connected for a "
             "Connecting frame)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="STEM",
        help="capture only these page stem(s); repeatable (e.g. --only spa-chat). "
             "session-detail still requires sessions when both are selected",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed. Run:")
        print("  .venv/bin/pip install playwright && .venv/bin/playwright install chromium")
        return 1

    screenshot_dir = SCREENSHOT_DIR / "mobile" if args.mobile else SCREENSHOT_DIR
    context_kwargs: dict = {"viewport": MOBILE_VIEWPORT if args.mobile else VIEWPORT}
    if args.mobile:
        context_kwargs.update(device_scale_factor=2, is_mobile=True, has_touch=True)

    assert_pages_adr001_contract()
    require_frontend_dist()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    reset_capture_responses_dir()
    reset_capture_user_data_dir()
    # Isolated sqlite has no tables until migrate; /v1/models 500s otherwise.
    ensure_superuser()
    print(f"Starting Django dev server on port {PORT} ...")
    print(f"  [store    ] SWARM_RESPONSES_DIR={CAPTURE_RESPONSES_DIR}")
    print(f"  [userdata ] SWARM_USER_DATA_DIR={CAPTURE_USER_DATA_DIR}")
    print(f"  [spa      ] {FRONTEND_DIST_INDEX.relative_to(REPO_ROOT)} present (ADR-001 / + /chat)")
    server = start_server()
    captured: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    entries: list[dict] = []
    sessions_captured = False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(**context_kwargs)
            # Authenticate up front: the chat websocket consumer only accepts
            # logged-in sessions, and authed pages render more realistically.
            try:
                ensure_superuser()
                page.goto(f"{BASE_URL}/accounts/login/", wait_until="networkidle")
                login_if_needed(page)
                print(f"  [auth     ] logged in as {ADMIN_USER}")
            except Exception as exc:
                print(f"  [auth     ] anonymous capture (login failed: {exc})")
            only = {s.strip() for s in (args.only or []) if s and s.strip()}
            if only:
                unknown = sorted(only - {stem for stem, _p, _n in PAGES})
                if unknown:
                    raise SystemExit(f"--only unknown stem(s): {', '.join(unknown)}")
                print(f"  [filter   ] --only {', '.join(sorted(only))}")
            for slug, path, name in PAGES:
                if only and slug not in only:
                    continue
                # Seed only after the empty list PNG so sessions.png stays empty-state.
                if slug == "session-detail":
                    if not sessions_captured:
                        entry = {
                            "stem": slug,
                            "path": path,
                            "name": name,
                            "ok": False,
                            "error": "seed blocked: sessions list was not captured first",
                        }
                        entries.append(entry)
                        skipped.append((f"{name} ({path})", entry["error"]))
                        print(f"  [skipped ] {name:40s} {path} -- {entry['error']}")
                        continue
                    try:
                        seed_session_detail_fixture()
                        seed_path = CAPTURE_RESPONSES_DIR / f"{SESSION_DETAIL_ID}.json"
                        if not seed_path.is_file():
                            raise FileNotFoundError(f"missing seed file {seed_path}")
                        print(f"  [seed     ] {SESSION_DETAIL_ID} → {CAPTURE_RESPONSES_DIR}")
                    except Exception as exc:
                        entry = {
                            "stem": slug,
                            "path": path,
                            "name": name,
                            "ok": False,
                            "error": f"seed failed: {exc}",
                        }
                        entries.append(entry)
                        skipped.append((f"{name} ({path})", entry["error"]))
                        print(f"  [skipped ] {name:40s} {path} -- {entry['error']}")
                        continue
                try:
                    entry = capture(
                        page,
                        slug,
                        path,
                        name,
                        screenshot_dir,
                        allow_connecting=bool(args.allow_connecting),
                    )
                except Exception as exc:  # never let one page kill the run
                    entry = {
                        "stem": slug,
                        "path": path,
                        "name": name,
                        "ok": False,
                        "error": f"error: {exc}",
                    }
                entries.append(entry)
                if entry.get("ok"):
                    if slug == "sessions":
                        sessions_captured = True
                    detail = entry.get("screenshot", "")
                    captured.append((name, detail))
                    redir = f" -> {entry.get('final_url', '')}" if entry.get("redirected") else ""
                    conn = entry.get("connection_status")
                    conn_s = f" [{conn}]" if conn else ""
                    banner = " +banner" if entry.get("banner_injected") else ""
                    print(f"  [captured] {name:40s} {path}{redir}{banner}{conn_s} -> {detail}")
                else:
                    detail = entry.get("error", "unknown")
                    skipped.append((f"{name} ({path})", detail))
                    print(f"  [skipped ] {name:40s} {path} -- {detail}")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        print("Django dev server stopped.")

    if args.manifest:
        manifest_path = Path(args.manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "base": BASE_URL,
            "port": PORT,
            "mobile": bool(args.mobile),
            "viewport": context_kwargs.get("viewport"),
            "pages": entries,
            "captured": len(captured),
            "skipped": len(skipped),
        }
        # Merge desktop+mobile into one file if both runs share a path.
        if manifest_path.is_file():
            try:
                prev = json.loads(manifest_path.read_text())
                key = "mobile" if args.mobile else "desktop"
                other = "desktop" if args.mobile else "mobile"
                merged = {
                    "base": BASE_URL,
                    key: report,
                    other: prev.get(other) or prev if other in prev or "pages" in prev else prev,
                }
                # If prev is a single-run report with pages, nest it.
                if "pages" in prev and key not in prev:
                    merged[other] = prev
                manifest_path.write_text(json.dumps(merged, indent=2))
            except Exception:
                manifest_path.write_text(json.dumps({"desktop" if not args.mobile else "mobile": report}, indent=2))
        else:
            key = "mobile" if args.mobile else "desktop"
            manifest_path.write_text(json.dumps({key: report}, indent=2))
        print(f"Manifest written to {manifest_path}")

    print(f"\nSummary: {len(captured)} captured, {len(skipped)} skipped")
    for name, detail in skipped:
        print(f"  skipped: {name} -- {detail}")
    return 0 if not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
