# REQ-22c — Core / Teams / Blueprint technical-debt audit

**Audit only. No production rewrite.**

> **REQ-22c:** technical debt AUDIT ONLY. Do not rewrite. Ranked list in
> final report and/or draft `docs/debt/core.md`.
>
> Scope: `src/swarm/core`, `src/swarm/blueprints`, openai-agents / MoA /
> hybrid_team / dynamic_team, CLI `swarm_cli`.
>
> Product direction: **Teams (not Blueprint) is the composition layer for
> API+CLI+remote; Blueprint stays API/python recipe.** Look for stale
> abstractions that assume API-only, unused blueprints, duplicate team/MoA
> paths, dead oracle/Neon callers, inefficient agent loops.
>
> Each finding: P0/P1/P2, path, why, action (`leave` / `wrap` / `delete`).
> Do not enable oracle or Neon. Quote this REQ.

Audited at `91dabd645d289ee539aa00bbe0721e1dc916b116`. This file is the
ranked report.

---

## How to read this

| Priority | Meaning |
|----------|---------|
| **P0** | Blocks or actively misleads the Teams-as-composition direction |
| **P1** | Real duplication, stale API-only assumption, or unsafe loop — next debt pass |
| **P2** | Dead code, husks, comments, leftover Django apps |

**Action vocabulary**

| Action | Meaning |
|--------|---------|
| **leave** | Keep as-is; do not expand; do not enable |
| **wrap** | Keep the behavior, hide it behind a Teams/core primitive, or alias it |
| **delete** | Safe to remove in a later debt PR (not this audit) |

