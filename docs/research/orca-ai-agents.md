# #1364 — ORCA AI agents integration

**Verdict: watch — drive the `orca` CLI / skill first; no stable third-party API for a remote seat.**

**Phase 1:** `skills/orca-cli/` ships the skill plus `drive.py`, which shells
out to the documented JSON commands (`status`, worktree, terminal) and refuses
`orca serve` / `orca account`. Pairing stays out of scope until Orca documents
a third-party API.

## Disambiguation (important)

"ORCA" is ambiguous. This brief assumes the most likely target given the sibling
issues (#1367 t3code, both local coding-agent control surfaces): **Orca ADE
("Agent Development Environment") by Stably**, repo `stablyai/orca`,
<https://github.com/stablyai/orca>, <https://www.onorca.dev>, MIT, ~79k stars as
of fetch.

Other products sharing the name — **not evaluated here**:

- Orca Security "Orca AI" (cloud security reasoning layer) — <https://orca.security/platform/orca-ai/>
- StreamNative "Orca Agent Engine" (event-driven agents) — <https://streamnative.io/blog/what-is-orca-agent-engine>
- Orca AI maritime situational awareness — <https://www.orca-ai.io>

If the issue author meant one of those, this brief does not apply. **Confirm the
intended ORCA before work.**

## What it is

Orca ADE is a desktop (macOS/Windows/Linux) + mobile + web **agent development
environment**. It runs Codex, Claude Code, OpenCode, Cursor, Grok, and many other
CLI agents **side-by-side, each in its own git worktree**, with diff review,
annotate-AI-diff, terminal splits, GitHub/Linear/Jira drawers, SSH worktrees,
computer use, and a mobile companion. "Works with any CLI agent — if it runs in a
terminal, it runs in Orca."

## Protocol / SDK / auth surface

Primary sources: repo README and <https://www.onorca.dev/docs>:

- **CLI (`orca`)** is the automation surface, with JSON output throughout:
  `orca status --json`, `orca worktree create|ps|current|set|rm`,
  `orca terminal list|read|send|wait|create|split`,
  `orca file open|diff|open-changed`, browser/emulator automation
  (`orca goto|snapshot|click|fill|screenshot`),
  `orca automations` (scheduled), `orca artifacts share|update|list|delete`.
  Docs: <https://www.onorca.dev/docs/cli/overview> and `/docs/cli/reference`.
- **Skills registry + MCP:** `orca skills install --skill orca-cli --skill orchestration`;
  `npx skills add https://github.com/stablyai/orca --skill orca-cli`. See
  `/docs/cli/skills` ("Orca skills registry & MCP").
- **Remote Orca Servers (beta):** `orca serve --pairing-address <addr> [--port 6768]`
  runs a headless runtime; clients pair with a **revocable per-client token** via
  a **pairing URL**. The server owns repos, worktrees, terminals, provider
  accounts, and agent sessions; the client is UI-only. Doc explicitly warns:
  keep on a private network (Tailscale/LAN), do not expose the port publicly.
- **Auth:** pairing tokens per client (revocable under "Shared Server Access");
  `orca account add --agent claude|codex` for managed provider accounts; artifact
  publishing uses the **signed-in Orca account** (opt-in).
- **Ownership model:** Orca never substitutes its own models; it wraps whatever
  provider CLIs are installed/authenticated on the host.

The client↔server transport beyond "pairing URL / revocable tokens" is **not
documented as a public HTTP/RPC API** — so a third-party integration cannot today
target `orca serve` as an HTTP endpoint without reverse-engineering it
(**unverified**).

## Mapping to Operating Swarm

Orca is a **control surface over CLI agents** — the same category as OS's `cli`
kind, not a new kind. It has no first-party model, so OS `remote`/model pinning
does not apply (its agents are already OS CLI-namespace agents like opencode,
claude, codex).

- **Best fit now:** treat `orca` as a **CLI tool + skill/MCP**, invoked by an OS
  cli seat or routine to create worktrees and drive terminals, consuming the
  `--json` output. This reuses the existing CLI adapter path
  (`src/swarm/core/cli_adapter.py`, `cli_registry.py`) and the skills system
  (`src/swarm/core/skills.py`, `skill_attach.py`).
- **`remote` fit:** only if Orca publishes a stable programmatic API for
  `orca serve`. Its session/worktree model is a plausible health/list/send
  surface, but the wire protocol is undocumented today.

## Proposed integration sketch

```text
Phase 1 (adapt, low risk): ship an "orca-cli" OS skill that teaches a CLI seat
  to call `orca worktree create --json`, `orca terminal send --text … --json`,
  `orca terminal wait --for tui-idle --json`, and read `orca terminal read --json`.
  No new kind; no model changes.

Phase 2 (watch): if Orca documents its remote-server API, add impl id `orca` to
  REMOTE_IMPL_IDS and implement health/list/send against it:
    health  → GET  status/ping
    list    → active worktrees/terminals/agents
    send    → create worktree + drive terminal, stream output
  Register aliases/labels alongside `herdr` (SSH-shaped) in
  src/swarm/core/remote_harness.py.
```

## Open questions / unknowns

- Does `orca serve` expose any documented HTTP/RPC endpoint for programmatic
  clients, or only the desktop/mobile pairing protocol? — **unverified**.
- Pairing protocol version/capabilities and whether a headless `orca` CLI can be
  driven without a desktop license — **unverified**.
- MCP server surface and tool names in `/docs/cli/skills` — **unverified**.
- Whether Orca's worktree/terminal state is durable enough to resume via CLI only
  — **unverified**.
- Ambiguity of the "ORCA" name (see above) — **needs author confirmation**.
- Enterprise API differences from the MIT OSS build — **unverified**.

## Sources

- <https://github.com/stablyai/orca>
- <https://www.onorca.dev/docs/cli/overview>
- <https://www.onorca.dev/docs/remote-servers>
- <https://www.onorca.dev/docs/cli/skills>
- <https://www.onorca.dev/docs>
