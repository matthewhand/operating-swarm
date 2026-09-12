# Examples & Recipes

Everything Open Swarm can do, as copy-paste recipes. Two parts:

1. **[Team examples](#part-1--team-examples)** — the consensus/persona *teams* you call as a `model`.
2. **[CLI + REST config](#part-2--cli--rest-config)** — how to wire the backends those teams run on.

Base URL in examples: `http://localhost:8000/v1` (swap for your host). Add
`-H "Authorization: Bearer $TOKEN"` if you enabled auth.

> The bundled blueprints are **examples of a composition system** — you assemble
> your own personas, teams, and consensus rules via config or Django
> [`/agent-creator/`](../FEATURE_STATUS.md) (the SPA Builder route is unmounted).
> Architecture + diagrams: [ORCHESTRATION_PATTERNS.md](./ORCHESTRATION_PATTERNS.md).
Forced / circular openai-agents graphs and the three harness types:
[openai-agents-handoff-graphs](./examples/openai-agents-handoff-graphs/README.md)
(REQ-156).

---

## Part 1 — Team examples

Every team is selected by the `model` field; per-request options go in `params`.
Most work with **config defaults** — `params` only overrides.

> **Naming:** the multi-agent orchestration *patterns* are published as
> **`swarm_*`** — `swarm_ensemble`, `swarm_map`, `swarm_recurse`, `swarm_pipeline`,
> `swarm_roundtable`, `swarm_planner`, `swarm_orchestrator` — because they're Swarm
> primitives, not CLI wrappers. The older **`cli_*`** names (and `cli_fusion`) still
> work as aliases. `cli_agent` keeps its name (it literally runs one CLI). Examples
> below use the `cli_*` names; swap in `swarm_*` freely.

### Single agent (with failover)
```bash
curl -s $B/chat/completions -d '{"model":"cli_agent","messages":[{"role":"user","content":"explain async/await"}],"params":{"cli":"claude"}}'
```
One CLI, falls over to the next installed one if it's down.

### Consensus panel — always (`cli_ensemble`)
```bash
curl -s $B/chat/completions -d '{"model":"cli_ensemble","messages":[{"role":"user","content":"capital of Canada?"}],"params":{"preset":"tri","show_analysis":true}}'
```
Fan to a panel in parallel → a judge synthesizes (a Mixture-of-Agents ensemble
over your CLIs). `show_analysis` surfaces consensus / contradictions / gaps per
model. Configured via the shared `cli_fusion` config block.

> **Naming:** `cli_ensemble` is the canonical name; **`cli_fusion` still works**
> as a back-compat alias (same behavior, same config). We renamed it to avoid
> colliding with OpenRouter's "Fusion" *tool* — ours is the inverse: the panel
> *is* the endpoint you call, not a tool a model invokes.

### Gated consensus — router decides (`cli_orchestrator`)
```bash
curl -s $B/chat/completions -d '{"model":"cli_orchestrator","messages":[{"role":"user","content":"is force-pushing to shared main safe?"}]}'
```
A cheap router answers directly and **only escalates** to the panel when the
question is high-stakes. One inference by default.

### Debate (`cli_roundtable`)
```bash
curl -s $B/chat/completions -d '{"model":"cli_roundtable","messages":[{"role":"user","content":"trunk-based vs feature branches?"}]}'
```
Debaters react to each other across bounded rounds; a moderator concludes.

### Sequential refine (`cli_pipeline`)
```bash
curl -s $B/chat/completions -d '{"model":"cli_pipeline","messages":[{"role":"user","content":"draft a release note for X"}]}'
```
Stage 1 drafts → stage 2 reviews → … each stage sees the running output.

### Map-reduce (`cli_map`)
```bash
curl -s $B/chat/completions -d '{"model":"cli_map","messages":[{"role":"user","content":"audit these 4 modules for security"}]}'
```
Decompose → distribute across workers → reduce. Best for decomposable tasks.

### Recursive divide & conquer (`cli_recurse`)
```bash
curl -s $B/chat/completions -d '{"model":"cli_recurse","messages":[{"role":"user","content":"design a fault-tolerant URL shortener"}],"params":{"max_depth":3,"max_subproblems":4,"max_nodes":20}}'
```
Each node decides to **solve** a problem directly or **split** it into
sub-problems — and every sub-problem is handed to a *fresh instance of the same
blueprint*, recursing until each leaf is atomic, then synthesizing back up. Three
limiters bound the tree so it can't run away: `max_depth` (how deep), `max_subproblems`
(fan-out width), `max_nodes` (a shared global budget — once spent, remaining nodes
solve directly). This is how the swarm breaks an arbitrarily large problem into
pieces of any size. (`cli_map` is the single-level version; this recurses.)

### Planner with a ledger (`cli_planner`)
```bash
curl -s $B/chat/completions -d '{"model":"cli_planner","messages":[{"role":"user","content":"checklist to safely drop a DB column"}]}'
```
A planner delegates subtasks, reviews results, re-plans on stall, then synthesizes.

### Hybrid — REST coordinator + CLI consensus (`hybrid_team`)
```bash
curl -s $B/chat/completions -d '{"model":"hybrid_team","messages":[{"role":"user","content":"capital of Germany?"}]}'
```
An LLM coordinator reasons, then delegates to CLI personas + a consensus panel as
tools — REST and CLI inference mixed in one run.

### Persona councils — diverse-lens consensus (`persona_council`)
Built-in councils need no config; pick with `params.council`:
```bash
# ethics: Utilitarian / Kantian / Virtue / Rawlsian / Care
curl -s $B/chat/completions -d '{"model":"persona_council","messages":[{"role":"user","content":"should a self-driving car swerve to kill 1 to save 5?"}],"params":{"council":"ethics","show_analysis":true}}'

# others: science | psych | decision | red_team
curl -s $B/chat/completions -d '{"model":"persona_council","messages":[{"role":"user","content":"should a 5-person startup adopt Kubernetes?"}],"params":{"council":"decision"}}'
```
Each lens examines the question through a distinct framework (the prompts channel
the actual thinkers — Mill, Kant, Rawls, Feynman, Munger, Schneier, …); a judge
reports **agreement, the real tensions, and a synthesized position**.

**Your own council** — pass a roster inline, or add presets in config (Part 2):
```bash
curl -s $B/chat/completions -d '{"model":"persona_council","messages":[{"role":"user","content":"<q>"}],"params":{"personas":[{"name":"Optimist","lens":"argue the upside only"},{"name":"Pessimist","lens":"argue the risks only"}],"judge":"claude"}}'
```

### Async — fire and poll (any team, long tasks)
```bash
# fire -> 202 {id, status:"queued"}
curl -s $B/responses -d '{"model":"cli_fusion","input":"<long task>","background":true}'
# poll
curl -s $B/responses/resp_abc           # -> queued -> in_progress -> completed
# cancel
curl -s -X POST $B/responses/resp_abc/cancel
```
Or auto-escalate: `"max_wait_seconds": 20` returns inline if fast, else a handle.
`chat/completions` also accepts `"background": true` (returns a `poll_url`).

---

## Part 2 — CLI + REST config

Config lives at `~/.config/swarm/swarm_config.json` (XDG). Secrets are `${ENV}`
refs — never inline. Full reference: [CONFIGURATION.md](../CONFIGURATION.md).

### A. CLI agents (`cli_agents`)
Wrap installed agentic CLIs. Each is an argv with a `{prompt}` token and a parse
rule. The CLIs carry **their own** auth — Open Swarm passes no key.
```jsonc
{
  "cli_agents": {
    "gemini": {"cmd": ["gemini", "-m", "gemini-2.5-flash-lite", "-p", "{prompt}"], "parse": "text", "timeout": 90, "mode": "write"},
    "claude": {"cmd": ["claude", "-p", "{prompt}"], "parse": "text", "timeout": 120, "mode": "write"},
    "grok":   {"cmd": ["grok", "-p", "{prompt}", "--output-format", "plain"], "parse": "text", "timeout": 120, "mode": "write"},
    "opencode": {"cmd": ["opencode", "run", "--model", "litellm/orchestration", "--", "{prompt}"], "parse": "text", "mode": "write"},
    "omp": {"cmd": ["omp", "-p", "--model", "litellm/orchestration", "--auto-approve", "--", "{prompt}"], "parse": "text", "mode": "write"}
  }
}
```
Generate this automatically from what's installed + authed:
`swarm-cli cli-agents --init --write`.

### B. REST / LLM profiles (`llm`)
OpenAI-compatible HTTP backends — `provider: openai` just means "OpenAI-style
client", not literally OpenAI. Point it anywhere:
```jsonc
{
  "llm": {
    "default": {"provider": "openai", "model": "qwen3.5",  "base_url": "http://10.0.0.107:1234/v1", "api_key": "${LITELLM_API_KEY}"},
    "openai":  {"provider": "openai", "model": "gpt-4o",   "base_url": "https://api.openai.com/v1", "api_key": "${OPENAI_API_KEY}"},
    "groq":    {"provider": "openai", "model": "llama-3.3-70b-versatile", "base_url": "https://api.groq.com/openai/v1", "api_key": "${GROQ_API_KEY}"},
    "ollama":  {"provider": "openai", "model": "qwen3.5:4b", "base_url": "http://localhost:11434/v1", "api_key": "ollama"}
  }
}
```
- **Local & keyless** (LM Studio / Ollama / LiteLLM): any non-empty `api_key`
  works — the backend ignores it (use a placeholder like `lm-studio`).
- The `default` profile powers the LLM/REST blueprints (chatbot, hybrid, …) and
  the REST half of `hybrid_team`.

### C. Mixing REST + CLI (this is the point)
A config with **both** an `llm.default` and `cli_agents` lets you run:
- pure-CLI consensus (`cli_fusion`), pure-REST (`chatbot`), **and** the hybrids
  (`hybrid_team` — REST coordinator that calls CLI personas + consensus as tools).

No extra wiring: the blueprint picks the surface it needs.

### D. Per-team config blocks
Each team reads its own block (and falls back to `cli_fusion`):
```jsonc
{
  "cli_fusion":       {"presets": {"tri": {"panel": ["gemini","claude","grok"], "judge": "claude"}}, "default_preset": "tri"},
  "cli_orchestrator": {"router": "grok", "panel": ["claude","grok"], "judge": "claude"},
  "cli_map":          {"planner": "grok", "workers": ["claude","grok"], "reducer": "claude"},
  "cli_pipeline":     {"stages": [{"cli":"grok","instruction":"draft"},{"cli":"claude","instruction":"review"}]},
  "cli_roundtable":   {"debaters": ["claude","grok"], "moderator": "claude", "rounds": 1},
  "cli_planner":      {"planner": "claude", "workers": ["grok"], "max_rounds": 3},
  "cli_recurse":      {"decomposer": "claude", "solver": "claude", "synthesizer": "claude",
                       "max_depth": 3, "max_subproblems": 4, "max_nodes": 20},
  "persona_council":  {"cli": "claude", "judge": "claude", "default_council": "ethics",
                       "councils": {"my_panel": [{"name":"A","lens":"..."},{"name":"B","lens":"..."}]}}
}
```

### E. Inference profiles (pick by traits, not brand)
A blueprint can ask for *what kind of thinking* it wants and let the closest
backend win:
```jsonc
{"params": {"profile": {"intelligence": 0.9, "speed": 0.2, "cost": 0.3}}}
```
See [CLI_FUSION.md](./CLI_FUSION.md#inference-profiles--say-what-you-want-not-which-model).

### F. Auth & async (env)
| Env | Effect |
|---|---|
| `API_AUTH_TOKEN` | Require `Authorization: Bearer <token>` on `/v1/*`. |
| `SWARM_ALLOW_NO_AUTH=true` | Boot in production with no token (front it with OAuth). |
| `SWARM_RESPONSES_SYNC_TIMEOUT` | Default seconds a `/v1/responses` call waits inline before returning a queued handle. |
| `SWARM_RESPONSES_DIR` | Where async task state persists (mount a volume in Docker). |

Full env table: [CONFIGURATION.md → Environment Variables](../CONFIGURATION.md#environment-variables).

---

See also: [VISION.md](./VISION.md) · [ORCHESTRATION_PATTERNS.md](./ORCHESTRATION_PATTERNS.md) ·
[CLI_FUSION.md](./CLI_FUSION.md) · [ASYNC_RESPONSES.md](./ASYNC_RESPONSES.md) ·
[ORACLE_DEPLOY.md](./ORACLE_DEPLOY.md).
