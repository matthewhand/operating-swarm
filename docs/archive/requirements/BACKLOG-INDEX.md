# Open Swarm REQ backlog (archived)

> **Historical.** This index is not the REQ source of truth. GitHub Issues
> are. Live pointers: [../../requirements/](../../requirements/).
>
> The body below is the former transcript index (stale “in flight” rows and a
> guest live-preview host). Do not treat it as current guidance.

> **This is docs-only.** These pages transcribe the tracked REQ backlog. They
> do not implement features, do not enable Neon, and do not resume oracle.

One markdown file per REQ (REQ-18/25 is one combined page). Do not invent
extra REQs here — only items already tracked in the product chat.

## Template

Every REQ page uses this shape:

| Section | What it holds |
|---|---|
| **Status** | PR number / merged / in flight |
| **Intent** | Why this exists |
| **Success** | What “done” looks like |
| **Constraints** | What must not happen |
| **Owner** | Who does what |

## Owner (same on every REQ)

- **CoS** transcribes
- **cloud** implements
- **engineer** GitHub-merge after skeptic
- **live preview** `198.51.100.30:8001` — guest dirty only

## Honesty (read before acting)

| Claim | Reality |
|---|---|
| Teams | **Live today are LLM-profile aliases** (`/teams/` + `/v1/teams` + `teams.json`). Not a multi-agent roster. Intended composition is a later REQ. |
| Grok-Bot chrome | Landed on `main` as PR 322 (`d926cdb4`). REQ-5 dark chrome ≠ the left-rail Bot product (REQ-16). |
| Neon / oracle | **Off.** Do not enable Neon. Do not resume oracle. |
| `/agents` | Agent Router (typed starters). Grok-Bot owns `/` + `/chat`. Do not alias `/agents` → `/chat`. |

In-flight PRs sit on their own branches. This tree does not include their code
until squash-merged.

## Index

