# ADR-001 SPA (`/` + `/chat`) is gitignored; bake dist into the image so
# Docker/Fly pullers get the dashboard instead of Django index fallback.
FROM node:24-bookworm-slim AS frontend
WORKDIR /frontend
COPY webui/frontend/package.json webui/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --legacy-peer-deps
COPY webui/frontend/ ./
RUN npm run build && test -f dist/index.html

FROM python:3.12-slim

# Build-time argument for runtime port (default: 8000)
ARG PORT=8000
ENV PORT=${PORT}

# Build deps plus sqlite3 (native/pytest/tiny-demo fallback only; compose
# durable default is Postgres — REQ-123 / #508).
# libopenblas-dev / liblapack-dev were here for the numpy/scipy tree that
# qdrant-client dragged in. qdrant moved to the `vector` extra and the base
# closure has no numpy/scipy/sklearn/torch/pandas import anywhere in src/, so
# the Fortran toolchain was pure image weight. If a future extra needs a
# source build, add it back with that extra, not here.
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    sqlite3 \
    curl \
    ca-certificates \
 && curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path \
 && install -m 755 /root/.opencode/bin/opencode /usr/local/bin/opencode \
 && /usr/local/bin/opencode --version \
 && rm -rf /root/.opencode \
 && rm -rf /var/lib/apt/lists/*

# #1718: Linux opencode is baked at /usr/local/bin for Docker dogfood
# (Windows Docker Desktop host mounts are PE / exit-126 shims). Discovery
# prefers /usr/local/bin over $HOME bins when /.dockerenv is present.

WORKDIR /app

# Copy all project files first (consider .dockerignore for efficiency)
COPY . .
# .dockerignore excludes webui/frontend/dist; copy the built SPA from the
# frontend stage so Path("webui/frontend/dist") resolves at runtime.
COPY --from=frontend /frontend/dist /app/webui/frontend/dist

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install BLIS (if still needed, uncomment)
# ENV BLIS_ARCH="generic"
# RUN pip install --no-cache-dir --no-binary=blis blis==1.2.0

# Install the project
# The `deploy` profile: core + gunicorn + the oauth extra. The server is the
# only place these are needed, so local checkouts stay on the barebones
# core (see the extras note in pyproject.toml).
RUN pip install '.[deploy]'

# Expose the specified port
EXPOSE ${PORT}

# --- Default Command ---
# This runs if no entrypoint overrides it. Includes DB setup.
# #1337: the swapfile shares the 1GB volume. A 768M file left ~138M free.
# Default is 384M, overridable at runtime with SWAP_SIZE_MB (fly.toml [env]).
# A Docker build ARG never reaches this shell, so the size is not a build arg.
# scripts/ensure_swapfile.sh replaces an existing file only when the size
# differs, and warns above 512M (half the volume) without failing.
CMD sh scripts/ensure_swapfile.sh && \
    python -c "from swarm.core.database_config import check_database_or_exit; check_database_or_exit()" && \
    if [ -n "${DATABASE_URL}" ] || [ -n "${POSTGRES_HOST}" ]; then \
      echo "Postgres configured (DATABASE_URL / POSTGRES_*); applying migrations" && \
      python manage.py migrate --fake-initial; \
    else \
      : "${DJANGO_DB_NAME:=${SQLITE_DB_PATH:-/app/db.sqlite3}}" && \
      export DJANGO_DB_NAME SQLITE_DB_PATH="${DJANGO_DB_NAME}" && \
      mkdir -p "$(dirname "$DJANGO_DB_NAME")" && \
      if [ "$FACTORY_RESET_DATABASE" = "True" ]; then \
        echo "FACTORY_RESET_DATABASE is True; deleting database file if it exists" && \
        rm -f "$DJANGO_DB_NAME"; \
      fi && \
      if [ -f "$DJANGO_DB_NAME" ]; then \
        TABLE_COUNT=$(sqlite3 "$DJANGO_DB_NAME" "SELECT count(*) FROM sqlite_master WHERE type='table';") && \
        if [ "$TABLE_COUNT" -gt 0 ]; then \
          echo "Database exists with tables; applying migrations with --fake-initial if needed" && \
          python manage.py migrate --fake-initial; \
        else \
          echo "Database exists but is empty; applying migrations normally" && \
          python manage.py migrate; \
        fi; \
      else \
        echo "No database found; creating and applying migrations" && \
        python manage.py migrate; \
      fi; \
    fi && \
    echo "--- Starting Open Swarm ASGI (uvicorn) ---" && \
    export SWARM_PROCESS_ROLE=serve && \
    exec uvicorn swarm.asgi:application --host 0.0.0.0 --port "$PORT" --workers "${SWARM_UVICORN_WORKERS:-1}"