Nothing in this document enables Oracle deploy or Neon. There are **no dead
oracle/Neon callers** in the audited Python trees; see [finding P2-1](#p2-1-no-dead-oracleneon-callers-in-scope).

---

## Product lens vs what the tree actually is

REQ-22c says Teams owns composition for **API + CLI + remote**, and Blueprint
is a **Python recipe** for the API.

Shipped vocabulary still says the opposite:

| Surface | What it is today |
|---------|------------------|
| `docs/GLOSSARY.md` | Team = `teams.json` **LLM-profile alias** via `DynamicTeamBlueprint`. “Not a multi-agent team builder.” Multi-agent work is a Blueprint / MoA / persona. |
| `docs/VISION.md` | Orchestration “exposed as **blueprints** (each is a `model` id).” |
| `src/swarm/views/teams_api.py` | Honesty docstring: team is `id` + `description` + `llm_profile`. |
| `src/swarm/core/swarm_cli.py` | Lifecycle is **blueprint** install / launch / wizard. No `teams` command. `moa --team` is a third meaning of “team.” |

So “Team” currently means three different things: profile alias, scripted MoA
specialists, and the future composition layer. That collision is the P0.

---

## Ranked index

| # | P | Finding | Primary path | Action |
|---|---|---------|--------------|--------|
| 1 | P0 | `/v1/teams` + `dynamic_team` is a profile alias, not composition | `blueprints/dynamic_team/`, `views/teams_api.py`, `views/utils.py` | wrap (rename conceptually; do not expand the stub) |
| 2 | P0 | CLI composition is Blueprint-only; no Teams surface | `core/swarm_cli.py` | wrap |
| 3 | P0 | Multi-agent composition registered as Blueprint `model` ids (API-only) | `hybrid_*`, `cli_*`, `moa_*`, `persona_council` | wrap |
| 4 | P0 | Docs/API honesty still teach Blueprint-as-composition | `docs/GLOSSARY.md`, `docs/VISION.md`, `teams_api.py` | wrap (docs in a later PR) |
| 5 | P1 | Dual consensus engines | `core/consensus.py`, `core/moa/orchestrator.py` | wrap |
| 6 | P1 | Dual “orchestrator” modules; agents one is a facade | `core/moa/orchestrator.py`, `core/moa/agents_orchestrator.py` | wrap |
| 7 | P1 | Triple `swarm-cli moa` backends | `core/swarm_cli.py` `moa` | wrap |
| 8 | P1 | Persona swarm vs MoA team — parallel specialist runners | `core/persona_swarm.py`, `core/moa/team.py` | wrap |
| 9 | P1 | CLI adapter/catalog vs MoA backends (conflicting grok argv) | `core/cli_adapter.py`, `core/cli_catalog.py`, `core/moa/backends.py` | wrap |
| 10 | P1 | `hybrid_team` nested loop: ThreadPool + `asyncio.run` | `blueprints/hybrid_team/blueprint_hybrid_team.py` | wrap |
| 11 | P1 | `hybrid_team` ≈ `hybrid_swarm` | those two packages | wrap |
| 12 | P1 | Nine `cli_*` strategy blueprints + two MoA alias packages | `blueprints/cli_*`, `cli_fusion`, `cli_ensemble` | wrap |
| 13 | P1 | `wizard` writes a Blueprint stub; `--role` is dead | `core/swarm_cli.py` `wizard_cmd` | delete stub / wrap to Teams |
| 14 | P1 | `BlueprintBase` god module + Django/import-time OpenAI + stdin approval | `core/blueprint_base.py` | wrap |
| 15 | P1 | `Runner.run` without `max_turns` on API blueprints | many `blueprint_*.py` | wrap |
| 16 | P1 | `django_chat` calls `django.setup()` at import | `blueprints/django_chat/blueprint_django_chat.py` | wrap |
| 17 | P1 | Deprecated `gawd` still discoverable | `blueprints/gawd/` | delete |
| 18 | P1 | Metadata / discovery schema drift | `core/blueprint_discovery.py` + several blueprints | wrap |
| 19 | P2 | No dead oracle/Neon callers in scope | `src/swarm/core`, `src/swarm/blueprints`, `swarm_cli` | leave |
| 20 | P2 | Broken unused `agent_utils.py` | `core/agent_utils.py` | delete |
| 21 | P2 | Test-only `common_utils` / `config_manager` | those two modules | delete |
| 22 | P2 | Duplicate `Spinner`; unused approval helpers | `blueprint_base.py`, `core/spinner.py` | delete |
| 23 | P2 | `chucks_angels` echo husk | `blueprints/chucks_angels/` | delete |
| 24 | P2 | `common/tool_utils.py` unused; gawd-only formatters | `blueprints/common/` | delete |
| 25 | P2 | Responses store / cancel live in `core` (API-only) | `core/responses_store.py`, `core/cancel_registry.py` | leave |
| 26 | P2 | Unreachable second `SWARM_TEST_MODE` in `install-executable` | `core/swarm_cli.py` | delete |
| 27 | P2 | Stale `extensions/` path comments | `blueprint_base.py`, `config_manager.py` | delete |
| 28 | P2 | Leftover Django `apps.py` in blueprint dirs | `zeus`, `gawd`, `whiskeytango_foxtrot` | delete |
| 29 | P2 | `harness_fleet` hardcoded LAN probe | `blueprints/harness_fleet/` | leave |
| 30 | P2 | `zeus` sync-generator `Runner.run` wrapper | `blueprints/zeus/blueprint_zeus.py` | wrap |

---

## P0 — product-direction mismatches

### P0-1. `/v1/teams` + `DynamicTeamBlueprint` is a profile alias, not composition

- **Path:** `src/swarm/blueprints/dynamic_team/blueprint_dynamic_team.py`,
  `src/swarm/views/teams_api.py`, `src/swarm/views/utils.py`
- **Why:** `DynamicTeamBlueprint.run()` is a thin `AsyncOpenAI` Chat Completions
  proxy to one `llm_profile`. The Teams API honesty note says each team is
  `id` / `description` / `llm_profile` — “not a multi-agent team builder.”
  Registry lives in `teams.json` and is merged into discovery as if it were a
  blueprint. That is the wrong object for “Teams is the composition layer for
  API+CLI+remote.” Expanding this stub into a graph editor would also be
  wrong; it is a naming trap, not a foundation.
- **Action:** **wrap** — keep the alias registry for now; stop calling it a
  team in new work. Real composition belongs beside (not inside) this class.
  Do not grow `DynamicTeamBlueprint`.
- **Evidence:**

```13:21:src/swarm/blueprints/dynamic_team/blueprint_dynamic_team.py
class DynamicTeamBlueprint(BlueprintBase):
    """
    Minimal dynamic team blueprint that proxies user messages to the configured
    LLM profile via OpenAI-compatible Chat Completions and yields a single final
    assistant message.
    ...
    """
```

```10:12:src/swarm/views/teams_api.py
Honesty: a "team" here is a named **LLM-profile alias** (id + description +
llm_profile), not a multi-agent team builder.
```

---

### P0-2. CLI treats Blueprint as the composition layer; no Teams command

- **Path:** `src/swarm/core/swarm_cli.py`
- **Why:** Shipped commands are `install-executable` / `install`, `launch`
  (`--pre` / `--listen` / `--post` **blueprint** hooks), `list`, `add`,
  `delete`, `uninstall`, `wizard`, `config`, `cli-agents`, `skills`, `moa`,
  `moa-init`. There is no `teams` list/create/run/export. `launch` runs
  PyInstaller bins of blueprints. `wizard` scaffolds a `BlueprintBase`.
  `cli-agents --init` seeds `cli_fusion` / `cli_orchestrator` / `cli_map`
  (blueprint composition). Remote/API operators therefore cannot share one
  Teams object with the CLI.
- **Action:** **wrap** — add a Teams CLI that talks to the same composition
  object the API and remote runner will use. Demote `launch` to “run a
  Blueprint recipe.” Keep `moa` as a Teams strategy, not a third product.
- **Evidence:** `wizard_cmd` help: “Scaffold a new team blueprint.”
  `launch` docstring/args are blueprint-executable only. Zero `teams`
  Typer command.

---

### P0-3. Multi-agent composition is still a pile of Blueprint model ids (API-only)

- **Path:**
  - `src/swarm/blueprints/hybrid_team/`
  - `src/swarm/blueprints/hybrid_swarm/`
  - `src/swarm/blueprints/hybrid_moa/`
  - `src/swarm/blueprints/moa_orchestrator/`
  - `src/swarm/blueprints/persona_council/`
  - `src/swarm/blueprints/cli_{agent,map,orchestrator,pipeline,planner,recurse,roundtable}/`
  - plus alias packages `cli_fusion`, `cli_ensemble`
- **Why:** These packages compose REST + CLI adapters + consensus / MoA /
  specialists. That is composition. They are consumed as OpenAI `model:` ids
  on `/v1/chat/completions`. `pyproject.toml` scripts expose only `swarm-cli`,
  `swarm-api`, `codey`, `suggestion` — so the composition family has **no CLI
  or remote story** except “POST a model id.” Team Launcher still picks
  blueprint ids. REQ-22c says that layer should be Teams; Blueprint stays a
  recipe.
- **Action:** **wrap** — keep the implementations as recipes or strategies;
  expose one Teams composition surface (API + CLI + remote). Deprecate the
  extra model ids rather than adding more.
- **Evidence:** `hybrid_team` module doc: “REST coordinator + grok CLI persona
  + consensus panel, in one `run()`.” `FEATURE_STATUS.md` already notes
  `/v1/teams` is not a multi-agent builder. ROADMAP §4.5 already flags
  “9 `cli_*` deliberation blueprints overlap.”

---

### P0-4. Shipped docs still teach Blueprint-as-composition

- **Path:** `docs/GLOSSARY.md`, `docs/VISION.md`, `docs/DEVELOPER_GUIDE.md`,
  `src/swarm/views/teams_api.py` (OpenAPI text)
- **Why:** GLOSSARY: “For multi-agent workflows, use a **Blueprint**.”
  VISION: orchestrate CLIs “exposed as **blueprints** (each is a `model` id).”
  Developer guide CLI surface is `list` / `install` / `launch` blueprints.
  Until those are updated, every new contributor will add another blueprint
  id instead of a Team.
- **Action:** **wrap** — later docs PR (not this audit). Align GLOSSARY:
  Team = composition (API+CLI+remote); Blueprint = Python recipe / model id.
  Keep the alias-registry honesty as a **legacy** `/v1/teams` caveat until
  the registry is renamed or replaced.

---

## P1 — duplicate paths, stale abstractions, unsafe loops

### P1-1. Two consensus engines

- **Path:** `src/swarm/core/consensus.py`, `src/swarm/core/moa/orchestrator.py`
- **Why:** `run_consensus` is “extracted from the cli_fusion blueprint”
  (panel → judge → most-corroborated). `MoAOrchestrator.default_synthesize`
  is another panel synthesizer with its own `_tokens()`. `hybrid_team` /
  `hybrid_swarm` / `persona_council` use the first; `moa` / `hybrid_moa` /
  `moa_orchestrator` use the second. Same product idea, two policies, two
  corroboration implementations.
- **Action:** **wrap** — one synthesizer; CLI-fusion and MoA become backends.

---

### P1-2. Two modules named “orchestrator”; the agents one is a facade

- **Path:** `src/swarm/core/moa/orchestrator.py` (`MoAOrchestrator`),
  `src/swarm/core/moa/agents_orchestrator.py` (`run_moa_agents_orchestrator`)
- **Why:** The agents module docstring says it is **not** a live
  openai-agents `Runner` path; it wraps `run_moa_then_team`. The name
  implies a third orchestration SDK. `moa_orchestrator` blueprint imports
  this facade. Operators cannot tell “MoA orchestrator” from “openai-agents
  orchestrator” from “hybrid_team coordinator.”
- **Action:** **wrap** — merge the facade into `moa/team.py` or rename it to
  a team runner. Reserve “orchestrator” for the Teams layer.

---

### P1-3. Triple `swarm-cli moa` internals

- **Path:** `src/swarm/core/swarm_cli.py` (`moa`, ~L527–639)
- **Why:** `--team` → `run_moa_then_team`; `--act` → `run_moa_cli`; default →
  `run_moa_consensus`. All three serialize slightly differently, then the
  printer special-cases `--act` vs team text. Drift risk; embedding the CLI
  means three `asyncio.run` entrypoints.
- **Action:** **wrap** — one `run_moa(mode=…)` used by CLI and API.

---

### P1-4. `persona_swarm` vs `moa.team` — two specialist runners

- **Path:** `src/swarm/core/persona_swarm.py`, `src/swarm/core/moa/team.py`
- **Why:** Model B (`run_scripted_persona_swarm`, `run_hybrid_scripted`,
  `run_persona_swarm_with_runner`) and MoA `--team` (`_run_specialist`,
  `run_moa_then_team`) both script researcher/implementer-style writes.
  `team.py` already imports `WorkspaceTools` from `persona_swarm`.
  `run_persona_swarm_with_runner` is the only `Runner.run` in core
  (`max_turns=4`) and **falls back silently** to the scripted swarm.
  `hybrid_moa` uses `run_hybrid_scripted`; `moa_orchestrator` uses
  `run_moa_then_team`.
- **Action:** **wrap** — Teams owns post-consensus specialists. Persona
  module keeps optional live Runner + `consult_moa` tool only.

---

### P1-5. Two grok CLIs: catalog `--always-approve` vs MoA `--disallowed-tools`

- **Path:** `src/swarm/core/cli_catalog.py` (`CATALOG["grok"]`),
  `src/swarm/core/cli_adapter.py`, `src/swarm/core/moa/backends.py`
  (`GrokParticipantBackend.build_command`)
- **Why:** Fusion catalog: `grok -p … --always-approve` (write mode).
  MoA backend: `grok -p … --disallowed-tools Write,Edit,… --max-turns 4`
  (read-only opinion). Same binary, opposite policy. `swarm-cli moa
  --backend grok` bypasses `CliAdapterRegistry`; `swarm-cli cli-agents`
  bypasses MoA backends. A Teams composition layer cannot have two
  subprocess stacks for one CLI.
- **Action:** **wrap** — `ParticipantBackend` on top of `CliAdapter` +
  catalog, with a readonly override. Do not “fix” by enabling write on MoA
  panelists.

---

### P1-6. `hybrid_team` — ThreadPool + nested `asyncio.run` (inefficient agent loop)

- **Path:** `src/swarm/blueprints/hybrid_team/blueprint_hybrid_team.py`
  (`_execute_delegations`, `_run_delegation`)
- **Why:** Outer `run()` is already async. Delegations are farmed to a
  `ThreadPoolExecutor`; each worker calls `asyncio.run(asyncio.wait_for(
  self._run_delegation(...)))`, and `_run_delegation` does `Runner.run`
  with **no `max_turns`**. New event loop per sub-task; no shared client;
  rate-limit sleep holds a thread. `persona_council` / `cli_map` already
  use `asyncio.gather`. Same pattern exists in
  `persona_swarm._consult_moa_sync` and
  `moa/agents_orchestrator._consult_configured`.
- **Action:** **wrap** — native `asyncio.gather` + semaphore; cap
  `max_turns`. Do not add more thread-pool Runner hops.

```311:334:src/swarm/blueprints/hybrid_team/blueprint_hybrid_team.py
        def _work(d: dict) -> dict:
            ...
                out = asyncio.run(
                    asyncio.wait_for(self._run_delegation(d), timeout=self._DELEGATION_TIMEOUT_S)
                )
        ...
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [loop.run_in_executor(pool, _work, d) for d in delegations]
```

---

### P1-7. `hybrid_team` and `hybrid_swarm` share ~70% of a pipeline

- **Path:** `src/swarm/blueprints/hybrid_team/blueprint_hybrid_team.py`,
  `src/swarm/blueprints/hybrid_swarm/blueprint_hybrid_swarm.py`
- **Why:** Both: REST plan → grok CLI persona → `run_consensus` / `consensus_fn`
  → concatenate. Team adds Claude-orchestrated delegations + optional
  auxiliary synthesis. Swarm stops at step 4. Two discoverable model ids
  for one hybrid recipe.
- **Action:** **wrap** — one recipe, `params.mode=team|swarm`, or one shared
  helper used by a future Team strategy.

---

### P1-8. Strategy family exploded into nine `cli_*` packages + two MoA aliases

- **Path:** `src/swarm/blueprints/cli_*`, `cli_fusion/`, `cli_ensemble/`,
  `src/swarm/core/blueprint_discovery.py` `BLUEPRINT_ALIASES`
- **Why:** `cli_fusion` and `cli_ensemble` are 30-line `MoABlueprint`
  subclasses (legacy model ids). The other seven (`agent`, `map`,
  `orchestrator`, `pipeline`, `planner`, `recurse`, `roundtable`) all import
  `blueprints.common.cli_fusion_support` and differ by orchestration
  template. Discovery also registers `swarm_*` aliases pointing at `cli_*`.
  ROADMAP §4.5 already says: consider one blueprint + `strategy` param.
  Under REQ-22c those strategies are **Team** strategies, not more
  blueprints.
- **Action:** **wrap** — collapse aliases into discovery metadata; one
  strategy enum on Teams. Keep packages as thin recipes until then.

---

### P1-9. `wizard` is labeled “team” and emits a dead Blueprint

- **Path:** `src/swarm/core/swarm_cli.py` `wizard_cmd` (~L1082–1113)
- **Why:** Help: “Scaffold a new team blueprint.” `--role` builds
  `agents_code` that is **never written**. Output is an inert
  `BlueprintBase.run` that yields `"Team {name} ready."` It does not
  write `teams.json`, MoA tasks, or a Team composition.
- **Action:** **delete** the stub generator, or **wrap** it to emit a Teams
  registry entry / MoA team template.

---

### P1-10. `BlueprintBase` is a god module with API-server assumptions

- **Path:** `src/swarm/core/blueprint_base.py` (~920 lines)
- **Why:** Import-time `configure_openai_client_from_env()`,
  `set_tracing_disabled`, Django `apps` as “primary source in server mode,”
  LLM profile resolution, memory wrap, `make_agent`, inline `Spinner`,
  interactive `request_approval` (`input()` — **no callers** in `src/`),
  session logger, CLI `print_help`. Every blueprint import pays Django +
  openai-agents + OpenAI client. ROADMAP §4.5 already lists this split
  (`MemoryMixin` / `ApprovalMixin` / `ConfigResolver`).
- **Action:** **wrap** — thin recipe base; lazy client; no stdin approval
  on the API path. Approval helpers are delete-candidates (unused).

---

### P1-11. Unbounded openai-agents loops on the API path

- **Path:** `Runner.run(...)` in `hybrid_team` (×3), `hybrid_swarm`,
  `geese`, `jeeves`, `codey`, `chatbot`, `suggestion`, `gawd`, `zeus`,
  `whiskeytango_foxtrot`, `stewie`. `grep max_turns src/swarm/blueprints`
  → **zero** matches. Only core `persona_swarm.run_persona_swarm_with_runner`
  passes `max_turns=4`.
- **Why:** Tool-using agents can loop until the gateway times out. API
  `/v1/chat/completions` has no per-blueprint turn cap. `zeus` and
  `whiskeytango_foxtrot` also treat `Runner.run` as a **sync generator**
  (`while True` over the gen) — a second, older SDK shape.
- **Action:** **wrap** — default `max_turns` on `BlueprintBase.make_agent` /
  a shared `run_agent` helper. Fix zeus/WTF to `await Runner.run`.

---

### P1-12. `django_chat` is not a portable recipe

- **Path:** `src/swarm/blueprints/django_chat/blueprint_django_chat.py`
- **Why:** Calls `django.setup()` at import; pulls `ChatConversation`,
  login/CSRF views, templates. Docstring: “HTTP-only; not intended for CLI
  use.” Discovery of this package from CLI/`swarm-cli list` boots Django.
  That is an API/server app living in the blueprint tree.
- **Action:** **wrap** — move views/urls/templates out of `blueprints/`;
  drop from default discovery or keep a thin recipe that does not
  `django.setup()`.

---

### P1-13. `gawd` is deprecated and still a `/v1/models` id

- **Path:** `src/swarm/blueprints/gawd/blueprint_gawd.py` (line 1:
  “DEPRECATED: superseded by Zeus”), `gawd/apps.py`
- **Why:** Still discovered, still in API smoke / gap-test matrices.
  Only consumer of `common/progress.py` and `common/output_formatters.py`.
  Duplicates zeus UX (`ProgressRenderer`, `Runner.run`).
- **Action:** **delete** (later PR) or mark `deprecated: true` and exclude
  from prod lists. Do not migrate new work here.

---

### P1-14. Discovery metadata is inconsistent and Blueprint-only

- **Path:** `src/swarm/core/blueprint_discovery.py`; worst offenders
  `gawd`, `geese`, `zeus` (no `metadata` dict — zeus has `get_metadata()`
  that discovery **does not call**); `chucks_angels` display name
  `"Chuck's Angels"` vs dir key. Zero blueprints set `category`.
  Comment still mentions deleted `audit_status.json`.
- **Why:** Teams are not discovered at all (`teams.json` is view-layer).
  Library grouping and slug checks cannot work. ROADMAP §4.5 already
  asks for a schema + CI validator.
- **Action:** **wrap** — schema + `discover_teams()` (or equivalent) when
  Teams is the composition layer. Do not add more `swarm_*` aliases.

---

## P2 — dead code, husks, leave-alones

### P2-1. No dead oracle/Neon callers in scope

- **Path:** `src/swarm/core/**`, `src/swarm/blueprints/**`,
  `src/swarm/core/swarm_cli.py` — grep `oracle|neon|NEON` → **no matches**.
- **Why:** Oracle/Neon exist only as **deploy docs and unit files**:
  `deploy/oracle/`, `docs/ORACLE_DEPLOY.md`,
  `docs/RUNBOOK_NEON_QUOTA_CRASH_LOOP.md`. `settings.py` has generic
  `DATABASE_URL` → dj-database-url (not a Neon client). Nothing in core,
  blueprints, or `swarm_cli` imports or enables those services.
- **Action:** **leave**. **Do not enable oracle or Neon.** Do not add
  callers in a cleanup PR.

---

### P2-2. `agent_utils.py` is dead and import-broken

- **Path:** `src/swarm/core/agent_utils.py`
- **Why:** `from blueprint_agents.agent import Agent` — package does not
  exist. Zero `src/` or test importers. Header claims openai-agents; code
  does not use it.
- **Action:** **delete**.

---

### P2-3. `common_utils.py` and `config_manager.py` are test-only

- **Path:** `src/swarm/core/common_utils.py`, `src/swarm/core/config_manager.py`
- **Why:** No production `src/` imports. `config_manager.py` still titled
  `# src/swarm/extensions/config/config_manager.py`. Live config CRUD is
  `swarm-cli config`. Tests in `tests/core/test_config_manager.py` /
  `test_common_utils.py` are the only callers.
- **Action:** **delete** (with the tests that exist only for them), or
  **leave** until a dedicated cleanup PR updates those tests.

---

### P2-4. Duplicate `Spinner`; unused stdin approval

- **Path:** `src/swarm/core/blueprint_base.py` (`class Spinner`,
  `request_approval`, `execute_tool_with_approval`);
  `src/swarm/core/spinner.py` (“single source of truth”)
- **Why:** Two spinner implementations. Approval helpers have **no
  callers** and block on `input()` — unusable under ASGI.
- **Action:** **delete** the inline Spinner and unused approval methods.

---

### P2-5. `chucks_angels` is an echo husk

- **Path:** `src/swarm/blueprints/chucks_angels/blueprint_chucks_angels.py`
- **Why:** `run()` prints to console and yields two canned strings. No
  agents, no tools. Survives for gap-test / library completeness. Name
  ≠ dirname (`"Chuck's Angels"`).
- **Action:** **delete**.

---

### P2-6. `common/` leftovers

- **Path:** `src/swarm/blueprints/common/tool_utils.py` (no production
  imports; `codey`/`chatbot` redeclare DummyTool locally);
  `common/progress.py` + `common/output_formatters.py` (gawd-only)
- **Why:** Dead after gawd/tool-utils consolidation.
- **Action:** **delete** with gawd, or **leave** `cli_fusion_support.py` and
  `operation_box_utils.py` (actively used — promote to `core/` later).

---

### P2-7. Responses store sits in `core` but is API-only

- **Path:** `src/swarm/core/responses_store.py`, `src/swarm/core/cancel_registry.py`
- **Why:** Used by `views/responses_views.py`, `chat_views.py`,
  `session_explorer.py`, `auth.py` — not by CLI or Teams composition.
  Placement implies shared runtime; it is `/v1/responses` persistence.
- **Action:** **leave** (relocation is churn without a Teams store). Wrap
  only if a remote runner needs the same records.

---

### P2-8. Unreachable second `SWARM_TEST_MODE` block — RESOLVED (REQ-871)

- **Path:** `src/swarm/core/swarm_cli.py` `install_executable` L180–186
  (`raise typer.Exit`) then L202–212 (dead second shim)
- **Why:** Confuses the compile/install story. Root `TODO.md` still
  mentions `swarm-cli compile` and missing `core/build_launchers.py`.
- **Action:** **delete** the dead block in a later PR. **leave**
  `install-executable` as the only compile path until Teams owns binaries.
- **Resolved:** [REQ-871](../qa/REQ-871-cli-blueprint-lifecycle.md) deleted the
  unreachable block and promoted `compile` to the primary name (`install` /
  `install-executable` stay as aliases on one shared build body). The stale
  `core/build_launchers.py` pointer and the non-existent
  `~/.cache/swarm/sessions` claim are corrected in `TODO.md`.

---

### P2-9. Stale `extensions/` headers

- **Path:** `blueprint_base.py` L31
  (`# --- Content for src/swarm/extensions/blueprint/blueprint_base.py ---`);
  `config_manager.py` L1
- **Why:** The extensions tree is gone (FEATURE_STATUS §1). Comments lie
  about ownership.
- **Action:** **delete** comments on next edit.

---

### P2-10. Leftover Django `apps.py` in blueprint packages

- **Path:** `blueprints/zeus/apps.py`, `gawd/apps.py`,
  `whiskeytango_foxtrot/apps.py` (`name = 'blueprints.gawd'` etc.)
- **Why:** Not the composition layer; leftover Django app registration
  inside recipe dirs. `django_chat/apps.py` is only justified if that
  web UI stays.
- **Action:** **delete** when those packages are normalized.

---

### P2-11. `harness_fleet` is an operator-specific LAN probe

- **Path:** `src/swarm/blueprints/harness_fleet/`
- **Why:** Hardcoded private fleet hosts; no LLM; useful as a recipe,
  not a Team. Screenshots treat it as a launcher dropdown item.
- **Action:** **leave** as a Blueprint recipe. Do not promote to Teams.

---

### P2-12. `zeus` sync-generator Runner wrapper

- **Path:** `src/swarm/blueprints/zeus/blueprint_zeus.py` (~L117–139)
- **Why:** Late-imports `Runner`, iterates a sync generator inside async
  `run()`, no `max_turns`, falls back to a canned line on any failure.
  Same older SDK shape as `whiskeytango_foxtrot` / `stewie`.
- **Action:** **wrap** — `await Runner.run` like `hybrid_team` / `codey`.

---

## Duplicate-path map (MoA / Team / CLI)

```
core primitives
  MoAOrchestrator          (moa/orchestrator.py)     ── panel determine/act
  run_consensus            (consensus.py)            ── CLI-fusion judge
  CliAdapter + catalog     (cli_adapter, cli_catalog)
  GrokParticipantBackend   (moa/backends.py)         ── second grok argv
  run_moa_then_team        (moa/team.py)
  persona_swarm            (scripted + optional Runner)

blueprint model ids (API)
  moa  ←── cli_fusion, cli_ensemble          (alias subclasses)
  hybrid_moa        → consult_moa + persona_swarm.run_hybrid_scripted
  moa_orchestrator  → agents_orchestrator → run_moa_then_team
  hybrid_team       → REST + delegations + cli_persona + run_consensus
  hybrid_swarm      → REST + cli_persona + run_consensus
  persona_council   → parallel CLI lenses + judge (third panel)
  cli_{agent,map,orchestrator,pipeline,planner,recurse,roundtable}
  dynamic_team      → AsyncOpenAI profile proxy  ← /v1/teams

CLI
  swarm-cli moa [--team|--act|consensus]     (three runners)
  swarm-cli launch / wizard / install        (blueprint composition)
  (no swarm-cli teams)
```

Overlap (order-of-magnitude):

| Cluster | Shared core | Redundancy |
|---------|-------------|------------|
| `moa` / `cli_fusion` / `cli_ensemble` | same class lineage | ~95% |
| `hybrid_team` / `hybrid_swarm` | REST+persona+consensus | ~70% |
| `hybrid_moa` / `moa_orchestrator` | MoA consult, different write-back | ~50% consult |
| `persona_council` / MoA / `cli_orchestrator` | panel + judge | conceptual |
| seven `cli_*` strategies | `cli_fusion_support` | ~60% boilerplate |
| `consensus.py` / `MoAOrchestrator` | token-overlap synthesize | duplicate engine |

---

## Blueprint inventory (discoverable packages)

Legend: **CLI** = pyproject entry or dedicated `*_cli.py`. **Tests** = dedicated
module (not only gap/smoke).

| Package | Tests | CLI | Role vs REQ-22c |
|---------|-------|-----|-----------------|
| `moa` | yes (core + api) | `swarm-cli moa` | Canonical read-only consensus — **Team strategy**, still a blueprint id |
| `moa_orchestrator` | unit | no | Consensus-then-specialists — composition, API-only |
| `hybrid_moa` | unit + integration | no | Consult then persona write — composition, API-only |
| `cli_fusion` / `cli_ensemble` | yes (alias asserts) | no | **Wrap** — delete packages once discovery aliases exist |
| `cli_*` (7 strategies) | yes | no | **Wrap** into Teams strategies |
| `hybrid_team` / `hybrid_swarm` | yes | no | **Wrap** — composition, not recipes |
| `persona_council` | yes | no | **Wrap** — third panel implementation |
| `dynamic_team` | gap only | no | Profile alias — **do not expand** |
| `fs_introspect` | yes | no | **Leave** as recipe (filesystem toolset) |
| `harness_fleet` | yes | no | **Leave** as operator recipe |
| `chatbot` | yes | `__main__` | **Leave** as recipe |
| `codey` | yes | `codey` | **Leave** as recipe |
| `suggestion` | smoke | `suggestion` | **Leave** as recipe |
| `rue_code` | tools | `rue_code_cli.py` | **Leave** as recipe |
| `jeeves` | partial | `jeeves_cli.py` | **Leave** as MCP demo recipe |
| `geese` | spinner only | `geese_cli.py` | **Leave**; thin coverage |
| `zeus` | spinner only | `zeus_cli.py` | **Leave** as flagship recipe |
| `stewie` | yes | `__main__` | **Leave** as MCP/WordPress recipe |
| `poets` | gap | `poets_cli.py` | **Leave** as SQLite demo |
| `django_chat` | config | rejects CLI | **Wrap** out of default discovery |
| `whiskeytango_foxtrot` | gap | `__main__` | **Leave** as hierarchical demo |
| `chucks_angels` | gap | no | **Delete** husk |
| `gawd` | gap | `__main__` | **Delete** (deprecated) |

`blueprints/common/` is not a blueprint. Keep `cli_fusion_support` and
`operation_box_utils`; delete or fold the rest (P2-6).

---

## openai-agents notes (in scope)

- SDK is a **core dep**. `BlueprintBase.make_agent` builds
  `OpenAIResponsesModel` vs `OpenAIChatCompletionsModel` from `api_mode`.
- Live `Runner.run` in core: only `persona_swarm.run_persona_swarm_with_runner`
  (capped, silent fallback).
- Live `Runner.run` in blueprints: unbounded (P1-11). `hybrid_team` also
  nests it in threads (P1-6).
- `moa/team.py` and default `moa_orchestrator` correctly **avoid** Runner.
  That scripted path is the one Teams should own.
- `build_moa_orchestrator_agents` exists for optional live Agents and is
  unused by the default dogfood path — naming debt only (P1-2).

---

## What this audit does **not** recommend

- Enabling Oracle (`deploy/oracle/`) or Neon (`DATABASE_URL` / quota runbook).
- Turning `DynamicTeamBlueprint` into a multi-agent graph.
- Adding more `cli_*` / `hybrid_*` / `swarm_*` model ids.
- Rewriting `BlueprintBase` or collapsing packages in this PR.

Next implementation pulse (out of scope here): introduce a Teams composition
object that API, `swarm-cli`, and remote share; wrap the MoA / hybrid / cli
strategies behind it; leave Blueprint as the Python recipe for a single
`model` id.
