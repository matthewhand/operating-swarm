# Architecture decision records

| ADR | Title |
|-----|--------|
| [ADR-001](../ADR-001-primary-ui.md) | Primary UI is Django; SPA Chat only |
| [ADR-002](./002-config-ownership.md) | Config ownership — `.env` vs XDG `swarm_config.json` vs Django DB (#776 Full coverage addendum) |
| [ADR-003](./003-desktop-packaging.md) | Desktop packaging — local server + pywebview (Windows first) |
| [ADR-004](./004-virtualized-chat-history.md) | Virtualized infinite chat history — `@tanstack/react-virtual` ≥ 3.14 (REQ-163) |
| [ADR-005](./005-kind-bases.md) | Three kind bases (API / CLI / remote) — Support subclasses these |
| [ADR-006](./006-api-vs-blueprint-kinds.md) | Separate API (inference seat) from Blueprint (programmatic) — REQ-193 |
| [ADR-007](./007-local-computer-control.md) | Local computer control — adapt OMB + Rakazo (REQ-189 / #645) |
| [ADR-008](./008-3d-robot-avatar-theme.md) | Optional 3D robot avatar theme family (Reachy-inspired; REQ-194 / #667). Report: [reachy-3d-avatar-inspiration.md](../reports/reachy-3d-avatar-inspiration.md) |
| [ADR-009](./009-peer-mailbox.md) | Peer mailbox — team graph + relationship edges, not a global mesh (REQ-153 / #561). Archived catalog flag is fed by REQ-154. |
| [ADR-010](./010-role-agent-invocation-modes.md) | Role-agent Mode A (human chat / wide context) vs Mode B (as-tool / caller context) — tip this PR; Mode B wiring deferred (REQ-191 / #648) |
| [ADR-011](./011-remote-harness.md) | Remote as abstract harness spec — Hermes / OMB / Rakazo / Herdr / nested swarm implement (REQ-203 / #680) |
| [ADR-012](./012-swarm-cli-tui.md) | swarm-cli TUI — Herdr-like rail + chat over the same API as WebUI (REQ-111 / #481) |

ADR-006 **amends** ADR-005’s `ApiKindBase` slot: user-facing kinds become CLI | API | Blueprint | Remote.

ADR-011 **amends** ADR-006: Remote stays one kind; variants are `RemoteHarness` implementations, not extra kinds.

ADR-012 **renumbers** the TUI Wave 0 record from draft ADR-011 to ADR-012 to resolve the collision with REQ-203 RemoteHarness ([#888](https://github.com/matthewhand/open-swarm/issues/888)).

Related research (not an ADR): [Grok Bot keybinding parity](../GROK_KEYBINDING_PARITY.md) (REQ-150 / #552).
