# Abstraction map — how Open Swarm's layers compose

> The one-picture version of the abstractions this repo defines, what subclasses
> typically override, and which layer each belongs to. Each box links to its
> detailed diagram. Planned abstractions are marked *(planned)* and name their
> tracking issue.

```mermaid
flowchart TB
    subgraph harness ["Harness layer — what executes a turn"]
        direction LR
        BB["BlueprintBase<br/><em>low-level openai-agents unit</em>"]
        KB["KindBase templates<br/><em>api · cli · remote</em>"]
        BB --> KB
    end

    subgraph behavior ["Behavior layer — who does what inside a turn"]
        direction LR
        Role["Role hooks<br/><em>on_turn_start · wrap_tool_calls · on_turn_end · as_tool</em>"]
        Roles["Gate · Skeptic · Advisor · Suggestions<br/>ChiefOfStaff · Engineer"]
        Role --> Roles
    end

    subgraph context ["Context layer — what the model sees"]
        direction LR
        Compact["chat_compact<br/><em>ConversationSummary + include_in_context</em>"]
        Raw["/chat/raw-context/<br/><em>honest model view</em>"]
        Skeptic["skeptic_loop<br/><em>bounded worker×skeptic rounds</em>"]
    end

    subgraph presentation ["Presentation layer — how it looks"]
        direction LR
        Bubble["Bubble themes<br/><em>speech · simple · irc · feed</em>"]
        Avatar["Avatar themes<br/><em>bee · blobs · bland · robot3d · robots×10</em>"]
        AppTheme["App theme<br/><em>dark · light · system</em>"]
    end

    Roster["team_rosters<br/><em>wires roles + advisors + skeptics onto seats</em>"]

    KB -->|"roles ride on kind bases"| Role
    Roster --> behavior
    Compact --> Raw
    Skeptic -->|"rework attempts"| behavior
    Bubble -->|"dresses the transcript"| presentation
```

| Layer | Abstraction | Subclasses implement | Detail |
|---|---|---|---|
| Harness | `BlueprintBase` → `KindBase` | `run()`, `get_navbar_items()` | [kind-bases.md](./kind-bases.md) |
| Behavior | `Role` registry | `on_turn_start`, `wrap_tool_calls`, `on_turn_end`, `as_tool` | [roles.md](./roles.md) |
| Context | `ConversationSummary` spans | `include_in_context` archive policy, raw splice | `chat_compact.py` |
| Context | Skeptic rework loop | worker / skeptic closures, bounded rounds | `skeptic_loop.py` |
| Presentation | Bubble themes | user/agent bubble shape, chrome placement *(planned)* | [bubble-themes.md](./bubble-themes.md) |
| Presentation | Avatar themes | family install set, per-agent resolution | [avatar-themes.md](./avatar-themes.md) |
| Presentation | App theme | `dark` / `light` / `system` + navbar visibility | `theme.ts` |

## Planned (tracked, not yet abstractions)

- Bubble themes as an abstract class with overridable interface
  (datetimestamp placement: bottom for traditional chat, above/beside for IRC).
- Chief-of-Staff sections: topology tools so a CoS can bound which
  agents talk to which, creating teams of teams.
- Theme-gated optional streaming with markdown-safe partial render.

## Honesty

`tests/core/test_docs_diagrams.py` asserts the modules and exports named here
exist; each linked diagram carries its own honesty tests.
