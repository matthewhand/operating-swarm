# REQ-845 — Composer never locks; offline sends queue (private #167)

> The chat composer stays **typeable and sendable** even when the websocket is
> closed or still connecting. Sends are queued per-conversation and drain on
> reopen; a visible status banner explains the offline state. Retro-fitted
> requirement + source-lock for the shipped fix.

**As-of:** branch `fix/149-cli-first-discovered-defaults` (dirty; feature shipped
in-session under #167).

**Issue:** [private #167](https://github.com/matthewhand/open-swarm-private/issues/167)

## Requirement

1. The composer textarea is **never disabled** by socket state — a draft can
   always be typed and the input keeps focus.
2. Submitting while the socket is not `open` must not drop the message: it is
   queued (`queued.enqueue`) and a toast explains it will send on reconnect.
3. Submitting while an assistant turn is already in flight is queued the same
   way (no double-`{message}` race).
4. A visible `.os-conn-status` banner (with dot + live label) is shown whenever
   `status !== 'open'`, covering both auth-rejected and offline cases.

## Acceptance criteria

- [x] `submitUserText` enqueues instead of dropping when `status !== 'open'`.
- [x] Reconnect toast copy present ("Chat is reconnecting — …").
- [x] Banner `data-testid="chat-conn-status"` rendered with `os-conn-status`
      class in `ChatPage.tsx` and `index.css`.
- [x] Offline banner copy tells the user they can keep typing.

## Locked sources

| File | Role |
|------|------|
| `webui/frontend/src/pages/ChatPage.tsx` | queue path + status banner + composer |
| `webui/frontend/src/index.css` | `.os-conn-status` chrome |
| `webui/frontend/src/pages/__tests__/ChatComposerResilience.test.tsx` | Behaviour spec of record (vitest) |

## Test map

- `tests/unit/test_req845_composer_resilience.py` — source-lock (this REQ).
- `ChatComposerResilience.test.tsx` (vitest) — offline queue + editable composer.