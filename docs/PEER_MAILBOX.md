# Peer mailbox (`list_agents` / `send_message`)

REQ-153 / [#561](https://github.com/matthewhand/open-swarm/issues/561). Graph ADR: [ADR-009](./adr/009-peer-mailbox.md).

This is **not** an openai-agents handoff graph ([REQ-156](./examples/openai-agents-handoff-graphs/README.md)). Handoff enforces a programmed topology. The mailbox lets an **API** agent **list peers** and **send a message** into another API agent’s chat transcript so the user can say “ask X to do Y” without copy-paste.

## Who gets the tools

Eligible in v1: **API-kind** agents (including Support). CLI, remote, and herdr do not get these tools yet.

| Caller | `list_agents` / `send_message` scope |
|--------|--------------------------------------|
| API agent on a team | Other **API** members of that team |
| API agent + relationship edge (team↔agent or team↔team) | Same-kind members across that edge |
| Support / CoS | All same-kind catalogued peers (allow-all) |
| Unteamed, non-Support API agent | Empty (no global roster dump) |

Hidden Bots are omitted and `send_message` fails with `target_hidden`. Archived seats fail with `target_archived` (REQ-154 `archive_agent` stamps the catalog flag that feeds this). Unknown ids, kind mismatch, and out-of-graph targets return those error codes.

## Delivery

`send_message(agent_id, content)` appends a **user** turn on the target’s `chat_store` thread (`name` = sender) plus hop chrome `Message from {sender}`. Scoped to the caller’s user key (no cross-tenant). Opening that agent in Chat shows the message.

Tool logs run through `redact_sensitive_data`. Key-shaped payloads are not stored raw.

## ACL (REQ-162 / #573)

Effective discoverability = team ∪ edges ∩ (whitelist / ¬blacklist), with Support/CoS default **whitelist everything** (allow-all). Mode is XOR: a caller is either on a whitelist or a blacklist, toggled in the Agent Editor.

**Entry kinds** (documented on `GET /v1/mailbox-acl/` and in the editor):

| Kind | Matches |
|------|---------|
| `agent` | One catalogued rail / roster agent id |
| `team` | Every member of that composition roster |
| `role` | Every peer whose canonical role matches (`support`, `gate`, `skeptic`, `chief_of_staff`, `engineer`, `suggestions`, `default`) |
| `section` | Every member of that CoS rail section (Issue #219 `set_talk_acl` / `create_section`) |

Per-agent overrides beat per-role policies. Empty blacklist = no extra cut. Empty whitelist = nobody, except Support/CoS allow-all. `list_agents` and `send_message` both apply the effective ACL.

## Section lock (Issue #163)

A custom rail section marked **internal-only** further cuts discoverability to
members of that section (including a team of one). Unassigned cannot be
locked. Unlock restores the team+ACL reach above. CoS/Support allow-all does
**not** bypass a locked section. SPA chrome persists the flag on
`swarm_rail_sections`; chat turns snapshot it as `params.rail_sections`.
Denied sends return `section_internal_only`. See
[ISSUE-163-section-internal-talk.md](./qa/ISSUE-163-section-internal-talk.md).

## Code

`swarm.core.agent_mailbox`, `swarm.core.agent_relationships` (`agent_relationships.json`), `swarm.core.agent_mailbox_acl` (`agent_mailbox_acl.json`) next to `team_rosters.json`. Agent Editor + `/v1/mailbox-acl/`. GitHub-only docs. No Neon. No secrets.
