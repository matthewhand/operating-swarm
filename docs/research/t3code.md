# #1367 — t3code integration

**Verdict: watch — no stable third-party API; it overlaps OS's own CLI-seat control.**

## What it is

**T3 Code** is an "agent harness control surface" from pingdotgg (Theo): a
desktop / web / mobile app that controls the **coding agents installed on your
machine** — Codex, Claude Code, Cursor, Grok Build, OpenCode, and Google
Antigravity. It runs the agents locally, gives them one UI, and reaches them
remotely from phone/desktop.

- Repo: <https://github.com/pingdotgg/t3code> (free/open source)
- Site: <https://t3.codes> · hosted web app <https://app.t3.codes>
- Docs in repo: `docs/` (no docs site yet).

## Protocol / SDK / auth surface

Primary sources: repo README + `docs/internals/overview.md`,
`docs/internals/environment-auth.md`, `docs/user/remote-access.md`.

- **Architecture:** "execution stays in the environment that owns the workspace."
  The server owns provider processes, terminals, git, and project files; web,
  desktop, and mobile clients control it over **authenticated RPC** (WebSocket).
  The **RPC contract is `packages/contracts/src/rpc.ts`** — the boundary between
  independently versioned clients and servers. Reactors perform side effects;
  the **event log is the source of truth** (orchestration engine → decider →
  projector, committed transactionally).
- **Capability negotiation:** clients negotiate via an **environment descriptor**
  (e.g. `threadPullRequests`, `threadPullRequestLinking`) — never by client
  version. Provider-specific behavior is behind an adapter.
- **Auth model** (`environment-auth.md`): the environment issues its own sessions
  and enforces per-RPC **scopes** (`every RPC declares a required scope`).
  Browser cookies, **bearer** tokens, and **DPoP** tokens adapt the same scoped
  session model (invalid DPoP proof must fail, not fall back to bearer).
  Short-lived **WebSocket tickets** obtained via authenticated HTTP so long-lived
  tokens stay out of socket URLs. Pairing delegates a set of scopes; it cannot
  widen authority. A relay token is never an environment login.
- **Remote access** (`remote-access.md`): `t3 serve [--host <ip>]`, `t3 pair`,
  `t3 connect` (cloud relay "T3 Connect", separate trust boundary), Tailscale
  HTTPS, desktop-managed **SSH** environments, pairing URLs / one-time links.
- **Storage:** each environment has its own SQLite data, signing keys, and
  revocation state; SQLite WAL by default. Checkpoints use hidden git refs.
- **Server runtime:** `t3` starts the server and local web app; `t3 service install`;
  install via `install.sh` / `npx t3@latest`.

No public REST/query API for third-party agents was documented — the RPC contract
is an internal, versioned boundary. Whether it is published as a stable client
SDK is **unverified**.

## Mapping to Operating Swarm

T3 Code is a **peer control surface over CLI agents** — the same conceptual space
as OS's `cli` kind (OS already runs and controls CLI agents). It is **not** a
model provider, so no model namespace entry is needed:

- **`remote`?** No documented HTTP/RPC endpoint or stable client SDK today; the
  pairing/DPoP/ticket handshake is internal. A `remote` impl would require
  reverse-engineering the RPC contract (**unverified**) — not viable now.
- **`cli`?** It is a UI over CLI agents, not itself a CLI agent. Driving it as a
  CLI is not its model.
- **Best framing now:** a **sibling operator UI / peer** to OS Chat. Do not add a
  fifth kind; per repo doctrine (ADR-005/ADR-011) no parallel abstraction.

## Proposed integration sketch

```text
Now (watch, no code):
  - Document T3 Code as a "peer agent control surface" in docs/research only.
  - Track whether pingdotgg publishes the RPC contract / a client SDK.

Later, if a stable API appears — two options:
  (a) remote impl `t3code` (HTTP/RPC):
        health → environment descriptor / status
        list   → projects, threads, agent sessions
        send   → create thread / send prompt to a provider agent
      Requires: pairing/token auth, scope mapping, capability negotiation.
  (b) "T3 Connect"-style inbound: let T3 Code connect to OS as an environment
      only if OS exposes a matching RPC contract — currently absent.
```

## Open questions / unknowns

- Is `packages/contracts/src/rpc.ts` published as a versioned, supported SDK for
  third parties, or internal only? — **unverified**.
- Exact pairing/DPoP/ticket flow a non-T3 client would need to implement —
  **unverified**.
- Any REST endpoints for agents (vs the WS RPC boundary) — **unverified**.
- Cross-platform server support for headless hosts (README notes `~/.t3/runtime`
  download on Linux / Apple-silicon Mac for SSH) — **unverified**.
- T3 Connect licensing/limits and whether relay use is permitted for
  programmatic clients — **unverified**.
- Overlap/collision risk: both OS and T3 Code control the same CLI agents — decide
  whether this is integration or competition.

## Sources

- <https://github.com/pingdotgg/t3code>
- <https://t3.codes>
- <https://app.t3.codes>
- `docs/internals/overview.md`, `docs/internals/environment-auth.md`,
  `docs/user/remote-access.md` in the repo above.
