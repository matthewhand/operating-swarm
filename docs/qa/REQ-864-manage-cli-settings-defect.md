# REQ-864 — Fix "Manage Cli" Navigation and Settings Page Rendering Defect (#254)

> Resolves the issue where selecting "Manage Cli" in the chat header dropdown navigates away from the React SPA to a broken-looking Django settings page. Clicking "Manage Cli" must open the modern in-app `SettingsSheet` at `section: 'cli-agents'`, and the legacy Django `/settings/` dashboard must render cleanly without visual defects.

**Issue:** [#254](https://github.com/matthewhand/open-swarm-private/issues/254)

---

## 1. Problem Description & Root Cause

When a user in `ChatPage` selects the CLI routing picker and clicks the footer action **"Manage Cli"**:
1. **Unintended Page Navigation**:
   In `webui/frontend/src/pages/ChatPage.tsx`:
   ```ts
   footerAction={{
     id: MANAGE_CLI_VALUE,
     label: 'Manage Cli',
     onSelect: () => {
       window.location.assign(MANAGE_CLI_HREF) // evaluates to '/settings/'
     },
   }}
   ```
   Instead of opening the in-app `SettingsSheet` (which contains `CliAgentsSettingsPane.tsx` under section `'cli-agents'`), the application triggers a hard browser redirect to `/settings/`.
2. **Visual & Functional Defect on `/settings/`**:
   - `/settings/` is a legacy server-rendered Django template (`src/swarm/templates/settings_dashboard.html`).
   - The user sees a jarring, outdated dashboard that lacks the modern DaisyUI styling of the React SPA.
   - The page has layout defects: `.settings-page` lacks base styles in `operator.css`, card margins and statistics progress bars render inconsistently against Bootstrap 5 dark theme tokens, and the page doesn't even contain CLI agent settings.

---

## 2. Requirements

### 2.1 In-App Sheet Navigation for "Manage Cli"
1. **Immediate In-App Opening**:
   - In `ChatPage.tsx`, `footerAction.onSelect` for `MANAGE_CLI_VALUE` must call:
     ```ts
     openSettingsSheet({ section: 'cli-agents' })
     ```
   - This must open the right-docked `SettingsSheet` with the CLI Agents pane pre-selected without unmounting `ChatPage` or reloading the browser.
2. **Parity for Sibling Dropdown Actions**:
   - Review and align all related header actions in `ChatPage.tsx`:
     - **Manage Teams**: Open the `TeamsSheet` overlay in-app (`setTeamsSheetOpen(true)`) or navigate via client-side router rather than a hard reload to `/teams/`.
     - **Manage Models**: Open `openSettingsSheet({ section: 'llm-profiles' })` rather than hard reload to `/profiles/`.

### 2.2 Django `/settings/` Visual Repair & Defect Resolution
1. **Layout & Container Styling**:
   - In `src/swarm/static/css/operator.css`, add explicit styling for `.settings-page`:
     - Proper horizontal and vertical padding (`padding: 1.5rem`).
     - Consistent maximum width and centering (`max-width: 1200px; margin: 0 auto;`).
2. **Card & Token Alignment**:
   - Fix styling for `.dashboard-header-card`, `.stat-card`, and `.chat-retention-card` to ensure consistent background, borders, and readable typography under both dark and light themes.
   - Clean up progress bar track/fill sizing in `.configuration-progress`.
3. **Operator Guidance Banner**:
   - Add a prominent top banner in `settings_dashboard.html` linking back to the modern SPA:
     *"Looking for WebUI settings? Open the [WebUI Settings](/chat?settings=true) or return to [Chat](/chat)."*

---

## 3. Acceptance Criteria

- [ ] **SPA Continuity**:
  - [ ] Clicking **Manage Cli** in `ChatPage` navbar picker opens `SettingsSheet` with `section: 'cli-agents'` without reloading the page.
  - [ ] The CLI Agents settings pane (`CliAgentsSettingsPane.tsx`) is immediately visible and interactive.
- [ ] **Django Settings Rendering**:
  - [ ] `/settings/` renders with proper card borders, paddings, and alignment in `settings_dashboard.html`.
  - [ ] Dark and light themes apply cleanly without broken or invisible text.
  - [ ] No unstyled `.settings-page` elements or overlapping stats cards.
  - [ ] Includes a clear link back to the modern WebUI chat and settings.
- [ ] **Tests**:
  - [ ] Vitest test in `webui/frontend/src/pages/__tests__/ChatPage.test.tsx` (or `NavbarRoutingPicker.test.tsx`) verifying that selecting "Manage Cli" triggers `openSettingsSheet` with `{ section: 'cli-agents' }`.
  - [ ] Python view test in `tests/views/test_settings_views.py` verifying clean 200 response and template rendering of `/settings/`.

---

## 4. Locked Sources

| File | Component / Role |
| :--- | :--- |
| `webui/frontend/src/pages/ChatPage.tsx` | Wire `openSettingsSheet({ section: 'cli-agents' })` to `footerAction` |
| `webui/frontend/src/lib/cliAgentContext.ts` | Update / alias `MANAGE_CLI_HREF` |
| `src/swarm/templates/settings_dashboard.html` | Settings dashboard template repairs |
| `src/swarm/static/css/operator.css` | `.settings-page` and dashboard card styles |
