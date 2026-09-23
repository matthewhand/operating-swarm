# REQ-871 — `swarm-cli` blueprint lifecycle: compile / launch / delete / session

> Spec for the four items that were open under **"CLI blueprint lifecycle (gaps in
> `swarm-cli`)"** in [TODO.md](../../TODO.md). Each item is re-specified here
> against what the code actually does today; three TODO lines were written
> against a tree that has since changed.

**Status: shipped — A, B, C and D landed together.** This page began as a
*forward* plan and keeps its §2 findings as the record of what the TODO text got
wrong. Artefacts:

| Artefact | Path |
| :--- | :--- |
| Source lock (all four workstreams) | `tests/unit/test_req871_cli_blueprint_lifecycle.py` |
| Behaviour tests — A/B/C | `tests/cli/test_blueprint_lifecycle.py` |
| Behaviour tests — D | `tests/cli/test_session_command.py` |

---

## 1. Context

All four items live in one module: `src/swarm/core/swarm_cli.py` (a single
Typer app, `app = typer.Typer(...)` at L36). Relevant commands:

| Symbol | Line | What it does |
| :--- | :--- | :--- |
| `_source_launch_target` | L135 | Fallback tiers: installed source → bundled source (read-only) |
| `_compile_blueprint_executable` | L157 | Shared build body: resolves source (user lib → bundled), finds entry point, runs `pyinstaller --onefile` into `get_user_bin_dir()` |
| `compile` | L248 | Primary command (workstream A); wraps the shared body |
| `install-executable` / `install` | L256 / L264 | Behaviourally identical aliases |
| `launch` | L272 | Compiled binary, else the source fallback; hook semantics unchanged |
| `_launcher_kind` | L890 | `shim` (a `#!` script) vs `executable` (compiled) |
| `list` | L904 | Lists bin-dir launchers with their kind, and source entry points |
| `_remove_blueprint_source` / `_remove_blueprint_binary` | L1422 / L1435 | Guarded single-artefact removal |
| `delete` | L1451 | `--source` / `--binary` / `--all` (default: both) |
| `uninstall` | L1481 | Binary-only alias |
| `session list` / `session show` | L1543 / L1605 | Chat store + provider stores; sub-app registered at L1668 |

Path helpers are in `src/swarm/core/paths.py` (`get_user_bin_dir` L31,
`get_user_cache_dir_for_swarm` L43). Session data lives in
`src/swarm/core/chat_store.py` and the provider-store readers
(`cli_session_select.py`, `cli_session_stores.py`).

---

## 2. Findings that reshape the TODO text

**F1 — `swarm-cli compile` is a rename, not new machinery.**
`install-executable` (L134) *already is* the PyInstaller compile path described
by the TODO. The TODO's pointer to `src/swarm/core/build_launchers.py` is
stale: **no such file exists** anywhere in the tree. This is already flagged in
[docs/debt/core.md](../debt/core.md) P2-8.

**F2 — the dead second `SWARM_TEST_MODE` block.** `install_executable` raises
`typer.Exit(code=0)` at L187 inside its test-mode branch, so the *second*
`SWARM_TEST_MODE` block at L203–214 is unreachable — it can never run in any
mode. P2-8 asks for its removal; it should go in the same edit as F1, since it
sits directly under the code being renamed.

**F3 — `delete`/`uninstall` are already split along the TODO's fault line.**
The TODO asks deletion to "handle removing source, compiled binary, or both".
Both halves already exist as separate commands with safety guards
(`_require_safe_blueprint_segment`, `_path_is_under_root`). The work is flag
wiring and reporting, not new deletion logic.

**F4 — `~/.cache/swarm/sessions` does not exist.** Nothing in the tree writes
there: the only cache consumers are PyInstaller `build/<name>` and `specs/`
(`swarm_cli.py:168-169`). Reality is split in two:

* **Swarm-side ids** — `chat_store` JSON under
  `get_user_data_dir_for_swarm()/chats`, layout `active/<user_key>/<agent_id>.json`,
  with CLI ids in the per-record `cli_sessions` map (`core/cli_sessions.py`).
