# REQ-28 — Chief of Staff role + team isolation + teams-of-teams

**Status:** this PR — in flight

> REQ-28 Chief of Staff role + team isolation + teams-of-teams. New PR from
> current main (ports are objects now).
>
> Intent: Add role `chief_of_staff` (cos). That agent may talk to any available
> team. By default teams cannot talk to other teams. Granularity is
> teams-of-teams (a team whose members include other teams).
>
> Success:
> 1. Role enum includes `chief_of_staff` (aliases: cos, chief). Distinct rail
>    look (not support/gate/skeptic colors). Hover-edit later can target its
>    blueprint; this PR at least shows the badge.
> 2. Isolation: members of Team A cannot handoff/as_tool to Team B or B's
>    members unless B is nested under A or the caller has role chief_of_staff.
> 3. Teams-of-teams: roster member kind=`team` with `team_id`. Parent team can
>    talk to child team (as a unit) and, if you choose, to child members —
>    document the choice: **parent talks to the child team as one member**
>    (send-to-all on the child), not automatically every grandchild. CoS
>    bypasses this and can target any team.
> 4. Default: no cross-team consult tools. CoS gets consult/handoff to every
>    team id. Tests for isolation deny + CoS allow + nested allow.
> 5. Persist in team_rosters / agent_team members:
>    `{id, kind: api|cli|remote|team|herdr, role, source}`.
> 6. Sidepane: CoS row looks distinct; nested team rows can nest or show a
>    team badge.
>
> Do not implement a full Grok chrome rewrite. Do not enable Neon. No guest
> auth. Quote this REQ.
> Owner: this cloud agent.

## Intent

Add role `chief_of_staff` (aliases `cos`, `chief`). That agent may talk to any
available team. By default teams cannot talk to other teams. Granularity is
teams-of-teams (a team whose members include other teams).

## Success

See the quoted REQ above. Documented parent→child choice lives in
[TEAM_ISOLATION.md](../TEAM_ISOLATION.md): **parent talks to the child team as
one member** (send-to-all on the child), not automatically every grandchild.

## Constraints

- Do not implement a full Grok chrome rewrite.
- Do not enable Neon. No guest auth.
- Django `/teams/` + `/v1/teams/` + `teams.json` stay LLM-profile aliases.
- Hover-edit of the CoS blueprint is later (REQ-25); this PR shows the badge.

## Owner

- CoS transcribes
- cloud implements (this PR)
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
