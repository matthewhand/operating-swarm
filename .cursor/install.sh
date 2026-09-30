#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for Operating Swarm.
# Runs after the repository is checked out. Safe to run repeatedly.
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo /workspace)"

# 1. Install uv (Python package/venv manager) if it is not already present.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# 2. Create .venv and install the project plus all extras from the committed
#    uv.lock (dev, test, memory, docs). Deterministic and idempotent.
uv sync --all-extras

# 3. Build the optional React SPA (webui/frontend/dist) so `/` serves the
#    dashboard + /chat. Django falls back to server-rendered templates if the
#    build is absent, so a Node failure here is non-fatal for backend work.
if command -v npm >/dev/null 2>&1; then
  ./scripts/build_frontend.sh || echo "WARN: frontend build failed; Django template UI will be used."
else
  echo "WARN: npm not found; skipping SPA build (Django template UI will be used)."
fi

echo "Operating Swarm install complete."
