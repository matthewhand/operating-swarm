#!/usr/bin/env python3
"""#934 visual proof: pinned tiles at 5.25rem with two-line labels."""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8002"
OUT = "/tmp/pr-visuals-934"

import os

os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.goto(f"{BASE}/accounts/login/", wait_until="load")
    pg.fill("input[name='username']", "fanfare-capture")
    pg.fill("input[name='password']", "fanfare-capture")
    pg.press("input[name='password']", "Enter")
    try:
        pg.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    pg.wait_for_timeout(1500)
    pg.goto(f"{BASE}/chat", wait_until="load")
    pg.wait_for_timeout(3500)

    rail = pg.locator("aside").first
    rail.screenshot(path=f"{OUT}/rail-default.png")

    grid = pg.locator("[data-testid='agent-fav-grid']")
    print("fav-grid present:", grid.count())
    if grid.count():
        tiles = pg.locator(".os-fav-tile")
        n = tiles.count()
        print("tiles:", n)
        for i in range(min(n, 4)):
            box = tiles.nth(i).bounding_box()
            print(f"tile {i} box:", box)
            tiles.nth(i).screenshot(path=f"{OUT}/tile-{i}.png")
    pg.screenshot(path=f"{OUT}/full.png")
    b.close()
print("saved to", OUT)
