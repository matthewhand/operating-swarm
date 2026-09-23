# ADR-016: Seat capabilities are declared by the kind base and published as data

**Status:** Accepted (#551, implementing ADR-005's doctrine)

## The rule

> A control appears because the seat **advertises the capability** — never
> because a string compared equal to `'api'`.

`BlueprintBase` stays kind-neutral. Each kind base declares its defaults;
an individual recipe may override a **single axis** on its own subclass with
no frontend change and no new conditional anywhere.

## The vocabulary (declared today)

| Capability | Question | API default | CLI default | Remote default |
|---|---|---|---|---|
| `attach` | may the user attach files? | ✅ | ❌ *File attachments aren't supported for CLI seats* | ❌ *…for remote seats* |
| `compact` | may the thread be summarised? | ✅ | ❌ *needs a default API profile or a provider `cli_compact` hook* | ❌ *the transcript belongs to the remote provider* |
| `plugins` | may the agent use plugin tools? | ✅ | ❌ *available on API and blueprint seats* | ❌ *available on API and blueprint seats* |
| `routines` | may the agent be scheduled? | ✅ | ❌ *routines drive swarm-side scheduling* | ❌ *routines drive swarm-side scheduling* |

A capability outside this vocabulary resolves to **not offered** (rule 4) —
a surface probing an unknown name can never receive "on".

## Declaration site

`src/swarm/core/kind_bases.py`:

```python
class CliKindBase(KindBase):
    seat_capabilities: ClassVar[dict[str, SeatCapability]] = {
        "attach": _cap(False, "File attachments aren't supported for CLI seats"),
        ...
    }

# A single recipe that genuinely differs overrides one axis:
class AttachyCli(CliKindBase):
    attach = {"enabled": True}
```

## Resolution order (`seat_capability(base, name)`)

1. a per-axis class attribute on the seat's own class;
2. the kind base's `seat_capabilities` declaration dict;
3. **not offered** — a capability nobody declared is never invented.

## Publication

`GET /v1/cli-agents/` carries `seat_capabilities`:

```json
{
  "api":     { "attach": {"enabled": true, "reason": ""}, … },
  "cli":     { "attach": {"enabled": false, "reason": "…"}, … },
  "remote":  { … }
}
```

The frontend consumes `declaredCapabilities` (via `composerMenuCapabilities`)
and defers to it; when the payload is absent (older backend), the previous
kind-derived gates remain as the fallback so an older payload can never
silently **widen** a seat's powers.

## Provenance

- Pilot: `attach` (was a hand-written `composerFileAttachSupported` kind check).
- Also folded: `plugins` (#516's `pluginsSwarmOwned` remains the fallback),
  `compact`, `routines`.
- Unknown-capability probe: `seat_capability(CliKindBase, "does_not_exist")`
  → not offered, with a reason.
- Vocabulary documented here feeds **#540** (browsable Blueprint SDK docs).
