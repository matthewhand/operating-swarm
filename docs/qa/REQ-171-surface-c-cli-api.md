# REQ-171 Surface C — look-only audit

> CLI / API / remote harnesses, session start, cwd/workdir, model/CLI
> dropdowns **backend**, plus cross-cutting `tests/` quality.
> **Look-only.** This file is a findings list for CoS triage. It does not
> change runtime product code, close [#596](https://github.com/matthewhand/open-swarm/issues/596),
> or implement fixes.

**As-of:** `origin/main` @ `f21d24ea` (`fix(webui): render CLI and API dropdowns with model selectors (REQ-133, Fixes #523) (#593)`).

**Umbrella:** [#596](https://github.com/matthewhand/open-swarm/issues/596) (REQ-171). This report is **audit partial** for surface **C** only. Surfaces A (chat/composer/WS) and B (rail/agents/blueprints) are sibling look-only PRs — do not re-file their HIGHs here.

**Method:** static read of `cli_adapter.py`, `cli_catalog.py`, `cli_models.py`, `cli_sessions.py`, `session_policy.py`, `workdir.py`, `cli_fusion_support.py`, `remotes.py`, `remote_teams.py`, `herdr/`, `consumers.py` (on-mode branch only), `views/api_views.py` (`CliAgentsView` / `ModelsListView`), ChatPage dropdown contract, `pytest.ini`, `.github/workflows/{python-pytest,visual-regression}.yml`, and the tests that claim to lock this surface. Prior leftover notes in `docs/debt/tests-ci.md` and `docs/debt/qa-wave1-tests-ci.md` were re-checked, not copied. No host bounce. No Neon. No secrets. No live LAN URLs.

**How to read**

| Sev | Meaning here |
|-----|----------------|
| **HIGH** | Wrong behaviour or a confinement/credential leak a user or API client can hit today. File a child Issue. |
| **MEDIUM** | Real hole, bounded (wrong resume argv shape, dual catalogs, isolate unused). Fix after HIGH waves. |
| **LOW** | Dead helpers, cache TTL, probe false-positives. Do not file unless a later REQ needs it. |

**Test column:** `missing` = no test would fail if the bug shipped. `weak` = a test exists but asserts a mock, a catalog field, or the buggy fallback itself. `theatre` = source-substring / invented payload that cannot bite production.

**Do not treat this PR as Fixes #596.** Fixes belong on child Issues, queued in waves of 2–3.

---

## Skipped open Cursor surfaces

REQ-171 asked look-only agents not to fight in-flight Cursor PRs unless the defect is critical. On this snapshot:

| Open PR | Surface | This audit |
|---------|---------|------------|
| [#576](https://github.com/matthewhand/open-swarm/pull/576) | ADR-003 desktop packaging (REQ-151) | **Skip.** Desktop PATH merge is Phase 2 of that ADR; C-H5 (list-models PATH) is server/Daphne today. |
| [#577](https://github.com/matthewhand/open-swarm/pull/577) | First-load keybinding tips (#571) | **Skip.** Composer chrome only. |
| [#578](https://github.com/matthewhand/open-swarm/pull/578) | REQ-156 graphs + REQ-159 kind bases | **Skip.** Do not rewrite remotes/kind-bases here. C-H3/C-H4 stay on the existing `remotes.py` / `remote_teams.py` split. |
| [#579](https://github.com/matthewhand/open-swarm/pull/579) | Persist favourites / Hidden / hostname | **Skip.** Prefs, not adapters. |
| [#582](https://github.com/matthewhand/open-swarm/pull/582) | ADR-004 virtualized chat (REQ-163) | **Skip.** Transcript virtualization. |
| [#599](https://github.com/matthewhand/open-swarm/pull/599) / [#600](https://github.com/matthewhand/open-swarm/pull/600) | REQ-171 surfaces B / A | **Skip.** Do not re-file rail or WS persist HIGHs. |

Related open product Issues (do **not** re-file as new product REQs; coordinate):

- [#588](https://github.com/matthewhand/open-swarm/issues/588) / [#590](https://github.com/matthewhand/open-swarm/issues/590) — CLI Folder / cwd UI. Success #3 (“unset → existing default”) **must not** lock process CWD as the API/WS default. C-H1 is the backend confinement hole underneath.
- [#572](https://github.com/matthewhand/open-swarm/issues/572) — “Restored session” status for every kind. Adjacent to C-H7 honesty, not a substitute.
- [#449](https://github.com/matthewhand/open-swarm/issues/449) — CLI session-start status line timing.
- [#468](https://github.com/matthewhand/open-swarm/issues/468) / [#469](https://github.com/matthewhand/open-swarm/issues/469) — Select / New session UX.
- [#463](https://github.com/matthewhand/open-swarm/issues/463) — Herdr SSH-shaped management. Adjacent to C-H4, different REQ.
- Surface A already filed [#601](https://github.com/matthewhand/open-swarm/issues/601) (team `?session=`). Surface B filed [#607](https://github.com/matthewhand/open-swarm/issues/607) (Add-agent rail seat).

---

## Surface map (what “C” is today)

| Piece | Role |
|-------|------|
| `src/swarm/core/cli_catalog.py` | Built-in CLI argv, `SESSION` resume policy, `which_cli` / `host_cli_path`, `LIST_MODELS` argv table, pinned `CLI_MODELS`. |
| `src/swarm/core/cli_adapter.py` | Launch, token sub, resume insert, `cwd=workdir or os.getcwd()`. |
| `src/swarm/core/cli_models.py` | Live list-models probe for Settings / Chat dropdowns. Still uses bare `shutil.which`. |
| `src/swarm/core/cli_sessions.py` | Sanitize + persist CLI ids on chat JSON (`cli_sessions`). |
| `src/swarm/core/session_policy.py` | REQ-65 on-mode; reads **settings** `cli_session_id`, not chat JSON. `_ACTIVE` is in-process. |
| `src/swarm/core/workdir.py` + `blueprints/common/cli_fusion_support.py` | Confine client paths. Blank + `required=False` → `None` → process CWD. |
| `src/swarm/core/remotes.py` | Settings catalog + `operate()`. Herdr **send** is a stub. |
| `src/swarm/core/remote_teams.py` | Sidebar/chat HTTP remotes + local `herdr` argv. Can send `API_AUTH_TOKEN` to peers. |
| `src/swarm/views/api_views.py` | `GET /v1/cli-agents/` (catalog, **no** `installed`/`configured`). `GET /v1/models/` lists **blueprint ids**. |
| `GET /v1/cli-agents/<cli>/models/` | Live probe → `{models, warning?}`. |
| Chat dropdowns (`ChatPage.tsx`) | Consumer of the above. In scope only as the **backend contract**. |

Session start (adapter/API, not Surface A persist):

| Surface | Who creates | When cwd/workdir is applied |
|---------|-------------|-----------------------------|
| `POST /v1/agents/<id>/sessions/` | `allocate_task_session` (memory id only) | never |
| `GET /chat/thread/` | nobody; reused `agt-{pk}-{agent}` | never |
| WS `ws/ai-demo/<id>/` | Django row on first save | only if client `params` include workdir **and** the blueprint confines it |
| `POST /v1/chat/completions` | new request | inside blueprint `run()` |
| `swarm-cli moa` | n/a | confined **before** run; `--cwd` optional |

---

## HIGH findings

Six child Issues for CoS (drafts at the bottom). Suggested first wave (2–3): **C-H1, C-H3, C-H6**.

### C-H1 — Unset CLI/API workdir is process CWD; AUTH.md claims a confined temp

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `resolve_workdir()` in `src/swarm/blueprints/common/cli_fusion_support.py`; `CliAdapter.stream_run()` in `src/swarm/core/cli_adapter.py`; `CliAgentBlueprint.run()`; claimed in `docs/AUTH.md` §5 |
| **Evidence** | AUTH.md: “Unset write workdirs get a per-run temp directory under that root.” CLI fusion does the opposite when `required=False` (the default every CLI blueprint uses): blank `workdir`/`cwd` returns `None`. The adapter then runs in `os.getcwd()`. WebSocket chat never sets workdir. Catalog CLIs are `mode: write` plus `--always-approve` / `--yolo` / `--dangerously-*`. An API/WS CLI turn with no `params.workdir` can read/write the Django process directory (often the repo or `/app`). `tests/core/test_workdir.py::test_cli_fusion_support_resolve_workdir` **asserts** `resolve_workdir({}) is None` — that encodes the hole. Related: `software_dev._workspace_root()` uses raw `params.workdir` or `Path.cwd() / ".software_dev_ws"` with no `resolve_confined_workdir`; MoA `--act-write` opens an unconfined path (`src/swarm/core/moa/cli.py`). |
| **Suggested fix Issue title** | Confine CLI/API write workdirs — do not default to process CWD (REQ-171 / #596) |
| **Test** | **Weak / missing.** Fusion test locks `None`. No test that API/WS CLI refuses process CWD. `#588` Folder UI must not treat “existing default” as server CWD. |
| **Coordinate** | [#588](https://github.com/matthewhand/open-swarm/issues/588). Do not fight the Folder field; change the **unset** backend default. |

```33:57:src/swarm/blueprints/common/cli_fusion_support.py
def resolve_workdir(...):
    ...
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        if not required:
            return None
        return str(resolve_confined_workdir(None, create=create))
```

```446:451:src/swarm/core/cli_adapter.py
        effective_workdir = (
            _apply_tokens(cfg.cwd, prompt, workdir or os.getcwd())
            if cfg.cwd
            else (workdir or os.getcwd())
        )
```

---

### C-H2 — Auto-run cleanup can delete a user workspace named `run-<12 hex>`

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `_looks_like_auto_run_dir()`, `cleanup_run_workdir()`, `prune_stale_run_workdirs()` in `src/swarm/core/workdir.py` |
| **Evidence** | Delete grant is marker **or** name match. A user dir `workspaces/run-deadbeefcafe` (no `.swarm-auto-run` marker) is removed by `cleanup_run_workdir` and by opportunistic prune on every blank `resolve_confined_workdir()` (`prune_stale=True` default). Docstring says it “Never deletes user-provided workspace paths.” |
| **Suggested fix Issue title** | Require auto-run marker before deleting workdirs (REQ-171 / #596) |
| **Test** | **Missing.** `test_cleanup_run_workdir_refuses_user_path` uses `"user-project"`. `test_cleanup_run_workdir_none_and_missing` uses a *missing* `run-deadbeefcafe`. No test that an existing user `run-<12hex>` is kept. |

```94:97:src/swarm/core/workdir.py
def _looks_like_auto_run_dir(path: Path) -> bool:
    if (path / AUTO_RUN_MARKER).is_file():
        return True
    return bool(_AUTO_RUN_NAME.match(path.name))
```

---

### C-H3 — `remote_teams` authenticates to foreign hosts with this server’s API token

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `chat_remote()`, `_http_get_json()` in `src/swarm/core/remote_teams.py` |
| **Evidence** | `token = api_key or os.getenv("REMOTE_TEAM_API_KEY") or os.getenv("API_AUTH_TOKEN")`. Discovery (`_http_get_json`) also falls back to `API_SERVER_KEY`. `remotes.py` correctly uses per-remote `api_key`. `remote_teams` can send this process’s bearer to Hermes / OMB / Rakazo / DSH during default discovery (on outside pytest) and chat. Credential leak plus wrong auth on the peer. |
| **Suggested fix Issue title** | Stop sending API_AUTH_TOKEN to remote harnesses (REQ-171 / #596) |
| **Test** | **Missing.** `test_chat_remote_parses_openai_payload` never asserts headers. `test_expand_http_children_from_catalog` stubs discovery. |

```157:159:src/swarm/core/remote_teams.py
    token = api_key or os.getenv("REMOTE_TEAM_API_KEY") or os.getenv("API_AUTH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
```

---

### C-H4 — Two Herdr stacks; `operate` send is a stub; sidebar ignores `remotes.herdr`

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `_herdr_send()` / `operate()` in `src/swarm/core/remotes.py`; `chat_herdr()` in `src/swarm/core/remote_teams.py`; `HerdrClient` in `src/swarm/herdr/client.py` |
| **Evidence** | Settings / `swarm-cli remotes` persist `remotes.herdr` and list via HTTP `GET /agents`. Send always returns `ok=False` with `gap="herdr_send_via_cli"`. Chat/sidebar uses a **different** wrapper: local `herdr` on PATH, no `--remote`, no `HerdrClient.from_remote_config`, no blocked preflight. A configured remote Herdr is listed in Settings and unused by the rail. `docs/REMOTE_HARNESSES.md` omits Herdr even though `REMOTE_IDS` includes it. |
| **Suggested fix Issue title** | One Herdr client for list + send; stop stubbing operate (REQ-171 / #596) |
| **Test** | **Theatre / weak.** `test_kind_id_is_herdr` / `test_herdr_not_configured_constant_mentions_settings` are string locks. `test_chat_herdr_prompt_then_read` only checks `"prompt"` / `"read"` in argv. |
| **Coordinate** | [#463](https://github.com/matthewhand/open-swarm/issues/463) (SSH-shaped Herdr) is a later shape; this Issue is “configured remote actually sends.” |

```1480:1493:src/swarm/core/remotes.py
def _herdr_send(...):
    return OperateResult(
        ...
        ok=False,
        detail=(
            "Herdr send uses HerdrClient (herdr agent prompt), not this HTTP "
            "operate path. ..."
        ),
        gap="herdr_send_via_cli",
    )
```

---

### C-H5 — List-models probe uses stripped PATH; rail/run do not

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `cli_models._resolve_executable`; contrast `cli_catalog.which_cli` / `host_cli_path`; `CliAdapter._resolved_argv` |
| **Evidence** | Daphne-stripped `PATH=/usr/bin:/bin` is a known host bug (`#581` fixed **runs**). Catalog + adapter prepend `~/.local/bin`, `~/.grok/bin`, nvm. List-models still calls bare `shutil.which`. Rail `installed: true` (`rail_cli_rows` → `which_cli`) can be true while `GET /v1/cli-agents/grok/models` returns “CLI not installed” + `models: []`. Chat then fabricates `default` (C-H6). MCP help probe (`cli_mcp.probe_cli_help`) also uses unresolved `"grok"` and caches empty failures. |
| **Suggested fix Issue title** | Resolve list-models / MCP help with which_cli (REQ-171 / #596) |
| **Test** | **Weak / inverted.** `test_which_cli_finds_user_local_bin_when_path_is_stripped` covers catalog only. `test_missing_cli_warns_empty_list` mocks `cli_models.shutil.which`, locking the wrong finder. |

```244:250:src/swarm/core/cli_models.py
def _resolve_executable(...):
    ...
    finder = which or shutil.which
    return finder(argv0)
```

```85:98:src/swarm/core/cli_catalog.py
def which_cli(exe: str) -> str | None:
    found = shutil.which(exe)
    if found:
        return found
    extra = extra_cli_path_dirs()
    ...
        return shutil.which(exe, path=os.pathsep.join(extra))
```

---

### C-H6 — Chat CLI/API dropdowns do not pin the harness; backend contract is invented in tests

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `CliAgentsView` (`api_views.py`); `ModelsListView`; `apply_overrides` / `CliAgentBlueprint.run`; `ChatPage.tsx` send + `availableCliModels`; `cliAgentContext.ts` |
| **Evidence** | Three stacked defects, one user-visible “dropdowns work” lie after `#593`: |
| | **1. Catalog GET has no host discovery.** `GET /v1/cli-agents/` returns `clis`, `catalog`, `rail`, `list_models` (**argv** table, not ids). No `installed` / `configured` / `default_cli`. `discoverChatClis` prefers those missing fields, else dumps the **entire** static catalog (uninstalled claude/codex/gemini). TS `CliAgentsInfo` also omits them. Unit/e2e tests **invent** `installed`/`configured` (`cliAgentContext.test.ts`, `e2e/cli-dropdown.spec.ts`). |
| | **2. Chat `params.model` is ignored.** Send includes `{ cli, model }` (skips `'default'`). `apply_overrides` only patches timeout. `cli_agent` calls `apply_model` only on inference-profile resolution. Agent Router pins `cli_model`, which Chat never sends. |
| | **3. API “Model” dropdown is a second blueprint picker.** `GET /v1/models/` lists blueprint ids in an OpenAI envelope (`ModelsListView` docstring). Not LiteLLM / `/v1/llm-profiles/` ids. Empty live lists become `['default']`; probe `warning` is never rendered; fallback to `list_models` argv can show `grok` / `models` as option values. |
| **Suggested fix Issue title** | Wire Chat CLI/API model dropdowns to a real pin contract (REQ-171 / #596) |
| **Test** | **Theatre.** `tests/unit/test_req133_cli_api_dropdowns_models.py` greps `data-testid="cli-select"` in TSX. Vitest REQ-133 asserts combobox presence with stub `{ clis: ['antigravity', 'grok'] }`. Playwright `cli-dropdown.spec.ts` is not in CI (C-H9) and stubs fields the view does not emit. No test that `params.model` reaches `apply_model`. |

```612:623:src/swarm/views/api_views.py
        return Response({
            "clis": cli_catalog.catalog_names(),
            ...
            "list_models": {
                n: cli_catalog.list_models_argv(n)
                ...
            },
        })
```

```377:386:src/swarm/blueprints/common/cli_fusion_support.py
def apply_overrides(...):
    """Apply per-request adapter overrides (currently: timeout) to a registry."""
```

```352:355:webui/frontend/src/pages/ChatPage.tsx
    const list = cliModelsQuery.data?.models ?? (cliQuery.data as any)?.list_models?.[currentCli] ?? []
    return list.length ? list : ['default']
```

---

### C-H7 — CLI session resume is split-brain; Pi `--no-session` contradicts resume; on-mode misses chat/WS

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `SESSION["pi"]` + `CATALOG["pi"]` in `cli_catalog.py`; `resume_cli_session_id()` in `session_policy.py`; `put_cli_session` / `get_cli_session` in `cli_sessions.py`; `allocate_task_session`; `DjangoChatConsumer.fetch_conversation` |
| **Evidence** | **Pi:** production cmd includes `--no-session`. Resume inserts `--session <id>` at index 1 **without removing** `--no-session` → `pi --session <id> -p … --no-session …`. `can_resume()` is still true. Catalog notes even say verify runs are ephemeral. |
| | **Two stores:** Settings `cli_session_id` is what `resume_cli_session_id()` reads when `stored` is omitted. Live adapter path writes chat JSON `cli_sessions`. SPA settings field is a no-op for actual `--resume`. Turning new-chat-per-task **off** later can resume an id captured during an “isolated” task because `_remember_session` always writes the default `(user, agent)` file. |
| | **On-mode create is not on the chat path.** Only `POST /v1/agents/<id>/sessions/` mints. GET `/chat/thread/` with `new_chat_per_task` and no cid returns empty messages but the **reused** `conversation_id_for`. `fetch_conversation` loads the Django row **before** the on-mode empty-disk branch — if that row exists (normal after any prior chat), the “new task” first message appends to the old transcript. `allocate_task_session` does not write an empty chat file; `_ACTIVE` is per-worker memory. |
| **Suggested fix Issue title** | One CLI session store; honour on-mode on chat/WS; fix Pi resume argv (REQ-171 / #596) |
| **Test** | **Weak / split.** `test_every_catalog_cli_documents_session_resume` only checks `resume_argv` exists — never builds full argv (Pi bug cannot fail). `test_session_policy.py` hits settings store; `test_cli_sessions.py` hits chat_store; nothing asserts they are the same id. Allocate tests never hit `fetch_conversation` + existing Django row. |
| **Coordinate** | Surface A H2/H4/H5 are persist/hydrate. This is **adapter resume + REQ-65 mint**. [#572](https://github.com/matthewhand/open-swarm/issues/572) is status copy only. |

```161:166:src/swarm/core/cli_catalog.py
    "pi": {
        "cmd": ["pi", "-p", "--mode", "text", "--no-session", "--approve", "{prompt}"],
```

```49:62:src/swarm/core/session_policy.py
def resume_cli_session_id(...):
    if stored:
        return text or None
    return stored_cli_session_id(agent_id)
```

```715:735:src/swarm/consumers.py
            chat = ChatConversation.objects.get(...)
            ...
            return list(messages)
        except ChatConversation.DoesNotExist:
            ...
            if agent_id and is_new_chat_per_task(agent_id):
                ...
                return []
```

---

### C-H8 — User prompt and session id are raw argv; `{workdir}` is substituted inside the prompt

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `_apply_tokens` / `_build_invocation` in `cli_adapter.py`; `sanitize_cli_session_id` in `cli_sessions.py`; positional `{prompt}` in opencode / pi / codex catalog cmds |
| **Evidence** | No shell, but user text is still a raw argv element. OpenCode / Pi / Codex put `{prompt}` in a **positional** slot. A prompt of `--help`, `--model evil`, or `--session other-id` is parsed as flags. `_apply_tokens` does `value.replace("{prompt}", prompt).replace("{workdir}", workdir)` — if the user writes `see {workdir}`, that becomes the real absolute cwd **inside** the CLI prompt, env values, and cwd template. Session ids matching `^[A-Za-z0-9._:-]{1,128}$` allow `--help`, `..`, `.`. Pi documents `--session` as `<path|id>`. `resume_cli_session_id(..., stored=)` returns unsanitized settings text. |
| **Suggested fix Issue title** | Treat CLI prompts and session ids as untrusted argv (REQ-171 / #596) |
| **Test** | **Missing.** Sanitize tests reject `../etc/passwd` (`/`) but not `--help` or `..`. Adapter tests use `"hello world"`. Zero tests for `_apply_tokens`. |

```240:241:src/swarm/core/cli_adapter.py
def _apply_tokens(value: str, prompt: str, workdir: str) -> str:
    return value.replace(PROMPT_TOKEN, prompt).replace(WORKDIR_TOKEN, workdir)
```

```25:28:src/swarm/core/cli_sessions.py
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
```

---

### C-H9 — Vitest and Surface C e2e never gate merges (cross-cutting)

| Field | Value |
|-------|--------|
| **Severity** | HIGH (test quality — not a product runtime bug) |
| **File / area** | `.github/workflows/python-pytest.yml` frontend job; `.github/workflows/visual-regression.yml` `if: false`; `webui/frontend/package.json` `"test": "vitest run"` |
| **Evidence** | Wave 1 **D-18** said Vitest runs in the visual job. That job is now hard-skipped (`if: false`, REQ-89 HOLD). Python Tests `frontend` job builds the SPA and runs **one** Playwright file: `e2e/chat-send.spec.ts`. Not in CI: Vitest (including REQ-133 ChatPage / `cliAgentContext`), 14 other Playwright specs (`cli-dropdown`, `chrome`, `settings-sheet`, …), `tests/e2e_visual`, `tests/system/*.sh`. Coverage `--cov-fail-under=0` cannot fail. A green `main` Python matrix does not mean dropdowns, rail, or session policy work. |
| **Suggested fix Issue title** | Gate Vitest on PRs; stop treating REQ-* source locks as coverage (REQ-171 / #596) |
| **Test** | n/a — this *is* the missing gate. Prior D-03 partially fixed (`chat-send` only). D-18 is **worse** than wave 1. |

---

## MEDIUM findings

| ID | Why | Test | Suggested later ticket |
|----|-----|------|------------------------|
| **C-M1** | OpenCode resume insert is 1 → `opencode --session <id> run …` not `opencode run --session`. Codex is the only entry that inserts after the subcommand. | `test_every_catalog_cli_documents_session_resume` never builds full argv. | Fold into C-H7 or a catalog-argv honesty ticket. |
| **C-M2** | `extract_session_id` last-path-wins. Defaults still add `.session` after per-CLI `.id`. JSON `{"session":"good","id":"msg_abc"}` stores `msg_abc`. | `test_extract_session_id_from_jsonl_last_wins` checks last **blob**, not last **path**. | Same ticket as C-H7. |
| **C-M3** | Grok model / MCP / native-consensus flags appended **after** `-p {prompt}`. Catalog comments say flags must sit before `-p`. | `test_with_model_pins_grok_dash_m` asserts `cmd[-2:]` — locks wrong placement. | Fold into C-H6 pin contract. |
| **C-M4** | API MoA aliases `workdir`≡`cwd` and always mints a temp dir; CLI `--cwd` is optional panel read context. Hybrid/orchestrator `finally` **deletes** auto workdirs so `meta.writes` point at gone files. | Cleanup is **required** by `test_hybrid_moa_cleans_auto_workdir`. | Split API cwd vs workdir; do not auto-clean write blueprints. |
| **C-M5** | `PARAM_ISOLATE` is never read. Consensus maps `workdirs=dict.fromkeys(names, workdir)` so self-consensus seats share one dir. | No isolate tests. | Implement isolate or delete the param + CLI_FUSION.md claim. |
| **C-M6** | `params.workdir` / `params.cwd` are unvalidated JSON. Escape becomes assistant text + HTTP 200, not 400. `ALLOW_UNRESTRICTED_WORKDIR` is process-global (API host can inherit a shell export). | Blueprint unit tests for hybrid_moa escape; no `/v1/chat/completions` 400. | Validate at serializer; ignore unrestricted flag on API unless explicit. |
| **C-M7** | Dual remote catalogs: `load_all_remotes` still returns hermes/omb/rakazo defaults (LAN `198.51.100.36:8642`); `remote_teams` uses different default URLs and expands live children outside pytest. Tests **assert** unconfigured remotes appear. | `test_listed_specs_always_include_catalog` freezes the inconsistency. | Team/list/health = `configured_remote_ids` only. Do not fight #578 kind-bases. |
| **C-M8** | `agy` / `pi` are first-class `SIDEBAR_CLIS` but absent from `LIST_MODELS`. Agent Router uses stale pinned `CLI_MODELS`. `codex`/`pi` have no `MODEL_FLAG` so `apply_model` is a no-op. | `test_every_catalog_cli_documents_a_list_models_probe` was narrowed to grok/claude/gemini/codex/opencode so adding agy/pi did not fail CI. | Extend LIST_MODELS + MODEL_FLAG; live probe for Router. |
| **C-M9** | `mint_task_conversation_id` slices `[:128]` after a long `agent_id`, dropping the unique suffix. Concurrent tasks can share one cid. | Tests use `"worker"`. | Put uuid first. |
| **C-M10** | `env_allowlist` as a string iterates characters → drops `ANTHROPIC_API_KEY`. `resume_insert=0` execs the flag as argv[0]. JSONL `parse: json:` fails while session extract still stores an id. | Allowlist test uses a real list. Insert tests use `2`. | Validate config types; parse JSONL like session extract. |
| **C-M11** | `cli_persona` / `consensus_fn` / `smoke_check` never pass workdir or session_id — write-mode auto-approve CLIs in `os.getcwd()`. | Echo adapters only. | Temp confined workdir for probes; thread workdir into tools. |
| **C-M12** | Two LLM-profile APIs (`/v1/llm-profiles/` vs `/v1/agents/llm-profiles/`). GET failures return HTTP 200 + empty + `list_models_source: "stub"`. Discovery cache has no TTL. | Settings tests happy-path. | One payload; expire cache; do not 200-empty on exception. |

---

## LOW findings

| ID | Note |
|----|------|
| **C-L1** | `SessionLogger` second-precision filenames (`"w"` overwrite), unsanitized `blueprint_name` in path. **No tests.** |
| **C-L2** | `_ACTIVE` never pruned. `should_resume_external_session("")` is `True`. |
| **C-L3** | nvm extra-PATH is lexicographic (`v9.1.0` > `v20.0.0`). Relative `cmd[0]` resolved vs process cwd, launched in workdir. |
| **C-L4** | MCP `--help` substring `"mcp-config"` false-positive. Auth timeout = UNKNOWN. |
| **C-L5** | `make_temp_workdir` unused. Relative `SWARM_WORKSPACES_DIR` follows CWD. |
| **C-L6** | OMB `operate send` auto-creates a bot when `target` is empty. |
| **C-L7** | `/v1/chat/completions` has no on-mode `previous_response_id` policy (Responses-only, keyed by model name). |
| **C-L8** | `visual-regression.yml` kept in-tree with `if: false` so the check can look required and always skip. |

---

## Cross-cutting test quality

### What can go red on `main` (merge gates)

| Workflow | Gates PRs? | What actually runs |
|----------|------------|--------------------|
| `python-pytest.yml` job `test` | **Yes** | `uv lock --check` + `uv run pytest` on 3.10 / 3.11 / 3.12. Uses **`pytest.ini`**: `--cov-fail-under=0`, `log_cli=true`. |
| `python-pytest.yml` job `frontend` | **Yes** | `scripts/build_frontend.sh` + **one** Playwright spec: `e2e/chat-send.spec.ts`. **No Vitest. No typecheck. No eslint.** |
| `visual-regression.yml` | **No** | Entire job `if: false` (REQ-89 HOLD). |
| `publish.yml` / `docker-io-fly-deploy.yml` | Not a PR gate | PyPI / Docker+Fly. |

`make test` → `scripts/run_tests.py` disables plugin autoload and pins plugins. **CI does not use it.** Dual config (wave 1 D-07 / D-08) is still true. `pyproject.toml` `fail_under = 70` is unused while ini forces `0`.

`FEATURE_STATUS.md` “Test suite health ✅” means “green Python Tests matrix + known golden-journey HOLD”, not “SPA/dropdown/session contracts are gated.”

### What never runs (or never gates)

1. **Vitest** — worse than wave 1 (visual job used to run `npm test`).
2. **14/15 Playwright specs** — only `chat-send.spec.ts` is in CI.
3. **`tests/e2e_visual`** — needs `RUN_E2E_VISUAL=1`; the workflow that would set it is skipped. Source **did** fix wave 1 D-04 / D-11 (Connected / `.btn-primary`); D-05 dark-mode skip remains.
4. **`tests/system/*.sh`** (9 scripts) — not pytest; `test_django_chat.sh` still points at pre-`src/` paths.
5. **Live mem0** — `RUN_MEM0_E2E=1` + real `OPENAI_API_KEY`. Other `tests/integration/*` **do** run (fake backends).
6. Journey capture / screenshot goldens — local only. Caption locks still theatre (D-01 / D-02 / D-14 still true as docs honesty, not re-pixel-verified here).

### Surface C coverage holes

| Path | What’s missing |
|------|----------------|
| Catalog resume argv **assembly** | Never assert full argv for grok/claude/gemini/agy/opencode/pi |
| `{prompt}` / `{workdir}` substitution | `_apply_tokens` untested |
| List-models under stripped PATH | Mocked `shutil.which`; rail vs probe disagree uncovered |
| Chat `params.model` → `apply_model` | No test |
| `/v1/models` as LLM dropdown | Tests lock blueprint-id envelope as correct |
| Dual session stores | Each store tested in isolation |
| On-mode + existing Django row | Allocate tests only |
| Herdr send / remote `Authorization` | Presence / catalog labels |
| `tests/cli/` list-models | All mock `cli_models.list_models` |
| MCP + `stream_run` | Unit `inject_mcp_argv` only; `probe_cli_help` short-circuits under pytest |

### Duplicated / weak unit tests (theatre factory)

`tests/unit/test_req*.py` (24 files) greps TSX/FEATURE_STATUS for testids and `it()` titles. REQ-133 / REQ-132 cannot fail if the strings exist but the runtime contract is wrong (C-H6). They **can** fail a rename.

Prior debt IDs still true vs wave 1 (delta, do not re-open as new product REQs unless listed HIGH above):

| Prior ID | Wave 1 claim | Today |
|----------|--------------|-------|
| D-01 / D-02 / D-14 | Stale screenshot goldens + caption lock | **Still true** as registry theatre |
| D-03 | Playwright e2e never in CI | **Partial:** `chat-send` only |
| D-04 / D-11 | Exact `Connected` / `.btn-primary` | **Fixed in e2e_visual source**; job still HOLD |
| D-05 | Dark-mode skip | **Still true** |
| D-07 / D-08 | Dual pytest + two runners | **Still true**; DEVELOPMENT now names pytest.ini |
| D-18 | Vitest only in visual | **Worse:** visual `if: false` → Vitest never gates |
| D-09 / D-12 / D-15 / D-16 / D-17 | Unused fixtures, slow/live markers | **Still true** (cleanup, not HIGH) |

---

## Test quality scorecard

### What’s good

- REQ-44 probe policy: missing CLI / timeout / nonempty stderr → `{models: [], warning}` + secret redaction. Fixtures for opencode lines and gemini JSON.
- CLI **execution** PATH repair (`which_cli` / `host_cli_path`) and a real stripped-PATH regression test **on the adapter**.
- `apply_model` replace-not-duplicate (`tests/core/test_cli_catalog_model_pinning.py`).
- Adapter launch: timeout + killpg, `aclose` reaping, stderr-vs-stdout deadlock avoidance, allowlist isolation **when the value is a list**.
- Python 3.10–3.12 matrix + `uv lock --check` actually gates merges.
- Chat-send Playwright with mock inference is a small, real browser gate.
- Integration MoA/persona proofs run keyless with fake backends.
- Golden-journey **source** was updated for ChatPage composer (even though CI does not run it).
- `xfail_strict = true` in pytest.ini.

### What’s theatre

- `tests/unit/test_req133_cli_api_dropdowns_models.py` and siblings: substring presence of testids / `it()` titles.
- Frontend unit/e2e that pass **invented** `/v1/cli-agents` fields (`installed` / `configured`).
- `test_every_catalog_cli_documents_session_resume` / `test_every_catalog_cli_documents_a_list_models_probe`: field existence, not assembled argv, and the probe set was **narrowed** so agy/pi would not fail CI.
- `test_with_model_pins_grok_dash_m` locking flags **after** `-p`.
- `test_cli_fusion_support_resolve_workdir` locking blank → `None` (the confinement hole).
- `test_listed_specs_always_include_catalog` locking unconfigured remotes into the team list.
- Coverage `fail_under=70` in pyproject vs `--cov-fail-under=0` in the ini CI uses.
- `visual-regression.yml` `if: false` — a check that cannot go red or green.
- Screenshot / FEATURE_STATUS caption locks that do not execute the product.
- FEATURE_STATUS “Test suite health ✅” while Vitest and 14 Playwright files never run.

### Blind spots (what a green `main` does not prove)

- List-models under Daphne PATH (C-H5) vs rail `installed`.
- Chat model dropdown changing CLI argv (C-H6).
- `/v1/models` ids being LLM models (they are blueprints).
- Unset workdir ≠ server CWD (C-H1).
- REQ-65 on-mode on the actual chat/WS first message (C-H7).
- Remote `Authorization` headers (C-H3).
- Herdr send (C-H4).
- Prompt/session argv injection (C-H8).
- SPA behaviour covered only in Vitest / laptop Playwright.

---

## Suggested fix waves (CoS; max 2–3)

1. **Wave 1 (safety):** C-H1 workdir confinement + C-H2 marker-only delete + C-H3 stop leaking `API_AUTH_TOKEN`.
2. **Wave 2 (dropdown honesty):** C-H5 `which_cli` on probes + C-H6 pin contract (`params.model` / host discovery / do not use `/v1/models` as LLM ids).
3. **Wave 3 (session):** C-H7 one store + on-mode on chat/WS + Pi argv; fold C-M1/C-M2.
4. **Wave 4 (harness + argv):** C-H4 one Herdr client; C-H8 `--` before positional prompts + sanitize `-`/`..`.
5. **Wave 5 (tests, can parallelise):** C-H9 Vitest in `python-pytest` frontend job (or a dedicated job). Do **not** re-enable golden-journey in the same wave. Optionally add `e2e/cli-dropdown.spec.ts` once the backend emits real `installed`/`models`.

Own-diff CI only. No Neon. No secrets.

---

## HIGH Issue drafts (for CoS — `gh` is read-only)

File these as child Issues of [#596](https://github.com/matthewhand/open-swarm/issues/596). Do not file MED/LOW unless a later REQ needs them.

### Issue 1 — Confine CLI/API write workdirs (C-H1 + C-H2)

**Title:** Confine CLI/API write workdirs — do not default to process CWD (REQ-171 / #596)

**Intent:** Write-capable CLI/API runs stay under `SWARM_WORKSPACES_DIR`. Unset workdir is a marked per-run temp (or an explicit Folder from [#588](https://github.com/matthewhand/open-swarm/issues/588)), never the Django process CWD. Cleanup never deletes a user dir just because it is named `run-<hex>`.

**Success:**

1. Blank `params.workdir`/`cwd` on `cli_agent` / fusion / WS chat mints or requires a confined path; `CliAdapter.stream_run` does not fall back to `os.getcwd()` on the API/WS path.
2. `cleanup_run_workdir` / prune require `AUTO_RUN_MARKER`; an existing `workspaces/run-deadbeefcafe` **without** the marker survives.
3. AUTH.md matches the code.
4. Tests bite: API/WS CLI with no workdir is confined; user `run-*` dir is kept; `#588` Folder when set is used.

**Constraints:** Look-only audit is #596 surface C. Coordinate #588 (Folder UI) — do not lock “unset = process CWD”. No Neon. No secrets. Own-diff CI only. Do not fight #576 desktop packaging.

**Owner:** CoS assigns a Cursor implementer (wave 1).

**Parent:** #596 (REQ-171). Evidence: this file C-H1, C-H2.

---

### Issue 2 — Stop sending API_AUTH_TOKEN to remotes (C-H3)

**Title:** Stop sending API_AUTH_TOKEN to remote harnesses (REQ-171 / #596)

**Intent:** Peer HTTP remotes authenticate only with that remote’s key.

**Success:**

1. `chat_remote` / `_http_get_json` never fall back to `API_AUTH_TOKEN` or `API_SERVER_KEY`.
2. Use `remotes.<id>.api_key` / `REMOTE_TEAM_API_KEY` only.
3. Tests assert `Authorization` is absent when those are unset, and equals the **per-remote** key when set.

**Constraints:** Do not rewrite kind-bases (#578). No live LAN. No secrets in repo.

**Owner:** CoS assigns (wave 1 with Issue 1 if capacity).

**Parent:** #596. Evidence: C-H3.

---

### Issue 3 — Wire Chat CLI/API model dropdowns (C-H5 + C-H6)

**Title:** Wire Chat CLI/API model dropdowns to a real pin contract (REQ-171 / #596)

**Intent:** The CLI/API Model controls change the next run. Empty/failed probes look empty (or show `warning`), not a fake `default`. Host discovery uses the same PATH as runs.

**Success:**

1. `cli_models` / MCP help resolve via `which_cli` + `host_cli_path`.
2. `GET /v1/cli-agents/` exposes host discovery the SPA already looks for (`installed` / `configured` / rail), **or** the SPA reads `rail` only — one contract, tests use the real payload.
3. Chat send `params.model` (or a renamed `cli_model`) reaches `apply_model` for CLIs that have `MODEL_FLAG`.
4. API Model dropdown is LLM/profile ids (or the control is removed/relabelled as blueprint). `/v1/models` stays honest as blueprints if OpenAI clients depend on it.
5. Tests: stripped PATH probe finds `~/.local/bin/grok`; `params.model` appears in assembled argv; empty probe does not render option `default` without a warning.

**Constraints:** Do not fight #577 keybinding tips or #593 chrome. Frontend contract change is allowed; this is the backend+wire, not a visual restyle.

**Owner:** CoS assigns (wave 2).

**Parent:** #596. Evidence: C-H5, C-H6.

---

### Issue 4 — One CLI session store + on-mode on chat/WS + Pi argv (C-H7)

**Title:** One CLI session store; honour on-mode on chat/WS; fix Pi resume argv (REQ-171 / #596)

**Intent:** Resume uses one id store. New-chat-per-task means a new CLI session on the path users actually send. Pi can resume.

**Success:**

1. Production Pi cmd does not include `--no-session` (keep it on smoke/verify only). Resume strips conflicting flags. Full assembled argv is tested for every catalog CLI.
2. `resume_cli_session_id` reads the same store the adapter writes (`cli_sessions`), after `sanitize_cli_session_id`.
3. On-mode GET `/chat/thread/` / WS `fetch_conversation` mint or refuse reuse **before** loading the old Django row. `allocate_task_session` persists an empty record.
4. Tests: on-mode + existing Django row does not append to the old transcript; settings `cli_session_id` alone does not resume if chat JSON is empty (or they are unified).

**Constraints:** Do not re-do Surface A persist-on-disconnect (#600 H2). Distinct from #572 status copy. No Neon.

**Owner:** CoS assigns (wave 3).

**Parent:** #596. Evidence: C-H7.

---

### Issue 5 — One Herdr client (C-H4)

**Title:** One Herdr client for list + send; stop stubbing operate (REQ-171 / #596)

**Intent:** A configured `remotes.herdr` can list and send. Sidebar and Settings use the same client.

**Success:**

1. `operate(..., "send")` calls `HerdrClient.from_remote_config` (or delete the operate path and document CLI-only).
2. `chat_herdr` delegates to that client (`check_blocked=True`, single `--until`).
3. Tests assert send argv/headers against the configured remote, not `"prompt" in argv`.

**Constraints:** Coordinate #463 (SSH shape) — this Issue is “the stub works,” not SSH. No live LAN in CI.

**Owner:** CoS assigns (wave 4).

**Parent:** #596. Evidence: C-H4.

---

### Issue 6 — Untrusted CLI argv (C-H8)

**Title:** Treat CLI prompts and session ids as untrusted argv (REQ-171 / #596)

**Intent:** User text cannot become extra flags. Session ids cannot be `--help` or `..`.

**Success:**

1. Insert `--` before positional prompts, or pass via stdin / `-p=`.
2. `_apply_tokens` does not substitute tokens **inside** the replacement values.
3. Sanitize rejects leading `-`, `.`, `..`. `resume_cli_session_id` sanitizes.
4. Tests: prompt `--model evil` does not appear as a flag; prompt `{workdir}` stays literal; session id `--help` is rejected.

**Constraints:** No change to catalog write/auto-approve flags in this ticket (that is C-H1/C-M11).

**Owner:** CoS assigns (wave 4 with Issue 5 or wave 5).

**Parent:** #596. Evidence: C-H8.

---

### Issue 7 — Gate Vitest (C-H9)

**Title:** Gate Vitest on PRs; stop treating REQ-* source locks as coverage (REQ-171 / #596)

**Intent:** SPA contract tests can go red on `main`. Source-grep REQ tests are not a substitute.

**Success:**

1. `python-pytest.yml` frontend job (or a sibling job) runs `npm test` (Vitest) after `npm ci`.
2. Do **not** re-enable `visual-regression.yml` / golden-journey in this Issue.
3. Optional follow-up: add `e2e/cli-dropdown.spec.ts` once Issue 3 emits a real payload; delete or shrink `test_req133_*` greps that only check testids.

**Constraints:** Own-diff CI. Keep the Python 3.10–3.12 matrix off browsers. HOLD golden-journey stays HOLD (REQ-89).

**Owner:** CoS assigns (wave 5; can parallelise with product waves).

**Parent:** #596. Evidence: C-H9 + scorecard.

---

## Out of scope / honesty

- No runtime product change in this PR.
- No `Fixes` / `Closes` on #596.
- No secrets, no Neon, no live LAN.
- Did not recapture screenshots or re-run the HOLD visual job.
- Did not implement desktop PATH merge (#576) or virtualized history (#582).
