# REQ-867 — Remove Chat Bubble Click-to-Edit to Restore Text Selection (#257)

> Removes the inline click/double-click edit trigger on chat message bubbles so users can select and copy text natively without triggering edit mode. In-place message editing is initiated exclusively via the explicit "Edit" button in the hover action toolbar.

**Issue:** [#257](https://github.com/matthewhand/open-swarm-private/issues/257)

---

## 1. Problem Description & User Impact

Currently in `ChatMessageBubble.tsx`:
```ts
const handleBubbleClick = (event: MouseEvent<HTMLDivElement>) => {
  if (!canEdit || streaming || editing) return
  const target = event.target as HTMLElement | null
  if (target?.closest('a, button, textarea, input')) return
  if (selectionIsActive()) return
  onStartEdit()
}
...
<div className="chat-bubble select-text ..." onClick={handleBubbleClick}>
```

When users attempt to double-click a word or drag to select text in a chat message bubble, `handleBubbleClick` frequently triggers:
- The bubble instantly transforms into a `<textarea>`, unmounting the rendered markdown and replacing it with raw text.
- This creates a jarring user experience and makes copying code snippets or text selections frustrating.
- A dedicated **Edit** action button (`Pencil` icon + "Edit" label) is already present in the bubble's action bar (visible on hover/focus) specifically to initiate edits.

---

## 2. Requirements

1. **Remove Bubble Body Click Handler**:
   - In `webui/frontend/src/components/ChatMessageBubble.tsx`:
     - Remove `onClick={handleBubbleClick}` from `.chat-bubble`.
     - Remove `handleBubbleClick` and `selectionIsActive()`.
2. **Preserve Dedicated Edit Button**:
   - Keep the existing `canEdit` toolbar button:
     ```tsx
     {canEdit ? (
       <button
         type="button"
         className="btn btn-ghost btn-xs gap-1"
         aria-label="Edit message"
         onClick={onStartEdit}
       >
         <Pencil className="h-3 w-3" aria-hidden="true" />
         Edit
       </button>
     ) : null}
     ```
   - Clicking this button remains the sole mechanism to enter in-place message edit mode.
3. **Native Text Selection**:
   - Single-clicking, double-clicking, triple-clicking, and drag-selecting text inside any chat bubble must behave as native browser text selection.

---

## 3. Acceptance Criteria

- [ ] Double-clicking text inside a chat bubble selects the word without entering edit mode.
- [ ] Drag-selecting text inside a chat bubble selects text without entering edit mode.
- [ ] Clicking the "Edit" button in the hover action bar enters edit mode as expected.
- [ ] Esc cancels edit mode; Enter (Cmd/Ctrl+Enter) saves edits.
- [ ] **Tests**:
  - [ ] Vitest test in `webui/frontend/src/components/__tests__/ChatMessageBubble.test.tsx` verifying that clicking or double-clicking the bubble does NOT trigger `onStartEdit`, but clicking the edit button does.

---

## 4. Locked Sources

| File | Component / Role | Planned Modification |
| :--- | :--- | :--- |
| `webui/frontend/src/components/ChatMessageBubble.tsx` | Message bubble container | Remove `handleBubbleClick`, `selectionIsActive`, and `onClick` on `.chat-bubble`. |
| `webui/frontend/src/components/__tests__/ChatMessageBubble.test.tsx` | Vitest test suite | Update/add tests asserting click-to-select behavior and explicit button edit trigger. |
