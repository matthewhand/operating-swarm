# Issue #1398 — Grok Bot interop spike (file-only)

Issue: #1398. Backend templates only. No SPA (#1399). No secrets.

## Finding

**File-only.** There is no documented, allowed public **share id** or **deep link** API for Grok Bot templates that Operating Swarm can call.

Live Grok call skipped because no `XAI_API_KEY` or `GROK_API_KEY` is set. Key names were checked only; values are not recorded here. The file mapper is the interop path either way — this spike does not call xAI.

xAI’s Grok / Grok Bot product surfaces bots inside the Grok app. Official template or bot cards, if they exist, are in-product. There is no published HTTP contract for:

- resolving a share id (`grok.ai/bot/<id>` or similar) into a recipe payload
- importing a third-party bot by URL
- listing official templates as JSON

Scraping grok.x.ai / grok.com HTML or undocumented app endpoints would violate the “no ToS scrape” constraint. This slice does not do that.

## What shipped

Canonical pack: `kind: agent_template`, `schema: 1` (`docs/schemas/agent_template.schema.json`, same bytes as `src/swarm/core/agent_template.schema.json`).

Field map: profile, memories, skills, gettingStarted, routines, plugins. Routines and plugins are the domain packs (`routine_pack`, `agent_plugin_pack`), not a side file. Import leaves routines inactive and `{{owner_repo}}` fill-ins pending. Plugin rows are ids only.

Grok projection: `kind: grok_bot_template` — the same recipe flattened to `name` / `description` / `title` / `role` / `avatar` plus `memories`, `skills`, `gettingStarted`, `routines`, `plugins`, `fill_ins`.

Round-trip:

1. `GET /v1/agents/<id>/template/grok/` — export the projection.
2. `POST /v1/agent-templates/from-grok/` — accept a Grok-shaped JSON file and return the canonical pack.
3. `POST /v1/agent-templates/import/` — create an agent from either shape (JSON body or uploaded `.json` file).

A body that is only a `https://` URL, or a JSON object with `share_id`, `share_url`, or `deep_link`, returns `400` / `grok_share_unsupported`. No network fetch.

Fixture: `tests/fixtures/grok_bot_template.json`. Swarm Engineer dogfood: `tests/fixtures/swarm_engineer_template.json`.

## If a share-id API appears later

Revisit this note. A future slice may add `share_id` / `deep_link` fields **only** when xAI documents a public, ToS-allowed endpoint. Until then, operators exchange `.json` files.

## Not in this slice

- UI gallery / installer (#1399)
- Live calls to Grok product APIs
- Secrets, tokens, or scraped catalog HTML
