# ADR-014: Herdr's kind — CLI subtype vs. Remote implementation

- **Status:** Proposed — needs operator sign-off (2026-09-17)
- **Date:** 2026-09-17
- **Issue:** [#454](https://github.com/matthewhand/open-swarm-private/issues/454) — decision tracking. Raised by the operator while configuring the Herdr remote on this host, 2026-09-17. Intended to fold into the pending major refactor.
- **Related:** [ADR-011](./011-remote-harness.md) (Remote as abstract harness — the record this one interrogates), [ADR-005](./005-kind-bases.md) / [ADR-006](./006-api-vs-blueprint-kinds.md) (four user-facing kinds), [ADR-012](./012-swarm-cli-tui.md) (`os-cli tui` is Herdr-*like* chrome, not this hop), [#463](https://github.com/matthewhand/open-swarm/issues/463) (Herdr SSH), [HERDR.md](../HERDR.md), [REMOTE_HARNESSES.md](../REMOTE_HARNESSES.md)
- **Amends:** ADR-011 §3 (classifier lock) and §5 (rejected alternatives) **only if** the move is accepted. ADR-011 §7 (Slack) is unaffected.
- **Supersedes:** none.

**Decision (proposed):** **Herdr stays a Remote implementation.** Its **transport** is a CLI subprocess (`herdr …`, local unix socket or SSH hop) — that is already the recorded model and it is the right one. What should change is **composition**: Herdr must stop being offered as a Team *member*, because its panes are externally-owned seats that do not hand off to each other, so a `consult_herdr` specialist misrepresents them.

The operator's observation is **right about transport** and **right about composition**, but **wrong about kind**: "CLI" in this codebase means *the swarm spawns and owns this process*, which is not what Herdr is.

---

## 1. Context

Herdr is the pane session server + CLI at [herdr.dev](https://herdr.dev/). It wraps the coding CLIs already running in panes on a host (`agy` / `pi` / `grok` / …). Open Swarm drives it as a **client**: one hop to the Herdr host, then the official `herdr` CLI there (local unix socket, or SSH when the host is remote). It does not own the panes.

The operator question, verbatim intent: *"we should not call this a 'remote' anymore, instead it is just another type of cli… a cli that is basically a team of agents that don't talk to each other. so we should treat this as an extension of the 'cli' subclass not 'remote'?"*

That is a falsifiable claim, so this ADR answers it with the three axes it actually mixes: **transport**, **ownership**, and **composition**.

---

## 2. What is already true (no change needed)

| Fact | Where |
|---|---|
| Herdr's transport is recorded as CLI, not HTTP | `REMOTE_IMPL_TRANSPORT["herdr"] = "cli"` (`core/remote_harness.py`) — every other impl is `http` |
| Its hop is a subprocess, never a URL | `HerdrClient.build_argv` → `herdr [--remote VALUE] …` (`herdr/client.py`) |
| Local mode needs no SSH | `herdr_mode=local` → `herdr workspace list`; empty `remote` means localhost |
| Its binary is overridable | `HERDR_BIN`, else `shutil.which("herdr")` |
| It has its own persistence + REST surface | `HerdrAgent` model (`herdr_agent` table) + 6 routes under `v1/herdr-agents/` (`views/herdr_api.py`) |

So the *transport* half of the proposal is not a proposal — it is implemented. Any ADR that "moves Herdr to CLI" must explain what it changes beyond a label that is already correct.

---

## 3. The two axes the proposal conflates

| Axis | CLI agent (`cli_agents`) | Herdr |
|---|---|---|
| Who spawns the seat | **The swarm.** Configured `command:` is exec'd per turn | **Herdr.** Panes exist before and after Open Swarm |
| Who owns the lifecycle | Swarm (`cliRunState`, Terminate, REQ-114 `cli_run_state`) | Herdr server; the swarm is a client |
| Boundary | None — direct exec on this host | Always a hop: unix socket locally, SSH remotely |
| Unit of work | One seat, one conversation | A **fleet**: `list` returned 7 members (`w2:pG`, `w2:pD`, `w3:p1`, …) |
| Do seats talk to each other? | n/a | **No.** Panes are independent; there is no handoff |

Herdr is therefore neither: not a CLI agent (it does not spawn or own seats) and not a plain HTTP remote (no HTTP at all). It is a **client of an external seat fleet**.

---

## 4. Options

| # | Option | Verdict |
|---|---|---|
| **A** | Keep status quo: Remote kind *and* Team member (`consult_herdr`) | Reject — the Team-member half is the part that lies (§3) |
| **B** | Move to a CLI subtype: `kind=cli`, reuse `cli_agents` seat plumbing | Reject — conflates "swarm spawns" with "swarm is a client"; requires the refactor in §5 for a label |
| **C** | **Recommended:** keep `kind=remote`; drop Team-member composition for Herdr; surface its seats as a fleet | Accept — fixes the real defect at near-zero cost |

**Recommendation: C.** Take the valid half of the operator's observation (a fleet of seats that do not hand off should not be one consultable agent) without paying §5's cost for a naming change.

**What would flip this to B:** if Herdr ever exposes pane-level `run`/`terminate`/stream semantics matching REQ-114, the seats become the unit of work and the CLI-seat model wins. Today it exposes `prompt` / `read` / `wait` / `get` — client verbs, not ownership verbs.

---

## 5. Cost inventory (if B is chosen anyway)

Measured on `main` @ `9e184b93`:

```bash
grep -rn -i "herdr" --include=*.py src/ | grep -v __pycache__ | wc -l   # 449 across 15 files
grep -rn -i "herdr" webui/frontend/src --include=*.ts --include=*.tsx | wc -l   # 271
grep -rln -i "herdr" tests/ --include=*.py | wc -l                      # 31 files
grep -rln -i "herdr" docs/ | wc -l                                      # 12+ docs
```

| Surface | Size | Why it moves |
|---|---|---|
| `core/remotes.py` | 147 matches | ~40 herdr-specific branches, `RemoteSpec.herdr_mode`, `ssh_host`, `ssh_user`, `ssh_port`, `ssh_identity_env`, `ssh_agent`, `_ENV_HERDR_*`, the `default_spec` row, opt-in catalog, `kind_of_instance` prefix matching |
| `swarm/herdr/` | 113 across `client.py` / `remote.py` / `__init__.py` / `ssh.py` | The whole client package — would become CLI-seat plumbing |
| `views/herdr_api.py` | 36 matches, 6 URL routes | Dedicated REST surface + `HerdrDiscoverAPIView` |
| `core/remote_teams.py` | 34 matches | Roster/member normalisation, `herdr agent list` client |
| `core/swarm_cli.py` | 16 matches | `remotes set herdr --herdr-mode …` flag set |
| `core/agent_kind.py` | 3 matches | **Classifier lock:** `classify_agent_kind` maps `herdr` / `herdr:w3:p1` → `remote`; ADR-011 §3 pins this |
| `views/remotes_api.py`, `urls.py`, `views/web_views.py`, `blueprints/agent_router`, `tui/client.py`, `models/herdr.py` | 43 matches | Catalog, routing, TUI parity, persisted rows |
| `webui/frontend/src` | 271 matches | `classifyAgentKind`, `AGENT_TYPES`, rail hotkeys, add-agent groups, team roster, teammate task, seat normalization |
| Tests | 31 files | Rewritten, not deleted — they encode the current contract |
| Docs | 12+ | `HERDR.md`, `REMOTE_HARNESSES.md`, `diagrams/kind-bases.md`, `QUICKSTART.md`, `ANNOUNCE.md`, taxonomy tree HTML, `FLEET-PATTERNS.md`, several `docs/qa/` pages |

Also required: a data migration for stored `kind=herdr` roster rows and mailbox keys, and an ADR-011 amendment — ADR-011 §5 explicitly lists *"Fifth user-facing kind `herdr`"* as rejected. This direction is not that, but it does reverse the sentence *"Herdr is a Remote implementation, not a fifth kind."*

**Estimate:** not a config change or a rename; it is a cross-stack refactor with a data migration, frontend classifier change, and a docs sweep. It belongs in the major refactor, not a side quest.

---

## 6. Sequencing (if C is accepted)

1. Keep `kind=remote` and `REMOTE_IMPL_TRANSPORT["herdr"]="cli"` as-is — no migration.
2. Stop offering Herdr as a Team member: no `consult_herdr` as_tool specialist, and exclude it from `agent_team.members` placement.
3. Keep `list` as the fleet view (it already returns typed members). Add seat-level labelling only if a real need appears.
4. Record the CLI-transport fact in the UI where the impl is listed, so operators are not surprised that it is not HTTP.

---

## 7. Rejected alternatives

| Option | Why not |
|---|---|
| Fifth user-facing kind `herdr` | Not what the operator asked for, and ADR-011 §5 already rejects it. Adds a kind without fixing composition. |
| `kind=cli` + reuse `cli_agents` spawn/terminate | Herdr does not spawn; Open Swarm prompts panes it does not own. Reusing the lifecycle would either be dead code or would misreport seat state. |
| Merge Herdr into `os-cli tui` | ADR-012 is explicit: the TUI is Herdr-*like* chrome and does not SSH to a Herdr host. Different hop. |
| Leave everything as-is (option A) | Keeps a Team member that cannot hand off, and a `consult_herdr` tool that implies one agent where there is a fleet. |

---

## 8. Cross-links

- [ADR-011](./011-remote-harness.md) — Remote as abstract harness (this amends §3/§5 if accepted)
- [HERDR.md](../HERDR.md) — local vs SSH hop, verbs
- [REMOTE_HARNESSES.md](../REMOTE_HARNESSES.md) — implementation table, operate gaps
- [diagrams/kind-bases.md](../diagrams/kind-bases.md) — kind-base tree (CLI / API / Blueprint / Remote)
- [ADR-012](./012-swarm-cli-tui.md) — `os-cli tui`, the Herdr-like chrome that is *not* this hop
