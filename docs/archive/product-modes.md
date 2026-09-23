# Archive: `product_modes` surface gating (superseded by always-on-if-configured)

**Status:** Archived per #736 Step 1. The gating layer shipped through commit
`5959df28` on `main` (PR #945) and is removed from `main` by the companion
simplification PR. This document preserves the recoverable contract; the full
implementation lives in git history at tag/commit `5959df28`.

## What shipped

Per-namespace surface toggles in **Settings → Rail** ("Manage surfaces"),
covering `cli`, `api`, `blueprint`, `team`, `remote`:

- **Persistence:** `settings.product_modes` in the Django config store,
  written via `patchConfigSection('settings', { upsert: { product_modes } })`.
- **Transport:** `GET /v1/cli-agents/` advertised `modes` and
  `mode_limitations`; payloads without `modes` were treated as legacy
  all-on (`LEGACY_ALL_ON_PRODUCT_MODES`).
- **Frontend module:** `webui/frontend/src/lib/productModes.ts` —
  `PRODUCT_MODE_KEYS`, `DEFAULT_PRODUCT_MODES`, `resolveProductModes`,
  `productModesWhenSettled` (#594: read modes only after the fetch settles,
  to stop first-paint flashing).
- **Gating sites:**
  - `AgentSidebar.tsx` — rail group filters (`productModes.cli|api|team|remote|blueprint`).
  - `ChatPage.tsx` — `renderRoutingPicker()` branches, composer session
    queries, remote/backed-team guardrails.
  - `SettingsSheet.tsx` — the "Manage surfaces" fieldset
    (`data-testid="product-modes"`).
  - Backend `src/swarm/core/cli_catalog.py` — advertised the modes payload.

## Why it was retired

1. First-paint flashing / race conditions on load (#594 chased, never fully fixed).
2. Toggle desync and mutation races (#710 had to force all-on-by-default).
3. Gating sprawl across four+ components with per-surface re-derivations.
4. Mental model: configured things should simply appear. An artificial
   secondary toggle only produced "X hidden by product modes — enable in
   Settings" noise on screen.

## Recovery recipe

1. Reintroduce `src/lib/productModes.ts` from `5959df28`.
2. Re-add the `modes` advertisement in `cli_catalog.py`.
3. Re-wire the filters in `AgentSidebar.tsx` / `ChatPage.tsx` (commit
   `5959df28` shows every call site).
4. Re-add the Settings fieldset (`Manage surfaces`) from the same commit.

Prefer not to. If a namespace needs gating, gate that one namespace behind a
purpose-built control, not a global mode matrix.
