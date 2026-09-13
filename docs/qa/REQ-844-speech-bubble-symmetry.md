# REQ-844 — Speech-bubble tails stay visible and symmetric (#166)

> Default chat transcript keeps the DaisyUI speech-bubble tail on **both**
> sides — assistant bottom-left, user bottom-right — with **equal inline
> room** so neither tail is clipped, flattened, or swallowed by the gutter.
> Retro-fitted requirement + source-lock for the shipped fix.

**As-of:** branch `fix/149-cli-first-discovered-defaults` (dirty; feature shipped
in-session under #166).

**Issue:** [#166](https://github.com/matthewhand/open-swarm/issues/166)

## Requirement

1. The default bubble theme is `speech` (`webui/frontend/src/lib/bubbleTheme.ts`).
2. The transcript reserves equal inline padding on both sides — at least one
   tail width (`>= 0.75rem`) — so a complete tail fits at either edge.
3. Assistant and user bubbles share one mirrored tail rule
   (`.chat-start .chat-bubble::before` / `.chat-end .chat-bubble::before`),
   so left and right tails are the same shape, not two divergent styles.
4. The equal-room gutter survives the `sm` breakpoint.

## Acceptance criteria

- [x] `DEFAULT_BUBBLE_THEME` is `'speech'`.
- [x] Base `.os-chat-transcript` rule has equal `padding-left` / `padding-right`.
- [x] Shared mirrored `::before` tail selector present for both chat sides.
- [x] `@media (min-width: 640px)` keeps the equal gutters.

## Locked sources

| File | Role |
|------|------|
| `webui/frontend/src/lib/bubbleTheme.ts` | `speech` default + theme enum |
| `webui/frontend/src/index.css` | `.os-chat-transcript` padding + mirrored tail rules |
| `webui/frontend/src/lib/__tests__/speechBubbleTails.test.ts` | Behaviour spec of record (vitest) |

## Test map

- `tests/unit/test_req844_speech_bubble_symmetry.py` — source-lock (this REQ).
- `webui/frontend/src/lib/__tests__/speechBubbleTails.test.ts` — numeric behaviour.