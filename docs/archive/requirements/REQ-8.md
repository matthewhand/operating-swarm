# REQ-8 — UX tighten (theme icon, unlabeled dropdowns, toast, hide popup)

**Status:** PR [312](https://github.com/matthewhand/open-swarm/pull/312) — in flight

## Intent

Tighten chat / sidepane chrome so healthy UI is quiet and controls are
icon-first. Not a new product surface.

## Success

- Theme toggle is a sun/moon **icon**, not a Light/Dark text button. Accessible name stays “Switch to light/dark theme”.
- Chat dropdowns have **no field labels**. Last item is `Manage Blueprints` → `/blueprint-library/`.
- Healthy connection is **silent**. Failures **toast**. No standing Connected badge.
- Composer footer is a compact tokens-in-context meter plus a live “who / how long” line while streaming.
- **No Hide-all.** When agents are hidden, the AGENTS list ends with `N hidden`; click opens a popup with Unhide per row. Persist `localStorage.swarm_hidden_agents`.

## Constraints

- Does not change OMB, LiteLLM, API auth, `SWARM_ALLOW_ANONYMOUS`, or default blueprints.
- Does not add Hide-all or a Support agent (that is REQ-7).
- After 312, tests must not wait on a Connected badge (REQ-13 follow-up).
- No Neon. No oracle. Docs-only on this PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
