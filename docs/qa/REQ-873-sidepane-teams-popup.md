# REQ-873 — Show Configured Teams in Sidepane Popup with New Team Button (#263)

> Opens a configured teams popup from the sidepane footer "Teams" button, allowing operators to inspect and chat with existing teams, and providing a "+ New Team" button to launch the team composer.

**Issue:** [#263](https://github.com/matthewhand/open-swarm-private/issues/263)

---

## 1. Context & Motivation

In [`AgentSidebar.tsx`](../../webui/frontend/src/components/AgentSidebar.tsx), the left sidepane footer includes a "Teams" button:
```tsx
<button
  type="button"
  className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-sm ..."
  onClick={() => window.dispatchEvent(new CustomEvent(OPEN_TEAM_COMPOSER_EVENT))}
  title="Teams"
  aria-label="Teams"
  data-testid="os-teams-button"
>
  <Users className="h-4 w-4 shrink-0" aria-hidden="true" />
  <span className="os-teams-label">Teams</span>
</button>
```

Currently, clicking this button immediately dispatches `OPEN_TEAM_COMPOSER_EVENT`, which opens the empty creation modal [`TeamComposer.tsx`](../../webui/frontend/src/components/TeamComposer.tsx). This completely bypasses the operator's existing configured teams (`/v1/team-rosters/`).

Operators expect clicking "Teams" to provide an overview of all currently configured teams, with the ability to launch team chats, edit or manage rosters, and create new teams on demand.

---

## 2. Requirements

### 2.1 Configured Teams Popup / Modal (`TeamsPopup` / `ConfiguredTeamsPopup`)
1. **Trigger from Sidepane**:
   - In `AgentSidebar.tsx`, clicking the "Teams" button (`os-teams-button`) opens the `ConfiguredTeamsPopup` (or dispatches `OPEN_CONFIGURED_TEAMS_EVENT` / opens a teams list overlay).
2. **Data Source**:
   - Fetches team rosters via `fetchTeamRosters()` (`queryKey: ['team-rosters']`), matching the true multi-agent roster store (`/v1/team-rosters/`).
3. **Team Roster List Presentation**:
   - Each team card or row displays:
     - Team name and ID
     - Member count and member avatar stack (or member list chips)
     - Role badges (e.g. Chief of Staff designation if configured)
     - Quick actions:
       - **Chat**: Directly navigates to `/chat?team=<teamId>` and closes the popup.
       - **Edit**: Opens the team in `TeamEditor` (or loads it into `TeamComposer` in edit mode).
       - **Delete**: Triggers team deletion with confirmation dialog.
4. **Empty State**:
   - When no team rosters exist, renders an informative empty state: "No teams configured yet" with a call-to-action button to create the first team.

### 2.2 "+ New Team" Creation Flow
1. **Prominent Header Action**:
   - The popup header or action bar includes a prominent **"+ New Team"** button.
2. **Reuse Existing Team Composer**:
   - Clicking "+ New Team" launches the existing `TeamComposer` modal (`OPEN_TEAM_COMPOSER_EVENT`) with blank draft state, allowing the operator to define team members, assign Chief of Staff, and configure communication wires.
   - The teams list popup either closes or yields focus to the `TeamComposer` modal.

---

## 3. Acceptance Criteria

- [ ] Clicking the "Teams" button in the left sidepane footer opens a popup listing currently configured teams.
- [ ] Configured teams display team name, member avatars/count, and action buttons (Chat, Edit, Delete).
- [ ] Clicking a team row or "Chat" navigates to `/chat?team=<teamId>`.
- [ ] A "+ New Team" button is displayed in the popup header.
- [ ] Clicking "+ New Team" opens the existing `TeamComposer` dialog to create a new team.
- [ ] When no teams are configured, a clean empty state is shown with a "Create Team" button.
- [ ] **Tests**:
  - [ ] Vitest test in `AgentSidebar.test.tsx` (or `ConfiguredTeamsPopup.test.tsx`) asserting that clicking "Teams" opens the configured teams list.
  - [ ] Vitest test asserting clicking "+ New Team" launches the team composer modal.

---

## 4. Key Files to Modify

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `webui/frontend/src/components/AgentSidebar.tsx` | Sidepane component | Update "Teams" footer button to open configured teams popup instead of directly opening empty composer. |
| `webui/frontend/src/components/ConfiguredTeamsPopup.tsx` | New/updated teams popup | Render list of configured team rosters with quick actions and "+ New Team" button. |
| `webui/frontend/src/components/TeamComposer.tsx` | Team composer modal | Ensure smooth transition when opened from "+ New Team" button in the teams popup. |
| `webui/frontend/src/components/__tests__/AgentSidebar.test.tsx` | Sidebar test suite | Test "Teams" button opening teams list popup and triggering composer. |
