# REQ-846 — Team dropdown defaults to CoS / first member (private #169)

> When a team is selected, the talk-to-member dropdown **defaults** to the
> configured Chief of Staff (`cos` / `chief_of_staff`) and otherwise to the
> team's first member — so the control shows a real member label instead of a
> vague "Pick a …" placeholder. Retro-fitted requirement + source-lock for the
> shipped fix. Builds on REQ-130 (talk-to-session defaulting).

**As-of:** branch `fix/149-cli-first-discovered-defaults` (dirty; feature shipped
in-session under #169).

**Issue:** [private #169](https://github.com/matthewhand/open-swarm-private/issues/169)

## Requirement

1. `defaultSessionForTeam(team)` prefers the member whose id/role/title marks
   them Chief of Staff, then falls back to `sessions[0]`, else `null`.
2. On team selection, `ChatPage` sets `memberTarget` to that default
   (`?? ALL_MEMBERS_TARGET` when the team has no members) — once per team via
   `teamDefaultedRef`, without clobbering an explicit URL `?team=`.
3. The dropdown therefore opens pre-selected with a member label (e.g. the
   CoS's name), not a generic prompt.

## Acceptance criteria

- [x] `defaultSessionForTeam` exported from `sessionPicker.ts` with cos-first
      ordering and `return cos || sessions[0] || null`.
- [x] `ChatPage` wires it: `defaultSessionForTeam(selectedTeam)?.memberId ??
      ALL_MEMBERS_TARGET` behind `teamDefaultedRef`.

## Locked sources

| File | Role |
|------|------|
| `webui/frontend/src/lib/sessionPicker.ts` | `defaultSessionForTeam` |
| `webui/frontend/src/pages/ChatPage.tsx` | team-select defaulting + dropdown |

## Test map

- `tests/unit/test_req846_team_default_session.py` — source-lock (this REQ).
- `webui/frontend/src/pages/__tests__/ChatPage.test.tsx` (vitest) — defaulting behaviour.