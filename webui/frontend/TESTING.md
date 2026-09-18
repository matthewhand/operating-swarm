# Testing notes (webui/frontend)

Vitest conventions and the shared-state reset contract established by **#592**
(a full `npx vitest run` must be green and order-independent).

## Per-file reset contract

Each test file owns cleanup for what it stubs. `src/setupTests.ts` resets the
shared singletons **every test** (remotes fetch cache, chat connection, SPA
version, GitHub release cache). On top of that, a file that touches any of the
below must reset them in its own `afterEach`:

| Shared thing | Reset in `afterEach` |
| --- | --- |
| Globals via `vi.stubGlobal` (fetch, WebSocket, Notification, …) | `vi.unstubAllGlobals()` |
| Mocks / spies | `vi.restoreAllMocks()` |
| Fake timers | `vi.useRealTimers()` |
| `Element.prototype.*` overrides (e.g. `scrollIntoView`) | delete the override or restore the saved descriptor |
| `localStorage` | `window.localStorage.clear()` |
| Module-level caches | call the module's `reset*ForTests()` hook (see `src/lib/api`, `src/lib/chatMeter` `resetConversationThreads`, …) |

Rule of thumb: anything a file mutates **outside** React state must be
restored, because vitest forks per file but the *globals and prototypes* are
fresh per worker, not per assertion — late async writes from a previous test
in the same file (or an unstubbed global) leak into the next one.

## Timeouts (why they are higher than the defaults)

- `testTimeout: 15000` in `vite.config.ts` — several integration tests mount
  the full ChatPage/AgentSidebar trees; in a full parallel run a busy CPU can
  push a cold mount past the 5s default. The failures were machine-speed
  flaky (membership changed run to run), not assertion bugs.
- `configure({ asyncUtilTimeout: 4000 })` in `src/setupTests.ts` — the
  default 1000ms `findBy*`/`waitFor` window is too tight for the same
  reason; prefer generous per-test `{ timeout }` overrides over shortening
  the global window.

Both are floors, not invitations: a test that *needs* 15s usually means the
thing under test is polling on a real timer and should get a fake-timer or
gate-based test instead.

## Known race fixed alongside (#592)

`AgentEditor` hydration used to write server defaults over controls the user
had already edited when the settings fetch resolved late. Hydration now skips
touched groups (see `AgentEditorHydrationRace592.test.tsx` for the contract).
