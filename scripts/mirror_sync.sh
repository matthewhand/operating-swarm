#!/usr/bin/env bash
# #1034 — private -> public mirror sync.
#
# The public mirror (matthewhand/operating-swarm) tracks the sanitised
# private SoT (matthewhand/open-swarm-private). This script makes the sync
# repeatable: sanitisation gate -> mirror commit on top of public main ->
# dated branch + PR -> optional prod fast-forward.
#
# Usage:
#   scripts/mirror_sync.sh                # build mirror branch + PR
#   scripts/mirror_sync.sh --fast-forward # also ff prod checkout, migrate, restart
#   scripts/mirror_sync.sh --check        # drift detector only (exit 1 if drifted)
#
# Hard stops honoured here:
#   - never pushes anything to public unless tests/test_tracked_files_sanitization.py is green
#   - upstream commits use author/committer mhand <11550632+matthewhand@users.noreply.github.com>
#   - a failed dated-branch push aborts the sync (#1112): the old
#     "push ... 2>/dev/null" could exit 0 having published nothing.
set -euo pipefail

# #1112: the mirror SoT is matthewhand/operating-swarm. The old default
# remote ("public" -> open-swarm.git) pushed dated branches to a repo that
# must not carry them, then gh pr create failed because the branch existed
# nowhere the PR could see.
PRIVATE_REMOTE="${PRIVATE_REMOTE:-mirror}"
PUBLIC_REPO="${PUBLIC_REPO:-matthewhand/operating-swarm}"
PUBLIC_MAIN="${PUBLIC_MAIN:-main}"
PROD_DIR="${PROD_DIR:-$HOME/dev/dormant/open-swarm}"
PROD_PORT="${PROD_PORT:-8102}"
MHAND_NAME="mhand"
MHAND_EMAIL="11550632+matthewhand@users.noreply.github.com"
DRIFT_THRESHOLD="${DRIFT_THRESHOLD:-50}"

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"

MODE="sync"
[ "${1:-}" = "--fast-forward" ] && MODE="ff"
[ "${1:-}" = "--check" ] && MODE="check"

git fetch "$PRIVATE_REMOTE" --quiet
PUBLIC_TIP="$(git rev-parse "$PRIVATE_REMOTE/$PUBLIC_MAIN")"
PRIVATE_TIP="$(git rev-parse HEAD)"

# #1112: prove the configured remote IS the mirror before publishing to it.
REMOTE_URL="$(git remote get-url "$PRIVATE_REMOTE")"
case "$REMOTE_URL" in
  *"operating-swarm"*) ;;
  *)
    echo "FAIL: remote '$PRIVATE_REMOTE' points at $REMOTE_URL, not the mirror" >&2
    echo "      fix: git remote add mirror https://github.com/matthewhand/operating-swarm.git" >&2
    exit 1
    ;;
esac

if [ "$MODE" = "check" ]; then
  # Content drift, not commit count: the mirror uses commit-tree, so private
  # history never lands in public — the trees are the truth. Tree equality
  # is the definitive "in sync" verdict (#1112); the file counter below it
  # only exists to warn before drift crosses the old threshold.
  PUBLIC_TREE="$(git rev-parse "$PRIVATE_REMOTE/$PUBLIC_MAIN^{tree}")"
  PRIVATE_TREE="$(git rev-parse HEAD^{tree})"
  if [ "$PUBLIC_TREE" = "$PRIVATE_TREE" ]; then
    echo "OK: trees identical (public $(echo "$PUBLIC_TIP" | cut -c1-8), private $(echo "$PRIVATE_TIP" | cut -c1-8))"
    exit 0
  fi
  changed="$(git diff --name-only "$PRIVATE_REMOTE/$PUBLIC_MAIN" HEAD | wc -l)"
  echo "drift: public at $(echo "$PUBLIC_TIP" | cut -c1-8), private at $(echo "$PRIVATE_TIP" | cut -c1-8): $changed files differ"
  if [ "$changed" -gt "$DRIFT_THRESHOLD" ]; then
    echo "FAIL: $changed files differ (threshold $DRIFT_THRESHOLD) — run scripts/mirror_sync.sh" >&2
    exit 1
  fi
  echo "OK: within threshold"
  exit 0
fi

