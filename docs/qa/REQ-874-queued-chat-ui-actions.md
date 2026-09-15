# REQ-874 — Complete Queued Chat UI Above Input Box with Send Now, Edit, and Delete (#265)

> Anchors a dedicated queued messages panel directly above the chat composer input box, providing explicit per-message actions for Send Now (interrupt & send), Edit (refine prompt), and Delete.

**Issue:** [#265](https://github.com/matthewhand/open-swarm-private/issues/265)

---

## 1. Context & Motivation

When backend access is lost (offline websocket / disconnected ASGI server) or when an assistant generation turn is in flight, the chat composer remains editable and typed sends are enqueued (REQ-845, REQ-90).

While a toast and status banner inform the user that messages are queued, the visual interface for managing queued messages is incomplete:
1. **Docking Position**: In [`ChatPage.tsx`](../../webui/frontend/src/pages/ChatPage.tsx), `QueuedSendPane` is currently positioned above the bottom dock rather than anchored directly above the composer input box inside `.os-chat-bottom-dock`. As a result, when long transcripts are scrolled, queued messages can be pushed out of immediate focus.
2. **Missing Action Controls**: In [`QueuedSendPane.tsx`](../../webui/frontend/src/components/QueuedSendPane.tsx), rows display only preview text and a single `X` remove icon. Users lack an explicit **"Edit"** button to refine their queued prompts before sending, and lack a dedicated **"Send Now"** button to immediately interrupt an in-flight generation and dispatch a specific queued prompt.

---

## 2. Requirements

### 2.1 Docked Queued Messages Container Above Input Box
1. **Placement**:
   - Dock the queued messages container directly above the composer input box within the bottom dock container (`bottomDockRef` / `.os-chat-bottom-dock` in `ChatPage.tsx`), immediately above suggestion chips and the composer form.
   - The panel must remain sticky and visible above the composer textarea regardless of transcript scroll position.
2. **Header & Capacity**:
   - Header displays a clear title and count, e.g. `Queued (N)`.
   - When more than 1 item is queued, provides a `Clear all` button to discard the queue locally without backend calls.
   - Max-height is capped (e.g. 1/3 of available transcript height) with smooth vertical scrolling for larger queues.

### 2.2 Three Explicit Actions per Queued Row
Each queued message row must provide three dedicated interactive controls:

1. **Send Now (`send-now`)**:
   - **Visual**: Prominent icon button (e.g. `Send` / `Play` / `Zap` or `Send now` label).
   - **Action**:
     - Immediately sends this specific queued message.
     - If an assistant generation turn is currently in flight, cancels/interrupts the active turn (`interruptRunningTurn` / `ws.send(buildCancelTurnFrame())`) and dispatches the queued prompt immediately.
     - Removes the message from the queue upon sending.
     - If currently offline, triggers an immediate reconnection attempt or informs the user.

2. **Edit (`edit`)**:
   - **Visual**: Dedicated edit button (e.g. `Pencil` icon).
   - **Action**:
     - Expands the row into an inline editing textarea populated with the prompt draft.
     - While editing, the row is held from automatic background draining (`onHoldIdsChange`).
     - Provides **Save** (commits updated text to local storage queue) and **Cancel** (discards unsaved edits) buttons.
     - Supports keyboard shortcuts: `Cmd/Ctrl+Enter` to save, `Escape` to cancel.

3. **Delete (`delete`)**:
   - **Visual**: Dedicated remove button (e.g. `Trash2` / `X` icon).
   - **Action**:
     - Discards the message from the queue immediately without sending.

### 2.3 Offline & Reconnect Integration
1. **Offline Visibility**:
   - When offline (`status !== 'open'`), any message submitted through the composer appears immediately in this queued pane.
   - A subtle status chip or indicator reflects that the messages are staged locally awaiting reconnect.
2. **Reconnection Drain**:
   - When the websocket reconnects, queued messages drain automatically in oldest-first order, except for rows currently being edited (`holdIds`).

---

## 3. Acceptance Criteria

- [ ] Queued messages are rendered in a pane anchored directly above the composer input box in the bottom dock.
- [ ] Every queued message row displays three distinct buttons: **Send Now**, **Edit**, and **Delete**.
- [ ] Clicking **Send Now** interrupts any running turn (if active) and sends that specific queued prompt immediately.
- [ ] Clicking **Edit** opens an inline textarea allowing the operator to refine the prompt text, with Save and Cancel actions.
- [ ] Clicking **Delete** removes the item from the queue.
- [ ] When offline, typed messages queue into this pane immediately.
- [ ] **Tests**:
  - [ ] Vitest test in `QueuedSendPane.test.tsx` verifying the presence and behavior of Send Now, Edit, and Delete buttons.
  - [ ] Vitest test in `ChatPage.queued.test.tsx` verifying Send Now interrupts an in-flight generation and sends the selected prompt.

---

## 4. Key Files to Modify

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `webui/frontend/src/components/QueuedSendPane.tsx` | Queued messages component | Add explicit Send Now, Edit, and Delete action buttons to every row with inline edit state. |
| `webui/frontend/src/pages/ChatPage.tsx` | Main chat view | Dock `QueuedSendPane` directly inside bottom dock above input box; pass `onSendNow` callback handling turn interruption and immediate dispatch. |
| `webui/frontend/src/components/__tests__/QueuedSendPane.test.tsx` | Component test suite | Add test coverage for the three row action buttons. |
| `webui/frontend/src/pages/__tests__/ChatPage.queued.test.tsx` | Integration test suite | Verify Send Now interrupt-and-send behavior in full chat flow. |
