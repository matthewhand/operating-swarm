# REQ-57 — Nest open-swarm as a remotes kind

**Status:** PR in flight — Fixes #380

## Intent

Treat another open-swarm instance as a remote harness (same family as Hermes /
OMB / Rakazo remotes) so one swarm can talk to agents on other systems
deployed for different needs.

## Success

1. Remote catalog includes an `open-swarm` (or `swarm`) kind, not only Hermes/OMB/Rakazo.
2. User can add a nested swarm by base URL (and existing remote auth header/token pattern from remotes work — env var name only, never paste secrets into the repo).
3. Parent swarm lists that remote’s agents (or a documented subset) and can send a message / handoff the same way as other remotes.
4. Child swarm is a normal deploy (its own process, its own local DB). Nesting is network remote, not in-process recursion.
5. Disconnect / unreachable shows the same remote-down treatment as other remotes (no hang forever).
6. Tests: register swarm remote; list agents from a stub child; send one message via the adapter; missing child is a clean error.
7. PR notes loop-risk: do not auto-add *this* instance as its own remote; a child should not be required to nest the parent.

## Constraints

- Reuse Herdr / remotes machinery (PR 318 and follow-ons). Do not invent a second remote stack.
- GitHub-only PR. Do not deploy or touch `http://198.51.100.30:8001/`.
- No Neon. Do not enable oracle.
- No secrets, live tokens, or LAN inventories in the Issue, PR, commits, or tests. Fixtures use `http://127.0.0.1:9` / `CHANGE_ME`.
- DaisyUI 5, React 18. Settings/Teams overlays; chat stays mounted.
- Do not fold into PR 344.
- One Cursor cloud. PR must say `Fixes` this issue.
- Cycles: v1 may refuse adding a remote whose URL is this server’s own listen URL.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
