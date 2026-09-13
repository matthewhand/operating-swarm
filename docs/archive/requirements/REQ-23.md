# REQ-23 — Teams in sidepane + send-to-all dropdown

**Status:** in flight (no PR number in this backlog slice)

## Intent

Composition **Teams** (REQ-20) show up in the AGENTS / conversation sidepane,
with a control to **send to all** members — not only the selected seat.

## Success

- Teams appear in the sidepane as first-class rows (roster teams, not `/teams/` LLM aliases).
- A dropdown (or equivalent unlabeled select, REQ-8) offers send-to-all vs a single member.
- Send-to-all fans the same user turn to the roster; per-member threads stay isolated (REQ-7).

## Constraints

- **Honesty:** Teams live today are **LLM-profile aliases**. This REQ is the composition roster, not more alias chrome on `/teams/`.
- Grok chrome is **not on `:8001` yet** — sidepane placement follows REQ-16 when that lands.
- No extra concurrent Grok / OMB / Rakazo seats; composition stays handoff / `as_tool`.
- No Neon. No oracle. Docs-only on this filing PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
