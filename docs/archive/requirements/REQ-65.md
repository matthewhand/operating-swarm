# REQ-65 — Agent setting: new chat per task

**Status:** this PR — in flight (GitHub #393)

## Intent

An agent can be set to start a **new chat per task** so a Chief of Staff can
run several worker instances concurrently, each with a clean context (like
Cursor cloud agents), instead of stuffing every job into one reused session.

## Success

1. Agent editor (agent-scoped pane, compatible with #382) has a **prominent**
   toggle. Label: **New chat per task**. Default **off**.
2. Hover tooltip (DaisyUI): *Agents reuse one session by default so they
   remember the thread. Turn this on for a worker that scales out: each task
   gets a fresh chat, and several can run at once.*
3. When **off**: later tasks/handoffs from CoS continue the existing
   conversation for that agent (one session).
4. When **on**: each new user task / CoS handoff / as_tool invocation gets a
   **new empty session**. Multiple such sessions may run concurrently.
5. API agents: swarm owns session create. CLI/remote: do **not** resume a
   stored session id when this is on (#369 still applies to reuse-mode agents).
6. Tests: default off reuses session id; on creates a new session per task;
   two concurrent on-mode tasks do not share transcript; tooltip/label present
   in the editor.

## Constraints

- Agent-editor only (not global Settings). Compatible with #382.
- DaisyUI 5, React 18. Chat stays mounted.
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- No Neon. No secrets.
- Do not fold into PR 344.
- `Fixes` #393.

## Owner

- CoS transcribes
- cloud implements (this PR)
- engineer GitHub-merge after skeptic
