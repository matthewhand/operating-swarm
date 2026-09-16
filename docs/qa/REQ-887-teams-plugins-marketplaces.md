# REQ-887 — Teams + Plugins marketplaces

Issue [#292](https://github.com/matthewhand/open-swarm-private/issues/292).
Spec of record for the in-app catalog: reuse MCP Registry and Agent Skills;
OS-native team packs (no fake team standard).

## Sources of truth

1. **Plugins** — Official MCP Registry (`https://registry.modelcontextprotocol.io`),
   cached client. GitHub topics `swarm-mcp-plugin` / `open-swarm-plugin` as
   fallback. Install → existing `mcpServers` plugin list + connect-check.
2. **Skills** — Agent Skills (`SKILL.md`, `parse_skill_md`). Install → user
   `skills/` directory, file copy only (no execution).
3. **Teams** — OS `team_rosters` packs from GitHub `swarm-team-pack`. There is
   **no widely adopted** / **no industry team-pack standard**. CrewAI and A2A
   Agent Cards are not team packs.

## Behaviour

- Community/external items labelled before install.
- MCP install shows required env **names**; connect-check after add.
- Skill install is a folder copy; no execution at install time.
- Team install is roster JSON only; missing CLI/API/remote members stay
  “needs configuration.”
- Offline / rate-limit: honest warning; last-good registry cache is OK.
- Registry is not queried on every keystroke.

## Verification

- `tests/unit/test_mcp_registry.py`
- `tests/unit/test_marketplace_catalog.py`
- `tests/unit/test_marketplace_catalog_api.py`
- `tests/unit/test_req887_marketplace.py`
- `webui/frontend/src/lib/__tests__/installCatalog.test.ts`
- `webui/frontend/src/components/__tests__/InstallCatalog.test.tsx`
