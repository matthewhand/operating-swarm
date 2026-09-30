# Agent template pack (#1398)

Version **1** JSON Schema: `src/swarm/core/agent_template.schema.json`.

The pack composes secret-free sections:

| Section | Shape |
| --- | --- |
| `profile` | Display name, description, title, role, avatar fields |
| `memories` | `profile` and `log` rows only (`title`, `body`) |
| `skills` | Prose skills (`name`, `description`, `instructions`) |
| `gettingStarted` | `{ "skill": "<packed skill name>" }` when skills are present |
| `routines` | Name, instruction, trigger, and `fill_ins` (`{{key}}` slots) |
| `plugins` | `pluginId`, `name`, `description` only |
| `fill_ins` | Slots aggregated from routines; import leaves them `pending` |

Routines and plugins are the domain packs (`routine_pack`, `agent_plugin_pack`). Import creates routines inactive and stores plugin ids only. A plugin that is already installed on the host can attach; anything else stays `pending` on the connect checklist. Connection fields (`url`, `command`, `args`, `headers`, `env`) are refused. Export reads those stores, and falls back to a legacy fragment file only when the domain store is empty. Import clears that fragment shadow.

## APIs

- `POST /v1/agents/<id>/template/` downloads the pack (`Content-Disposition: attachment`). `GET` returns the same JSON.
- `POST /v1/agent-templates/import/` creates an agent from a JSON body or a `file` / `pack` upload. `POST /v1/agents/<id>/template/import/` writes onto an existing seat and also accepts a file upload.
- `POST /v1/agent-templates/validate/` checks the JSON Schema and refuses credentials, secret keys, and binary fields.

## Grok mapper

File only. `GET /v1/agent-templates/grok-mapper/` documents the field map. `POST /v1/agent-templates/from-grok/` and `GET /v1/agents/<id>/template/grok/` translate `grok_bot_template` JSON. A bare `https://` body, or a JSON object with `share_id`, `share_url`, or `deep_link`, returns `grok_share_unsupported`.

The live Grok call is skipped when `XAI_API_KEY` and `GROK_API_KEY` are unset. This spike does not call out even if a key name is present.
