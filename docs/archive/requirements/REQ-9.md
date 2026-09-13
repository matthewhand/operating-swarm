# REQ-9 — gate + skeptic roles as-tool

**Status:** PR [314](https://github.com/matthewhand/open-swarm/pull/314) — in flight

## Intent

Agents get first-class **roles** so they look different in the AGENTS sidepane,
and one agent’s output can feed another’s input via openai-agents **`as_tool` /
handoff** — not extra concurrent Grok / OMB / Rakazo seats.

## Success

| Role | Sidepane | Runtime |
|---|---|---|
| `default` | no badge | ordinary worker |
| `support` | teal | Support seat (REQ-7). Talks about the others. |
| `gate` (`tool_gate`) | amber | Classifies a **pending tool call** as dangerous or not (YES/NO). |
| `skeptic` | violet | Reviews the **original prompt** + output. |

- **Default-open gate.** If no `gate` / `tool_gate` is on the roster, every tool call is approved and the user is never elicited.
- **Skeptic is a bounded retry, not a nag.** Failure hands findings back (max 2). Success stops.
- Team Creator writes `AGENT_SPECS[].role` plus `gate_agent` / `skeptic_agent`. `GET /v1/blueprints/` includes role metadata so the sidepane can highlight seats.

## Constraints

- Roles are **seats, not models**. Assigning gate/skeptic does not add another worker.
- Composition is openai-agents handoff / `as_tool` only.
- Support UX (pill / threads / cards) is REQ-7, not this PR.
- First-load hide of gate/skeptic is REQ-26 — do not re-seed hide here.
- No Neon. No oracle. Docs-only on this PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
