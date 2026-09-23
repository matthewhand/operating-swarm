# REQ-861 — Left and right sidepane conceal buttons and click-outside dismissal (#251)

> Both left and right sidepanes feature intuitive, accessible buttons in their top-left headers to conceal them, complementing existing click-outside and backdrop dismissal. The left sidepane features the Open Swarm logo (in mono-colour matching the active WebUI theme) as its top-left conceal button when expanded. The right sidepane features a double-chevron/double-less-than `>>` button in its top-left header to tuck/conceal the pane.

**Issue:** [#251](https://github.com/matthewhand/open-swarm-private/issues/251)

---

## 1. Background & Rationale

Users navigating the WebUI require immediate, visible, and predictable affordances to dismiss or conceal docking panes:
- **Left Sidepane (`AgentSidebar`)**: Serves as the primary navigation and agent rail. When expanded out, users need a prominent, brand-aligned conceal trigger in the top-left corner, paired with canvas/backdrop click-to-dismiss.
- **Right Sidepane(s)**: Right-docked drawers and sheets (such as `SettingsSheet`, `TeamsSheet`, `AgentEditorSheet`, and `GenerationsPanel`) need a consistent tuck/conceal button (`>>`) located in the top-left of the right-hand panel, alongside click-outside dismissal.

---

## 2. Detailed Requirements

### 2.1 Left Sidepane (Agent Rail)
1. **Top-Left Open Swarm Brand Mark Button**:
   - When the left sidepane is open/expanded, the top-left corner must display an interactive button containing the Open Swarm logo.
   - **Styling**: The logo must be mono-colour, styled dynamically to match the active WebUI theme (e.g., using `currentColor` / `text-base-content` via the mono geometry from `assets/brand/webui-geometric-mono.svg` or `webui-geometric.svg`).
   - **Action**: Clicking this button conceals the sidebar:
     - On desktop (`lg+`): Collapses the sidebar to the avatar-only / compact rail or toggles the rail closed.
     - On mobile / drawer view (`narrow`): Invokes `onClose()` to conceal the slide-out drawer.
   - **Accessibility**: Must be a semantic `<button>` with `aria-label="Conceal sidebar"`, `title="Conceal sidebar"`, visible focus styling, and a minimum touch target (>= 32x32px).
2. **Click-Outside Dismissal**:
   - Clicking anywhere outside the expanded left sidepane (such as the modal backdrop or the main chat/canvas area) must conceal the sidepane.

### 2.2 Right Sidepane(s) (Settings, Teams, Generations, etc.)
1. **Top-Left `>>` Conceal Button**:
   - Right-docked surfaces must feature a double less-than `>>` icon button positioned in the **top-left** of the pane header.
   - **Icon**: Use a double right-pointing chevron / double less-than glyph `>>` (e.g., Lucide `ChevronsRight` or an inline SVG equivalent) indicating the pane will slide/tuck away towards the right margin.
   - **Action**: Clicking this button invokes the pane's `onClose()` callback to conceal/close the pane.
   - **Surfaces Covered**:
     - `Modal.tsx` when configured with `placement="end"` and/or `size="sheet"`.
     - `SettingsSheet.tsx` (top-left of the sheet / navigation header).
     - `TeamsSheet.tsx` (top-left of sheet header).
     - `GenerationsPanel.tsx` (top-left of the floating generations drawer header).
     - Other right-docked sheets (`AgentEditorSheet.tsx`, `BlueprintsSheet.tsx`, `RolePaneSheet.tsx`).
   - **Accessibility**: Semantic `<button>` with `aria-label="Conceal sidepane"`, `title="Conceal sidepane"`, visible focus rings, and proper keyboard navigation (Enter/Space).
2. **Click-Outside Dismissal**:
   - Clicking anywhere outside the right sidepane (e.g., clicking on the backdrop or the main content canvas) must dismiss/conceal the sidepane.

---

## 3. Acceptance Criteria

- [ ] **Left Sidepane Conceal Button**:
  - [ ] Top-left of the expanded left sidepane renders the Open Swarm logo in mono-colour matching `text-base-content`.
  - [ ] Clicking the logo button triggers sidepane concealment/collapse.
  - [ ] Button provides `aria-label="Conceal sidebar"` and keyboard accessibility.
  - [ ] Clicking outside the sidebar (backdrop or main canvas) conceals the sidebar when open in drawer/overlay mode.
- [ ] **Right Sidepane Conceal Button**:
  - [ ] Right-docked sheets and panels (`SettingsSheet`, `TeamsSheet`, `GenerationsPanel`, etc.) render a `>>` (`ChevronsRight`) button in their top-left header.
  - [ ] Clicking `>>` triggers `onClose` and conceals the panel.
  - [ ] Button provides `aria-label="Conceal sidepane"` and keyboard accessibility.
  - [ ] Clicking outside the right pane (backdrop / canvas click) conceals/dismisses the pane.
- [ ] **Tests**:
  - [ ] Frontend Vitest test coverage for left sidepane conceal button rendering, accessibility, and click handlers.
  - [ ] Frontend Vitest test coverage for right sidepane `>>` conceal button in `Modal`, `SettingsSheet`, and `GenerationsPanel`.
  - [ ] Python source inspection lock in `tests/unit/test_req861_sidepane_conceal_buttons.py`.

---

## 4. Key Implementation Locations

| File | Component / Role | Planned Modification |
|------|-------------------|----------------------|
| `webui/frontend/src/components/AgentSidebar.tsx` | Left sidepane rail container | Mount top-left mono logo conceal button; wire conceal/collapse action. |
| `webui/frontend/src/components/AgentSidebar/SidebarHeader.tsx` | Header row of AgentSidebar | Incorporate the mono brand mark conceal button on expanded views. |
| `assets/brand/webui-geometric-mono.svg` | Brand asset | Mono geometry with `currentColor` fill for WebUI theme adherence. |
| `webui/frontend/src/components/DaisyUI/Modal.tsx` | Base modal / right-docked sheet | Provide top-left `>>` (`ChevronsRight`) conceal button when `placement="end"`. |
| `webui/frontend/src/components/SettingsSheet.tsx` | Settings right sidepane | Render top-left `>>` conceal button in navigation/header area. |
| `webui/frontend/src/components/GenerationsPanel.tsx` | Generations right drawer | Add `>>` conceal button in the top-left of the drawer header. |
| `webui/frontend/src/components/overlays/TeamsSheet.tsx` | Teams right sheet | Ensure top-left `>>` conceal button is present and wired to `onClose`. |

---

## 5. Test Plan & Verification

1. **Vitest Unit Tests**:
   - `webui/frontend/src/components/__tests__/AgentSidebar.test.tsx`:
     - Test that the mono Open Swarm logo button renders in top-left when expanded.
     - Test that clicking the logo triggers conceal/collapse.
     - Test accessibility attributes (`aria-label`, button role).
   - `webui/frontend/src/components/DaisyUI/__tests__/Modal.test.tsx`:
     - Test that right-docked modal (`placement="end"`) renders the top-left `>>` button and clicking it calls `onClose`.
   - `webui/frontend/src/components/__tests__/GenerationsPanel.test.tsx`:
     - Test that `GenerationsPanel` renders `>>` in top-left and invokes `onClose`.
2. **Python Source Inspection Guard**:
   - `tests/unit/test_req861_sidepane_conceal_buttons.py`:
     - Enforces presence of REQ-861 documentation.
     - Verifies `AgentSidebar` references the brand logo conceal button.
     - Verifies right-docked surfaces reference the `>>` / `ChevronsRight` conceal button.
