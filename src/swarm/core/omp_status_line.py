"""omp-inspired CLI status line (REQ-843)."""

from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import dataclass
from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "ascii": {
        "left": ["model", "path", "git"],
        "right": ["session"],
        "separator": "ascii",
    },
    "minimal": {
        "left": ["path", "git"],
        "right": ["session"],
        "separator": "slash",
    },
    "compact": {
        "left": ["model", "git"],
        "right": ["session"],
        "separator": "pipe",
    },
    "default": {
        "left": ["model", "path", "git"],
        "right": ["session", "hostname"],
        "separator": "powerline-thin",
    },
    "full": {
        "left": ["model", "hostname", "path", "git"],
        "right": ["session"],
        "separator": "powerline",
    },
}

SEPARATORS: dict[str, tuple[str, str]] = {
    "ascii": ("|", "|"),
    "slash": ("/", "/"),
    "pipe": ("|", "|"),
    "powerline-thin": ("›", "‹"),
    "powerline": ("▶", "◀"),
    "none": (" ", " "),
}

_GIT_TIMEOUT = 1.0


@dataclass(frozen=True)
class GitSnapshot:
    branch: str
    staged: int = 0
    unstaged: int = 0
    untracked: int = 0

    @property
    def dirty(self) -> bool:
        return bool(self.staged or self.unstaged or self.untracked)


def normalize_preset(name: str | None) -> str:
    key = str(name or "ascii").strip().lower()
    if key == "nerd":
        return "full"
    if key == "custom":
        return "ascii"
    return key if key in PRESETS else "ascii"


def inspect_git(cwd: str | None) -> GitSnapshot | None:
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if branch.returncode != 0:
            return None
        name = (branch.stdout or "").strip() or "HEAD"
        porcelain = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        staged = unstaged = untracked = 0
        for raw in (porcelain.stdout or "").splitlines():
            if raw.startswith("?"):
                untracked += 1
                continue
            if len(raw) < 2:
                continue
            if raw[0] not in {" ", "?"}:
                staged += 1
            if raw[1] not in {" ", "?"}:
                unstaged += 1
        return GitSnapshot(name, staged=staged, unstaged=unstaged, untracked=untracked)
    except Exception:
        return None


def _abbrev_path(cwd: str | None) -> str:
    if not cwd:
        return ""
    path = os.path.abspath(cwd)
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        path = "~" + path[len(home) :]
    parts = path.replace("\\", "/").rstrip("/").split("/")
    if len(parts) <= 2:
        return "/".join(parts) or path
    return "/".join(parts[-2:])


def _git_text(snap: GitSnapshot) -> str:
    bits = [snap.branch]
    if snap.unstaged:
        bits.append(f"*{snap.unstaged}")
    if snap.staged:
        bits.append(f"+{snap.staged}")
    if snap.untracked:
        bits.append(f"?{snap.untracked}")
    return " ".join(bits)


def _segment(
    sid: str,
    *,
    cli: str | None,
    workdir: str | None,
    session: str | None,
    hostname: str | None,
    git: GitSnapshot | None,
) -> str:
    if sid == "model":
        return str(cli or "").strip()
    if sid == "path":
        return _abbrev_path(workdir)
    if sid == "git":
        return _git_text(git) if git else ""
    if sid == "session":
        raw = str(session or "").strip()
        return raw[-8:] if raw else ""
    if sid == "hostname":
        host = hostname if hostname is not None else socket.gethostname()
        return str(host).split(".", 1)[0]
    return ""


def render_status_line(
    *,
    workdir: str | None = None,
    cli: str | None = None,
    preset: str | None = None,
    session: str | None = None,
    hostname: str | None = None,
    git: GitSnapshot | None = None,
) -> str:
    """Render an omp-style status line. Never raises."""
    name = normalize_preset(preset)
    spec = PRESETS[name]
    left_sep, right_sep = SEPARATORS.get(spec["separator"], SEPARATORS["ascii"])
    snap = git if git is not None else inspect_git(workdir)
    kwargs = {
        "cli": cli,
        "workdir": workdir,
        "session": session,
        "hostname": hostname,
        "git": snap,
    }
    left = [part for sid in spec["left"] if (part := _segment(sid, **kwargs))]
    right = [part for sid in spec["right"] if (part := _segment(sid, **kwargs))]
    left_text = f" {left_sep} ".join(left)
    right_text = f" {right_sep} ".join(right)
    if left_text and right_text:
        return f"{left_text}  {right_text}"
    return left_text or right_text
