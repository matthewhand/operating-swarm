# REQ-14 — Chat JSON persist + Settings retention

**Status:** PR [319](https://github.com/matthewhand/open-swarm/pull/319) **merged** `4d554ea5`

## Intent

Each agent chat thread persists so switching agents or reloading Chat restores
that agent’s context. Retention lives on **Settings only** — not in Grok-Bot
Chat chrome.

## Success

- Source of truth is **JSON on disk** (`$SWARM_CHAT_DIR/active/<user>/<agent>.json`; trash beside it). Django DB remains a consumer mirror.
- Reload / agent switch restores that agent’s thread. Default max age **90** days (`SWARM_CHAT_MAX_AGE_DAYS`); `0` disables auto-archive. Auto-archive moves to trash; empty trash is a **manual** Settings action.
- Settings-only: counts, disk use, per-chat Move to trash / Restore, Move all / Empty trash.
- Chat chrome unchanged aside from silent restore — no history sidebar, no archive/delete controls in chat.

## Constraints

- Not markdown session logs (`SessionLogger` stays unused by SPA Chat).
- Grok chrome is **not on `:8001` yet** — do not put retention UI there.
- No Neon. No oracle. **This filing PR is docs-only** (319 already merged; do not re-implement).

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
