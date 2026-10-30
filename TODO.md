# TODO

> **Project status and priorities now live in [ROADMAP.md](ROADMAP.md).**
> This file previously held a large phase-based plan; most of it was either
> completed, superseded, or promoted to the roadmap. Only genuinely-current,
> fine-grained engineering tasks are kept below. Add new strategic items to
> `ROADMAP.md`, not here.

## CLI blueprint lifecycle (`swarm-cli`)

Shipped as [REQ-871](docs/qa/REQ-871-cli-blueprint-lifecycle.md), locked by
`tests/unit/test_req871_cli_blueprint_lifecycle.py`.

- [x] `swarm-cli compile <blueprint_name>` — PyInstaller compile into `get_user_bin_dir()` (`_compile_blueprint_executable` in `src/swarm/core/swarm_cli.py`); `install` / `install-executable` stay behaviourally identical aliases. Behaviour tests: `tests/cli/test_blueprint_lifecycle.py`.
- [x] `swarm-cli launch` prefers the compiled binary in `get_user_bin_dir()` and falls back to installed, then bundled, source. Non-interactive by design: it never offers to compile, because the `--pre` / `--listen` / `--post` hooks it drives cannot answer a prompt.
- [x] `delete` takes `--source` / `--binary` / `--all` (default: both) and reports each artefact separately; `uninstall` stays the binary-only alias.
- [x] `swarm-cli session list` / `session show` — reads the chat store (`SWARM_CHAT_DIR`, else `<user data>/chats`) plus provider session stores. Note: **there is no `~/.cache/swarm/sessions` store** — that path never existed, and `session` deliberately does not create one (`tests/cli/test_session_command.py` asserts this).

## Blueprint metadata

- [x] Add `abbreviation: Optional[str]` to `BlueprintBase` metadata and extract it in `blueprint_discovery.py`. (Added default metadata dict & abbreviation property to `BlueprintBase` in `src/swarm/core/blueprint_base.py`; verified in `tests/core/test_blueprint_base.py` and `tests/core/test_blueprint_discovery_behavior.py`).
- [x] Verify/document docstring fallback for `description` metadata (`src/swarm/core/blueprint_discovery.py` lines 326–339; documented in `DEVELOPMENT.md`).
- [x] Remove any remaining legacy `metadata.json` files from blueprints (verified none exist).

## Tests still missing (config/core)

- [x] Per-blueprint and per-agent model override logic (`tests/core/test_blueprint_model_override.py`).
- [x] Fallback to default model/profile with warning when requested profile is missing (`tests/core/test_fallback_to_default_model.py`).
- [x] MCP server config add/remove/parse (`tests/core/test_mcp_server_config.py`).
- [x] Redaction of secrets in logs and config dumps (`tests/core/test_redact_sensitive_data.py`).
- [x] CRUD tests for `/v1/blueprints/custom/` endpoints (create, read, update, delete, filters; `tests/views/test_api_views.py`).

## Docs

- [x] USERGUIDE.md: document XDG file locations and full `swarm-cli` command reference with examples.
- [x] DEVELOPMENT.md: document blueprint-management internals, PyInstaller usage, `abbreviation` metadata, XDG path management.
- [x] Document `--pre`, `--listen`, `--post` hook flags and slash-command REPL behavior.

**Recent unification (config loaders now central in core/, extensions are thin delegates; deprecate/status in discovery; resolver tests; wizard+audit improvements; docs refreshed; audit_status.json expanded; debug noise reduced; discovery/UX edges fixed for django/stewie/messenger; tool/spinner dupe sweep). See subagent work for details. Remaining: full metadata in all bps, use deprecate flag in CLI/UI, more coverage, central tools registration, full local uv run deps.**

---

Superseded content (web UI, MCP server mode, SAML IdP, marketplace, blueprint
rationalization, spinner/config-loader consolidation, dual-CLI split) is
tracked in [ROADMAP.md](ROADMAP.md).
