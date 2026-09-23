# REQ-872 — Fix Undraggable Agents in Sidepane (#261)

> Restores reliable HTML5 drag-and-drop across all sidepane agent rows, resolving drag failures on multi-session (scale-out) buttons, remote agent drop blockers, and dynamic subagents.

**Issue:** [#261](https://github.com/matthewhand/open-swarm-private/issues/261)

---

## 1. Context & Root Cause Analysis

Users reported that while most agents in the sidepane can be dragged and reordered normally, certain agents—specifically more recent or actively used agents—cannot be dragged at all.

Investigation of `webui/frontend/src/components/AgentSidebar.tsx` identified several distinct defects:

### 1.1 Scale-Out Native Button Capturing (`<button draggable="true">`)
- In `renderAgentRow`, single-session agents render as `<Link to={...} {...dragHandlers}>` (`<a>` tag), which has full native HTML5 drag support.
- When an agent has 2 or more sessions (`sessions.length >= 2`), which routinely happens for recently chatted agents or active tasks, `shouldOpenSessionPicker(sessions)` returns `true` (`scaleOut = true`).
- Under `scaleOut = true`, the row renders as a native HTML `<button>`:
  ```tsx
  <div className="os-agent-row-wrap" data-role={role} data-scale-out="true">
    <button type="button" className={`${className} w-full`} {...dragHandlers}>
      {body}
    </button>
  </div>
  ```
- **The Browser Bug**: In Chromium, WebKit, and Firefox, `<button>` elements capture `mousedown` / `pointerdown` events for button press/activation states. The native HTML5 drag manager suppresses `dragstart` on `<button>` elements unless event defaults are bypassed or dragging is bound to a non-button container. Because `{...dragHandlers}` was placed on the `<button>` rather than the outer wrapper `.os-agent-row-wrap`, dragging recent/active agents failed completely.

### 1.2 Remote Agent Drop Blocker (`renderRemoteRow`)
- In `renderRemoteRow`, the drop handlers still retained legacy code:
  ```tsx
  onDragOver={(event) => {
    const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
    if (isPinnedId(fromId)) {
      allowRowDrop(event, hideId)
      return
    }
    try {
      event.dataTransfer.dropEffect = 'none'
    } catch { /* ... */ }
  }}
  onDrop={dropOnSelf}
  ```
- For unpinned agents or remotes (such as newly integrated **TrueForge** agents), `dropEffect` was explicitly set to `'none'`, and `onDrop` called `dropOnSelf` instead of `dropReorder(event, hideId)`. Consequently, no agent could be reordered around or dropped next to remote agents, and remote agents could not be dropped onto other remotes.

### 1.3 Dynamic Subagents Section Desynchronization
- Dynamic subagents (`dynamicSubagents`, `kind: 'subagent'`) are rendered in a virtual `subagentsBlock` with ID `'subagents'`.
- `'subagents'` is not registered in `railSections.ts` (`state.sections`). As a result:
  - `sectionIdForAgent` returns `UNASSIGNED_SECTION_ID` for dynamic subagents.
  - Dropping onto the `Subagents` section header calls `moveAgentToSection(current, fromId, 'subagents')`, which deletes section membership rather than persisting the assignment.
  - Furthermore, if dynamic subagents have multiple sessions, they also encounter the `scaleOut` button drag failure.

### 1.4 Nested Team Member Slots
- In `renderTeamRow`, nested child slots and unresolved team members render as plain `<span>` elements without `draggable` or drag listeners.

---

## 2. Requirements

### 2.1 Universal Row Draggability (Container-Level Dragging)
1. **Move Drag Handlers to Container or Accessible Target**:
   - In `AgentSidebar.tsx`:
     - Attach `dragHandlers` (`draggable={!hidden}`, `onDragStart`, `onDragEnd`, `onDragOver`, `onDrop`) to the container `<div className="os-agent-row-wrap">`, or provide a dedicated drag grip / use an accessible non-button interactive element that does not swallow native HTML5 drag gestures.
     - Ensure the inner session picker `<button>` does not stop propagation of `dragstart` events to the container.
2. **Prevent Pointer Hijacking**:
   - Ensure avatar badges and nested action buttons stop event propagation only on `click`, allowing drag gestures across the row area to initiate cleanly.

### 2.2 Fix Remote Agent Drag & Drop (`renderRemoteRow`)
1. **Enable Drop Target on Remote Rows**:
   - Replace `onDrop={dropOnSelf}` with `onDrop={(event) => dropReorder(event, hideId)}`.
   - Update `onDragOver` in `renderRemoteRow` to call `allowRowDrop(event, hideId)` uniformly, matching `renderAgentRow` and `renderTeamLink`.
2. **Support Remote Reordering**:
   - Allow TrueForge and other remote agents to be freely reordered alongside catalog and CLI agents on the rail.

### 2.3 Dynamic Subagents Drag & Section Stability
1. **Consistent Drop Reordering**:
   - Enable dragging and reordering within the `Subagents` block and across other sections.
   - Handle `'subagents'` in section state or ensure dropping on virtual section headers correctly moves agents into the subagent block without corrupting `sectionState.membership`.

---

## 3. Acceptance Criteria

- [ ] Multi-session (scale-out) agents can be dragged and dropped to reorder on the rail.
- [ ] Single-session agents and inactive agents continue to drag and reorder normally.
- [ ] Remote agents (e.g. TrueForge) accept drops and can be reordered on the rail.
- [ ] Dynamic subagent rows can be dragged and reordered.
- [ ] Clicking a scale-out agent still opens the session picker dialog without accidental drag activation.
- [ ] **Tests**:
  - [ ] Vitest in `AgentSidebar.test.tsx` verifying drag initiation and reordering on scale-out (`data-scale-out="true"`) agent rows.
  - [ ] Vitest in `AgentSidebar.test.tsx` verifying drag-and-drop reordering over remote agent rows.

---

## 4. Key Files to Modify

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `webui/frontend/src/components/AgentSidebar.tsx` | Main sidebar component | Move drag handlers to row container for scale-out buttons; update `renderRemoteRow` to use `allowRowDrop` and `dropReorder`. |
| `webui/frontend/src/lib/railSections.ts` | Rail sections logic | Support virtual/dynamic sections or harmonize `subagents` section assignment. |
| `webui/frontend/src/components/__tests__/AgentSidebar.test.tsx` | Sidebar test suite | Add test cases asserting drag/drop on scale-out rows and remote rows. |
