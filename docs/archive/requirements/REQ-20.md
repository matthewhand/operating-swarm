# REQ-20 — Teams composition roster DnD (not LLM aliases)

**Status:** PR [323](https://github.com/matthewhand/open-swarm/pull/323) — in flight

## Intent

**Teams** is the composition abstraction: a drag-drop roster of API / CLI /
remote members that can see and talk via handoff / `as_tool`. This is **not**
the Django `/teams/` LLM-alias admin.

## Success

- First-launch two panes: left = drop zone (“drop agents here”); right = available agents (API / CLI / remote), HTML5-draggable. Context-menu Add/Remove. No `@dnd-kit`.
- Member chips: name, kind badge (`API` | `CLI` | `remote`), optional role (`support` | `gate` | `skeptic` | `default`).
- Per-team wires: `handoff` and `as_tool` toggles (default on). Persist a roster contract that is **not** `teams.json`.
- Django Team Launcher / Admin / Swarm Creator stay aliases.

## Constraints

- **Honesty:** Teams live today **are** LLM-profile aliases (`/teams/` + `/v1/teams` + `teams.json`). Do not rewrite that admin in this REQ. Do not call aliases a multi-agent builder.
- No SPA Teams tab / Grok chrome in the 323 slice unless later REQs say so.
- No Neon / oracle, no guest auth, no `.30` deploy from cloud.
- Docs-only on this filing PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
