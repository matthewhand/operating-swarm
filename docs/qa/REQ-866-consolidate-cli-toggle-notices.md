# REQ-866 — Consolidate CLI Toggle Info Messages (#256)

> Eliminates repetitive status spam when switching CLI agents in the chat header dropdown. Replaces three redundant status messages with a single consolidated notice emitted when the user toggles, including `(from_cli → to_cli)` in parentheses within the message.

**Issue:** [#256](https://github.com/matthewhand/open-swarm-private/issues/256)

---

## 1. Problem Description & Root Cause

When a user switches between CLI agents (e.g., from `qwen` to `omp`), three separate messages currently appear in the chat pane:
1. **Message 1 (Dropdown Change)**:
   In `ChatPage.tsx`:
   ```ts
   recordDropdownChange('cli', next.previous.agent, next.agent)
   // Emits: "CLI: qwen → omp <timestamp>"
   ```
2. **Message 2 (Session Hop Result)**:
   In `src/swarm/core/cli_session_hop.py`:
   ```python
   # hop_notice_text() emits:
   "Started a new omp session. No prior context to carry from qwen."
   ```
3. **Message 3 (Subsequent Prompt Send)**:
   In `src/swarm/consumers.py`:
   ```python
   # _emit_new_cli_session_notice() on subsequent user send emits:
   "Started a new omp session."
   ```

Having three separate notices for a single CLI switch clutters the chat transcript with redundant noise.

---

## 2. Requirements

### 2.1 Consolidate to a Single Status Message
- When the user toggles between CLIs in the dropdown, **exactly one** status notice must be recorded and displayed.
- The single notice must appear **when the user actually toggles** the dropdown.

### 2.2 Ditch Message 1 (Standalone Dropdown Status)
- In `ChatPage.tsx`, suppress `recordDropdownChange('cli', ...)` when switching between distinct CLIs (`fromCli !== toCli`), as `hopCliSession` produces the authoritative status notice.

### 2.3 Ditch Message 3 (Prompt Pre-Emit Notice)
- In `src/swarm/consumers.py` (`_emit_new_cli_session_notice`), ensure that `transcript_already_has_notice` treats any existing session hop notice containing `to_cli` as satisfying the new session notice requirement, preventing a redundant `"Started a new {to_cli} session."` line on prompt send.

### 2.4 Update Message 2 (Single Unified Notice Format)
- In `src/swarm/core/cli_session_hop.py` (`hop_notice_text`), include `({from_cli} → {to_cli})` in parentheses:
  - **No prior context / empty thread**:
    ```
    Started a new {to_cli} session ({from_cli} → {to_cli}). No prior context to carry from {from_cli}.
    ```
  - **With context carried**:
    ```
    Started a new {to_cli} session ({from_cli} → {to_cli}). Carried {mode} context ({tokens} tokens).
    ```
  - **Empty with export warning**:
    ```
    Started a new {to_cli} session ({from_cli} → {to_cli}). {export_warning} Nothing to carry.
    ```

---

## 3. Acceptance Criteria

- [ ] Switching between CLIs (e.g., `qwen` → `omp`) emits **only 1** status message in the chat transcript.
- [ ] No standalone `CLI: qwen → omp` message appears when switching CLIs.
- [ ] No duplicate `Started a new omp session.` message appears when the user sends their subsequent message.
- [ ] The single status message includes the transition in parentheses:
  - e.g., `Started a new omp session (qwen → omp). No prior context to carry from qwen.`
- [ ] **Tests**:
  - [ ] Vitest test in `webui/frontend/src/pages/__tests__/ChatPage.test.tsx` verifying that a single consolidated status message is emitted on CLI change.
  - [ ] Python tests in `tests/core/test_cli_session_hop.py` and `tests/test_consumers.py` verifying the updated string shape and suppression of redundant prompt notices.

---

## 4. Key Files to Modify

| File | Role |
| :--- | :--- |
| `src/swarm/core/cli_session_hop.py` | Update `hop_notice_text` format to include `({from_cli} → {to_cli})` |
| `webui/frontend/src/pages/ChatPage.tsx` | Bypass `recordDropdownChange('cli', ...)` in favor of `hopCliSession` |
| `src/swarm/core/chat_transcript.py` | Recognize hop notices in `transcript_already_has_notice` to suppress prompt duplicates |
| `src/swarm/consumers.py` | Ensure `_emit_new_cli_session_notice` does not emit duplicate lines |
