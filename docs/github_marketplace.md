GitHub‑Driven Marketplace for Blueprints and MCP Config Templates
================================================================

Overview
--------
Instead of hosting or moderating a centralized catalog, we leverage GitHub’s
native discovery and tagging to surface community repositories that share
Operating Swarm blueprints and MCP configuration templates (never secrets).

How It Works
------------
- Repositories opt in by adding one or more GitHub topics (tags):
  - `open-swarm-blueprint` for agent blueprints
  - `open-swarm-mcp-template` for MCP config templates
  - Optional: `open-swarm-marketplace` for general discovery
- Our backend queries the GitHub Search API (or GraphQL) for repos with these
  topics, and returns a curated summary for the Web UI.
- For each repo we fetch lightweight, non-sensitive metadata files:
  - A repo‑level manifest: `open-swarm.json` describing contained items.
  - Or per‑item manifests inside conventional paths, for example:
    - `swarm/blueprints/<name>/manifest.json`
    - `swarm/mcp/<name>/manifest.json`
  - These manifests describe display metadata, version, tags, instructions to
    install/use (but must never include secrets or credentials).

Security & Privacy
------------------
- No secrets are stored or transmitted. Manifests and templates must be safe for
  publication. Any references to credentials use placeholders (e.g. `${VAR}`).
- The app only reads public repo metadata and manifest files.
- If a GitHub token is configured, it is used solely for higher rate limits; it
  is not exposed to clients.
- Client `org` / `topic` query params are validated against
  `GITHUB_MARKETPLACE_ORG_ALLOWLIST` and `GITHUB_MARKETPLACE_TOPICS`. When an
  allowlist is **non-empty**, values outside it are rejected with **400** (they
  cannot replace the configured scope and ride the server `GITHUB_TOKEN`). When
  an allowlist is **empty**, filters stay open: any client `org`/`topic` is
  applied as-is — set the org allowlist in locked-down deployments.

Sorting, Filtering, and Search
------------------------------
- Default sort: by GitHub popularity (stars) descending.
- Alternate sorts: by last updated (updatedAt) and (optionally) by creation date.
  - REST Search supports `sort=stars|updated`; GraphQL supports ordering by `STARS` and `UPDATED_AT`.
  - For created date, we can either filter via `created:` qualifiers or fetch timestamps and sort client‑side.
- Name search: use `in:name` (REST) or `query: "in:name"` (GraphQL) combined with the required topics.
- Additional filters: by org (`org:` qualifier), by topic, by tag within manifest items.

Implementation Plan (Backend)
-----------------------------
1. Settings
   - `ENABLE_GITHUB_MARKETPLACE` (default false)
   - `GITHUB_TOKEN` (optional; improves rate limits)
   - `GITHUB_MARKETPLACE_TOPICS` default:
     - `open-swarm-blueprint`, `open-swarm-mcp-template`
   - `GITHUB_MARKETPLACE_ORG_ALLOWLIST` (optional) — to scope results by org.
     Empty = unscoped (client may pass any `org`). Non-empty = only listed orgs;
     unknown client `org` → 400.
2. Service module
   - `swarm/services/github_topics_service.py` with functions:
     - `search_repos_by_topics(topics: list[str], orgs: list[str]|None) -> list[Repo]`
     - `fetch_repo_manifests(repo) -> list[Item]` (look for known manifest paths)
     - `to_marketplace_items(repo, items) -> list[dict]` (normalized objects)
   - Use GitHub REST or GraphQL; respect rate limits; add simple caching.
3. API endpoints (headless)
   - `GET /marketplace/github/blueprints/` → list blueprint items
   - `GET /marketplace/github/mcp-configs/` → list MCP configs
   - Filters: `search` (name), `org`, `topic`, `tag` (`org`/`topic` must be
     allowlisted when those lists are configured)
   - Sorts: `sort=stars|updated|created` (created via client sort or GraphQL), `order=desc|asc`
4. Tests
   - Mock GitHub API responses and verify:
     - Repo search, manifest fetch, normalization
     - Filter behavior, error handling, and caching

Implementation Plan (Web UI)
---------------------------
- Add a new tab in the Blueprint Library: “GitHub”
- Display cards similar to the local marketplace, with source repo links
- For MCP templates, show config templates with copy‑paste examples

Demonstration / Examples
------------------------
- Phase 1 (in‑repo demo): Keep example blueprints/MCP templates inside this app’s
  repository for initial demonstration and dogfooding. Tag this repo with the
  marketplace topics so it is discoverable via GitHub. Manifests live at
  `open-swarm.json` and/or the conventional per‑item paths.
- Phase 2 (external repos): Prepare one or more example repos under a known org
  (e.g. `open-swarm-examples`) tagged with `open-swarm-blueprint` and/or
  `open-swarm-mcp-template`.
- Include minimal manifests at either `open-swarm.json` or
  `swarm/blueprints/<name>/manifest.json` & `swarm/mcp/<name>/manifest.json`.
  The manifests should include: name, description, version, tags, and install/
  usage instructions; no secrets.

Notes
-----
- This model mirrors successful approaches (e.g., pinokio.computer) and avoids
  centralized content hosting while keeping the showcase fresh and community‑led.

