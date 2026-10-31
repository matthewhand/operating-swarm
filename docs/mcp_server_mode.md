# MCP Server Mode (`ENABLE_MCP_SERVER`)

**Crystal clear:**

| Feature | Status | Behavior |
|---|---|---|
| Server Mount | ✅ Active | When `django-mcp-server` is installed, mounts **`/mcp/`** and adds `mcp_server` to `INSTALLED_APPS` |
| Safe Degradation | ✅ Active | Logs a warning if the package is missing (no crash) |
| Blueprint Tool Bridge | ✅ Active | Discovered blueprints are automatically registered as MCP tools on `mcp_server.mcp_server` (supporting both modern `mcp_server` ≥0.5 `add_tool` and legacy `registry.register_tool`) |
| Client Auth | ✅ Active | Authenticates MCP clients via `Bearer <token>` or `X-API-Key` headers matching `API_AUTH_TOKEN` / `SWARM_API_KEY` |

`ENABLE_MCP_SERVER=true` makes `swarm/settings.py` add `'mcp_server'` to
`INSTALLED_APPS` and `swarm/urls.py` mount `path('mcp/', include('mcp_server.urls'))`.
Both are gated on the module being importable, so with the package **absent** the
flag is a no-op with a clear logged warning (it does not break startup).

When enabled and installed, `swarm.mcp.apps.MCPIntegrationConfig.ready()` invokes
`swarm/mcp/integration.py::register_blueprints_with_mcp()`, exposing all discovered
Operating Swarm blueprints as callable tools on the MCP server.

## Install

The endpoint is provided by the [`django-mcp-server`](https://pypi.org/project/django-mcp-server/)
distribution, whose import module is **`mcp_server`**. It is declared as an optional extra `[mcp]` in `pyproject.toml` and locked in `uv.lock`. Install via:

```bash
pip install '.[mcp]'
# or:
pip install django-mcp-server
export ENABLE_MCP_SERVER=true
```

Verified working at the Django layer — with the package installed and the flag set, `manage.py check` passes and `/mcp/` is mounted with blueprints registered.

## Authentication

MCP clients authenticate using the project's token authentication story:
- **Bearer Token**: `Authorization: Bearer <token>` where `<token>` matches configured `API_AUTH_TOKEN` or `SWARM_API_KEY(S)`.
- **API Key Header**: `X-API-Key: <token>`.
- In local development (`DJANGO_DEBUG=true` without auth tokens configured), auth checks remain permissive to facilitate testing.

See [docs/AUTH.md](./AUTH.md) for details on token principals and multi-key allowlists.

## Blueprint Tool Invocation

Each discovered blueprint is registered as an MCP tool with schema:
- **Name**: Blueprint ID (e.g., `suggestion`, `codey`, `geese`, `zeus`, `software-dev`).
- **Description**: Blueprint title / metadata description.
- **Arguments**: `{"instruction": "<string>"}`.

When an MCP client invokes a blueprint tool, execution routes through `BlueprintMCPProvider.call_tool()` which executes the blueprint synchronously and returns structured `content` output.

## Tests

- `tests/mcp/test_mcp_urls.py` exercises the mount and URL routing.
- `tests/mcp/test_mcp_missing_package_warning.py` guards the warning path when the package is absent.
- `tests/mcp/test_integration_register.py` verifies both modern `mcp_server.mcp_server.add_tool` (≥0.5.0) and legacy `registry.register_tool` registration paths.
- `tests/mcp/test_provider.py` & `tests/mcp/test_provider_execute.py` test blueprint tool execution and error handling.
