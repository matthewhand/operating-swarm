Blueprints API (Simple CRUD + Filtering)
=======================================

This document describes a minimal REST API for managing blueprints in Operating Swarm. It is intentionally simple: clients can create, read, update, and delete custom blueprints stored in the user's JSON library, and list bundled/available blueprints with basic filtering. Clients are expected to inspect a blueprint's contents/metadata to infer MCP requirements.

Endpoints
---------

- GET /v1/blueprints/
  - Lists discovered/bundled blueprints with metadata.
  - Query params:
    - search: case-insensitive substring across id, name, description.
    - required_mcp: filter by required MCP server name (if blueprint metadata exposes required_mcp_servers).

- GET /v1/blueprints/custom/
  - Lists user-created custom blueprints from `$XDG_CONFIG_HOME/swarm/blueprint_library.json` (default `~/.config/swarm/blueprint_library.json`).
  - Query params:
    - search: case-insensitive substring across id, name, description.
    - tag: match a tag in the tags array.
    - category: equals match on category.

- POST /v1/blueprints/custom/
  - Create a new custom blueprint entry.
  - Body (JSON):
    - id (optional; auto-slug from name if omitted)
    - name (required if id omitted)
    - description (optional)
    - category (optional; default ai_assistants)
    - tags (optional array)
    - requirements (optional string, free-form notes)
    - code (optional string; client-managed source)
    - required_mcp_servers (optional array of strings)
    - env_vars (optional array of strings)

- GET /v1/blueprints/custom/<id>/
  - Retrieve a custom blueprint by id.

- PATCH /v1/blueprints/custom/<id>/ (alias PUT)
  - Update fields of a custom blueprint.

- DELETE /v1/blueprints/custom/<id>/
  - Delete the custom blueprint.

Responses
---------

- Lists return: {"object": "list", "data": [ { ...blueprint fields... } ]}
- Single item returns the blueprint object or {"error": "not found"} with 404.
- Validation errors return {"error": "..."} and a 4xx code.

Notes
-----

- This API stores custom blueprints in a local JSON library for simplicity; no database migrations are required.
- MCP requirements are not computed server-side here; clients can infer from code and required_mcp_servers/env_vars if present.
- For environment readiness visualization in the Web UI, see /blueprint-library/requirements/ which reports MCP compliance per blueprint against the active configuration.

Examples
--------

- List all bundled blueprints containing "code" and requiring filesystem:
  GET /v1/blueprints/?search=code&required_mcp=filesystem

- Create a custom blueprint:
  POST /v1/blueprints/custom/
  {"name":"Demo Analyzer","description":"Analyze things","category":"ai_assistants","tags":["demo","analysis"],"code":"# your python code here","required_mcp_servers":["filesystem"],"env_vars":["ALLOWED_PATH"]}

- Update tags:
  PATCH /v1/blueprints/custom/demo_analyzer
  {"tags":["analysis","utility"]}

- Delete:
  DELETE /v1/blueprints/custom/demo_analyzer

Filtering syntax
----------------

- Use simple, explicit query params (search, required_mcp, tag, category).
- This keeps implementation light without pulling in heavy query DSLs.
- If a more expressive filter is needed later, consider adopting a well-known pattern like filter[field]=value alongside the existing keys.

