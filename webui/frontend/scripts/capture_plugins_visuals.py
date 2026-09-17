"""REQ-910/911/912 visual proof: capture the Plugins popup panes + rail gate.

Runs against the vite dev/preview server for the BRANCH under test (not the
container, which serves main) so the screenshots show the fixed UI.
"""
import os
from playwright.sync_api import sync_playwright

OUT = "/tmp/pr-visuals"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://127.0.0.1:4174/", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(3500)

    # The rail footer buttons live in the left sidepane.
    plugins_btn = page.get_by_test_id("os-plugins-button")
    plugins_btn.scroll_into_view_if_needed()
    page.screenshot(path=f"{OUT}/1-rail.png")

    # Open Plugins on the default (swarm-owned) seat.
    plugins_btn.click()
    page.wait_for_selector('[data-testid="os-plugins-popup"]', timeout=8000)
    page.wait_for_timeout(600)
    page.screenshot(path=f"{OUT}/2-plugins-chat-pane.png")

    page.get_by_role("tab", name="Add tools").click()
    page.wait_for_timeout(800)
    page.screenshot(path=f"{OUT}/3-plugins-tools-pane.png")

    page.get_by_role("tab", name="Add skills").click()
    page.wait_for_timeout(800)
    page.screenshot(path=f"{OUT}/4-plugins-skills-pane.png")

    # Close, select a CLI seat if present, and show the greyed gate.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    try:
        cli = page.locator('[data-testid="os-plugins-button"][data-disabled="true"]')
        if cli.count() == 0:
            page.get_by_test_id("cli-select").first.click()
            page.get_by_role("menuitem", name="grok").first.click()
            page.wait_for_timeout(800)
        plugins_btn.hover()
        page.wait_for_timeout(400)
        page.screenshot(path=f"{OUT}/5-rail-gated-tooltip.png")
    except Exception as exc:  # noqa: BLE001 — best-effort capture
        print(f"gate capture skipped: {exc}")

    browser.close()
    print("saved:", sorted(os.listdir(OUT)))
