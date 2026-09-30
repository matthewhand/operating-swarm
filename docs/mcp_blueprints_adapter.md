Expose Blueprints as MCP Tools via `django-mcp-server`
=====================================================

Objective
---------
Let external MCP clients call Operating Swarm blueprints as tools using the Django-hosted MCP server (`omarbenhamid/django-mcp-server`). Keep it opt-in and safe by default.

High-level Approach
-------------------
- Install and enable `django-mcp-server` as an optional app behind a feature flag.
- Register a provider that:
  - Enumerates available blueprints (bundled + custom if desired).
  - Maps blueprint execution into MCP Tool definitions (name, description, parameters schema).
  - Executes blueprint calls by invoking the blueprint’s `run` (or `Runner.run`) with parsed args, returning structured output.
- Serve MCP over the same host under `/mcp/` (configurable), reusing Operating Swarm auth.

Tool Definition Design
----------------------
- Tool name: blueprint id (e.g., `suggestion`, `codey`).
- Description: from blueprint metadata/docstring.
- Parameters: JSON schema for args. Minimal MVP could take a single `instruction` string, with future expansion to structured inputs.
- Output: text or JSON. For structured output blueprints (e.g., Suggestion’s `output_type`), return JSON.

Execution Flow (MVP)
--------------------
1. MCP client calls tool `suggestion` with `{ "instruction": "..." }`.
2. Provider resolves blueprint by id, prepares minimal messages list, and calls `Runner.run` (or `blueprint.run`) non-interactively.
3. Stream/return final output. For streaming, integrate MCP server’s streaming protocol if available; otherwise return a single completion.

Security & Safety
-----------------
- Expose only whitelisted blueprints as tools (configurable).
- Ensure no secrets leak in tool schemas or outputs. Respect existing sandboxing/approval flags if applicable.
- Log and rate-limit. Optional auth integration with a session or token-based gate.

Config & Flags
--------------
- `ENABLE_MCP_SERVER=true` to add `django-mcp-server` to `INSTALLED_APPS` and include its URLs (e.g., `/mcp/`).
- `MCP_EXPOSED_BLUEPRINTS`: comma-separated allowlist; default to a small safe set.
- Optional: per-tool schema overrides in config.

Tests (TDD Plan)
----------------
1. Unit test for provider registry: enumerates a fake blueprint set and produces tool defs.
2. Unit test for call path: given a tool invocation, calls a stub blueprint and returns expected JSON.
3. Integration (skipped unless package installed): MCP discovery lists tools; call returns expected data.
4. Security tests: only allowlisted blueprints appear; invalid args rejected with clear errors.

Open Questions
--------------
- Streaming support: integrate MCP streaming or return full results only?
- Structured parameters per blueprint: generate JSON schema from metadata or a decorator?
- Auth bridging: require session/token for tool calls in production?

Next Steps
----------
- Spike with `django-mcp-server` locally; validate provider hook points and URL include.
- Implement minimal provider and one example tool (`suggestion`).
- Add flags/config, wire URLs, and ship behind opt-in.

