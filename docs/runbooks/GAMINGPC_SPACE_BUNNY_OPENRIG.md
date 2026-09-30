# GAMINGPC OpenRig — Space Bunny / OpenCode dogfood (#1747)

OpenRig terminology. Grok Bot seats are **inspiration only** (roles/workflow), not product chrome.

## Concurrency (hard cap)

**Space Bunny / OpenCode concurrent runs on GAMINGPC: cap 3.**

Do not launch more than three `opencode run … space-bunny-free` (or OpenRig CLI seats pinned to that model) at once on this host.

## Seat mapping (Grok Bot gloss → OpenRig)

| Grok Bot gloss | OpenRig seat (name) | Kind | Default model | Role | Notes |
| --- | --- | --- | --- | --- | --- |
| Swarm Engineer / Engineer | Engineer | `cli` (`opencode`) | `opencode/space-bunny-free` | `engineer` | Eng default when Grok Bot quota is exhausted |
| Skeptic | Skeptic | `cli` (`opencode`) | `opencode/space-bunny-free` | `skeptic` | Verdict via `submit_skeptic_verdict` workflow id |
| Chief of Staff | Chief of Staff | opt-in | documented per seat | `chief_of_staff` | **Opt-in / non-blocking** — do not force-seed |
| BA / documenter | BA | opt-in | OpenCode + Space Bunny when wired | `default` (or BA badge) | Child **#1770** |

Skill / workflow pointers only (no private prompt dumps): OpenRig roles in [`docs/AGENT_ROLES.md`](../AGENT_ROLES.md); skeptic/gate tools as documented there.

## Defaults (Success 2)

Catalog CLI `opencode` ships:

```text
opencode run --model opencode/space-bunny-free --auto -- {prompt}
```

`opencode/space-bunny-free` is allowlisted for CLI (other `opencode/*` free ids stay app-gated). Override with seat model / `opencode models` (e.g. `litellm/orchestration`, `opencode-go/*`).

CoS / demo seats remain opt-in on provider setup — see `#1700` / `#1699` and [`docs/SHOWOFF_DEMO_AGENTS.md`](../SHOWOFF_DEMO_AGENTS.md).

## Operator prove (Success 3)

On GAMINGPC Docker OpenRig (`swarm`, host port **:8002**, `HOME=/home/swarm`):

1. Open OpenRig UI → select the **OpenCode** CLI seat (or mirrored Engineer once seeded — `#1771`).
2. Send a trivial prompt, **or** from the swarm container:

```bash
opencode run -m opencode/space-bunny-free --auto 'Reply with exactly: SPACE_BUNNY_OK and nothing else.'
```

Expect `SPACE_BUNNY_OK` without using Grok Bot.

Working folder tip: `_dogfood_scratch` under the bind mount when proving multi-turn (#1766 durable HOME).

## Opt-in roster (not force-seeded)

Example Mode-B-style roster (CLI OpenCode + roles):  
[`docs/examples/openai-agents-handoff-graphs/demo-opencode-dogfood.json`](../examples/openai-agents-handoff-graphs/demo-opencode-dogfood.json)

Apply only when the operator asks (additive Demo). CoS member is absent by design (opt-in elsewhere).

## Child Issues

| Issue | Intent |
| --- | --- |
| [#1770](https://github.com/matthewhand/open-swarm-private/issues/1770) | BA/documenter seat + diagrams skill path |
| [#1771](https://github.com/matthewhand/open-swarm-private/issues/1771) | Engineer + Skeptic seat seed / role wiring |
| [#1772](https://github.com/matthewhand/open-swarm-private/issues/1772) | E2E dogfood leaf BA→Engineer→Skeptic |
| [#1707](https://github.com/matthewhand/open-swarm-private/issues/1707) | Pre-existing dogfood squad programme |

Parent programme: [#1747](https://github.com/matthewhand/open-swarm-private/issues/1747).

## Constraints reminder

- Private repo; no secrets in Issues/PRs.
- Prefer Docker `make dev`.
- Do not block UI leaves `#1740`, `#1746`, programme `#1744`.
