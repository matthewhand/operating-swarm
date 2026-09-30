# #1363 — Alibaba Open Code Review as agents

**Verdict: adapt — run it as a CLI-namespace reviewer seat / routine, not an API model.**

## What it is

**OpenCodeReview** (`ocr`) is Alibaba's open-sourced AI code-review assistant.
Repo `alibaba/open-code-review`, Apache-2.0, ~41.7k stars as of fetch. It
originated as Alibaba's internal AI review tool and combines a **deterministic
pipeline** (file selection, bundling, rule matching, comment positioning) with an
**LLM agent** that reads full files and searches the repo to emit line-level
review comments. Two modes: diff review (`ocr review`) and full-file scan
(`ocr scan`).

- Repo: <https://github.com/alibaba/open-code-review>
- Site/docs: <https://open-codereview.ai> · <https://open-codereview.ai/docs>
- Benchmark (AACR-Bench): <https://huggingface.co/datasets/Alibaba-Aone/aacr-bench>

## Protocol / SDK / auth surface

Primary source = repo README:

- **Distribution:** Go CLI (`bin/opencodereview`) plus npm package
  `@alibaba-group/open-code-review` → `ocr` on PATH; install script / release
  binary / from source also documented. Requires **Git ≥ 2.41**.
- **Commands:** `ocr config provider` / `ocr config model`; `ocr review`
  (workspace / `--from`/`--to` / `--commit` / `--resume <session-id>`);
  `ocr scan [--path …]`; `ocr delegate preview|rule …`; `ocr session list`.
  Machine output: `ocr review --format json --output result.json` (recommended
  "for AI host agents").
- **Auth / models:** you configure an **OpenAI- or Anthropic-compatible endpoint**
  and API key yourself (`ocr config provider` + env vars). **No Alibaba account is
  required** — it is local/self-hosted. In **Delegation Mode** the host coding
  agent performs the review using its own LLM and no OCR LLM key is configured;
  OCR still does file selection + rule resolution (`ocr delegate rule …`).
- **Extensibility:** an **MCP server** to extend the review agent with external
  tools (<https://open-codereview.ai/docs/mcp>); agent plugins/skills for Claude
  Code, Codex, Cursor, Kimi Code, and **OpenCode** (`plugins/open-code-review/`);
  CI integrations (GitHub Actions `action.yml`, GitLab, GitFlic, Gerrit).
- **Session viewer:** browse/replay sessions, mark comments fixed/ignored.
- **Telemetry:** opt-in OpenTelemetry.

Cost/latency claims: the README states higher precision/F1 and ~1/9 tokens vs
general-purpose agents (images not parsed) — **treat the specific numbers as
unverified**.

## Mapping to Operating Swarm

`ocr` is a **tool/CLI**, not a hosted model service. Natural fit:

- **Kind:** `cli`. OS's `cli` namespace accepts the CLI's own configured model,
  so a pinned OCR model stays CLI-namespace-correct (no foreign API id leaks
  into `remote`/`api`).
- **Role:** a reviewer seat can carry `skeptic` (pass/fail review) or `gate`
  (classify pending changes) semantics, or be a plain `engineer`-adjacent
  reviewer blueprint. Its structured JSON comments feed an OS reviewer agent.
- **Routine:** `ocr review --format json` can be triggered per PR/diff by an OS
  routine (`docs/routines`), matching the CI/CD intent.
- **Team:** a roster could include an OCR reviewer member (kind `cli`) wired
  `as_tool` so a CoS can call it (`docs/TEAM_ROSTERS.md`).

It is **not** a `remote`: there is no self-hosted HTTP agent-session service; the
MCP server is the closest service-shaped surface but is for tool extension.

## Proposed adapter sketch

```text
Option A (simplest): a CLI adapter / blueprint "code-reviewer"
  - cmd: ["ocr", "review", "--format", "json", "--output", "-"]
  - parse stdout JSON → list[{file, line, severity, message, rule}]
  - feed into a skeptic/gate verdict agent; persist as OS activity/comments
  - role: skeptic | gate ; kind: cli

Option B: MCP — register OpenCodeReview's MCP server as an OS MCP tool provider
  and expose `review`/`scan` as tools to any API/team agent.

Option C (CI): reuse `action.yml` / `ocr delegate` in CI, keep OS as the
  operator surface that reads the resulting session JSON.
```

Prefer **Option A** for an in-app reviewer seat and **Option C** for PR-time
automation; Option B if other agents should call review directly.

## Open questions / unknowns

- Exact JSON schema of `--format json` — **unverified** (not fetched).
- MCP server transport (stdio vs HTTP) and tool names — **unverified**.
- Whether `ocr review` can target an arbitrary OS git worktree / non-cwd repo —
  **unverified**.
- Benchmark precision/F1/token/cost numbers — **unverified** (image-only).
- License of bundled multi-language rulesets vs Apache-2.0 repo — **unverified**.
- Whether Delegation Mode can be driven by an OS CLI agent without an extra key —
  plausible from README, but the exact host contract is **unverified**.

## Sources

- <https://github.com/alibaba/open-code-review>
- <https://open-codereview.ai/docs>
- <https://open-codereview.ai/docs/delegate>
- <https://open-codereview.ai/docs/mcp>
- <https://open-codereview.ai/docs/cicd>
