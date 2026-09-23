"""#1030 — source-surface reader for source-pin tests.

#856 keeps shedding code out of the orchestrator components into packages
(``features/chat/*``, ``components/sidebar/*``, the ``lib/api`` package, ...).
Every extraction slice breaks the crop of source-pin tests that read the
orchestrator file directly and assert a token exists — see the churn in
#1024 and #1027.

Contract: **pin behaviour, not file location.** Pass the orchestrator plus
every package directory it may shed code into; the pin then survives future
slices by construction.

    from helpers.source_surface import chat_surface, sidebar_surface

    def test_wires_generation_complete():
        assert "notifyGenerationComplete" in chat_surface()

Surface = the orchestrator file plus every ``*.ts``/``*.tsx`` under the
package directories, concatenated in sorted order (deterministic across
platforms and runs).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "webui" / "frontend" / "src"

_ORCHESTRATORS: dict[str, Path] = {
    "chat": FRONTEND_SRC / "pages" / "ChatPage.tsx",
    "sidebar": FRONTEND_SRC / "components" / "AgentSidebar.tsx",
    "settings": FRONTEND_SRC / "components" / "SettingsSheet.tsx",
}

_PACKAGES: dict[str, list[Path]] = {
    "chat": [FRONTEND_SRC / "features" / "chat"],
    "sidebar": [FRONTEND_SRC / "components" / "sidebar", FRONTEND_SRC / "features" / "sidebar"],
    # #1016 split SettingsSheet into components/settings/ (kernel + panes).
    "settings": [FRONTEND_SRC / "components" / "settings"],
}


def surface(orchestrator: Path, *package_dirs: Path, glob: str = "*.ts*") -> str:
    """Concatenated source of an orchestrator component and its packages.

    The orchestrator file is always included; each package directory is
    included when it exists (pre-extraction repos stay green), reading every
    file matching ``glob`` in sorted order.
    """
    parts = [orchestrator.read_text(encoding="utf-8")]
    for pkg in package_dirs:
        if pkg.is_dir():
            parts.extend(
                p.read_text(encoding="utf-8") for p in sorted(pkg.glob(glob)) if p.is_file()
            )
    return "\n".join(parts)


def _named(name: str) -> str:
    orch = _ORCHESTRATORS[name]
    return surface(orch, *_PACKAGES.get(name, ()))


def chat_surface() -> str:
    """ChatPage + ``features/chat/*``."""
    return _named("chat")


def sidebar_surface() -> str:
    """AgentSidebar + ``components/sidebar/*`` + ``features/sidebar/*``."""
    return _named("sidebar")


def settings_surface() -> str:
    """SettingsSheet + ``components/settings/*``."""
    return _named("settings")


def api_surface() -> str:
    """The ``lib/api`` package in its entirety (#856 slice A made the package
    the single home — there is no ``lib/api.ts`` orchestrator anymore)."""
    pkg = FRONTEND_SRC / "lib" / "api"
    if not pkg.is_dir():
        legacy = FRONTEND_SRC / "lib" / "api.ts"
        if legacy.is_file():
            return legacy.read_text(encoding="utf-8")
        raise FileNotFoundError(f"neither {pkg} nor {legacy} exists")
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(pkg.glob("*.ts")) if p.is_file()
    )


# ---------------------------------------------------------------------------
# #1055 — declarative assertions with messages that NAME the home.
#
# A raw ``assert 'token' in surface()`` dumps 6,000 concatenated lines on
# failure and hides which file the token lives in (or was expected in).
# ``pin_source`` searches per file and reports homes by name.

_SURFACE_PARTS = {
    "chat": [("pages/ChatPage.tsx", _ORCHESTRATORS["chat"])],
    "sidebar": [("components/AgentSidebar.tsx", _ORCHESTRATORS["sidebar"])],
    "settings": [("components/SettingsSheet.tsx", _ORCHESTRATORS["settings"])],
}


def _parts(name: str) -> list[tuple[str, Path]]:
    """(label, path) pairs for a surface, orchestrator first."""
    parts = list(_SURFACE_PARTS[name])
    for pkg in _PACKAGES.get(name, ()):
        if pkg.is_dir():
            parts.extend((p.name, p) for p in sorted(pkg.glob("*.ts*")) if p.is_file())
    return parts


def pin_source(
    surface_name: str,
    *,
    contains: list[str] | None = None,
    not_contains: list[str] | None = None,
    count: dict[str, int] | None = None,
    regex: list[str] | None = None,
) -> tuple[bool, str]:
    """Declarative source-pin over a named surface.

    Returns ``(ok, message)`` — never raises — so callers can simply
    ``assert ok, msg``. On failure the message names the home each token was
    found in (or the full list of homes searched), not a file dump.
    """
    import re as _re

    contains = contains or []
    not_contains = not_contains or []
    count = count or {}
    regex = regex or []

    parts = _parts(surface_name)
    texts = [(label, p.read_text(encoding="utf-8")) for label, p in parts]
    homes = ", ".join(label for label, _ in parts)
    problems: list[str] = []

    for token in contains:
        found_in = [label for label, t in texts if token in t]
        if not found_in:
            problems.append(f"{token!r} not found in any of: {homes}")

    for token in not_contains:
        found_in = [label for label, t in texts if token in t]
        if found_in:
            problems.append(f"forbidden token {token!r} found in: {', '.join(found_in)}")

    for token, minimum in count.items():
        total = sum(t.count(token) for _, t in texts)
        if total < minimum:
            problems.append(f"{token!r} occurs {total}x, expected >= {minimum}")

    for pattern in regex:
        if not any(_re.search(pattern, t) for _, t in texts):
            problems.append(f"regex {pattern!r} matched none of: {homes}")

    if problems:
        return False, "\n".join(problems)
    return True, f"ok ({surface_name}: {homes})"
