#!/usr/bin/env python3
"""DuckDuckGo web search — free, no API key, stdlib only.

Usage:
    python3 search.py "query" [--max N] [--json]

Hits the DuckDuckGo lite HTML endpoint (no JavaScript required) and prints
numbered results (title, URL, snippet). Honesty contract: on failure, print
the error and exit non-zero — never fabricate results.

Reference: https://mcp.directory/skills/ddg-search (openclaw ddg-search skill).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

LITE_URL = "https://lite.duckduckgo.com/lite/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
TIMEOUT_SECONDS = 15
MAX_RESULTS_CAP = 10
MAX_SNIPPET_CHARS = 300

# Result links look like /l/?uddg=<urlencoded-destination>&rut=...
_UDDG_RE = re.compile(r"[?&]uddg=([^&]+)")


class _LiteParser(HTMLParser):
    """Extract (title, url, snippet) triples from the lite results table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._link: str | None = None
        self._in_title = False
        self._in_snippet = False
        self._title = ""
        self._snippet = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        css_class = attrs_dict.get("class") or ""
        if tag == "a" and "result-link" in css_class:
            href = attrs_dict.get("href") or ""
            # Lite responses mix redirect links (/l/?uddg=<enc>) with direct
            # http(s) hrefs; accept both.
            if "uddg=" in href or href.startswith(("http://", "https://", "//")):
                if self._link is not None:
                    self._flush()  # previous row is complete: emit it
                self._link = href
                self._title = ""
                self._in_title = True
        elif tag == "td" and "result-snippet" in css_class:
            self._in_snippet = True
            self._snippet = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        elif tag == "td" and self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title += data
        elif self._in_snippet:
            self._snippet += data

    def close(self) -> None:  # noqa: D102 (flush the trailing row on close)
        super().close()
        self._flush()

    def _flush(self) -> None:
        title = " ".join(self._title.split())
        if self._link and title:
            self.results.append(
                {
                    "title": title,
                    "url": _decode_uddg(self._link),
                    "snippet": " ".join(self._snippet.split())[:MAX_SNIPPET_CHARS],
                }
            )
            self._link = None


def _decode_uddg(href: str) -> str:
    """Decode a duckduckgo redirect link to its destination URL."""
    if href.startswith("//"):
        href = "https:" + href
    match = _UDDG_RE.search(href)
    if match:
        return html.unescape(urllib.parse.unquote(match.group(1)))
    return urllib.parse.urljoin(LITE_URL, href)


def _dedupe(results: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in results:
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        out.append(row)
    return out


def search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    """Return up to *max_results* {title, url, snippet} rows for *query*."""
    if not query or not query.strip():
        raise ValueError("query must be non-empty")
    limit = max(1, min(int(max_results), MAX_RESULTS_CAP))
    body = urllib.parse.urlencode({"q": query.strip()}).encode("utf-8")
    request = urllib.request.Request(
        LITE_URL,
        data=body,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            page = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # must precede URLError (it subclasses it)
        raise RuntimeError(
            f"duckduckgo request failed: HTTP {exc.code} {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise RuntimeError(
                f"duckduckgo request timed out after {TIMEOUT_SECONDS}s"
            ) from exc
        raise RuntimeError(
            f"duckduckgo request failed: {type(reason).__name__}: {reason}"
        ) from exc
    except TimeoutError as exc:  # some transports surface socket timeouts directly
        raise RuntimeError(
            f"duckduckgo request timed out after {TIMEOUT_SECONDS}s"
        ) from exc

    # html.parser.HTMLParseError is never raised by the lenient CPython parser
    # (it was removed as a raised exception in 3.5+). What can escape feed()/
    # close() is an exception from our own handle_*/_flush callbacks or a
    # RecursionError on pathologically nested markup. Both are wrapped with
    # context below instead of being masked by a bare except.
    parser = _LiteParser()
    try:
        parser.feed(page)
        parser.close()
    except RecursionError as exc:
        raise RuntimeError(
            "duckduckgo response parse failed: markup too deeply nested"
        ) from exc
    except (TypeError, AttributeError, ValueError, IndexError) as exc:
        raise RuntimeError(
            f"duckduckgo response parse failed: {type(exc).__name__}: {exc}"
        ) from exc

    results = _dedupe(parser.results)[:limit]
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search the web via DuckDuckGo.")
    parser.add_argument("query", help="search query text")
    parser.add_argument("--max", type=int, default=8, help="max results (1-10)")
    parser.add_argument("--json", action="store_true", help="emit JSON rows")
    args = parser.parse_args(argv)

    try:
        results = search(args.query, max_results=args.max)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("No results.")
        return 0

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    for index, row in enumerate(results, start=1):
        print(f"{index}. {row['title']}")
        print(f"   {row['url']}")
        if row["snippet"]:
            print(f"   {row['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
