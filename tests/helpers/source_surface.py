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
    "settings": [FRONTEND_SRC / "features" / "settings"],
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
    """SettingsSheet + ``features/settings/*``."""
    return _named("settings")
