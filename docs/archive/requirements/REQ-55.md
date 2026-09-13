# REQ-55 — Safety role: tool-status badges + user approval (API agents only)

**Status:** PR in flight — builds on REQ-9 / PR 314 (not merged). This tree ships
minimal Safety-as-tool policy in `swarm.core.safety` without taking PR 314’s
`tool_gate.py` / skeptic / Team Creator files.

## Intent

When an API agent runs a tool, the assistant popup shows a coloured status
badge (blue running and animated, green allowed/done, red blocked). If the
safety role (formerly gate) is concerned about the call, pause and prompt the
user to Allow, Always allow, or Deny.

## Success

1. API-agent tool popups in chat show a badge: blue + animated while the tool is running, green on success/allowed, red on deny/error.
2. Safety is the user-facing name. Replace “gate” in UI copy and the role badge. Internal `tool_gate` / `gate` may stay if cheaper. Safety classifies a pending tool call; when concerned, the chat pauses with an approval card: Allow once / Always allow / Deny. “Always allow” persists for that tool name on this agent (v1; no arg fingerprint required).
3. Default remains all-approved until a safety role is assigned **and** flags concern (same as REQ-9). Unconcerned calls do not prompt.
4. CLI and remote agents are out of scope. They keep their own approval UIs. Swarm must not intercept or re-prompt those sessions.
5. PR body includes a **look-only** section: how each shipped CLI adapter (and remote Herdr) behaves when run non-interactively (`-p` / no TTY) if that CLI would have asked for approval — auto-approve, fail, hang, or env flag. Document only; do not change those CLIs.
6. Tests: badge states; prompt-on-concern; always-allow skips the next prompt for that tool; CLI/remote path does not call swarm approval.

## Constraints

- API agents only (we own the runtime).
- Do not wire CLI/remote into swarm safety.
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- No Neon. Local sqlite is fine; do not mention Django in UI copy.
- DaisyUI 5, React 18, Vite, Tailwind 4. No shadcn.
- Chat stays mounted; this is chat chrome, not a new SPA page.
- Do not fold into PR 344.
- One Cursor cloud. PR must say `Fixes` this issue.
- No secrets, tokens, or personal dumps in the Issue, PR, commits, or screenshots.
- Builds on REQ-9 / PR 314. Start from `main`. If 314 is not merged, include minimal safety-as-tool wiring here; do not fight 314’s branch.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
