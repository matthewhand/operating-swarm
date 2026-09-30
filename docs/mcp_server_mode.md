# MCP Server Mode (`ENABLE_MCP_SERVER`)

**Crystal clear:**

| What the flag does | What it does **not** do |
|---|---|
| When `django-mcp-server` is installed, mounts **`/mcp/`** and adds `mcp_server` to `INSTALLED_APPS` | Expose Operating Swarm **blueprints as MCP tools** |
| Logs a warning if the package is missing (no crash) | Port the blueprint→tool bridge to `mcp_server` ≥0.5 |

`ENABLE_MCP_SERVER=true` makes `swarm/settings.py` add `'mcp_server'` to
`INSTALLED_APPS` and `swarm/urls.py` mount `path('mcp/', include('mcp_server.urls'))`.
Both are gated on the module being importable, so with the package **absent** the
flag is a no-op with a clear logged warning (it no longer breaks startup).

**Blueprints are NOT MCP tools** until
`swarm/mcp/integration.py::register_blueprints_with_mcp()` is ported off the
legacy flat `registry.register_tool` API. On `mcp_server` ≥0.5 that call is an
intentional no-op that now logs **`logger.error`** (not silent). `/mcp/` still
serves django-mcp-server’s own toolset surface only.

## Install

The endpoint is provided by the [`django-mcp-server`](https://pypi.org/project/django-mcp-server/)
distribution, whose import module is **`mcp_server`** (not `django_mcp_server` —
that mismatch is what previously made the flag dead on a clean install). Install
it manually:

```bash
pip install django-mcp-server
export ENABLE_MCP_SERVER=true
```

It is **not** declared as an `open-swarm` extra: its transitive `mcp` SDK
dependency only resolves with pre-releases enabled, which would break
`uv lock --check` in CI. Verified working at the Django layer — with the package
installed and the flag set, `manage.py check` passes and `/mcp/` is mounted.

## Known gap — blueprint→tool bridge

`swarm/mcp/integration.py::register_blueprints_with_mcp()` was written against a
flat `registry.register_tool(...)` API. `mcp_server` ≥0.5 replaced that with an
`MCPToolset` / decorator paradigm, so the bridge is currently a **no-op** that
returns 0 and emits **`logger.error`** (registration failure is loud on purpose).
Porting it to expose Operating Swarm blueprints as MCP tools is tracked in
[ROADMAP.md §3.3](../ROADMAP.md). Until then:

- ✅ Flag + package → `/mcp/` mount works
- ❌ Flag + package → blueprints appear as MCP tools (**not until API fixed**)

## Tests

`tests/mcp/test_mcp_urls.py` exercises the mount by stubbing `mcp_server` in
`sys.modules`; `tests/mcp/test_mcp_missing_package_warning.py` guards the
warning path by masking `mcp_server.urls` (hermetic whether or not the real
package is installed). Bridge no-op logging is covered via
`tests/mcp/test_provider_edge_cases.py` / registration tests.
