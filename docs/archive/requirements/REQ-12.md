# REQ-12 — Harness-of-harnesses docs

**Status:** PR [315](https://github.com/matthewhand/open-swarm/pull/315) — in flight

## Intent

Direction write: Open Swarm is turning from *an* agent harness into a
**harness for other harnesses** (Hermes, OMB, Rakazo). Composition is
openai-agents **handoff / `as_tool`**, not extra concurrent Grok / Rakazo / OMB
seats.

## Success

Honesty table lands in VISION / GLOSSARY / README pointers:

| Surface | Honesty |
|---|---|
| Running today | API, blueprints, CLI fusion / MoA, Django + SPA `/` + `/chat`, REQ-5 dark chrome |
| **Teams** | **Live:** LLM-profile alias registry. **Intended:** wire API / CLI / remote so they can see and talk. Admin does not do inter-agent talk. |
| Grok-Bot-like UI | **Not live.** Dark chrome ≠ Bot product. Not on `:8001` yet. |
| Support / gate / skeptic | In flight (not on `main` / this starting tree). |
| Remotes (REQ-11) | Not landed. Do not claim remotes work. |

Differentiator: coordinator invokes another harness as a tool / handoff.

## Constraints

- Docs only (this REQ and this filing PR). Not the generic audit in #297.
- Does not enable Neon / oracle.
- Does not implement remotes, Support, gate, skeptic, or the intended Team graph.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
