# REQ-869 — Move Message "Edit" Button Alongside Reaction Buttons (#259)

> Unifies chat message action and reaction controls into a single consolidated row. Moves the message "Edit" button from its isolated sub-row inside `ChatMessageBubble.tsx` into `MessageRowActions.tsx` alongside `Copy`, `Read Aloud`, `Retry`, and emoji reaction buttons.

**Issue:** [#259](https://github.com/matthewhand/open-swarm-private/issues/259)

---

## 1. Context & Motivation

Currently, message actions in `ChatPage.tsx` and `ChatMessageBubble.tsx` are fragmented across multiple separate UI elements:
- In `ChatMessageBubble.tsx` (lines 282-294):
  An isolated `<div>` renders `{canEdit && <button ...><Pencil /> Edit</button>}`.
- In `MessageRowActions.tsx` (and `ChatPage.tsx` line 3446):
  A separate reaction row renders `Copy`, `ReadAloudButton`, `ChatMessageActions` (`Retry`), and emoji reactions.

This split creates an inconsistent, cluttered interface where actions appear scattered across different vertical positions. Unifying the "Edit" button into the same horizontal line as the reaction buttons establishes a single, predictable location for all message actions.

---

## 2. Requirements

### 2.1 Unified Horizontal Action Bar
1. **Placement Alongside Reactions**:
   - The message **Edit** button must render directly within the horizontal action row (`MessageRowActions.tsx`), placed alongside `Copy`, `Read Aloud`, and `Retry`.
   - Recommended ordering:
     `[Edit]` (when `canEdit`) → `[Copy]` → `[Read Aloud]` (when available) → `[Retry]` (when available) → `[Emoji Reactions]`
2. **Remove Isolated Sub-Row in Bubble**:
   - Remove the standalone edit button container from `ChatMessageBubble.tsx` (lines 282–294) to eliminate redundant vertical spacing.
   - Context compression action (`onCompressToHere` / "Compress to here") may either sit inside `MessageRowActions` or as an option within the action group.
3. **Support for User & Assistant Messages**:
   - Both user and assistant messages (when editable) should display their actions using this unified row pattern.
4. **Visual & Interaction Polish**:
   - Retain standard action row visibility styling:
     - On desktop: `opacity-0 pointer-events-none group-hover/osrow:opacity-100 group-hover/osrow:pointer-events-auto group-focus-within/osrow:opacity-100 transition-opacity`.
     - On mobile/touch: visible or revealed on message tap.

---

## 3. Acceptance Criteria

- [ ] The **Edit** button appears in the same horizontal row alongside **Copy**, **Read Aloud**, and reaction buttons.
- [ ] No duplicate or orphaned edit button renders in a separate sub-row under `ChatMessageBubble`.
- [ ] Clicking **Edit** enters inline edit mode as expected.
- [ ] Action buttons remain hidden until hover/focus on desktop, avoiding visual clutter.
- [ ] **Tests**:
  - [ ] Vitest test in `webui/frontend/src/components/__tests__/MessageRowActions.test.tsx` verifying that `Edit` button renders when `canEdit={true}` and triggers `onStartEdit`.
  - [ ] Vitest test in `webui/frontend/src/pages/__tests__/ChatPage.test.tsx` verifying the unified actions layout.

---

## 4. Key Files to Modify

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `webui/frontend/src/components/MessageRowActions.tsx` | Message actions container | Accept `canEdit` and `onStartEdit` props; render `Pencil` Edit button in the row. |
| `webui/frontend/src/components/ChatMessageBubble.tsx` | Message bubble container | Remove isolated sub-row rendering `Edit`. |
| `webui/frontend/src/pages/ChatPage.tsx` | Message list in chat | Pass `canEdit` and `onStartEdit` into `MessageRowActions`. |
