# REQ-66 — Scale-out rail: stacked avatars + session picker

**Status:** this PR — in flight (#394)

## Intent

When an agent runs multiple sessions (New chat per task / scale-out, #393),
the sidepane stays one row with stacked avatars. Clicking it opens a
search-style popup of that agent’s sessions (live and finished) so the user
can pick one.

## Success

1. A scale-out agent is **one row** in the rail, not N rows. Show stacked
   avatars (same treatment as consolidated inter-bot hop avatars) with a
   **max of 3** faces plus a remainder if needed (e.g. +N). The sidepane must
   not grow one row per session.
2. Clicking that row opens a popup modeled on the **search palette** (same
   chrome: list, keyboard, filter box), **pre-filtered** to this agent’s
   sessions only.
3. The list includes **running** sessions and **older finished** sessions for
   that agent. Clicking a row opens that session in the main chat (chat stays
   mounted).
4. Empty: “no sessions yet”. Search/filter inside the popup filters that
   agent’s sessions by title/snippet.
5. Agents with the scale-out toggle **off** keep today’s single-session row
   (no stack, no picker unless they somehow have history worth showing —
   v1: picker only when session count > 1).
6. Tests: 4 concurrent sessions → 3 stacked avatars + remainder, still one
   rail row; popup lists all 4 plus a finished fixture; filter narrows; click
   selects that session id.
7. **Every** avatar in the scale-out stack is animated, not only the currently
   working one. Stagger animation phase by session `startedAt` so they do not
   pulse in lockstep. Same motion language (`os-scale-out-pulse`, 1.4s).
   Tests: 4 stacked faces, different `started_at` → different `animation-delay`.

## Constraints

- Builds on #393 (new chat per task). Distinct overlay, not a new SPA page
  (#364).
- DaisyUI 5, React 18. Native list; reuse search-palette patterns from merged
  chrome where they exist.
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- Do not fold into PR 344.
- No Neon. No secrets.
- One Cursor cloud. PR must say `Fixes` this issue.
- Shared widget: `AvatarStack` + `lib/avatarStack.ts` (max 3 + remainder).
  REQ-68 (#398) should import that stack for teams/remotes. This PR does
  **not** implement team/remote stacking.

## Owner

- CoS transcribes
- cloud implements (this PR)
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
