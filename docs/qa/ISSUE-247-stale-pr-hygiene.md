# Issue #247 — Stale-PR hygiene (rebase-or-close)

Process note only. Not a product change. Contributor-facing summary:
[CONTRIBUTING.md](../../CONTRIBUTING.md). Source-locked by
`tests/unit/test_issue247_stale_pr_hygiene.py`.

## Window

The clock starts when GitHub marks the PR **CONFLICTING** with `main`,
not when the PR was opened.

| Age while CONFLICTING | Action |
|-----------------------|--------|
| **>48h** | Nudge comment: rebase onto `main`, or say why the PR is still live. |
| **>72h** | Close as superseded. Cite the landed equivalent on `main`. |

No stale-bot. Enforcement is at triage.

## Triage order

1. **Check-if-fixed first** — grep `main` for the fix before reading the
   branch. Most conflicting PRs here had already landed another way.
2. **Always salvage tests** — extract unique regression tests (pattern:
   #132 kept two fallback tests) or file a successor issue with a port
   inventory (pattern: #245 for #140). Do not drop coverage because the
   branch is unrebasable.
3. **Close with evidence** — the close comment names the `main` commit
   or PR that superseded it.

## Stacked PRs

Declare the **base PR** in the body. Squash-merge of the base otherwise
orphans the stack (#237).
