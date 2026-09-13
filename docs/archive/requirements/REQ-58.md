# REQ-58 — Agent editor is agent-scoped; Blueprint is a picker

**Status:** in flight (GitHub #382)

## Intent

The edit-agent pane/popup is only about that agent. Blueprint there means
“choose this agent’s blueprint from the list of blueprints.” Do not mix
agent-scoped fields with global Settings sections such as Remotes.

## Success

1. The agent editor (pane/popup) contains only agent-scoped controls, e.g. name,
   role, which blueprint this agent uses, per-agent LLM override if that exists.
   No Remotes, System, CLI catalog, or other global Settings items in that
   pane’s nav or body.
2. The Blueprint control is a **selector** of existing blueprints (the same
   list Settings → Blueprints shows). Picking one assigns that blueprint to
   this agent. It is not a nested copy of the global Settings chrome.
3. Optional affordance: “Edit blueprint…” (or equivalent) opens Settings →
   Blueprints with **that** blueprint selected in the list — still the
   Blueprints list, not Remotes.
4. Global Remotes stay under Settings (global). Same for System and other
   instance-wide sections.
5. Tests: agent editor DOM/nav has no Remotes (or System) item; assigning a
   blueprint from the picker persists on that agent; opening Edit blueprint
   lands on the Blueprints list with the assigned item selected.

## Constraints

- Distinct from REQ-42 (#356, role-badge explained pane) and REQ-25 (#334,
  hover-pencil → Python). Do not fold this into those PRs or into PR 344.
- DaisyUI 5, React 18. Chat stays mounted (editor is an overlay/popup).
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- No Neon. No secrets.
- One Cursor cloud. PR must say `Fixes` this issue.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
