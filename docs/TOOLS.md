# Tools & the injectable Filesystem Toolset

Operating Swarm blueprints get capabilities three ways today:

| Mechanism | Where | Used by |
|---|---|---|
| `function_tool()` (openai-agents SDK) | native Python blueprints, `Agent(tools=[...])` | `rue_code`, `codey`, `geese`, … |
| MCP servers (`mcpServers` in `swarm_config.json`) | `required_mcp_servers` / `tool_requirements` metadata | `whiskeytango_foxtrot`, `stewie`, … |
| Skills (prompt-injection + asset staging) | `params.skill`, CLI-agnostic | any `cli_*` blueprint |

`cli_*` blueprints have **no native tools** — they inherit whatever the wrapped
CLI (claude/qwen/opencode) can do. That makes file inspection via `cli_agent`
slow and unreliable (the CLI runs a full agentic loop, ~130–200s, and often
can't read files in non-interactive mode).

## The Filesystem Toolset

`swarm/core/filesystem_toolset.py` is a **generic, injectable, safety-first**
filesystem accessor.

### Permission levels
- `none` — all ops denied.
- `readonly` (default) — `read` / `list` / `stat` / `tree`.
- `readwrite` — adds `write` (opt-in only; a per-request param can never
  *escalate* beyond what config grants).

### Safety
- **Path allow-listing**: every op resolves to a real path (symlinks followed)
  that must sit inside a configured `allowed_paths` root — escape attempts raise
  `PathNotAllowed`.
- **Size limits**: `max_read_bytes`, `max_write_bytes`, `max_list_entries`.
- **Audit logging**: every op logs to the `swarm.filesystem.audit` logger.

### Declaring it in `swarm_config.json`
```json
"filesystem": {
  "permission": "readonly",
  "allowed_paths": [
    "~/.config/swarm",
    "~/open-swarm",
    "~/.local/share/swarm"
  ],
  "max_read_bytes": 1000000,
  "max_list_entries": 2000,
  "audit": true
}
```

### Injecting into a native blueprint
```python
from swarm.core.filesystem_toolset import FilesystemToolset

fs = FilesystemToolset.from_config(self._config)        # reads the "filesystem" block
agent = Agent(..., tools=[*fs.as_function_tools(), other_tool])
```
`as_function_tools()` returns `function_tool`-wrapped `fs_read_file`,
`fs_list_dir`, `fs_stat` (and `fs_write_file` when `permission == "readwrite"`).
It returns `[]` if the agents SDK isn't installed, so importing is always safe.

### Using it directly (no LLM)
```python
fs = FilesystemToolset.from_config(config, overrides=params)
text = fs.read("~/.config/swarm/swarm_config.json")
```

## `fs_introspect` blueprint — fast, reliable introspection

`model: "fs_introspect"` exposes the toolset over the OpenAI-compatible API with
**no LLM call** — sub-second, deterministic. Built so connector clients (e.g.
Grok) can inspect config/logs/code without CLI timeouts.

```
POST /v1/chat/completions
{"model":"fs_introspect","messages":[{"role":"user","content":"read ~/.config/swarm/swarm_config.json"}]}
```

Grammar (first word, else inferred): `read|cat <path>`, `list|ls <path>`,
`stat <path>`, `tree <path>`, `grep <pattern> <path>`, `find <glob> in <dir>`,
`head <path> [n]`, `tail <path> [n]` (log inspection),
`read <path> <start> <end>` (line range), or a bare path. Structured params also
work: `params: {"op":"read","path":"...","start_line":1,"end_line":40}` and
`{"op":"grep","pattern":"...","path":"..."}`. `grep`/`find` skip VCS/cache/binary
noise (`.git`, `__pycache__`, `.pyc`, …).

Measured on the oracle host: `read swarm_config.json` returns in **~0.45s** vs
**~133–200s** for the same ask routed through `cli_agent`.

## Browser (this machine) — REQ-45

`swarm.core.browser_control` is a small Playwright driver for **this machine**
(launch Chrome / attach via `SWARM_CHROME_CDP`, then navigate + snapshot). The
same module is what an agent uses from CLI, API, or a remote seat. Inject
`StubBrowser` in tests. Missing Playwright or Chrome returns `ok: false` and
does not crash.

Sandbox / Docker and SaaS **browser providers** are not implemented (UI rows
are grey TODO). OMB and Rakazo remain **remote harness members** (`consult_omb`
/ `consult_rakazo`) — that is not a local sandboxed Chrome. Desktop/OS control
is out of scope (#341).

## Choosing the right model for a task
- **Inspect a file / dir / config / log** → `fs_introspect` (instant, reliable).
- **Reason about / transform code** → `cli_agent` (or `cli_fusion` / `cli_roundtable`
  for higher-quality design work) — but prefer the async `/v1/responses`
  pattern for anything long-running so the connection isn't held open.
