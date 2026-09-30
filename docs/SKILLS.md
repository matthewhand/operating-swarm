# Skills (SKILL.md)

Reusable, named capabilities. Format follows Anthropic's
[Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
open standard: a directory containing `SKILL.md` (YAML frontmatter `name` +
`description`, plus a markdown body of instructions) and optional bundled
assets (scripts, templates).

Related: [SKILLS_AND_CONSENSUS_WALKTHROUGH](./SKILLS_AND_CONSENSUS_WALKTHROUGH.md),
[CLI_FUSION](./CLI_FUSION.md#skills--reusable-capabilities-portable-across-clis),
[ADR-006 API vs Blueprint](./adr/006-api-vs-blueprint-kinds.md) (#652).

## Discovery path

Default roots: `<project_root>/skills` (bundled) and
`get_user_data_dir_for_swarm()/skills` (installed packs, overlay).

Marketplace browse/install (REQ-887) uses this same Agent Skills format —
see [MARKETPLACE.md](./MARKETPLACE.md). Do not invent a parallel schema.

A skill is **any directory** that holds a `SKILL.md`. The walker is
`swarm.core.skills.discover_skills()` (`src/swarm/core/skills.py`):

1. Resolve `skills_root()` → `Path(get_project_root_dir()) / "skills"`.
2. `rglob("SKILL.md")` (sorted, first-wins on name).
3. Parse frontmatter; skip malformed files (never raise).
4. Optional override: `swarm-cli skills --dir <path>`.

Bundled examples live at repo-root `skills/<name>/SKILL.md`
(`conventional-commit`, `counting-lines`, `reviewing-code`,
`writing-changelog`, `support-session-ownership`, `self-update-pr`,
`orca-cli`).

The MIT TeamAI template (#1366) is vendored in the same catalog:
`skills/ecc/` and `skills/mattpocock/` keep their upstream skill names, and
`skills/teamai-baseline/` is the shared rules fragment. Reviewer seats are
the `code_reviewer` (skeptic), `security_reviewer` (gate), and
`database_reviewer` (engineer) blueprints. `teamai-cli` is not a seat.
`swarm-cli teamai-import <repo>` copies a TeamAI checkout into a skills
directory without executing it. Notices: `packs/teamai/ATTRIBUTION.md`.

List/detail over HTTP:

- `GET /v1/skills/` — `{object: list, data: [{name, id, description, path, assets}]}`
- `GET /v1/skills/<name>/` — same plus `instructions`. Missing name → **404**
  with `{found: false, error: "..."}` (honest; no invented body).
- `GET /v1/config-options/` still embeds the catalog (now includes `id` + `path`).

`path` is the repo-relative `skills/<name>/SKILL.md` string used as the chip
source id.

## Per-agent CRUD + pack (#1392)

Each seat has a prose skill list plus optional `gettingStarted.skill`.
Skills are name / description / instructions — no binaries, assets, or
secrets. The SPA editor is #1393.

- `GET/POST /v1/agents/<id>/skills/` — list or create. POST `{name, description, instructions}` authors a skill; POST `{name}` / `{attach}` copies a library `SKILL.md` onto the seat.
- `GET/PATCH/DELETE /v1/agents/<id>/skills/<name>/` — one attached skill.
- `PATCH /v1/agents/<id>/skills/` with `{gettingStarted: {skill}}` — must name an attached skill.
- `POST /v1/agents/<id>/pack/` — pack selected (or all attached) skills as prose. Body may name `skills` and `gettingStarted`. **`gettingStarted.skill` must name a packed skill** or validation fails.
- `POST /v1/agents/<id>/pack/import/` — recreate those skills on the seat and mark `gettingStarted` for first-run (applied on the next turn).
- `POST /v1/agent-packs/validate/` — same validation, no write.

Pack JSON::

    {
      "object": "agent_pack",
      "kind": "swarm-agent-pack",
      "skills": [{"name": "welcome-tour", "description": "…", "instructions": "…"}],
      "gettingStarted": {"skill": "welcome-tour"}
    }

## SPA editor + export picker (#1393)

Agent editor (Model & inference) consumes the #1392 APIs:

- List / create / edit / delete prose skills. The description field is labeled
  **When to use**.
- Attach a library `SKILL.md` (POST `{attach}`).
- Export picker: multi-select skills + gettingStarted. **gettingStarted must
  name a selected skill** or Export stays disabled (same backend rule).
- Import pack JSON recreates skills and marks gettingStarted for first-run.
  The next empty chat surfaces that skill (when-to-use chip). Backend applies
  it on the first turn.

## Attach (one or more)

Params on `/v1/chat/completions` and the chat websocket:

| Param | Shape | Meaning |
|-------|--------|---------|
| `skill` | string | One skill name (existing `cli_agent` form). |
| `skills` | string[] | One or more names. Merged with `skill`, de-duplicated, order preserved. |

Unknown names are skipped and reported (`_Skill \`name\` not found — running without it._`).
The turn still runs.

**CLI:** `cli_agent` applies skills itself (prepend instructions, stage assets).

**Today's API seats (Blueprint-backed):** the consumer / chat-completions path
applies `skill` / `skills` to the last user message before the recipe runs
(`swarm.core.skill_attach`). That includes `api_agent` → `chatbot` and other
non-CLI recipes. The WebUI agent editor persists attached names on the seat
(`localStorage` agent edits) and the composer `/skill <name>` slash item adds
them for that turn.

**Support** still hard-attaches `support-session-ownership` on every turn.

## Kinds (#652 / ADR-006)

| Kind (target) | Skills today |
|---------------|----------------|
| **CLI** | Yes — `cli_agent` `skill=` / `skills=`. |
| **Blueprint** (today's stored `api` seats) | Yes — same params; applied on the Blueprint run path. |
| **API** (true inference-only seat) | **N/A until ADR-006 Phase 2.** Those seats do not exist on `main`. When they land, skill attach stays on Blueprint-backed seats unless a follow-up adds an inference-client hook. Do not treat a LiteLLM profile as a skill host. |
| **Remote** | Not attached here. |

Until Phase 1/2, UI copy still says “API” for Blueprint-backed seats. REQ-212
attaches skills to **that** bucket, not to a future bare inference client.

## Chat chips + popup

Chat renders `/skill <name>`, `skills/<name>/SKILL.md`, and `skill:<name>` as
an inline chip (not bare path-only text). Click opens a dismissible card:
name, short description, source path/id, Instructions preview. Missing /
unloadable skills show **Missing** on the chip and an honest error in the card.
The popup does not navigate away from the thread.

View-only in this slice (no Publish / Delete).
