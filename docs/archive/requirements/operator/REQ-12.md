# REQ-12

Intent: Shift+Tab cycles operator session mode: plan, auto-edit, default. Always-approve is not a cycle stop because Operating Swarm already simulates it on host CLIs.

Success:
1. Agent Router composer (SPA + Django fallback): Shift+Tab cycles **default → plan → auto-edit → default**.
2. **Plan** prefixes the outbound user message so the agent plans and does not edit or run mutating commands.
3. **Auto-edit** prefixes so file edits may proceed without asking; destructive shell / secrets still need a pause. Stupidity-checker approval cards are skipped in this mode.
4. **Default** sends the message unchanged (current routing + oversight).
5. Always-approve stays in `cli_catalog` (`--always-approve`, `--yolo`, `--dangerously-skip-permissions`, …) so one-shot CLIs do not block. It is not a Shift+Tab mode.
6. Persist the session mode in localStorage. Show the current mode next to the composer.

Constraints: Do not remap Grok TUI bindings. Do not add Always-approve to the Operating Swarm cycle.

Owner: open-swarm engineer.
