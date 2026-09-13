# REQ-10 — Favourites tile grid (left rail, not top chrome)

**Status:** PR [311](https://github.com/matthewhand/open-swarm/pull/311) — in flight (**wrong place**)

## Intent

An unlabeled favourite / pin **tile grid** so operators can keep a short set of
agents one click away. Pin is a copy, not a move.

## Success

- Unlabeled compact tiles. No “Favourites” heading. No hide-all.
- Drag an AGENTS row onto the grid → tile. Persist `localStorage.swarm_pinned_agents`. Duplicate drops are no-ops. Remove control on each tile.
- Clicking a tile opens that agent’s chat (`/chat?blueprint=<id>`).
- **Placement:** left rail, under Search (see REQ-16). Native HTML5 drag. No `@dnd-kit`.

## Constraints

- **PR 311 put the grid in top chrome.** That is the wrong place. Do not land 311 as the product location.
- Correct home is the Grok-Bot **left rail** (PR 322 / REQ-16). Treat 311 as a misplaced attempt, not the target layout.
- Sidepane list stays unchanged — pin is a shortcut.
- No Neon. No oracle. Docs-only on this PR — do not implement here.
- Grok chrome is **not on `:8001` yet**.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
