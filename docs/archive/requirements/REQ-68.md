# REQ-68 — Stacked avatars for teams and remotes

**Status:** this PR — in flight (Fixes #398)

## Intent

A remote (especially OpenMousBot, which may be a CoS plus several agents) and a
local team should look like scale-out: one rail row with stacked avatars of the
**3 most recent** working members, animated so you can see the CoS tasking
others without exploding the sidepane.

## Success

1. Reuse the shared stacked-avatar widget (`AvatarStack` + `avatarStack.ts`) —
   max 3 faces + remainder. One row per team or per configured remote, not one
   row per member. **#394 should import this widget** rather than rewrite it.
   PR #394 had not landed when this shipped, so the widget lives here.
2. **Local team:** stack shows the 3 most recently active members (including
   CoS). Talking to the team is talking to its CoS; other faces appear as they
   are tasked. Click opens the #394-style session picker filtered to that team.
3. **Remote (OpenMousBot / Hermes / Rakazo / nested swarm):** if the remote
   reports multiple bots/agents (or a CoS + workers), stack those the same way.
   Label is **OpenMousBot**, not OMB. A single-agent remote stays one avatar
   (no stack).
4. **Every** avatar in the team/remote stack is animated (not only the
   currently working face). Stagger `animation-delay` from `started_at` so the
   stack does not pulse in lockstep. Same motion language as the working-agent
   pulse.
5. Clicking the row uses the search-palette picker (`SessionPicker`), listing
   that team’s or remote’s member sessions (running + finished).
6. Tests: team of 5 → 3 stacked + remainder; remote with 1 agent → no stack;
   3 faces have distinct `animation-delay` from `started_at`; click opens the
   filtered picker.

## Constraints

- Builds on #394 and #393. Compatible with remotes opt-in (#384). DaisyUI 5,
  React 18. Chat stays mounted.
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- Do not fold into PR 344. Do not rewrite #394’s PR.
- GET `/v1/remotes/` list only — no health/operate, no live LAN, no Neon, no
  secrets.
- One Cursor cloud. PR must say `Fixes` this issue.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` — guest dirty only
