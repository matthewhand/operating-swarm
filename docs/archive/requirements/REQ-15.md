# REQ-15 — CLI dropdown lists CLIs

**Status:** PR [316](https://github.com/matthewhand/open-swarm/pull/316) — in flight

## Intent

When the selected agent / mode is a CLI agent, the Chat dropdown must list
**available CLIs**, not the full blueprint catalog. (Grok CLI can already
answer; the dropdown still listed blueprints.)

## Success

- CLI-agent context: selected / `?blueprint=` is `cli_agent` or any `cli_*` slug, or `?mode=cli` / `?cli=<name>`.
- Dropdown prefers host-exposed CLIs (`installed` ∪ `configured` from `GET /v1/cli-agents/`), then falls back to the static catalog.
- Selecting a CLI sends `{"message", "blueprint": "cli_agent", "params": {"cli": "grok"}}` (or the chosen name). Consumer forwards `params`.
- In CLI context the dropdown is **unlabeled** (REQ-8) and ends with **Manage Cli** → `/settings/`. Blueprint-mode chats still list `/v1/blueprints`.

## Constraints

- Not piled onto 313. Not a Grok-Bot chrome rewrite.
- Builder SPA stays deleted (ADR-001).
- No Neon. No oracle. Docs-only on this PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
