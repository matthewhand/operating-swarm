"""Issue #1256 — confined host directory browsing for the agent Folder picker.

A CLI agent can bind a *Folder* as its process cwd, but the SPA Folder field
was a raw text input. ``GET /v1/fs/directories`` now lists the child
directories of a server path so the editor can offer a browser.

Browsing is confined to a small set of roots so the endpoint can never become
an arbitrary filesystem oracle:

* the user's home directory (the default root), and
* the Swarm workspaces root (``workdir.get_workspaces_dir``).

``ALLOW_UNRESTRICTED_WORKDIR=true`` — the existing local power-user escape
(see :mod:`swarm.core.workdir`) — lifts the confinement. Tests override the
roots with ``SWARM_FS_BROWSE_ROOTS`` (``os.pathsep``-separated) so no real
home directory is read.
"""

from __future__ import annotations

import os
from pathlib import Path

from swarm.core.workdir import (
    _is_under,
    get_workspaces_dir,
    unrestricted_workdir_allowed,
)

ENV_FS_BROWSE_ROOTS = "SWARM_FS_BROWSE_ROOTS"


class FsBrowseError(ValueError):
    """A browse request the endpoint must reject. ``status_code`` is the HTTP code."""

    status_code = 400


class FsBrowseNotFound(FsBrowseError):
    status_code = 404


class FsBrowseForbidden(FsBrowseError):
    status_code = 403


def get_browse_roots() -> list[Path]:
    """Resolved roots a request may browse. Empty only when none are usable."""
    override = os.environ.get(ENV_FS_BROWSE_ROOTS, "").strip()
    if override:
        raw_roots = [part for part in override.split(os.pathsep) if part.strip()]
    else:
        raw_roots = [str(Path.home()), str(get_workspaces_dir())]
    roots: list[Path] = []
    for raw in raw_roots:
        try:
            roots.append(Path(raw).expanduser().resolve())
        except OSError:
            continue
    return roots


def _default_root() -> Path:
    roots = get_browse_roots()
    if not roots:
        raise FsBrowseForbidden("No browse roots are configured on this server.")
    return roots[0]


def _is_allowed(path: Path) -> bool:
    if unrestricted_workdir_allowed():
        return True
    return any(_is_under(path, root) for root in get_browse_roots())


def resolve_browse_path(raw: str | None) -> Path:
    """Resolve *raw* to an existing directory under the allowed roots.

    Blank / ``None`` defaults to the first browse root (the user's home).
    Relative paths join under that root. ``..`` / symlink escapes are blocked
    by resolving before the containment check.
    """
    text = (raw or "").strip()
    if "\x00" in text:
        raise FsBrowseError("Invalid path.")
    root = _default_root()
    candidate = Path(text).expanduser() if text else root
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise FsBrowseError(f"Could not resolve path: {exc}") from exc
    if not _is_allowed(resolved):
        raise FsBrowseForbidden(
            "That path is outside the permitted browse roots on this server."
        )
    if not resolved.exists():
        raise FsBrowseNotFound(f"{resolved} does not exist.")
    if not resolved.is_dir():
        raise FsBrowseError(f"{resolved} is not a directory.")
    return resolved


def list_child_directories(path: Path) -> list[dict]:
    """Immediate child directories of *path*: name, full path, git-repo flag.

    Directories that resolve outside the allowed roots (e.g. a symlink to
    ``/etc``) are skipped so the browser never advertises a forbidden target.
    """
    try:
        entries = list(os.scandir(path))
    except OSError as exc:
        raise FsBrowseError(f"Could not read {path}: {exc}") from exc

    restrictive = not unrestricted_workdir_allowed()
    children: list[dict] = []
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=True):
                continue
        except OSError:
            continue
        child = Path(entry.path)
        if restrictive:
            try:
                if not _is_allowed(child.resolve()):
                    continue
            except OSError:
                continue
        try:
            is_git_repo = (child / ".git").exists()
        except OSError:
            is_git_repo = False
        children.append(
            {"name": entry.name, "path": str(child), "is_git_repo": is_git_repo}
        )
    children.sort(key=lambda item: item["name"].lower())
    return children


def _parent_of(path: Path) -> str | None:
    """Parent path for the Up control, or ``None`` at a browse boundary."""
    parent = path.parent
    if parent == path:
        return None
    if not unrestricted_workdir_allowed() and not _is_allowed(parent):
        return None
    return str(parent)


def browse_directory(raw: str | None = None) -> dict:
    """Listing payload for the directory picker."""
    path = resolve_browse_path(raw)
    return {
        "path": str(path),
        "parent": _parent_of(path),
        "roots": [str(root) for root in get_browse_roots()],
        "entries": list_child_directories(path),
    }
