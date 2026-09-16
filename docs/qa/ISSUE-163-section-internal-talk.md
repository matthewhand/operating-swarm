# Issue #163 — Section internal-only talk (lock)

Issue: #`163`.

**Intent:** When agents share a sidebar section, operators can mark that
section **internal-only** (lock) so members may talk only among themselves —
not to agents outside the section — including a team of one.

SPA rail sections stay the chrome SoT (`localStorage.swarm_rail_sections`,
REQ-209). This slice adds an `internalOnly` flag on custom sections, a
lock/unlock control, and the same rule in `swarm.core.section_talk` so peer
mailbox `list_agents` / `send_message` can enforce it. Chat turns snapshot
the flag as `params.rail_sections` (only when a section is locked) — not a
second JSON store, not mailbox ACL dual-write.

Unassigned is never lockable. Unlock restores normal mailbox / team reach.
CoS/Support allow-all does **not** bypass a locked section.

Does not change Operating Swarm branding. No LiteLLM catalog. No Neon. No
secrets.

## Success (this PR)

1. **Chrome** — custom section headers show a lock control: **Talk internal
   only** vs **Talk externally** (locked vs unlocked). The section menu
   mirrors the same toggle.
2. **Persist** — `internalOnly` is stored on the section in
   `swarm_rail_sections`. Remount keeps the lock.
3. **Talk discipline** — members of a locked section may `list_agents` /
   `send_message` only to other members of that section. Outbound to
   non-members is denied (`section_internal_only`) with an honest tool
   error. Inbound from outsiders is also denied. A locked section of one
   agent talks to nobody else; unlock restores reach.
4. **Prove** — unit tests for the rule + vitest for persist/chrome +
   mailbox tests. No screenshots. No secrets.

## Prove recipe (host CLI)

From a clean checkout of this branch:

```bash
uv run pytest tests/core/test_section_talk.py tests/core/test_agent_mailbox.py tests/unit/test_issue163_section_internal_talk.py -q
cd webui/frontend && npx vitest run src/lib/__tests__/railSections.test.ts src/lib/__tests__/railContextMenu.test.ts src/components/__tests__/RailSections.test.tsx
```

Expected: pytest and vitest green. No API token, no Neon, no LiteLLM catalog
edit.

## Not in this slice

- Django prefs sync for rail sections (#540).
- Dual-write into `agent_mailbox_acl.json`.
- Unassigned lock (Unassigned is not a team).
- Operating Swarm rebrand copy.

Fixes #163.
