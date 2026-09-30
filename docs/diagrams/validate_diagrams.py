#!/usr/bin/env python3
"""Geometry sanity check for the diagram sources.

Loads each ``*.html`` source in a headless Chromium and, for every ``<text>``
node, measures its SVG user-space bounding box and asserts it falls inside the
SVG ``viewBox``. Catches clipped / off-canvas labels that a screenshot can hide
at a glance.

    python docs/diagrams/validate_diagrams.py

Exits non-zero if any label escapes the canvas. Geometry that *should* extend
beyond a viewBox (none by convention here) would be reported as a failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Measure text bboxes in user units regardless of CSS scaling.
JS = """
() => {
  const svg = document.querySelector('svg');
  if (!svg) return {error: 'no svg'};
  const vb = svg.viewBox.baseVal;
  // Pin the SVG to 1 CSS px per user unit so getCTM returns viewBox units.
  svg.style.width = vb.width + 'px';
  svg.style.height = vb.height + 'px';
  svg.setAttribute('width', vb.width);
  svg.setAttribute('height', vb.height);
  void svg.getBoundingClientRect();  // force reflow before measuring
  const out = [];
  svg.querySelectorAll('text').forEach((t) => {
    let b, m;
    try { b = t.getBBox(); m = t.getCTM(); } catch (e) { return; }
    if (!m) return;
    // Map the local bbox corners into the SVG viewport space.
    const pts = [
      [b.x, b.y], [b.x + b.width, b.y],
      [b.x, b.y + b.height], [b.x + b.width, b.y + b.height],
    ].map(([x, y]) => ({ x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f }));
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const x0 = Math.min(...xs), y0 = Math.min(...ys);
    const x1 = Math.max(...xs), y1 = Math.max(...ys);
    const label = (t.textContent || '').trim().slice(0, 48);
    if (x0 < -1 || y0 < -1 || x1 > vb.width + 1 || y1 > vb.height + 1) {
      out.push({
        label,
        x: Math.round(x0), y: Math.round(y0),
        w: Math.round(x1 - x0), h: Math.round(y1 - y0),
      });
    }
  });
  return {vw: Math.round(vb.width), vh: Math.round(vb.height), overflow: out};
}
"""


def check(slug: str) -> list[str]:
    from playwright.sync_api import sync_playwright

    src = HERE / f"{slug}.html"
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.goto(src.as_uri())
        page.wait_for_load_state("networkidle")
        result = page.evaluate(JS)
        browser.close()

    if isinstance(result, dict) and result.get("error"):
        return [f"{slug}: {result['error']}"]
    for o in result.get("overflow", []):
        problems.append(
            f"{slug}: text {o['label']!r} at ({o['x']},{o['y']}) "
            f"{o['w']}x{o['h']} escapes {result['vw']}x{result['vh']}"
        )
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slugs", nargs="*", help="Default: every *.html source.")
    args = ap.parse_args(argv)
    slugs = args.slugs or sorted(p.stem for p in HERE.glob("*.html"))
    all_problems: list[str] = []
    for slug in slugs:
        problems = check(slug)
        all_problems.extend(problems)
        print(("FAIL " if problems else "ok   ") + slug)
    if all_problems:
        print("\n--- problems ---")
        for p in all_problems:
            print(p)
        return 1
    print(f"\n{len(slugs)} diagram(s): all labels inside their viewBox.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
