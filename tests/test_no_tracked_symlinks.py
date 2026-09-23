"""#630 — the index must not track symlinks; .gitignore must match them.

`node_modules/` (trailing slash) matches *directories only*, so an
accidentally committed `node_modules` **symlink** slipped into the index:
fresh clones materialise a dangling absolute path and every host whose
on-disk layout differs from the committer's sees phantom typechange dirt in
`git status`. Both halves must hold: no tracked symlinks anywhere, and a
type-agnostic ignore pattern for `node_modules`.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TRACKED_SYMLINKS = [
    line.split(maxsplit=3)[3]
    for line in subprocess.check_output(
        ["git", "ls-files", "-s"], cwd=REPO_ROOT, text=True
    ).splitlines()
    if line.startswith("120000")
]


def test_index_tracks_no_symlinks():
    """A symlink in the index breaks fresh clones and phantom-dirties status."""
    assert TRACKED_SYMLINKS == [], (
        "symlinks tracked in the index defeat directory-only .gitignore "
        "patterns and break fresh clones — untrack these and ignore them "
        f"by name: {TRACKED_SYMLINKS}"
    )


def test_gitignore_matches_node_modules_regardless_of_type():
    """.gitignore must hide `node_modules` whether it is a directory or a
    symlink on disk — the directory-only `node_modules/` form is the hole
    that let the symlink get committed."""
    gitignore = [
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    ]
    assert "node_modules" in gitignore, (
        ".gitignore needs a bare `node_modules` pattern (not only the "
        "directory-only `node_modules/`) so a symlink of that name is also "
        "ignored"
    )
