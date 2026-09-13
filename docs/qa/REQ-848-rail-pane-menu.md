# REQ-848 — Right-click rail background to create a section (private #173)

> Right-clicking **empty rail space** offers **New section**; the new section is
> created empty and opens in inline rename. The section-header menu also gains
> New section. Agents and pinned tiles drag onto section headers to move in —
> the grouping mechanism for roster/locked-comms workflows. Retro-fitted
> requirement + source-lock for the shipped fix. Builds on REQ-209 (#689 /
> #845 custom sections + dropOnSection).

**As-of:** branch `fix/149-cli-first-discovered-defaults` (dirty; feature shipped
in-session under #173).

**Issue:** [private #173](https://github.com/matthewhand/open-swarm-private/issues/173)

## Requirement

1. `paneMenuItems()` returns a single `section-create` ("New section") item for
   the rail-background context menu.
2. `sectionMenuItems()` (section-header menu) also includes `section-create`.
3. `AgentSidebar` shows the pane menu on `<nav>` right-click, **bailing** when
   the target is a row/section/pin (`[data-rail-id], .os-rail-section,
   .os-pin`) so those keep their own menus — no double-open.
4. `handlePaneMenuSelect` creates an empty section and starts inline rename,
   mirroring the existing Move-to → New section flow.
5. `RailContextMenu` can render the new item (icon map includes
   `'section-create': FolderPlus`).

## Acceptance criteria

- [x] `paneMenuItems` + `section-create` in both menus.
- [x] `openPaneMenuAt` / `handlePaneMenuSelect` wired; `paneMenu` state closes
      with the shared outside-click / Escape handler.
- [x] Pane right-click bails on row/section/pin targets.
- [x] Menu renderer has an icon for `section-create`.

## Locked sources

| File | Role |
|------|------|
| `webui/frontend/src/lib/railContextMenu.ts` | `paneMenuItems` + `section-create` |
| `webui/frontend/src/components/AgentSidebar.tsx` | pane menu state + handlers + `<nav>` |
| `webui/frontend/src/components/RailContextMenu.tsx` | icon map |

## Test map

- `tests/unit/test_req848_rail_pane_menu.py` — source-lock (this REQ).
- `webui/frontend/src/components/__tests__/RailSections.test.tsx` (vitest) — pane
  right-click → create → rename → drop hint.