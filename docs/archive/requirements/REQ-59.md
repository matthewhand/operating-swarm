# REQ-59 — Remotes are opt-in — empty until +, OpenMousBot not OMB

**Status:** in flight (GitHub #384)

## Intent

Settings → Remotes must not show UI for harnesses the user has not added.
Start with + Add remote. Only after a remote is configured does it appear in
the Remotes list and in any remote dropdown. The OpenMausBot kind is labelled
**OpenMousBot**, not OMB.

## Success

1. Settings Remotes with zero configured remotes shows an empty state plus
   **+ Add remote**. No pre-filled Hermes / Rakazo / OpenMousBot / open-swarm
   cards, rows, or connection panes.
2. Add remote: user picks a kind, then enters connection details (URL /
   existing remote auth pattern). That remote then appears in the Settings list.
3. Remote dropdowns (composer, Settings, Teams) list **only** configured
   remotes, plus an add/create path. Unused kinds do not occupy the dropdown.
4. Kind label is **OpenMousBot** everywhere in UI copy (not OMB). Internal id
   may stay `omb`.
5. Removing a remote drops it from the list and from dropdowns.
6. Tests: empty catalog → no kind rows, + Add visible; after add, one row +
   dropdown option; OpenMousBot string in UI, no user-facing `OMB` label.

## Constraints

- Reuse remotes / Herdr machinery (PR 318 and follow-ons). Distinct from
  REQ-57 nested swarm (#380) but compatible (open-swarm is just another kind
  you add).
- DaisyUI 5, React 18. Chat stays mounted.
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- No Neon. No secrets in Issue/PR/commits (placeholders only).
- Do not fold into PR 344.
- One Cursor cloud. PR must say `Fixes` this issue.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
