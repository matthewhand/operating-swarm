# REQ-16 — Grok-Bot left rail chrome

**Status:** PR [322](https://github.com/matthewhand/open-swarm/pull/322) — in flight

## Intent

Grok-Bot **product chrome**: left rail + selected-agent main pane. Not piled
onto PRs 309–315 (those are other layouts). Favourites live in the **left rail
under Search**, not in top chrome like #311.

## Success

**Left rail (top → bottom):** Search (opens palette — REQ-17) → unlabeled favourite tile grid → conversation list with **Support first / highlighted** → Hidden via end-of-list `N hidden` popup (Unhide only, no Hide-all) → Plugins → editable hostname.

**Main pane:** selected agent’s chat only. No Home / Chat / Blueprints / Teams / Settings top nav. Header = agent name + icon tools (theme is sun/moon, not Light). Composer pill: `[+] [ Message … ] [mic]`. `+` reaches Django Blueprints / Teams / Settings. Footer is laconic. Errors toast. No standing Connected. Switching agents opens a unique websocket thread.

## Constraints

- No `@dnd-kit`, no shadcn migration.
- No `SWARM_ALLOW_ANONYMOUS` / guest auth. No oracle / Neon.
- **Honesty:** Grok chrome is **not on `:8001` yet.** REQ-5 dark chrome ≠ this Bot product.
- Docs-only on this filing PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
