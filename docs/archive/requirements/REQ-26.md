# REQ-26 — First load hide gate and skeptic

**Status:** in flight (no PR number in this backlog slice)

## Intent

On a **first** visit, **gate** and **skeptic** are hidden from the sidepane so
the roster is not noisy. **Support stays visible.** If the user has already
customized hide/unhide, do **not** re-seed.

## Success

- Fresh `localStorage` (no `swarm_hidden_agents` yet): seed hide for gate + skeptic (and `tool_gate` if present). Support remains listed and highlighted when REQ-16/7 apply.
- If `swarm_hidden_agents` already exists — including an empty list the user chose — **do not re-seed**. User customization wins.
- Unhide from the `N hidden` popup (REQ-8 / REQ-24) is enough to bring gate/skeptic back.

## Constraints

- Do not hide Support on first load.
- Do not hide-all. Do not rewrite role wiring (REQ-9).
- No Neon. No oracle. Docs-only on this filing PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
