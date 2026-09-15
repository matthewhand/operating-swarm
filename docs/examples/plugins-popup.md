### Plugins popup — per-chat tool toggles (#805)

Rail **Plugins** opens a search palette (same chrome family as agent search /
session picker) over the still-mounted chat. Each row is a discovered tool
with a visible **On/Off** switch scoped to the **current conversation**.
Enabled tools sort first when the popup opens; toggling On/Off does not
move rows until it is closed and opened again (#278). Search filters in
that frozen order.

**Manage servers** opens Settings → Plugins (#502 / #750 add/edit/remove +
Local MCP / Remote MCP / OpenAPI (mcp-openapi-proxy) + discover). Servers
persist in `swarm_config.json` `mcpServers`. Auth is `${VAR}` only. See
[plugins-mcp.md](./plugins-mcp.md).

#### Discovery degrade

The popup prefers `GET /v1/mcp-plugins/` discovered tools. If that list is
empty, it falls back to `GET /v1/config-options/` `mcp_catalog`, then the
document-store cache, then the shipped fixture catalog in
`webui/frontend/src/lib/chatPluginTools.ts` so toggle / sort / search stay
real. The popup says so when it is using the fixture.

On send, Chat includes `params.enabled_tools` (the On ids). Catalog tools
that are Off are excluded; blueprint-native tools that are not in the catalog
stay available.
