# REQ-52 — Persist CLI session ids and resume them

**Status:** in flight (GitHub #369)

## Intent

CLI tools own their sessions. Open Swarm tracks each CLI **session id** so when
the user comes back to that CLI agent, we pass the id back and the CLI restores
context. (API threads we own and persist ourselves; remotes are the remote’s
session.)

## Success

1. For each catalogued CLI (grok, claude, gemini, codex, opencode; antigravity
   if already wired): document how that CLI names a session (`--session` /
   `--resume` / id file). Swarm stores that id next to the chat thread.
2. Resume: the next send to that CLI agent includes the stored id so the CLI
   restores its own context. Missing/expired id starts a new session and we
   store the new id.
3. Honest UI: if a CLI cannot resume, no fake “restored” — show we started a
   new session (bubble-less line is OK; related to #362).
4. Tests: fixture CLI that echoes `--resume ID`; second turn passes the stored
   id. No secrets in stored records.

## Constraints

- Distinct from #366 (API edit).
- No live preview. No secrets. GitHub PR only (`Fixes` #369).
- Do not confuse with Django/API conversation ids or OS `start_new_session`.
- Keep catalog one-shot flags for first turn; add resume argv only when a
  stored id exists.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` — guest dirty only (not this PR)