* **Provider-owned sessions** — enumerated/read by
  `list_provider_sessions()` (`cli_session_select.py:397`, via list argv or a
  store) and `list_store_sessions()` (`cli_session_stores.py:45`, e.g.
  `~/.grok/sessions`, `~/.qwen/projects`).

So TODO item 4 is mis-specified and must be re-scoped before it can be built.

---

## 3. Decisions (recorded)

| # | Decision | Rationale |
| :--- | :--- | :--- |
| **D1** | `session list` / `session show` scope to the **existing** stores (chat_store records + `cli_sessions` ids, with optional `--provider` passthrough to `list_provider_sessions`). No new `~/.cache/swarm/sessions` layer. | The cache-store path was aspirational. Adding a third session store when two already exist contradicts `cli_sessions.py`'s stated design ("we do not invent a parallel session DB"). TODO line 4 gets rewritten to match. |
| **D2** | `compile` becomes the primary command name; `install` and `install-executable` stay as aliases. | TODO asks for `compile`; the aliases are load-bearing in `QUICKSTART.md` §2, `USERGUIDE.md` (:50, :149) and existing tests. |
| **D3** | `launch`'s source fallback must be **non-interactive** by default (never block on a prompt). | `launch` already shells out to `--pre` / `--listen` / `--post` hooks; a prompt in the main path would hang hook-driven runs. Any "offer to compile" behaviour hangs off an explicit flag. |
| **D4** | `delete --all` default removes **both** source and binary, echoing exactly what existed and what was removed. | Matches the TODO's intent and keeps `swarm-cli list --installed` honest afterwards. |

---

## 4. Workstreams

### A — `compile` command + dead-block removal

**Requirements**
1. Register `compile <blueprint_name>` performing today's `install-executable`
   work (source resolution → `find_entry_point` → PyInstaller onefile into
   `get_user_bin_dir()`).
2. Keep `install` and `install-executable` as behaviourally identical aliases.
3. Delete the unreachable `SWARM_TEST_MODE` block at L203–214 (F2).
4. Preserve both escape guards (`output_bin_path` vs bin dir; `pyinstaller_workpath`
   vs cache root) verbatim.

**Acceptance criteria**
- [ ] `swarm-cli compile <name>` and both aliases produce an identical
      `subprocess.run` argv.
- [ ] `src/swarm/core/swarm_cli.py` contains exactly **one** `SWARM_TEST_MODE`
      branch in `install_executable`.
- [ ] Non-safe names (`../x`, absolute paths) still exit 1 before any build.

**Locked sources:** `src/swarm/core/swarm_cli.py` (L134–232) ·
`tests/cli/test_launchers.py` · `USERGUIDE.md` L50, L149 · `QUICKSTART.md` §2.

### B — `launch` falls back to source

**Requirements**
1. Resolution order: executable in `get_user_bin_dir()` → installed user source
   (`python3 <entry_point>`) → bundled source. Echo which tier was used.
2. Missing binary must no longer be a hard failure when source exists.
3. Emit the existing "not found" error only when all three tiers miss, keeping
   the `install-executable` hint.
4. `--pre` / `--listen` / `--post` hook semantics unchanged.

**Acceptance criteria**
- [ ] Empty bin dir + installed source ⇒ launch succeeds and states the fallback
      tier in its output.
- [ ] `find_entry_point` priority (`{name}_cli.py` → `{name}.py` →
      `blueprint_{name}.py`) is honoured on the fallback path.
- [ ] No prompt is issued in the default path (D3).

**Locked sources:** `src/swarm/core/swarm_cli.py` (L243–336) ·
`tests/cli/test_launchers.py`.

### C — unified `delete` / `uninstall`

**Requirements**
1. `delete` gains `--source` / `--binary` / `--all` (D4: default `--all`).
2. Report each artefact's presence and removal separately; exit 0 if anything
   was removed, exit 1 with a message if nothing was.
