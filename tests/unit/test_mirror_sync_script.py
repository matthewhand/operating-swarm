"""#1112 — mirror_sync.sh must publish to the real mirror and never lie.

The script's job is public-mirror publication; two defects made it silently
publish nothing: it pushed the dated branch to a repo that shouldn't carry
mirror branches (open-swarm.git), and ``2>/dev/null`` swallowed the push
failure while the script exited 0. These pins lock the repaired contract:

1. the default remote/repo pair targets ``matthewhand/operating-swarm`` and
   the script verifies the configured remote's URL before doing anything;
2. a failed dated-branch push is fatal, and the PR step only runs after the
   branch is verified present on the mirror;
3. ``--check`` accepts tree equality (not just a file-count threshold) — the
   mirror uses commit-tree, so identical trees mean "in sync" regardless of
   commit counts.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "mirror_sync.sh"
DOC = REPO / "docs" / "MIRROR_SYNC.md"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_mirror_targets_operating_swarm():
    text = _text()
    assert "PUBLIC_REPO:-matthewhand/operating-swarm}" in text
    # The dated branch lands on the mirror repo, not open-swarm.git.
    assert "PRIVATE_REMOTE:-mirror}" in text
    # And the script proves the configured remote is the mirror before pushing:
    assert 'operating-swarm' in text
    assert "git remote get-url" in text


def test_push_failure_is_fatal_and_branch_verified():
    text = _text()
    # The dated-branch push is not error-swallowed.
    push_line = next(
        ln for ln in text.splitlines() if f"refs/heads/$BRANCH" in ln
    )
    assert "2>/dev/null" not in push_line, "push errors must not be swallowed"
    # ...and the script verifies the branch exists on the mirror before
    # asking GitHub to open a PR from it.
    assert "git ls-remote" in text
    assert "dated branch missing on" in text or "branch missing on" in text


def test_check_mode_accepts_tree_equality():
    text = _text()
    assert "^{tree}" in text
    # The tree-equality verdict must be reachable in --check mode.
    check_region = text.split('if [ "$MODE" = "check" ]; then', 1)[1].split(
        "\nfi\n", 1
    )[0]
    assert "trees identical" in check_region


def test_doc_matches_the_repaired_defaults():
    text = DOC.read_text(encoding="utf-8")
    assert "PRIVATE_REMOTE` (default `mirror`)" in text
    assert "git remote add mirror" in text