| REQ | Title | Status |
|---|---|---|
| [REQ-7](./REQ-7.md) | Support agent (pill, threads, question cards) | PR 313 — merged |
| [REQ-8](./REQ-8.md) | UX tighten (theme icon, unlabeled dropdowns, toast, hide popup) | PR 312 — in flight |
| [REQ-9](./REQ-9.md) | gate + skeptic roles as-tool | PR 314 — in flight |
| [REQ-10](./REQ-10.md) | Favourites tile grid (left rail, not top chrome) | PR 311 — in flight |
| [REQ-11](./REQ-11.md) | Remotes Hermes / OMB / Rakazo | PR 318 — in flight |
| [REQ-12](./REQ-12.md) | Harness-of-harnesses docs | PR 315 — in flight |
| [REQ-13](./REQ-13.md) | Mock inference fast + >60s | PR 317 — in flight |
| [REQ-14](./REQ-14.md) | Chat JSON persist + Settings retention | PR 319 **merged** `4d554ea5` |
| [REQ-15](./REQ-15.md) | CLI dropdown lists CLIs | PR 316 — in flight |
| [REQ-16](./REQ-16.md) | Grok-Bot left rail chrome | PR 322 **merged** `d926cdb4` |
| [REQ-17](./REQ-17.md) | Search command palette | inside PR 322 — merged |
| [REQ-18/25](./REQ-18-25.md) | Support Socratic+MCQ (into 313); hover-edit role → blueprint Python | absorbed / in flight |
| [REQ-19](./REQ-19.md) | DaisyUI settings sheet `modal-end` + Menu + Join | PR 320 — in flight |
| [REQ-20](./REQ-20.md) | Teams composition roster DnD (not LLM aliases) | PR 323 — in flight |
| [REQ-21](./REQ-21.md) | Herdr client localhost default + optional `--remote` | in flight |
| [REQ-23](./REQ-23.md) | Teams in sidepane + send-to-all dropdown | in flight |
| [REQ-24](./REQ-24.md) | Drag any agent incl. roles into Hidden drop zone | in flight |
| [REQ-26](./REQ-26.md) | First load hide gate and skeptic | in flight |
| [REQ-28](./REQ-28.md) | Chief of Staff + team isolation + teams-of-teams | merged (#345) |
| [REQ-37](./REQ-37.md) | Nested conversation compact / summaries | merged (#365) |
| [REQ-42](./REQ-42.md) | Role badge → explained Settings pane + LLM summary | in flight |
| [REQ-43](./REQ-43.md) | Settings default LLM + per-task override | this PR — #358 |
| [REQ-28](./REQ-28.md) | Chief of Staff + team isolation + teams-of-teams | this PR |
| [REQ-37](./REQ-37.md) | Nested conversation compact / summaries | in flight (#350) |
| [REQ-68](./REQ-68.md) | Stacked avatars for teams and remotes | this PR (#398) |
| [REQ-58](./REQ-58.md) | Agent editor is agent-scoped; Blueprint is a picker | merged (#382) |
| [REQ-65](./REQ-65.md) | Agent setting — new chat per task | merged (#393) |
| [REQ-67](./REQ-67.md) | Role chrome is the badge only — no row fill/border | merged (#396) |
| [REQ-66](./REQ-66.md) | Scale-out rail — stacked avatars + session picker | merged (#394) |
| [REQ-52](./REQ-52.md) | Persist CLI session ids and resume them | in flight (#369) |
| [REQ-57](./REQ-57.md) | Nest open-swarm as a remotes kind | in flight (#380) |
| [REQ-59](./REQ-59.md) | Remotes opt-in catalog — empty until +, OpenMousBot not OMB | in flight (#384) |
| [REQ-106](./REQ-106.md) | Bee brand mark — SVG favicon + multi-size app icons | this PR (#470) |

REQ-22 (debt audits) and earlier REQ-5 / REQ-6 chrome/avatar work are **not**
filed here — they were not in this backlog slice.

---

## Operator / Agent Router track (PR 321)

A second numbering (REQ-1…15) was captured on the Agent Router branch **before**
this backlog used the same IDs. Those pages stay under
[operator/](./operator/) plus [REQ-1](REQ-1.md)–[REQ-6](REQ-6.md) (no collision).
Do not overwrite this index with that numbering.

| ID | Title |
|---|---|
| [REQ-1](REQ-1.md) | Typed agents: api / cli / remote |
| [REQ-2](REQ-2.md) | Default LiteLLM, LAN, global + per-agent override |
| [REQ-3](REQ-3.md) | Operator UX: source, teams, favourites, compact chat, `/chat` sockets |
| [REQ-4](REQ-4.md) | Builder + skeptic / custom CoS+engineer+skeptic (separate track) |
| [REQ-5](REQ-5.md) | OMB-style dark chrome (historical, landed) |
| [REQ-6](REQ-6.md) | Hide all, keep typed starters |
| [operator/REQ-7](operator/REQ-7.md) | Hermes + DeepSeek Harness remotes, Ollama/npx DSH launch |
| [operator/REQ-8](operator/REQ-8.md) | Agents primary tab; More popup for the rest |
| [operator/REQ-9](operator/REQ-9.md) | Default empty-chat quickstarts |
| [operator/REQ-10](operator/REQ-10.md) | Per-agent Gen quickstarts from name + system prompt |
| [operator/REQ-11](operator/REQ-11.md) | Agent-assisted BlueprintBase Python class from the interface spec |
| [operator/REQ-12](operator/REQ-12.md) | Shift+Tab: plan / auto-edit / default (always-approve via CLI catalog) |
| [operator/REQ-13](operator/REQ-13.md) | Dev-mode LAN auth-free login including websockets |
| [operator/REQ-14](operator/REQ-14.md) | Sidebar groups by api / cli / remote; type-gated header extras |
| [operator/REQ-15](operator/REQ-15.md) | Support agent: highlighted default, briefing, Python code blocks |