drift="$(git diff --name-only "$PRIVATE_REMOTE/$PUBLIC_MAIN" HEAD | wc -l)"
if [ "$drift" -eq 0 ]; then
  echo "Mirror already up to date ($PRIVATE_TIP); nothing to do."
  exit 0
fi
echo "private tree differs from public in $drift files — syncing"

echo "== sanitisation gate =="
API_AUTH_TOKEN="" .venv/bin/pytest tests/test_tracked_files_sanitization.py -q --no-cov

DATE_STAMP="$(date +%Y-%m-%d)"
BRANCH="mirror-sync-$DATE_STAMP"
TREE="$(git rev-parse HEAD^{tree})"

MSG="$(cat <<EOF
mirror: sync sanitised runtime from private SoT ($DATE_STAMP)

Tree identical to the private source of truth tip ($PRIVATE_TIP);
sanitisation gate green. See docs/MIRROR_SYNC.md.

Generated with Codebuff
Co-Authored-By: Codebuff <noreply@codebuff.com>
EOF
)"

MCOMMIT="$(printf '%s\n' "$MSG" | GIT_AUTHOR_NAME="$MHAND_NAME" GIT_AUTHOR_EMAIL="$MHAND_EMAIL" \
  GIT_COMMITTER_NAME="$MHAND_NAME" GIT_COMMITTER_EMAIL="$MHAND_EMAIL" \
  git commit-tree "$TREE" -p "$PUBLIC_TIP")"
echo "mirror commit: $(echo "$MCOMMIT" | cut -c1-8)"

# #1112: a failed push used to be swallowed here (2>/dev/null), so the
# script printed the commit hash and exited 0 having published nothing.
# Now: loud failure, then verification that the branch actually landed.
echo "== publish dated branch =="
git push "$PRIVATE_REMOTE" "$MCOMMIT:refs/heads/$BRANCH" --quiet
if ! git ls-remote --heads "$PRIVATE_REMOTE" "refs/heads/$BRANCH" | grep -q "$MCOMMIT"; then
  echo "FAIL: dated branch missing on $PRIVATE_REMOTE after push" >&2
  exit 1
fi

PR_URL="$(gh pr create --repo "$PUBLIC_REPO" --base "$PUBLIC_MAIN" --head "$BRANCH" \
  --title "mirror: sync sanitised runtime from private SoT ($DATE_STAMP)" \
  --body "Scheduled sanitised mirror sync ($drift files differ from the last sync).

- Tree identical to the private tip; sanitisation gate green.
- Author/committer: \`$MHAND_NAME <$MHAND_EMAIL>\` per upstream policy.

Ref: matthewhand/open-swarm-private#1034")"
echo "PR: $PR_URL"

if [ "$MODE" = "ff" ]; then
  echo "== prod fast-forward ($PROD_DIR) =="
  gh pr merge "$BRANCH" --repo "$PUBLIC_REPO" --merge --admin
  sleep 3
  git -C "$PROD_DIR" fetch origin --quiet
  git -C "$PROD_DIR" merge --ff-only origin/main
  ( cd "$PROD_DIR" && uv sync --frozen )
  ( cd "$PROD_DIR" && .venv/bin/python manage.py migrate --no-input )
  if curl -sf "http://localhost:$PROD_PORT/healthz/" >/dev/null 2>&1; then
    pid="$(ss -ltnp 2>/dev/null | grep ":$PROD_PORT " | grep -oP 'pid=\K[0-9]+' | head -1)"
    [ -n "$pid" ] && kill "$pid" && sleep 2
  fi
  TMUX= tmux kill-session -t "os$PROD_PORT" 2>/dev/null || true
  TMUX= tmux new-session -d -s "os$PROD_PORT" \
    "cd '$PROD_DIR' && exec .venv/bin/python -m uvicorn swarm.asgi:application --host 0.0.0.0 --port '$PROD_PORT' --workers 1 > '/tmp/os-$PROD_PORT.log' 2>&1"
  sleep 8
  curl -sf "http://localhost:$PROD_PORT/healthz/" >/dev/null && echo "prod :$PROD_PORT healthy" || {
    echo "prod :$PROD_PORT did not come up — check /tmp/os-$PROD_PORT.log" >&2
    exit 1
  }
  git push "$PRIVATE_REMOTE" --delete "$BRANCH" --quiet 2>/dev/null || true
fi
