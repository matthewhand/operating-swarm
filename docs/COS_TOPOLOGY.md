# CoS first-class agents + section topology (Issue #219)

Issue: [#219](https://github.com/matthewhand/open-swarm-private/issues/219).
Pairs with Support/CoS lifecycle [REQ-154](./AGENT_LIFECYCLE.md) and mailbox ACL
[REQ-162](./PEER_MAILBOX.md).

TrueForge treats agents as second-class: its `create_subagent` tool only makes
**temporary** agents that die with the session. In Open Swarm a
`chief_of_staff` seat is a first-class operator:

* **Create real agents** — REQ-154 already ships `create_agent` /
  `archive_agent` / `restore_agent` / `list_archived_agents` for Support and
  API CoS. Created seats are persistent (own config, mailbox, role, kind).
* **Manage the comms topology** — CoS tools create/reshape **sections** and
  write talk ACL, composing teams by conversation (the OpenMousBot pattern).

No Neon. No secrets. No live demo-port seed.

## Who gets the tools

v1 tools attach on **API-kind** Chat / `/v1/chat/completions` runs.

| Caller | Lifecycle (REQ-154) | Section / talk ACL (this issue) |
|--------|---------------------|----------------------------------|
| **Support** | Yes | No — Support stays the onboarder, not the topology editor |
| **CoS** on an **API** seat | Yes | Yes — `create_section` / `rename_section` / `archive_section` / `move_agent_to_section` / `set_talk_acl` / `list_sections` |
| **CoS** on a **CLI** seat | No | No — CLI harness does not attach function tools in v1 |
| **Everyone else** | No | No |

Tools attach through `ChiefOfStaffRole.attach_as_tool` (Issue #206 Phase 3),
not ad-hoc blueprint wiring.

## Sections

`create_section(name, agent_ids="", internal_only=false)` writes
`agent_sections.json` next to `agent_mailbox_acl.json`.

| Tool | Effect |
|------|--------|
| `create_section` | Persistent custom rail section (`sec_…`). Optional comma-separated `agent_ids` join it. |
| `rename_section` | Rename. Unassigned cannot be renamed this way. |
| `archive_section` | Soft-hide. Members return to Unassigned. Unassigned itself is protected. |
| `move_agent_to_section` | Rail regroup. `section_id=unassigned` drops membership. |
| `list_sections` | Active sections + member ids. |

Unknown agent or section ids fail with `unknown_id` / `unknown_section`. No
silent no-ops.

## Talk ACL

`set_talk_acl(agent_id, allow="", deny="")` writes `agent_mailbox_acl` (the
store `resolve_acl_policy` already consumes). Mode is XOR: pass **allow**
(whitelist) or **deny** (blacklist), never both.

Entries:

| Token | Matches |
|-------|---------|
| agent id | That catalogued rail / roster seat |
| section id | Every member of that section |
| `team` | Every member of the target agent's roster(s) |

CoS (and Support) keep their default **allow-all** mailbox policy for
themselves via `default_policy_for_role`.

## NL path

"put the two skeptics in a locked review section" is one tool call:

```text
create_section(name="locked review", agent_ids="skeptic_a,skeptic_b", internal_only=true)
```

That creates the section, moves the agents, and writes each member a
whitelist of `{kind: section, id: <section>}`.

## Code

`swarm.core.cos_topology`, `swarm.core.agent_sections`. Wired next to
lifecycle on Chat WS + completions via `ChiefOfStaffRole`. Tests:
`tests/core/test_cos_topology.py`, `tests/core/test_agent_sections.py`,
`tests/unit/test_issue219_cos_topology.py`. Own-diff CI:
`.github/workflows/issue219-cos-topology.yml`.
