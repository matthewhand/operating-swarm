# Team isolation and teams-of-teams (REQ-28)

Composition **Teams** (rosters in `team_rosters.json`, not `/v1/teams`
LLM-profile aliases) cannot talk across team boundaries by default.

## Choice: parent talks to the child as one member

**Parent talks to the child team as one member** (send-to-all on the child),
**not** automatically every grandchild.

| Caller | Target | Result |
|---|---|---|
| Member of Team A | Team B (sibling) or B's people | **Deny** |
| Member of Team A | Child team C (`kind=team`, `team_id=C` on A's roster) | **Allow** — consult/handoff is send-to-all on C's *direct* members |
| Member of Team A | A person on C, or grandchild team D | **Deny** |
| `chief_of_staff` (`cos`, `chief`) | Any team id | **Allow** — CoS bypasses isolation |

Send-to-all on the child includes that child's people (`api` / `cli` /
`remote` / `herdr`) and any nested `kind=team` slot **as a team id**. It does
not expand grandchildren into individual seats.

## Roles

| Role | Aliases | Badge (REQ-67: badge only, no row fill/border) |
|---|---|---|
| `default` | worker, agent | no badge |
| `support` | helper | teal |
| `gate` | tool_gate | amber |
| `skeptic` | reviewer | violet |
| `chief_of_staff` | cos, chief | ice-steel (`#4f8ec9`) — not support/gate/skeptic |

Hover-edit of a CoS blueprint is a later REQ. This slice shows the **CoS** badge.

## Persist

`team_rosters` / `agent_team` members:

```json
{ "id": "research", "kind": "team", "team_id": "research", "role": "default", "source": "team:research" }
```

`kind`: `api` | `cli` | `remote` | `team` | `herdr`.

## Tools

Default: **no** cross-team consult tools. A parent only receives consult +
handoff for each **direct child** team id. CoS receives consult + handoff for
**every** team id. Isolation is re-checked when the tool runs.

Code: `swarm.core.agent_roles`, `swarm.core.team_rosters`,
`swarm.core.team_isolation`, `swarm.core.team_consult`.

Peer mailbox (`list_agents` / `send_message`, REQ-153) is a **different**
channel: same-kind API tools, team-scoped plus relationship edges. CoS/Support
are allow-all same-kind on that graph, then REQ-162 whitelist/blacklist ACL
applies. A locked rail section (Issue #163) further restricts mailbox talk to
members of that section; CoS/Support allow-all does not bypass it. See
[ADR-009](./adr/009-peer-mailbox.md) and
[ISSUE-163-section-internal-talk.md](./qa/ISSUE-163-section-internal-talk.md).
