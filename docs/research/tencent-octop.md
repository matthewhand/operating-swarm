# #1365 — Tencent Octop AI agents

**Verdict: adapt/adopt — best `remote` candidate in this batch; add impl id `octop`.**

## What it is

**Octop** (`TencentCloud/Octop`, MIT) is a self-hosted, multi-user, multi-agent
AI assistant that runs as **one process** and serves a web dashboard, a CLI, IM
channels (Feishu, DingTalk, QQ, WeChat, Telegram, Discord, WeCom, …), and cron —
all on one control-plane DB under `~/.octop/` (SQLite default, PostgreSQL
optional). Python 3.12+, FastAPI + uvicorn, React dashboard. Version 1.0.2b3 on
PyPI (`pip install octop`).

- Repo: <https://github.com/TencentCloud/Octop>
- Docs: repo `docs/` (architecture.md, acp.md, cli.md, configuration.md, adr/)
- Related libraries: `octop-harness` (agent runtime), `octop-gateway` (IM bridge),
  `octop-memory`, `octop-browser`.

Not to be confused with Octopus Deploy's AI assistant or the "Octopus v3" model
paper. Confirm if disambiguation matters.

## Protocol / SDK / auth surface

Primary source = repo README + `docs/acp.md`:

- **HTTP API** (FastAPI): full programmatic access over **HTTP + SSE + WebSocket**.
  Interactive API docs at `/api/docs`, **disabled by default**
  (`"enable_api_docs": true` in `config.json`). Verified example routes:
  `GET/PUT /api/acp`, `GET/PUT/DELETE /api/acp/{runner_name}`,
  `GET/PUT /api/agents/{agent_id}/acp`, `PUT /api/agents/{agent_id}/acp/tool`.
- **Auth:** **multi-user JWT authentication with an admin role**. First-run setup
  (`octop init`) creates the SQLite DB, JWT secret, and admin account. Docker
  bootstrap writes a generated admin password to `credential.txt`, or accepts
  `OCTOP_DEFAULT_PASSWORD` (≥8 chars, letters+digits). Per-user agents and
  workspaces (JWT isolation).
- **CLI (`octop`):** `octop run`, `octop init`, `octop agent`, `octop chats`,
  `octop acp`, `octop channel`, `octop cron`, `octop models`, `octop skills`,
  `octop plugin`, `octop backup`, `octop service`.
- **ACP (Agent Client Protocol), stdio JSON-RPC only — no HTTP ACP endpoint:**
  - Inbound: `octop acp --agent main` exposes an Octop agent as an ACP server for
    Zed/OpenCode (sessions map to `thread_id`).
  - Outbound: the `acp_runner` tool delegates to OpenCode, CodeBuddy, Claude Code,
    Codex, Cursor CLI, Kimi, Pi (`action=list|start|message|respond|status|close`).
- **Agent/team model:** per-user **experts** (each with own workspace, providers,
  channels, cron, 16 MBTI persona templates); **AgentTeams** *(beta)* — a
  coordinator schedules member experts for multi-step work
  (`docs/expert-teams.md`).
- **Extensibility:** Connectors (OAuth + MCP gateway), plugins, knowledge base /
  RAG, workspace backends (local disk, Docker sandbox, PostgreSQL, COS/S3).
- **Providers:** OpenAI-compatible APIs, DashScope (Qwen), Ollama, other presets —
  configured per agent (`octop models`, `octop provider`).

## Mapping to Operating Swarm

Octop is a self-hosted HTTP agent/assistant service → the **canonical `remote`**
shape (health / list / send), matching Hermes / TrueForge / Open WebUI:

- **Kind:** `remote`, new impl id `octop`.
- **AgentTeams** (coordinator + members) maps conceptually to OS **`team`**
  rosters, but it must remain an Octop-internal concept — OS should treat an Octop
  deployment as one remote, not re-model its experts as OS seats.
- **Experts** map to OS `api` blueprints (conceptually); not required for a remote
  adapter.
- **`acp_runner`** is conceptually parallel to OS's CLI delegation; an OS cli seat
  could instead drive `octop acp --agent …` via ACP (stdio) if desired.
- **Model namespace:** a `remote` model is valid **only if the remote's config
  declares it** (`model_namespace._remote_model_valid`). Octop declares
  provider/model per agent, so OS must **not** offer arbitrary model pins for an
  Octop remote — read Octop's `octop models` instead. Its own AGENT_CLIENT_PROTOCOL
  and provider layer stay inside Octop.

## Proposed adapter sketch

```text
src/swarm/core/remote_impls/octop.py   (RemoteHarness)
  health(spec)  -> GET  {base}/api/... health endpoint        (path TBD)
  list(spec)    -> GET  {base}/api/agents                     (shape TBD)
  send(spec, session_id, text)
                -> POST {base}/api/... chat/session message    (path TBD)
                   auth: spec.headers Authorization: Bearer <JWT or API token>

register:
  REMOTE_IMPL_IDS += ("octop",)
  REMOTE_IMPL_CLASSIFIER_IDS += {"octop", "tencent-octop"}
  _IMPL_ALIASES += {"tencentoctop": "octop"}
  REMOTE_IMPL_LABELS["octop"] = "Tencent Octop"
```

Do **not** model Octop's AgentTeams as OS TeamKindBase; keep one remote boundary.

## Open questions / unknowns

- Exact REST paths/schemas for **chat send**, agent list, and session/turn state —
  **unverified** (only the ACP routes are confirmed; `/api/docs` is off by
  default and not fetched).
- Whether Octop issues **long-lived API tokens** for headless clients, or only
  interactive JWT login — **unverified**.
- SSE/WebSocket message envelopes — **unverified**.
- AgentTeams API stability (documented **beta**) — **unverified**.
- Since Octop exposes ACP over **stdio only** (no HTTP ACP), an OS `remote` needs
  the REST API, not ACP — confirm REST parity with the CLI/UI — **unverified**.
- Default `enable_api_docs` off means OS may need its own client against
  undocumented routes; consider asking Tencent for a stable OpenAPI contract.

## Sources

- <https://github.com/TencentCloud/Octop>
- <https://github.com/TencentCloud/Octop/blob/main/docs/acp.md>
- <https://github.com/TencentCloud/Octop/blob/main/docs/architecture.md>
- <https://pypi.org/project/octop/>
- <https://github.com/TencentCloud/octop-harness>
