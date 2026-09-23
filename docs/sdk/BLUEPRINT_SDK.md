# Blueprint SDK — the contract for Operating Swarm recipes

This is the reference half of the Blueprint SDK (REQ-921 / #540); the
worked half is the teaching bundle under
[`src/swarm/blueprints/example_*`](../../src/swarm/blueprints/README.md)
(REQ-920 / #539). Read both: the examples show the shape, this document
states the rules. A test (`tests/unit/test_req921_sdk_docs.py`) asserts
every public hook of the base classes is documented here, so the docs
cannot silently rot.

Audience: a developer writing a blueprint. This page takes you from an
empty directory to a loading, catalog-visible recipe, and tells you what
the runtime enforces versus what is merely conventional.

---

## 1. The class hierarchy — which base, and when

```
BlueprintBase                 ← the low-level openai-agents unit. Do not
  └── KindBase                ← subclass this directly except to add a new
        ├── ApiKindBase         *documented* kind.
        ├── CliKindBase
        └── RemoteKindBase
```

| Base | kind | The brain lives… | Pick it when… |
|---|---|---|---|
| `ApiKindBase` | `api` | inside Open Swarm (openai-agents graphs, Runner) | you need programmatic workflows: handoffs, fan-out, `as_tool`, skeptic loops |
| `CliKindBase` | `cli` | in a host CLI process (claude, codex, gemini, omp, agy…) | you are adapting an installed, authenticated CLI and want its session to stay native |
| `RemoteKindBase` | `remote` | on a remote harness (OMB, Hermes, Rakazo, Herdr, nested swarm, TrueForge…) | Open Swarm sits in front of another service over HTTP |
| `BlueprintBase` | — | — | only for legacy recipes; new work uses a kind base |

References: [ADR-005 kind bases](adr/005-kind-bases.md) (REQ-159 / #570),
the REQ-851 follow-up that made them first-class (`base_class_for_kind()`,
in-tree migration), ADR-011 / REQ-203 (remote = one kind, many
implementations).

Selection is mechanical: `base_class_for_kind(kind)` returns the base name
for a kind string and is the single source of truth for the codegen
emitters (agent creator, CLI wizard, blueprint library), so hand-written
and generated recipes cannot drift.

**The decisive rule** (ADR-005): openai-agents handoff edges apply only
inside the API kind. A CLI or remote recipe must not assume Runner,
`as_tool`, or handoff graphs exist in the provider's process.

---

## 2. Every hook, one by one

Signatures abbreviate; the code is `src/swarm/core/blueprint_base.py` and
`src/swarm/core/kind_bases.py`. "Runtime calls" = discovery, the REST/WS
chat surface, or the kind base's default `run()`.

### Lifecycle & construction

| Hook | Signature | Runtime calls it | Must return | If it raises |
|---|---|---|---|---|
| `__init__` | `(self, blueprint_id, config=None, config_path=None, **kwargs)` | once per seat instantiation | — | seat fails to construct; the error surfaces as a friendly config error, not a traceback dump |
| `metadata` (ClassVar) | `dict` | discovery + catalog rows + rail gate | name/title/description/version/tags/required_mcp_servers/env_vars | missing `name`/`title`/`description` degrades the catalog row |

### The turn

| Hook | Signature | Runtime calls it | Must return | If it raises |
|---|---|---|---|---|
| `run` | `async (messages: list[dict], **kwargs) -> AsyncGenerator[dict, None]` | every chat turn | yields `{"messages": [...], "final": bool}` chunks | the chunk stream ends; the surface reports an error honestly — never a fake answer |
| `create_starting_agent` | `(self, mcp_servers: list) -> Agent` | by `ApiKindBase.run()` each turn | an `agents.Agent` | kind base catches, yields an error chunk after the timeout budget |

Contract notes for `run()`:
- The kind bases ship a **complete default `run()`**. ApiKindBase's default
  extracts the last user instruction, builds your agent, attaches sandbox
  tools, runs Runner with `SWARM_AGENT_RUN_TIMEOUT` (default 30s), and
  yields exactly one final chunk. CliKindBase/RemoteKindBase defaults
  keep the provider session native. Override `run()` only when the
  default cannot express your graph — and never change its *semantics*
  (yield shape, `final: True` termination) in a refactor.
- `run()` is async-generator code on the event loop: **never block it**
  with `time.sleep`, synchronous subprocess waits, or sync file locks.
  Use `await asyncio.sleep` / `asyncio.create_subprocess_exec`, or push
  blocking work into a tool.
- CLI sessions: resume policy is the kind base's job (`resume_cli_session_id`,
  session stores). A recipe declares policy flags; it does not reimplement
  session plumbing.

### Model & config

| Hook | Runtime calls it | Notes |
|---|---|---|
| `config` (property) | anywhere | the merged per-blueprint config dict |
| `llm_profile_name` (property/settable) | model resolution | honours settings → default profile; the ONLY sanctioned way to pick a model |
| `get_llm_profile(profile_name)` | `_get_model_instance` | profile dict for a name |
| `_get_model_instance(profile_name)` | your `create_starting_agent` | cached `Model` instance; this is how chatbot and the teaching examples wire `Agent(model=...)` |

### Capabilities & chrome

| Hook | Runtime calls it | Notes |
|---|---|---|
| `get_navbar_items()` | the navbar renderer | return `[]` unless you contribute chrome |
| `seat_capabilities` / per-axis attributes | the seat capability resolver (#551) | axes: `attach`, `compact`, `plugins`, `routines`. Declared per kind base; a subclass overrides ONE axis with `{"enabled": bool, "reason": str}`. **A capability nobody declared is never invented** — resolution returns "Not declared by this seat kind" |
| `cli_slash_commands` (ClassVar) | the composer slash popup (REQ-910 / #641) | `dict[str, CliSlashCommand]`; each entry must be *verified* against real CLI behaviour — `available=False` + `unavailable_reason` for commands print-mode cannot run |
| `cli_compact` (ClassVar) | composer Compact for CLI seats (#636) | provider-native compact argv template with `{session_id}`; leave `None` until verified |

### Declaration surface (metadata keys the platform consumes)

| Key | Consumed by | Meaning |
|---|---|---|
| `name`, `title`, `description`, `version`, `author`, `tags` | catalog/library rows | identity |
| `rail` | `metadata_rail()` → `isRailSeat()` (`webui/frontend/src/lib/railSeats.ts`) | **default deny**: only `rail: True` opts a discovered recipe onto the rail; otherwise catalog/library only. CLI/API-kind rows are seats through the kind gate, not this flag |
| `required_mcp_servers` | MCP session setup | servers the recipe needs attached |
| `env_vars` | config validation | env the recipe expects (never values) |
| personas (`parse_openai_agent_personas`) | persona parsing / Definition pane | `swarm.core.persona_parse`; serialized back into source by the editor |

---

### Complete hook index

Every callable the base classes declare, for reference. Detailed contracts
for the common ones are above; the rest are one-liners.

| Hook | One-line contract |
|---|---|
| `config` (property) | merged per-blueprint config dict |
| `llm_profile` (property) | the resolved profile dict |
| `llm_profile_name` (property, settable) | which profile models resolve through |
| `get_llm_profile(profile_name)` | profile dict by name |
| `_get_model_instance(profile_name)` | cached `Model` for `Agent(model=...)` |
| `make_agent(name, instructions, tools, mcp_servers=None, …)` | convenience Agent factory with role/memory wiring |
| `run(messages, **kwargs)` | the turn — async generator of chunks (§2) |
| `create_starting_agent(mcp_servers)` | agent the Runner executes (§2) |
| `get_navbar_items()` | navbar chrome rows |
| `splash` (property) / `get_cli_splash(color, emoji)` | TUI splash text |
| `display_splash_screen(animated=False)` | print the splash |
| `should_output_markdown` (property) | markdown rendering opt-out |
| `memory_backend` (property) | lazily built memory store |
| `inject_memory_context(messages, user_id=None)` | prepend stored memory to the turn |
| `store_run_memory(messages, run_chunks=None, user_id=None)` | persist memory after a run |
| `start_session_logger(blueprint_name, global_instructions=None, project_instructions=None)` | open the per-session log |
| `log_message(role, content)` | session log writer |
| `log_tool_call(tool_name, result)` | session log writer for tools |
| `close_session_logger()` | flush/close the session log |
| `request_approval(action_type, action_summary, action_details=None)` | human-approval gate |
| `execute_tool_with_approval(tool_func, action_type, action_summary, action_details=None, *args)` | run a tool behind the approval gate |
| `print_help()` | CLI help text |
| `slash_commands` (property) | legacy slash-command surface |
| `slash_command(name)` (classmethod) | `CliSlashCommand` lookup (§2) |
| `supports_slash_command(name)` (classmethod) | declared AND runnable |
| `supports_cli_compact()` (classmethod) | provider-native compact available |
| `cli_compact_argv(session_id)` (classmethod) | compact argv template |

## 3. What is enforced, not merely conventional

Enforcement lives in `src/swarm/core/blueprint_source.py` +
`src/swarm/core/blueprint_sandbox.py`; every edit/install path goes
through `validate_writable_source()`:

1. `content` must be a string; length ≤ **`MAX_SOURCE_CHARS`** (200,000).
2. Suffix must be in **`ALLOWED_SOURCE_SUFFIXES`** (`.py .md .json .txt
   .toml .yaml .yml .cfg`); non-`.py` files skip the Python gate.
3. `.py` sources must `compile()` — syntax errors are rejected at write
   time, not discovery time.
4. `assert_safe_blueprint_source()` runs a **static AST check** banning
   escape-hatch constructs (dangerous `os` attrs and imports). Be clear
   about its limits: it is a *blocklist*, not a sandbox — see
   ROADMAP Phase 2 for real sandboxing. User-dir discovery enables the
   sandbox automatically (`SWARM_USER_BLUEPRINT_SANDBOX` opt-out).
5. Discovery itself never executes metadata claims: `rail` is read, not
   trusted — the frontend gate re-checks (`isCatalogRailSeat`).

Tracked-file hygiene is separately enforced by
`tests/test_tracked_files_sanitization.py` — no LAN IPs and no internal
host names from any dev/prod box (the test's ban list is the source of
truth) and no secrets. Your blueprint must pass it too.

---

## 4. The lifecycle: empty directory → conversation

1. **Create** `src/swarm/blueprints/<your_id>/blueprint_<your_id>.py`
   (discovery accepts `<id>.py` or `blueprint_<id>.py`; the directory
   name is the blueprint key). `__init__.py` not required.
2. **Declare** the class: subclass a kind base, fill `metadata`, override
   the hooks you need (start from an `example_*` recipe).
3. **Discovery** — `discover_blueprints(BLUEPRINT_DIRECTORY)` imports each
   candidate module, extracts metadata (docstring fallback for
   description), and merges community/user extra dirs
   (`BLUEPRINT_EXTRA_DIRS`: the user data `blueprints/` dir, sandboxed,
   bundled wins on name collision). `swarm_*` aliases are applied for
   `cli_*` patterns.
4. **Catalog vs rail** — `GET /v1/blueprints/` lists everything discovered;
   the rail seats only what passes `railSeats.ts`. Examples never set
   `rail`.
5. **Edit/upload** (#538, REQ-919) — the library and Settings write
   through `validate_writable_source`; the Definition pane shows
   "How it works" + source; user-dir trees shadow nothing bundled (the
   bundle wins collisions).
6. **Conversation** — the seat instantiates on first chat; `run()`
   consumes turns per §2.

---

## 5. Worked example — from empty to loading

Follow this verbatim; it is the acceptance path for this document.

```bash
mkdir -p src/swarm/blueprints/my_recipe
cat > src/swarm/blueprints/my_recipe/blueprint_my_recipe.py <<'PY'
"""my_recipe — one-line description."""
from typing import Any, ClassVar
from agents import Agent
from swarm.core.kind_bases import ApiKindBase

class MyRecipeBlueprint(ApiKindBase):
    metadata: ClassVar[dict[str, Any]] = {
        "name": "my_recipe",
        "title": "My Recipe",
        "description": "What it does, honestly.",
        "version": "0.1.0",
        "author": "you",
        "tags": ["custom"],
    }

    def create_starting_agent(self, mcp_servers=None) -> Agent:
        return Agent(
            name="my_recipe",
            instructions="Answer in one sentence.",
            model=self._get_model_instance(self.llm_profile_name),
            mcp_servers=list(mcp_servers or []),
        )
PY
```

Verify (no server needed):

```bash
uv run python -c "
from swarm.core.blueprint_discovery import discover_blueprints
from swarm.settings import BLUEPRINT_DIRECTORY
found = discover_blueprints(BLUEPRINT_DIRECTORY)
assert 'my_recipe' in found, sorted(found)[:5]
print('my_recipe discovered OK')
"
```

That is the whole loop: the recipe now appears in the catalog, can be
chatted with once a model profile is configured, and never touched the
rail. The teaching bundle (`example_*`) shows the same shape per kind.

---

## 6. Anti-patterns / known footguns

- **Blocking the event loop** in `run()` — sync sleeps/subprocess on the
  loop stall every seat on the process. Async equivalents or tools.
- **Provider exclusion lies** — a locked CLI must never silently fall
  back to a different backend, and must document the lock (the canonical
  case: `agy` is Gemini-only and cannot target LiteLLM orchestration —
  see `example_cli_provider_agy`). State the lock in the docstring, the
  metadata description, and the honest error.
- **Rewriting `run()` semantics in refactors** — chunk shape and
  `final: True` are the transport contract; "just restructuring run()"
  breaks every surface that consumes it.
- **Aspirational slash commands** — declaring `cli_slash_commands` for
  behaviour the CLI has not been verified to support. Declare
  `available=False` with a reason, or do not declare.
- **Inventing capabilities** — `seat_capabilities` resolution never
  invents an axis; do not "fix" a disabled control by flipping it on
  without a real provider reason string.
- **Hard-coding sub-agent ids** in team recipes — bind roles, resolve
  members at run time (`example_team_orchestrator`).
- **Secrets/LAN literals in source** — the sanitization gate fails the
  build; config belongs in profiles/registry, never in tracked files.
- **Putting examples or catalog recipes on the rail by default** —
  `rail: True` is a deliberate opt-in, not a growth hack.

---

## Related

- Teaching bundle: `src/swarm/blueprints/README.md` §Teaching examples
- ADR-005 (kind bases), ADR-011 (remote harness), ADR-006 (user-facing kinds)
- `webui/frontend/src/lib/railSeats.ts` (seat gating)
- `src/swarm/core/rail_seats.py` (`metadata_rail`)