3. Keep `uninstall` as the binary-only alias.
4. `list --installed` distinguishes test-mode stub/shim installs from real
   binaries, so removal output can be honest about what a file is.

**Acceptance criteria**
- [ ] source-only / binary-only / both / neither each produce the documented
      exit code and message.
- [ ] Path-escape attempts are rejected before any `rmtree`/`unlink`.
- [ ] No `_path_is_under_root` guard is dropped.

**Locked sources:** `src/swarm/core/swarm_cli.py` (L1366–1400) ·
`tests/cli/test_launchers.py`.

### D — `session list` / `session show` (D1 scope)

**Requirements**
1. `session list` enumerates Swarm-side records from `chat_store`, showing
   agent id, last-updated, and the CLI session ids held in `cli_sessions`.
2. `--provider <cli>` (or `--all-providers`) passes through to
   `list_provider_sessions()` and surfaces its `can_list=False` / warning
   returns as "this CLI can't list sessions" rather than inventing rows.
3. `session show <agent_id>` prints the record's session map plus transcript
   location. `--provider <cli>` verifies the stored id against that CLI's
   current session list, and reports the id as **unverified** when the CLI
   cannot list sessions rather than trusting it.
4. No secrets: reuse `sanitize_cli_session_id` and the existing redaction
   conventions. Never open secret-shaped payloads.
5. Rewrite `TODO.md` line 4 to describe this scope.

**Acceptance criteria**
- [ ] On a tree with no `chats/` records, `session list` exits cleanly with an
      empty-state message (no crash, no fabricated rows).
- [ ] A CLI with no list argv and no store reports "can't list sessions".
- [ ] Nothing is written under `~/.cache/swarm/sessions`.

**Locked sources:** `src/swarm/core/chat_store.py` · `core/cli_sessions.py` ·
`core/cli_session_select.py` (L397) · `core/cli_session_stores.py` (L45) ·
`src/swarm/core/swarm_cli.py` · `TODO.md`.

---

## 5. Order and dependencies

```
A (separate, self-contained)
  └─> C   (both touch the bin-dir artefact vocabulary from `list`)
B (depends on nothing; carries D3's UX decision)
D (depends on D1; independent of A/B/C)
```

A → C → B → D. A is a rename plus dead-code removal; C is flag wiring over
existing guards; B carries the only UX judgement call; D is the largest and
the only one needing a re-specified TODO line. All four landed in one change.

## 6. Verification

- `make test` (→ `scripts/run_tests.py`), scoped first to `tests/cli/`.
- `swarm-cli --help` snapshot — confirms `compile` appears and aliases do not
  disappear.
- Main CI does **not** set `SWARM_TEST_MODE` (only
  `.github/workflows/req158-nl-blueprints.yml` does, locally), so the real
  build path is exercisable with `subprocess.run` mocked.
  Test conventions to follow: `CliRunner`, the XDG-patching `mock_dirs`
  fixture, and `@patch("subprocess.run")` — all in `tests/cli/test_launchers.py`.
- Source lock: `tests/unit/test_req871_cli_blueprint_lifecycle.py` — one file
  for the whole REQ, matching the other `tests/unit/test_req###_*.py` locks.

## 7. Doc follow-ups

- [x] `TODO.md` — the stale `src/swarm/core/build_launchers.py` pointer and the
      `~/.cache/swarm/sessions` claim are replaced with what shipped.
- [x] `docs/debt/core.md` P2-8 — the unreachable second `SWARM_TEST_MODE` block
      is deleted, so the item is resolved.
- [x] `docs/qa/README.md` — lock-spec table row for REQ-871.
- [x] `USERGUIDE.md` — `compile` is the documented primary name, plus the
      `launch` fallback tiers, the `delete` flags and the `session` commands.
      No new ```text fences were added, so `tests/core/test_userguide_captures.py`
      is unaffected.
- [x] `DEVELOPMENT.md` — blueprint-management internals: `compile`,
      `_source_launch_target` tiers, the `delete` flags, and the session stores
      (chat store + provider stores), including that no `~/.cache/swarm/sessions`
      store exists.
