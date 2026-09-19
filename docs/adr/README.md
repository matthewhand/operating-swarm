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
| [ADR-012](./012-swarm-cli-tui.md) | `os-cli tui` — Herdr-like rail + chat over the same API as WebUI (REQ-111 / #481) |
| [ADR-013](./013-agent-initiated-questions.md) | Agent-initiated multi-choice questions — `ask_user` tool + WS elicit (spike, #221) |
| [ADR-014](./014-herdr-kind-cli-vs-remote.md) | Herdr's kind — CLI subtype vs. Remote implementation (proposed: keep Remote, drop Team-member composition) |
| [ADR-015](./015-identity-vs-provider-binding.md) | Identity and provider binding are separate axes — provider changes are inert (REQ-904 / #502) |
| [ADR-016](./016-seat-capabilities.md) | Seat capabilities are declared by the kind base and published as data (#551, ADR-005 enforcement) |

ADR-006 **amends** ADR-005’s `ApiKindBase` slot: user-facing kinds become CLI | API | Blueprint | Remote.

ADR-011 **amends** ADR-006: Remote stays one kind; variants are `RemoteHarness` implementations, not extra kinds.

ADR-012 **renumbers** the TUI Wave 0 record from draft ADR-011 to ADR-012 to resolve the collision with REQ-203 RemoteHarness ([#888](https://github.com/matthewhand/open-swarm/issues/888)).

ADR-014 is **Proposed** and would **amend** ADR-011 §3/§5 if accepted: it keeps Herdr a Remote implementation and drops its Team-member composition. ADR-011 §7 (Slack) is unaffected.

Related research (not an ADR): [Grok Bot keybinding parity](../GROK_KEYBINDING_PARITY.md) (REQ-150 / #552).
