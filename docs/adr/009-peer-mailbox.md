# ADR-009: Peer mailbox — team graph, not a global mesh

- **Status:** Accepted for v1 runtime (2026-09-05)
- **Date:** 2026-09-05
- **Issue:** [#561](https://github.com/matthewhand/open-swarm/issues/561) (REQ-153)
- **Related:** [#573](https://github.com/matthewhand/open-swarm/issues/573) (REQ-162 ACL UI), [#475](https://github.com/matthewhand/open-swarm/issues/475) / [#520](https://github.com/matthewhand/open-swarm/issues/520) (teams CoS), [TEAM_ISOLATION.md](../TEAM_ISOLATION.md) (REQ-28), [openai-agents-handoff-graphs](../examples/openai-agents-handoff-graphs/README.md) (REQ-156)
- **Supersedes:** none. Complements [ADR-005](./005-kind-bases.md) (kind bases) and [ADR-006](./006-api-vs-blueprint-kinds.md) (API vs Blueprint).

**Decision:** Inter-agent `list_agents` / `send_message` tools are a **peer mailbox**, not openai-agents handoff. v1 is **API↔API**, **team-scoped**, plus optional **relationship edges**. Do **not** dump the rail roster into every agent.

No secrets. No Neon. GitHub-only docs (no local demo-port seed).

---

## Issue quote (REQ-153)

**Intent:** User says “ask X to do Y” → agent uses tools, not the human copy-pasting between chats.

**Success (v1 — API↔API):**

1. Tools on eligible agents: `list_agents` (kind=`api`) and `send_message` (target id + content).
2. Delivered messages appear in the **target agent’s chat/transcript** with sender attribution.
3. Same-kind only (API→API). No cross-tenant leaks. No secrets in tool payloads logged raw.
4. Clear tool errors (unknown id, kind mismatch, target hidden/archived).
5. Tests for list + send + kind guard. `Fixes` this Issue.

**Visibility (Matthew 2026-09-04):** when a bot is on a **team**, list/send is **only other members of that team**. A **relationship** between team↔agent or team↔team makes members mutually discoverable across that edge — not a global mesh.

**ACL (REQ-162 / #573):** Support allow-all (same-kind); others start at team ∪ edges; per-agent or per-role **whitelist XOR blacklist**. Entries target **agent** (rail/roster id), **team** (roster id → every member), **role** (canonical role), or **section** (CoS rail section, Issue #219). Agent Editor toggles the mode and add/removes entries — no config-file hunting. Empty Support whitelist stays allow-all. CoS `set_talk_acl` writes the same store.

**Constraints:** Align with teams CoS. No Neon. No secrets in Issues.

---

## Eligible agents (v1)

| Caller | Tools | Who they can list/send |
|--------|--------|-------------------------|
| **API** kind (rail / blueprint, including Support) | `list_agents`, `send_message` | Same-kind peers in scope |
| **CLI** / **remote** / **herdr** | none | later REQ |

Support (`role=support`) and Chief of Staff (`chief_of_staff` / `cos` / `chief`) are **allow-all same-kind** so they can coordinate without a global mesh for ordinary workers. CoS alignment: REQ-28 / #475.

Unteamed, non-Support API agents see **no one** until they join a team or gain an edge.

---

## Graph model

```text
discoverable = (
    same_team_members
    ∪ relationship_edge_members
    ∪ support_or_cos_allow_all
)
effective = discoverable
    ∩ same_kind(api)
    ∩ (whitelist | ¬blacklist)
    − hidden − archived − self
```

**Team membership** lives on `team_rosters.json` (REQ-28). Nested `kind=team` slots are units for handoff; mailbox v1 lists **people** on shared rosters, not grandchildren as automatic peers (same isolation story as [TEAM_ISOLATION.md](../TEAM_ISOLATION.md)).

**Relationship edges** live on XDG `agent_relationships.json` (never `teams.json`):

```json
{
  "schema": 1,
  "edges": [
    {"from_kind": "team", "from_id": "office", "to_kind": "agent", "to_id": "ada"},
    {"from_kind": "team", "from_id": "office", "to_kind": "team", "to_id": "ops"}
  ]
}
```

Edges are **undirected**. v1 pairs: team↔agent, team↔team. Agent↔agent is reserved (would become a silent mesh).

**ACL entries** live on XDG `agent_mailbox_acl.json` (never `teams.json`): `{kind: agent|team|role, id}` plus `mode: whitelist|blacklist` per agent or role. Empty blacklist = no extra cut. Empty whitelist = nobody, except Support/CoS default **allow-all**. REST: `/v1/mailbox-acl/`.

**Hidden** = `UserPreference.hidden_agents`. **Archived** = catalog flag (`archived` + `archived_at` on custom-library / remotes rows; REQ-154 `archive_agent` feeds `catalog_archived_ids()` into this mailbox). Distinct tool errors.

**Tenant:** `send_message` writes the target thread under the caller’s `chat_store` `user_key` only.

---

## Delivery

Target transcript (JSON `chat_store`, same store Chat restores):

* user turn with `name` = sender id (model-visible attribution)
* hop chrome `Message from {sender}` (`kind=hop`, already rendered by InterBot lines)

Not a second Neon inbox. Not a local demo-port webhook.

---

## Not this ADR

* openai-agents `handoff` / `as_tool` topology (REQ-156)
* CLI↔CLI / remote↔remote / cross-kind allowlist (later)
* ACL management UI — shipped in REQ-162 / #573 (Agent Editor + `/v1/mailbox-acl/`)
* Soft-delete + ~30d purge — shipped as REQ-154 / [#562](https://github.com/matthewhand/open-swarm/issues/562) (`docs/AGENT_LIFECYCLE.md`)

---

## Code

`swarm.core.agent_mailbox`, `swarm.core.agent_relationships`, `swarm.core.agent_mailbox_acl`. Wired on Chat WS + `/v1/chat/completions` for API-kind runs. Tests: `tests/core/test_agent_mailbox.py`, `tests/core/test_agent_relationships.py`, `tests/core/test_agent_mailbox_acl.py`. Own-diff CI: `.github/workflows/req153-mailbox.yml`, `.github/workflows/req162-mailbox-acl.yml`.
