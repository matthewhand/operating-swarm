# REQ-13 — Mock inference fast + >60s

**Status:** PR [317](https://github.com/matthewhand/open-swarm/pull/317) — in flight

## Intent

TDD for the SPA chat **Send** path with **MOCK inference** — prove both a fast
reply and a >60s reply without live LiteLLM / Qwen / Fly.

## Success

1. User types a message, clicks **Send**, the conversation log shows a canned assistant reply.
2. **FAST** mock: reply well under 60s (wall clock from Send, e.g. under 2s).
3. **SLOW** mock: assistant frames scheduled at **61s**. Playwright `page.clock` fast-forwards — still no reply at 59s, reply appears after +2s. No false timeout, no stuck Send, no silent drop.
4. Tests fail if mock strings never render.

## Constraints

- No live LiteLLM / Qwen / Fly. No oracle / Neon. No Grok-Bot chrome. No Hide-all.
- After REQ-8 (PR 312) removes standing Connected, FAST/SLOW waits must target composer-ready / enabled Send / conversation log — **not** a Connected badge. Do not reintroduce Connected.
- Docs-only on this PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
