"""Parsed CSS rule reads, for the properties that really do live in a stylesheet.

Why this exists
---------------
``assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css`` is the
canonical rotted assertion in this repo. It breaks the moment the grid is
re-tuned (it was, in #1262) even though the *behaviour* is intact, and it
passes when the same declaration shows up on some unrelated selector — in a
6,400-line ``index.css`` there are four different ``white-space: pre-wrap``
declarations, so the old pin could not tell the composer's from a routine
dry-run card's.

:func:`rule_bodies` brace-matches each rule body, so nested ``@media`` /
``@container`` / ``@keyframes`` blocks are read whole rather than truncated at
the first ``}``. :func:`declarations` normalises whitespace, so a reformat or
a value written with different spacing is not a failure while a *different
value* still is.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "read_css",
    "rule_bodies",
    "rule",
    "declarations",
    "declaration",
    "declaration_in",
    "selectors",
]

_AT_RULE = re.compile(r"@[\w-]+")


def read_css(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _balanced_bodies(css: str, selector: str) -> list[str]:
    """Every brace-matched body whose prelude ends with ``selector``."""
    out: list[str] = []
    for match in re.finditer(re.escape(selector), css):
        at = match.end()
        # The selector must be a whole compound in its prelude: only whitespace
        # then `{` (or `,` for a grouped selector) may follow. That rejects
        # `.os-fav-tile` matching inside `.os-fav-tile .os-stacked-avatars`,
        # `.os-fav-tile:hover`, and `.os-fav-grid--active` — three different
        # rules that a plain substring would all satisfy.
        tail = at
        while tail < len(css) and css[tail] in " \t\r\n":
            tail += 1
        if tail >= len(css) or css[tail] not in "{,":
            continue
        open_at = css.find("{", at)
        if open_at == -1:
            continue
        close_at = _matching_brace(css, open_at)
        if close_at == -1:
            continue
        out.append(css[open_at + 1 : close_at])
    return out


def _matching_brace(css: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(css)):
        char = css[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def rule_bodies(css: str, selector: str) -> list[str]:
    """All bodies for ``selector`` in source order (a repeated selector gives many)."""
    return _balanced_bodies(css, selector)


def rule(css: str, selector: str) -> str:
    """The first body for ``selector``, or ``''``."""
    bodies = _balanced_bodies(css, selector)
    return bodies[0] if bodies else ""


def selectors(css: str) -> list[str]:
    """Every selector/at-rule prelude in the sheet, in source order."""
    out: list[str] = []
    for match in re.finditer(r"([^{}]+)\{", css):
        prelude = match.group(1).strip()
        if prelude:
            out.append(prelude)
    return out


def declaration_in(css: str, selector: str, prop: str, *, within: str) -> str | None:
    """``prop`` on the rule for ``selector`` inside the body of ``within``.

    For nested rules — a ``prefers-reduced-motion`` block that carries a media
    guard on every one of its selectors.
    """
    for body in _balanced_bodies(css, within):
        for inner in _balanced_bodies(body, selector):
            value = declarations(inner).get(prop.lower())
            if value is not None:
                return value
    return None


def declarations(body: str) -> dict[str, str]:
    """``{'white-space': 'pre-wrap'}`` for a rule body, comments stripped.

    Chunks containing a brace are skipped: a body taken from an at-rule still
    holds the nested rule's selector text, and a pseudo-class in that selector
    (``html:not(...)``) would otherwise be parsed as a declaration whose
    property is ``html``.
    """
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    flat = re.sub(r"\s+", " ", body)
    out: dict[str, str] = {}
    for decl in flat.split(";"):
        if ":" not in decl or "{" in decl:
            continue
        prop, _, value = decl.partition(":")
        prop = prop.strip().lower()
        if not re.fullmatch(r"-?[a-z][a-z0-9-]*", prop):
            continue
        out[prop] = value.strip()
    return out


def declaration(css: str, selector: str, prop: str) -> str | None:
    """The value ``prop`` takes in the *first* body for ``selector``.

    ``None`` when the rule or the declaration is absent, so callers can assert
    on the absence explicitly rather than on a substring not appearing.
    """
    body = rule(css, selector)
    if not body:
        return None
    return declarations(body).get(prop.lower())
