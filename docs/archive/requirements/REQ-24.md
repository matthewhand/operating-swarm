# REQ-24 — Drag any agent incl. roles into Hidden drop zone

**Status:** implemented in #342 (left-rail Hidden drop zone; hide wins for list + pin grid)

## Intent

Hide is a **drop zone**, not only a context-menu. Any agent — including
**role** seats (support / gate / skeptic / default) — can be dragged there.

## Success

- Drag any AGENTS / conversation row onto a Hidden drop zone → that id joins `localStorage.swarm_hidden_agents`.
- Role-badged rows (REQ-9) are eligible. Support can be hidden if the user does it (first-load default is REQ-26).
- Unhide remains per-row from the `N hidden` popup (REQ-8). **No Hide-all.**
- Pin / favourite (REQ-10) is a copy on pin. **Choice: hide wins** — hiding a pinned row removes it from the conversation list **and** the favourite pin grid. Unhide restores the list row only (does not re-pin).

## Constraints

- Native HTML5 drag. No `@dnd-kit`.
- Do not hide-all. Do not re-seed hide on every load (REQ-26).
- No Neon. No oracle.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
