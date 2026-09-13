# REQ-37 — Compact / nested summaries

**Status:** in flight (GitHub #350)

## Intent

Let Matthew compact a chat so the model sees a nested summary tree, while the
full raw transcript stays on disk and the UI shows which spans were summarised.

## Success

1. A Compact action (composer `+` menu) summarises the current backlog (or a
   selected span) into one summary block used as context from then on.
2. Nesting: a later compact may summarise a mix of raw turns and earlier
   summaries. Recursion is first-class (`parent_summary_id`).
3. Persistence: **raw** conversation remains the source of truth on disk
   (existing JSON persist). **Django/sqlite** (not Neon) tracks summary records:
   id, conversation_id, span, parent_summary_id, body, created_at.
4. UI: summarised spans render with a distinct **border** and a “Summary” label.
   Nested summaries nest visually.
5. Tests: compact replaces context; nested compact; raw file still has
   originals; sqlite has parent_summary_id; UI class for bordered summary.

## Constraints

- No Neon/oracle. Local Django sqlite only.
- GitHub PR only; no `:8001` while Herdr w3 owns the tree.
- No secrets in Issues/PRs/fixtures.
- `Fixes` #350. `+` Reset (conversation_id mint) is a follow-on.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
