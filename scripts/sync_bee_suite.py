#!/usr/bin/env python3
"""Sync the Open Swarm bee avatar suite into its deployment surfaces.

Mirrors the suite from ``assets/avatars/bee`` into:
  - Django static: ``src/swarm/static/img/avatars/bee``
  - Vite public:   ``webui/frontend/public/avatars/bee``

Mirror semantics: destination SVGs that no longer exist in the source are
removed, so renaming/deleting an icon cannot leave stale copies behind.
``manifest.json`` is regenerated and ``catalog.html`` is copied alongside.

The script fails loudly with actionable errors (source missing, wrong SVG
count, unwritable destinations) instead of crashing on bare asserts.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "assets" / "avatars" / "bee"
TARGETS = [
    REPO / "src" / "swarm" / "static" / "img" / "avatars" / "bee",
    REPO / "webui" / "frontend" / "public" / "avatars" / "bee",
]
EXPECTED_SVG_COUNT = 12


def _fail(msg: str) -> RuntimeError:
    """Build a RuntimeError with an actionable, prefixed message."""
    return RuntimeError(f"sync_bee_suite: {msg}")


def _sync_target(target: Path, svgs: list[Path], source_names: set[str]) -> None:
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _fail(f"failed to create directory {target}") from exc

    # Mirror: drop destination SVGs that no longer exist in the source so
    # renames/deletes cannot leave stale icons behind.
    for existing in sorted(target.glob("*.svg")):
        if existing.name not in source_names:
            try:
                existing.unlink()
            except OSError as exc:
                raise _fail(f"failed to remove stale destination {existing}") from exc
            print(f"removed stale {existing.relative_to(REPO)}")

    for svg in svgs:
        try:
            shutil.copy2(svg, target / svg.name)
        except OSError as exc:
            raise _fail(f"failed to copy {svg} -> {target}") from exc

    try:
        shutil.copy2(SRC / "catalog.html", target / "catalog.html")
    except OSError as exc:
        raise _fail(f"failed to copy catalog.html -> {target}") from exc


def main() -> int:
    if not SRC.is_dir():
        raise _fail(f"source directory missing: {SRC}")

    svgs = sorted(SRC.glob("*.svg"))
    if len(svgs) != EXPECTED_SVG_COUNT:
        raise _fail(
            f"expected {EXPECTED_SVG_COUNT} SVGs but found {len(svgs)} in {SRC}"
        )
    source_names = {svg.name for svg in svgs}

    manifest = {
        "suite": "Open Swarm Bee Avatar Suite",
        "version": "1.0.0",
        "count": len(svgs),
        "icons": [
            {
                "filename": svg.name,
                "category": "profile" if "profile" in svg.name else "face",
                "url_spa": f"/avatars/bee/{svg.name}",
                "url_django": f"/static/img/avatars/bee/{svg.name}",
            }
            for svg in svgs
        ],
    }

    try:
        manifest_json = json.dumps(manifest, indent=2)
        (SRC / "manifest.json").write_text(manifest_json, encoding="utf-8")
    except OSError as exc:
        raise _fail(f"failed to write manifest to {SRC}") from exc

    for target in TARGETS:
        _sync_target(target, svgs, source_names)
        try:
            (target / "manifest.json").write_text(manifest_json, encoding="utf-8")
        except OSError as exc:
            raise _fail(f"failed to write manifest to {target}") from exc

    print(
        f"Synced {len(svgs)} SVGs + manifest.json + catalog.html "
        f"to {len(TARGETS)} targets."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
