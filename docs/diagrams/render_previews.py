#!/usr/bin/env python3
"""Render PNG previews from the editable HTML/SVG diagram sources.

Every diagram in this directory is authored as a self-contained HTML file with
an inline, accessible SVG (the *editable source*). This script is the single
render step: it opens each source in a headless Chromium (Playwright) and
screenshots the diagram's ``<svg>`` node to ``previews/<slug>.png``.

Rasters are ALWAYS generated from the source — never hand-edited. If a
preview looks wrong, fix the HTML and re-run:

    python docs/diagrams/render_previews.py            # all diagrams
    python docs/diagrams/render_previews.py hero-...   # one or more slugs

Requires: playwright (``python -m playwright install chromium``). See
docs/diagrams/README.md for the full regeneration workflow.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIEW_DIR = HERE / "previews"

# 2x device scale keeps text crisp; a wide viewport avoids the min-width
# horizontal scroll that some SVGs use for small screens.
VIEWPORT = {"width": 1600, "height": 1200}
SCALE = 2


def render(slug: str) -> Path:
    from playwright.sync_api import sync_playwright

    src = HERE / f"{slug}.html"
    if not src.exists():
        raise FileNotFoundError(src)

    out = PREVIEW_DIR / f"{slug}.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport=VIEWPORT, device_scale_factor=SCALE
        )
        page.goto(src.as_uri())
        # Wait for webfonts so Geist / Instrument Serif are painted, not a
        # fallback metric, before measuring and shooting the SVG node.
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts && document.fonts.ready")
        svg = page.query_selector("svg")
        if svg is None:
            browser.close()
            raise RuntimeError(f"{src.name}: no <svg> node found")
        svg.screenshot(path=str(out))
        browser.close()
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "slugs",
        nargs="*",
        help="Diagram slugs (filename without .html). Default: every *.html source.",
    )
    args = ap.parse_args(argv)

    if args.slugs:
        slugs = args.slugs
    else:
        slugs = sorted(p.stem for p in HERE.glob("*.html"))

    if not slugs:
        print("No diagrams found.", file=sys.stderr)
        return 1

    PREVIEW_DIR.mkdir(exist_ok=True)
    failures = 0
    for slug in slugs:
        try:
            out = render(slug)
            print(f"  ok  {out.relative_to(HERE.parent.parent)}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures += 1
            print(f"FAIL  {slug}: {exc}", file=sys.stderr)
    print(f"\n{len(slugs) - failures}/{len(slugs)} rendered → previews/")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
