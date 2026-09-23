#!/usr/bin/env python
"""Capture the flagship rail screenshot (REQ-852 / #465).

Drives the LIVE dev server (default http://127.0.0.1:8002) with Playwright
Chromium at the canonical 1280x800 viewport, full-page PNG:

1. Open ``/?settings=rail`` — ChatPage consumes that query and opens the
   settings sheet directly on the Rail section (no gear hunting).
2. Toggle "Showcase rail sections" ON (the repo's honest demo profile —
   no synthetic seats are invented; sections derive from live rows).
3. Close the sheet, wait for section headers (CLI / API / Remote / Fancy)
   to appear in the rail, then capture ``docs/screenshots/flagship-rail.png``.

Usage:
    .venv/bin/python scripts/capture_flagship_465.py [--url URL] [--out PATH]

Nothing is faked: if the toggle cannot be applied the script exits non-zero
rather than capturing an unsectioned rail.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "docs" / "screenshots" / "flagship-rail.png"

SECTION_NAMES = ("CLI", "API", "Remote", "Fancy")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(args.timeout * 1000)

        page.goto(args.url + "/?settings=rail", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid='os-agent-rail']", timeout=30000)
        page.wait_for_selector("[data-testid='demo-sections-toggle']", timeout=30000)

        # The toggle stays disabled until the blueprint catalog query settles
        # (and it can be briefly rate-limited after many captures) — poll for
        # enablement rather than assuming it is clickable straight away.
        toggle = page.get_by_label("Showcase rail sections")
        deadline = time.time() + 90
        while time.time() < deadline and not toggle.is_enabled():
            time.sleep(1.0)
        if not toggle.is_enabled():
            print("showcase toggle never enabled (catalog fetch throttled?)",
                  file=sys.stderr)
            return 5
        if not toggle.is_checked():
            toggle.check(force=True)

        # Allow the rail event to propagate and the hint to flip to "applied".
        hint = page.locator("[data-testid='demo-sections-hint']")
        hint_deadline = time.time() + 10
        hint_text = ""
        while time.time() < hint_deadline:
            hint_text = hint.inner_text() if hint.count() else ""
            if "applied" in hint_text:
                break
            time.sleep(0.5)

        if "applied" not in hint_text:
            print("demo profile did not apply: " + (hint_text or "(no hint)"),
                  file=sys.stderr)
            return 2

        # Close the sheet: Escape closes the modal. The sheet keeps its DOM
        # (hidden) after close, so "closed" means no open dialog remains —
        # NOT the toggle disappearing.
        page.keyboard.press("Escape")
        deadline = time.time() + 8
        while time.time() < deadline:
            if page.locator("dialog[open], .modal.modal-open").count() == 0:
                break
            time.sleep(0.3)
        else:
            print("settings sheet did not close", file=sys.stderr)
            return 3

        # Wait until at least one demo section header is visible in the rail.
        deadline = time.time() + 20
        seen = ""
        while time.time() < deadline and not seen:
            for name in SECTION_NAMES:
                if page.get_by_text(name, exact=True).count():
                    seen = name
                    break
            if not seen:
                time.sleep(0.5)
        if not seen:
            print("no showcase section header appeared in the rail", file=sys.stderr)
            return 4

        time.sleep(1.0)  # settle avatars/badges
        page.screenshot(path=str(out_path), full_page=True)
        browser.close()

    print(f"captured {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
