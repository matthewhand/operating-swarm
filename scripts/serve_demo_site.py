#!/usr/bin/env python3
"""Serve the mocked VITE_DEMO_MODE SPA for local or kiosk hosting (issue #439).

No Django, no LLM, no Fly token. Build first with ``make demo-build``.
``/`` and ``/chat`` both return ``index.html``.
"""

from __future__ import annotations

import argparse
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIST = REPO / "webui" / "frontend" / "dist"
DEFAULT_PORT = 8765


def demo_file_for(url_path: str, dist: Path) -> Path:
    """Map a request path onto dist. SPA routes fall back to index.html."""
    raw = urlparse(url_path).path
    rel = raw.lstrip("/")
    if not rel or rel.endswith("/"):
        nested = dist / rel / "index.html" if rel else dist / "index.html"
        return nested if nested.is_file() else dist / "index.html"
    fs = dist / rel
    if fs.is_file():
        return fs
    if fs.is_dir() and (fs / "index.html").is_file():
        return fs / "index.html"
    if rel.startswith("assets/") or rel.startswith("favicon") or Path(rel).suffix:
        return fs
    return dist / "index.html"


def require_dist(dist: Path) -> None:
    index = dist / "index.html"
    if not index.is_file():
        raise SystemExit(
            f"Demo dist missing ({index}). Run: make demo-build\n"
            "Then: python scripts/serve_demo_site.py"
        )


class DemoHandler(SimpleHTTPRequestHandler):
    dist: Path = DEFAULT_DIST

    def translate_path(self, path: str) -> str:  # noqa: D401
        mapped = demo_file_for(path, self.dist)
        return os.fspath(mapped.resolve())

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("demo-serve: " + (fmt % args) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify dist exists and print the URL, then exit (no listen).",
    )
    args = parser.parse_args(argv)
    dist = args.dist.resolve()
    require_dist(dist)
    print("Operating Swarm DEMO — mocked inference, no live LLM.")
    print(f"dist={dist}")
    print(f"Open http://127.0.0.1:{args.port}/ and http://127.0.0.1:{args.port}/chat")
    if args.check:
        return 0
    DemoHandler.dist = dist
    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), DemoHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
