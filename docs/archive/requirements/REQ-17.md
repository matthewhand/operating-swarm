# REQ-17 — Search command palette

**Status:** inside PR [322](https://github.com/matthewhand/open-swarm/pull/322) — in flight

## Intent

Search in the left rail is a **command palette overlay**, not an in-place
filter of the AGENTS dump.

## Success

- Focus/click Search opens a dark overlay with large rounded corners.
- Magnifying glass + placeholder exactly `Search`.
- Tabs: All (pill) · Messages · Bots · Groups · Files · Links · Routines · Actions.
- Rows: icon + name + one-line desc + ⌃N. First row highlighted; arrows + Enter; Esc / click-outside close.
- Does **not** filter the 50-row AGENTS list in place.

## Constraints

- Ships inside REQ-16 / PR 322 — do not open a separate Search PR.
- Existing experimental `CommandPalette` is not the product unless 322 adopts it.
- No Neon. No oracle. Grok chrome **not on `:8001` yet**.
- Docs-only on this filing PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
