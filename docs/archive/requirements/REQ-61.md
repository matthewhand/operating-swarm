# REQ-61 — Hermes remote — add, list, send (kind complete)

**Status:** in flight (GitHub #387)

## Intent

Hermes is a complete remote kind: after the user + adds it, Settings can
health / list / send through Hermes’ API. No Hermes UI is shown until added
(see [REQ-59](https://github.com/matthewhand/open-swarm/issues/384)).

## Success

1. Kind id `hermes`. After add (base URL + api-key-env name only), Settings
   shows that one remote: health, list, send.
2. List uses Hermes session/job/model list as already documented in
   [`docs/REMOTE_HARNESSES.md`](../REMOTE_HARNESSES.md). Send uses the
   documented run/jobs path (`POST /v1/runs`).
3. DOWN is a report, not a crash. Timeout, no retries-as-exception.
4. Tests: stub HTTP for health/list/send; missing remote is empty not a
   default card. No live LAN calls in CI.
5. Do not bounce Hermes. Do not delete `SKILL.md`. Do not commit tokens or
   live URLs.

## Constraints

- Compatible with #384 (opt-in) and #380 (swarm as another kind). Reuse
  `src/swarm/core/remotes.py` / Herdr client — no second stack.
- GitHub-only. No `:8001`. No Neon. No secrets. No Fly open-litellm URLs.
- One Cursor cloud. `Fixes` this issue. Do not fold into 344.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
