# REQ-19 — DaisyUI settings sheet `modal-end` + Menu + Join

**Status:** PR [320](https://github.com/matthewhand/open-swarm/pull/320) — in flight

## Intent

Settings opens as a DaisyUI **popup over SPA chat** instead of a top-nav eject
to the Django dashboard.

## Success

- Gear (`Open settings`) opens a right-docked `<dialog class="modal modal-end">` over `/` and `/chat`. Esc and backdrop close.
- Inner nav is DaisyUI **`menu`** + `menu-dropdown` (e.g. Remotes: Hermes / OMB / Rakazo placeholders).
- Segmented controls use DaisyUI **`join`** (e.g. Retention: Count | Disk | Archive | Trash).
- Settings is **not** in the desktop top-nav text links or the mobile dock. Django `/settings/` remains the operator dump.
- Narrow viewports stack the menu above the pane so Retention / Hostname stay usable.

## Constraints

- React 18 + Tailwind 4 + DaisyUI 5 only. No Drawer, no Join-as-section-nav, no `btn-group`.
- Guest auth / Neon / oracle untouched.
- Teams live today are LLM aliases; remotes in the sheet may be placeholders until REQ-11 lands.
- Docs-only on this filing PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
