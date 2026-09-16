# Makefile for Open-Swarm
# Usage: `make help`

PY ?= uv run
CLI ?= swarm-cli
BIN ?= $(HOME)/.local/share/swarm/bin

.PHONY: help dev test frontend list-installed list-available build build-shim build-all-shims build-all-executables launch uninstall build-pyinstaller build-all-pyinstaller demo-deploy demo-build

COMPOSE ?= docker compose
# Host-coupled local mappings (gitignored). Auto-included by `make dev` when
# present, so host-only paths land in the dev container — the agentic CLIs
# (claude/opencode/qwen/grok) and harness binaries/sockets (herdr); a no-op on
# hosts without it. dev.yml stays LAST so its !override ports win.
DEV_OVERRIDE := $(wildcard docker-compose.override.yml)

help:
	@echo "Open-Swarm Makefile"
	@echo ""
	@echo "Common targets:"
	@echo "  make dev                                # Containerized API with live code-reload (host :8002)"
	@echo "  make test                               # Run the full test suite"
	@echo "  make frontend                           # Build ADR-001 SPA (webui/frontend/dist)"
	@echo "  make demo-build                         # Static SPA with VITE_DEMO_MODE mocked inference"
	@echo "  make demo-deploy                        # Operator-gated Fly/Pages publish (skips if unauthed)"
	@echo "  make list-installed                     # List installed blueprint executables"
	@echo "  make list-available                     # List available blueprints (bundled/user)"
	@echo "  make launch NAME=codey MESSAGE=\"Hi\" # Launch installed executable with a message"
	@echo "  make uninstall NAME=codey               # Remove installed executable"
	@echo ""
	@echo "Build options (choose one):"
	@echo "  🚀 SHIMS (fast, lightweight ~100 bytes each):"
	@echo "    make build-shim NAME=codey              # Build single lightweight shim"
	@echo "    make build-all-shims                    # Build shims for all blueprints"
	@echo ""
	@echo "  📦 EXECUTABLES (full PyInstaller ~10-50MB each):"
	@echo "    make build-pyinstaller FILE=src/swarm/blueprints/codey/codey_cli.py NAME=codey   # One-off"
	@echo "    make build-all-executables              # Build full executables for all blueprints"
	@echo ""
	@echo "  🔄 LEGACY:"
	@echo "    make build NAME=codey                   # Build (uses shim if SWARM_TEST_MODE=1, else PyInstaller)"
	@echo "    make build-all-pyinstaller              # Bulk build via scripts/packaging/build_all_blueprints.py"

# Containerized dev server with uvicorn --reload (same ASGI path as prod).
# Bind-mounts the source via docker-compose.dev.yml; publishes host :8002 so it
# coexists with the native :8001 service. Ctrl-C to stop.
dev:
	$(COMPOSE) -f docker-compose.yml $(if $(DEV_OVERRIDE),-f $(DEV_OVERRIDE)) -f docker-compose.dev.yml up --build

test:
	$(PY) python scripts/run_tests.py -q

# Gitignored SPA assets for local `/` + `/chat` (Docker bakes these in-image).
frontend:
	./scripts/build_frontend.sh

# REQ-882 / #279: static demo SPA (mocked inference). Deploy is operator-gated.
demo-build:
	cd webui/frontend && npm run build:demo

demo-deploy:
	$(PY) python scripts/deploy_demo_site.py

list-installed:
	$(PY) $(CLI) list --installed

list-available:
	$(PY) $(CLI) list --available

# Build an executable (shim in test mode if SWARM_TEST_MODE=1 is set in env)
build:
	@if [ -z "$(NAME)" ]; then echo "ERROR: Set NAME=<blueprint_name>"; exit 1; fi
	$(PY) $(CLI) install-executable $(NAME)

# Force a fast shim (no pyinstaller) for local/dev/testing
build-shim:
	@if [ -z "$(NAME)" ]; then echo "ERROR: Set NAME=<blueprint_name>"; exit 1; fi
	SWARM_TEST_MODE=1 $(PY) $(CLI) install-executable $(NAME)

# Build shims for all detected blueprint_*.py modules
build-all-shims:
	@echo "Building shims for all blueprints..."
	@SWARM_TEST_MODE=1 bash -c 'set -euo pipefail; for f in $$(find src/swarm/blueprints -type f -name "blueprint_*.py"); do m=$$(basename $$f .py | sed "s/blueprint_//"); echo "==> Installing shim: $$m"; $(PY) $(CLI) install-executable $$m || echo "Failed to install $$m, continuing..."; done'

# Build full PyInstaller executables for all blueprints (requires pyinstaller)
build-all-executables:
	@echo "Building full PyInstaller executables for all blueprints..."
	@echo "This will create large standalone binaries (~10-50MB each)"
	@echo "Make sure pyinstaller is installed: pip install pyinstaller"
	@echo ""
	@bash -c 'set -euo pipefail; for f in $$(find src/swarm/blueprints -type f -name "blueprint_*.py"); do m=$$(basename $$f .py | sed "s/blueprint_//"); echo "==> Building executable: $$m"; pyinstaller --onefile --name $$m --distpath ./dist $$f || echo "Failed to build $$m, continuing..."; done'

launch:
	@if [ -z "$(NAME)" ]; then echo "ERROR: Set NAME=<blueprint_name>"; exit 1; fi
	@if [ -n "$(MESSAGE)" ]; then \
		$(PY) $(CLI) launch $(NAME) --message "$(MESSAGE)"; \
	else \
		$(PY) $(CLI) launch $(NAME); \
	fi

uninstall:
	@if [ -z "$(NAME)" ]; then echo "ERROR: Set NAME=<blueprint_name>"; exit 1; fi
	@echo "Removing $(BIN)/$(NAME)"
	@rm -f "$(BIN)/$(NAME)"

# Build a single-file binary using PyInstaller
build-pyinstaller:
	@if [ -z "$(FILE)" ] || [ -z "$(NAME)" ]; then echo "ERROR: Set FILE=<path_to_cli_or_blueprint.py> NAME=<output_name>"; exit 1; fi
	pyinstaller --onefile --name $(NAME) --distpath ./dist $(FILE)

# Bulk PyInstaller build using repository helper script
build-all-pyinstaller:
	python scripts/packaging/build_all_blueprints.py


