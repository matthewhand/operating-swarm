# REQ-7 — Support agent (pill, threads, question cards)

**Status:** PR [313](https://github.com/matthewhand/open-swarm/pull/313) — in flight

## Intent

A first-class **Support** seat that talks *about* the other agents. Welcome
intel is a one-way system pill (not a transcript dump). Each agent keeps its
own chat thread. Configuration help is question cards, not a wall of prose.

## Success

- Default Support chat is quiet; one **System → Support** pill expands compressed intel (agents, inference, gate/skeptic). Visible chips: **New team**, **Set inference**, **Write blueprint**. Support cannot reply to the pill.
- Support chat ≠ hybrid_team chat ≠ skeptic chat — messages do not leak. Switching away and back restores that agent’s thread. Default `/chat` opens Support. Header name/avatar match the selected agent.
- Any agent can emit a ` ```question ` fence. Chat renders a **question card**: multiple-choice chips plus a last open-string. Cards are user-answerable.

## Constraints

- Role looks (support / gate / skeptic) stay seats, not extra Grok / OMB / Rakazo workers.
- No auth skip. No Neon. No oracle. Docs-only on this PR — do not implement here.
- Socratic + MCQ (REQ-18) is absorbed into 313; do not open a second Support UX PR.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
