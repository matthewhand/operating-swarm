#!/usr/bin/env bash
# Long-lived SPA preview for visual QA / sign-off (dev-worker-max historically :8001).
# Serves webui/frontend/dist via vite preview. Does NOT bind :8000 (LiteLLM).
set -euo pipefail

PORT="${SPA_PREVIEW_PORT:-8001}"
HOST="${SPA_PREVIEW_HOST:-0.0.0.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FE="$ROOT/webui/frontend"
LOG_DIR="${SPA_PREVIEW_LOG_DIR:-$HOME/grok-logs}"
mkdir -p "$LOG_DIR"

if [[ ! -f "$FE/dist/index.html" ]]; then
  echo "dist missing; building frontend first..."
  "$ROOT/scripts/build_frontend.sh"
fi

if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "ERROR: :${PORT} already in use" >&2
  ss -ltnp 2>/dev/null | grep ":${PORT}" || true
  exit 1
fi

# Guard: refuse to target LiteLLM port
if [[ "$PORT" == "8000" ]]; then
  echo "ERROR: refusing port 8000 (reserved / LiteLLM). Set SPA_PREVIEW_PORT." >&2
  exit 1
fi

cd "$FE"
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh"
  nvm use 22 >/dev/null 2>&1 || true
fi

# Build provenance: record the SHA that actually produced dist/, not blindly
# the current HEAD. When dist is newer than the repo's last commit and carries
# a marker, keep the original marker (greptile P1: provenance must not be
# overwritten by a launcher run from a different checkout).
SHA="$(git -C "$ROOT" rev-parse HEAD)"
MARKER="$FE/dist/.preview-sha"
DIST_INDEX="$FE/dist/index.html"
if [[ -s "$MARKER" && -f "$DIST_INDEX" ]] && [[ "$MARKER" -nt "$DIST_INDEX" ]]; then
  PREV_SHA="$(cat "$MARKER")"
  if [[ -n "$PREV_SHA" && "$PREV_SHA" != "$SHA" ]]; then
    echo "NOTE: dist was built from $PREV_SHA (newer than dist itself); keeping its marker (HEAD is $SHA)" >&2
    SHA="$PREV_SHA"
  fi
else
  echo "$SHA" > "$MARKER"
fi
echo "Starting vite preview on ${HOST}:${PORT} (SHA=$SHA)"
LOG="$LOG_DIR/spa-preview-${PORT}.log"
PIDFILE="$LOG_DIR/spa-preview-${PORT}.pid"
nohup npx --yes vite preview --host "$HOST" --port "$PORT" >"$LOG" 2>&1 &
echo "$!" >"$PIDFILE"
# Prefer the node listener pid if we can resolve it
if command -v ss >/dev/null; then
  REAL="$(ss -ltnp 2>/dev/null | awk -v p=":$PORT" '$0 ~ p {print}' | sed -n "s/.*pid=\([0-9]*\).*/\1/p" | head -1 || true)"
  if [[ -n "${REAL:-}" ]]; then echo "$REAL" >"$PIDFILE"; fi
fi
echo "PID=$(cat "$PIDFILE") log=$LOG"

# Readiness probe with retry budget (greptile P1: failures must not exit 0).
# vite preview may take >1s to bind, or bind only on the configured host.
PROBE_URL="http://127.0.0.1:${PORT}/"
if [[ "$HOST" == "127.0.0.1" || "$HOST" == "localhost" ]]; then
  PROBE_URL="http://${HOST}:${PORT}/"
fi
READY=0
for _ in $(seq 1 30); do
  if curl -sS -o /dev/null -w "%{http_code}" "$PROBE_URL" | grep -q "^2"; then
    READY=1
    break
  fi
  sleep 1
done
if [[ "$READY" -eq 1 ]]; then
  echo "prove_http=200 url=$PROBE_URL sha=$SHA"
  exit 0
fi
echo "ERROR: SPA preview did not become ready on $PROBE_URL within 30s" >&2
echo "--- last 40 log lines ($LOG):" >&2
tail -n 40 "$LOG" >&2 || true
exit 1
