#!/usr/bin/env python3
"""#675 / #681 live verification against the :8002 instance.

Logs in as the capture user, then:
  1. IRC theme  — per-row dividers exist, drag persists width, CSS var syncs.
  2. Picker     — pill opens the two-stage dialog: stage 1 providers,
                  stage 2 Use-default-first, Esc back-out, breadcrumb.
Screenshots land in /tmp/ui-verify-675-681/.
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("VERIFY_BASE", "http://localhost:8002")
OUT = "/tmp/ui-verify-675-681"
os.makedirs(OUT, exist_ok=True)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} — {name}" + (f"  [{detail}]" if detail else ""))


def login(page):
    page.goto(f"{BASE}/accounts/login/", wait_until="networkidle")
    page.fill("input[name='username']", "fanfare-capture")
    page.fill("input[name='password']", "fanfare-capture")
    page.click("button[type='submit'], input[type='submit']")
    page.wait_for_load_state("networkidle")


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = ctx.new_page()
    login(page)

    # ---------------------------------------------------------------- IRC
    page.goto(f"{BASE}/chat?blueprint=codey", wait_until="networkidle")
    page.evaluate("localStorage.setItem('os.bubbleTheme', 'irc')")
    page.reload(wait_until="networkidle")
    # Dividers render per message row — seed the thread if it is empty.
    composer = page.locator("textarea[aria-label='Chat message'], textarea[name='message']")
    if composer.count():
        composer.first.fill("Verification ping for the IRC gutter divider.")
        composer.first.press("Enter")
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/01-irc-theme.png", full_page=False)

    dividers = page.locator("[data-testid='irc-gutter-divider']")
    n = dividers.count()
    check("IRC: per-row dividers render", n > 0, f"count={n}")

    if n:
        first = dividers.first
        # The transcript root publishes the persisted width.
        var_before = page.evaluate(
            "() => document.querySelector('.os-chat-transcript')?.style.getPropertyValue('--irc-gutter-px') || ''"
        )
        check("IRC: --irc-gutter-px set on transcript", var_before.endswith("px"), var_before)

        # Drag the first divider +60px.
        before = page.evaluate("() => parseInt(localStorage.getItem('os.ircGutterPx') || '140', 10)")
        box = first.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 60, box["y"] + box["height"] / 2, steps=5)
            page.mouse.up()
            page.wait_for_timeout(300)
        after = page.evaluate(
            "() => parseInt(localStorage.getItem('os.ircGutterPx') || '140', 10)"
        )
        check("IRC: drag persists new width", after > before, f"{before} -> {after}")

        var_after = page.evaluate(
            "() => document.querySelector('.os-chat-transcript')?.style.getPropertyValue('--irc-gutter-px') || ''"
        )
        check(
            "IRC: CSS var follows the drag",
            var_after == f"{after}px",
            f"{var_before} -> {var_after}",
        )
        page.screenshot(path=f"{OUT}/02-irc-after-drag.png", full_page=False)

        # Double-click reset.
        dividers.first.dblclick()
        page.wait_for_timeout(200)
        reset = page.evaluate(
            "() => parseInt(localStorage.getItem('os.ircGutterPx') || '140', 10)"
        )
        check("IRC: double-click resets to 140", reset == 140, f"value={reset}")

    # ------------------------------------------------------------- Picker
    page.evaluate("localStorage.setItem('os.bubbleTheme', 'bubble')")
    page.goto(f"{BASE}/chat?blueprint=api_agent", wait_until="networkidle")
    # The DRF throttle (see #680/#581) can leave the profiles query empty for
    # up to a minute, and an empty payload means the picker renders nothing.
    # Wait patiently for the pill instead of failing on the throttle.
    pill = page.locator("[data-testid='routing-pill-agent']")
    pill_ok = False
    for attempt in range(8):
        if pill.count():
            pill_ok = True
            break
        page.wait_for_timeout(15000)
        page.reload(wait_until="networkidle")
    check("Picker: routing pill present", pill_ok)
    if not pill_ok:
        page.screenshot(path=f"{OUT}/05-picker-throttled.png", full_page=False)
        browser.close()
        failed = [r for r in results if not r[1]]
        print(f"\n{len(results) - len(failed)}/{len(results)} checks passed (throttle blocked picker); screenshots in {OUT}")
        sys.exit(1)
    page.wait_for_timeout(1500)
    pill.click()
    page.wait_for_timeout(400)
    dialog = page.locator("[data-testid='composer-picker']")
    check("Picker: two-stage dialog opens", dialog.count() > 0)
    page.screenshot(path=f"{OUT}/03-picker-stage1.png", full_page=False)

    crumb = page.locator("[data-testid='composer-picker-breadcrumb']")
    check(
        "Picker: stage-1 breadcrumb reads Providers",
        crumb.count() > 0 and "Providers" in (crumb.text_content() or ""),
        crumb.text_content() or "",
    )

    # Descend into the API gateway provider.
    api_row = page.get_by_text("API gateway", exact=False).first
    if api_row.count():
        api_row.click()
        page.wait_for_timeout(400)
        crumb2 = page.locator("[data-testid='composer-picker-breadcrumb']")
        ok = "API gateway" in (crumb2.text_content() or "")
        check("Picker: descend → breadcrumb 'Providers › API gateway'", ok, crumb2.text_content() or "")

        rows = page.locator("[data-testid='composer-picker-row']")
        first_row = rows.first.text_content() or ""
        check(
            "Picker: Use-default row first",
            "Use default" in first_row,
            first_row.strip()[:60],
        )
        page.screenshot(path=f"{OUT}/04-picker-stage2.png", full_page=False)

        # Esc backs out one stage (dialog stays open, back on providers).
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        still_open = page.locator("[data-testid='composer-picker']").count() > 0
        crumb3 = page.locator("[data-testid='composer-picker-breadcrumb']")
        back_on_providers = (
            still_open
            and crumb3.count() > 0
            and "API gateway" not in (crumb3.text_content() or "")
        )
        check("Picker: Esc backs out one stage", back_on_providers)
    else:
        check("Picker: API gateway row present", False, "row not found")

    # Esc from stage 1 closes.
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    check(
        "Picker: Esc from stage 1 closes",
        page.locator("[data-testid='composer-picker']").count() == 0,
    )
    page.screenshot(path=f"{OUT}/05-picker-closed.png", full_page=False)

    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed; screenshots in {OUT}")
sys.exit(1 if failed else 0)
