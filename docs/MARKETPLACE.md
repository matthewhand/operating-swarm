# Marketplace sources of truth (REQ-887)

Teams, Plugins, and Skills share one in-app catalog shell (search, filters,
detail drawer, install progress). They do **not** share one install format.
There is no Wagtail/CMS marketplace.

Preferred product install remains Docker Compose / Hub. This catalog is for
operators who already have Open Swarm running.

## Three sources of truth

| Kind | Source of truth | Install target | Not this |
|------|-----------------|----------------|----------|
| **Plugins** | Official [MCP Registry](https://registry.modelcontextprotocol.io) (`server.json`, cached client) | Existing `mcpServers` / `/v1/mcp-plugins/` | A second MCP index hosted by OS |
| **Skills** | [Agent Skills](https://agentskills.io) (`SKILL.md` + YAML `name`/`description`) | User `skills/` dir (`get_user_data_dir_for_swarm()/skills`) or project `skills/` | SkillsMP wholesale scrape; a parallel schema |
| **Teams** | **OS team pack** (`team_rosters.json` / `team-pack.json`) published to GitHub topic `swarm-team-pack` | `/v1/team-rosters/` | CrewAI `agents.yaml`, A2A Agent Cards, AutoGen GroupChat |

GitHub topic scan (`swarm-mcp-plugin`, `open-swarm-plugin`, `swarm-team-pack`)
is a **fallback** for plugins unpublished to the Official Registry, and the
discovery path for OS team packs. It is not a second MCP or skills store.

## Plugins (MCP Registry)

- Metadata SoT: `GET https://registry.modelcontextprotocol.io/v0.1/servers`
- OS polls/caches (24h TTL, last-good on offline / rate-limit). It does **not**
  query the registry on every keystroke — search is local on the cached page.
- Installing a plugin adds an MCP server to the existing Plugins path, shows
  required **env names** (values stay `${VAR}`), then connect-checks
  (`POST /v1/mcp-plugins/discover/`).
- Community/external rows are labelled before install. Downloaded code is
  never auto-run.

## Skills (Agent Skills)

Format stays `swarm.core.skills.parse_skill_md`. A pack is a folder with
`SKILL.md` (and optional helper files). Install is a **file copy** into the
user skills directory — no execution at install time.

Curated GitHub sources (for example `anthropics/skills`) are listed as
Agent Skills packs. SkillsMP is not ingested.

## Teams (OS-native packs — no fake standard)

There is **no** widely adopted catalog format for “install this multi-agent
team.” Nearby specs solve different problems:

| Thing | What it actually is |
|-------|---------------------|
| A2A Agent Card | Talk to **one** remote agent |
| CrewAI `agents.yaml` / `tasks.yaml` | One framework’s crew |
| AutoGen GroupChat / ACS `.agents/` | Framework- or project-local |

**OS team pack stays native.** Example `team-pack.json`:

```json
{
  "id": "ops-pack",
  "name": "Ops Pack",
  "members": [
    {"id": "jeeves", "name": "Jeeves", "kind": "api", "role": "chief_of_staff", "source": "blueprint:jeeves"},
    {"id": "grok", "name": "Grok CLI", "kind": "cli", "role": "skeptic", "source": "cli:grok"},
    {"id": "acp", "name": "ACP Remote", "kind": "remote", "role": "support", "source": "remote:acp"}
  ],
  "wires": {"handoff": true, "as_tool": true},
  "chief_of_staff_id": "jeeves",
  "chief_of_staff_instructions": "Coordinate this team's roster."
}
```

Install writes roster JSON only. It must not pull CLI binaries. Members that
need a missing CLI, blueprint, or remote stay visible as **needs
configuration**. Preview members / CoS / wires before write.

## HTTP

- `GET /v1/marketplace/?kind=teams|plugins` — GitHub topic scan (#179)
- `GET /v1/marketplace/catalog/?kind=teams|plugins|skills` — catalog
- `GET /v1/marketplace/preview/?kind=&id=` — inspect, no write
- `POST /v1/marketplace/install/` — `{kind, id}`

Listings never include secret values.
