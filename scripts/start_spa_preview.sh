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

SHA="$(git -C "$ROOT" rev-parse HEAD)"
echo "$SHA" > "$FE/dist/.preview-sha"
echo "Starting vite preview on ${HOST}:${PORT} (SHA=$SHA)"
LOG="$LOG_DIR/spa-preview-${PORT}.log"
PIDFILE="$LOG_DIR/spa-preview-${PORT}.pid"
nohup npx --yes vite preview --host "$HOST" --port "$PORT" >"$LOG" 2>&1 &
echo $! >"$PIDFILE"
sleep 1
# Prefer the node listener pid if we can resolve it
if command -v ss >/dev/null; then
  REAL="$(ss -ltnp 2>/dev/null | awk -v p=":$PORT" '$0 ~ p {print}' | sed -n "s/.*pid=\([0-9]*\).*/\1/p" | head -1 || true)"
  if [[ -n "${REAL:-}" ]]; then echo "$REAL" >"$PIDFILE"; fi
fi
echo "PID=$(cat "$PIDFILE") log=$LOG"
curl -sS -o /dev/null -w "prove_http=%{http_code}\n" "http://127.0.0.1:${PORT}/" || true
