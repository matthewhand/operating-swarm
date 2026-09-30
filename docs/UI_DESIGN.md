# Operating Swarm — UI design doctrine

The rules that make the chat UI feel like one product. This is the **human-readable** reference;
`AGENTS.md` §3 only points here so the agent contract stays short.

Each rule states the rule, why it exists, where it is implemented, and **how to verify it** —
because most of these are invisible to jsdom and were previously only folklore in code comments.

Related: [ADR-001 primary UI](./ADR-001-primary-ui.md) (which framework owns which route).

---

## 1. Styling

### Design tokens, not literals
Use CSS theme variables (`var(--color-base-100)`, `var(--color-base-content)`,
`var(--os-rail-gutter)`, `--os-top-chrome-h`). Do not hardcode hex where a token exists, and do not
hand-roll a second scale next to Tailwind's — a Tailwind `pt-3` paired with a bespoke `0.4rem` is
how a spacing bug becomes unfixable-by-inspection.

### Role colour belongs to the badge only
Role colour lives **only** on `.os-agent-role-badge`. Rail rows never carry role fill, left borders
or background outlines.

### One capsule, one rule
Shared chrome (a group box, a card, a section shell) must be styled by a **single shared selector**.
Hand-copying a border/background/radius into a second rule is how two visually identical things
drift apart — the copy has no owner and no test. Extract a shared rule or a shared custom property.

---

## 2. Interaction

### Hover-reveal on pointer devices only
Per-row chrome — the message action row (copy / retry / read-aloud / edit) and the per-agent **Stop**
control — is revealed on hover **or keyboard focus** at `md` and above, and is **always visible
below `md`**, where there is no hover and no focus ring.

Canonical class set (`webui/frontend/src/components/MessageRowActions.tsx`):

```
opacity-100 pointer-events-auto
md:opacity-0 md:pointer-events-none
group-hover/osrow:md:opacity-100 group-hover/osrow:md:pointer-events-auto
group-focus-within/osrow:md:opacity-100 group-focus-within/osrow:md:pointer-events-auto
transition-opacity motion-reduce:transition-none
```

Two failure modes to avoid:
- **Unconditional hover-reveal** — unreachable by touch and by keyboard. Always pair the bare
  hover classes with their `md:` counterparts, and assert on the `md:` variants in tests.
- `pointer-events-none` while hidden, or the invisible control still eats clicks.

### Stop interrupts one agent
Clicking Stop aborts **that agent's turn only**; other agents keep streaming. The Stop control is
reachable from either working indicator (see below).

---

## 3. Working-state indicators are additive, never duplicated

A turn's status is signalled in exactly these places, and each is owned by **one** state:

| Indicator | Means | Owner |
|---|---|---|
| **3 eye-dots on the avatar** — sidepane row *and* toppane/composer | the agent is working: waiting on a model response | `AgentAvatar` `status="working"` (#791) |
| **"Running" badge** — `RunningStopBadge` | *additionally*, a **tool call** is in flight | turn/tool-phase signal |
| **Stop** | interrupts the current turn | see §2 |

Rules:
1. **Both avatars agree.** The sidepane row and the composer must never disagree about whether the
   agent is working.
2. **The badge is additive, never a substitute.** It is not "instead of" the eye-dots.
3. **Never drive both from one flag.** That is the bug this rule exists to prevent: with the badge
   keyed off the same `isStreaming` flag that already animates the avatar, a streaming row shows a
   spinner *and* dots on the face, reading as two things happening when only one is.


> **#1764 — one place says Running.** The under-message `RunningStopBadge` pill is the
> single Running affordance for the seat under chat (tool or function in flight). The bottom
> fan-out card stack is for **sibling** legs only — the roster executor's leg for the seat
> being talked to is excluded (`cardsForFanOutLegs({ excludeSeatIds })`). The in-bubble
> `ToolCallPopup` status badge suppresses its own "Running" label when that under-message
> pill already covers the same call (`hideRunningBadge`). Direct replies with no tool /
> subagent show avatar + bubble ellipsis only.
>
> **Status: implemented.** The tool-in-flight signal now exists end to end. The backend emits live
> `tool_status` frames (`src/swarm/core/turn_phase.py`), the client folds them into the turn registry
> (`lib/agentTurns.ts` — `ActiveTool` + the `tool_phase` reducer arm), and `RunningStopBadge` is gated
> on that signal rather than on `isStreamingAssistant`. The badge reads `Running · read_file` when a
> tool is named, and renders **no** pill when nothing is in flight.
>
> Four things the implementation had to get right, and that a future change must not undo:
>
> 1. **Never stuck**, via three independent layers: the terminal `tool_status` is emitted inside the
>    SDK run and therefore always *before* `turn_finished`; the client reducer clears `activeTool`
>    on the `turn_finished` arm unconditionally; and a per-tool watchdog
>    (`TOOL_STATUS_WATCHDOG_MS`) disarms on any terminal status. The bound is derived, not guessed:
>    `elicit_tool_approval` waits 300s for a human and the turn is capped at 600s, so it must clear
>    the former.
> 2. **The Stop control keeps its own gate.** The slot is still `isStreamingAssistant &&
>    interruptRunningTurn` — "this turn is live, so Stop must be reachable" — which is a different
>    contract from "a tool is in flight". Collapsing the two would hide Stop during the
>    pre-first-token window.
> 3. **Attach where seats are BUILT, not where one of them runs.** The first attempt put the attach
>    in `ApiKindBase.run`, which is dead for three of the nine API seats because they shadow `run`
>    and call `Runner.run` themselves — including `ChatbotBlueprint`, which is what `api_agent`
>    resolves to, i.e. *the default chat seat*. A producer wired to a method that does not run is
>    the same defect as a fix on an uncalled path: correct, tested, and invisible. The hooks are
>    therefore installed on the agent factories (`BlueprintBase.make_agent`, and
>    `create_starting_agent` overrides via `ApiKindBase.__init_subclass__`), which every seat
>    converges on. `attach_turn_phase_hooks` is idempotent, so the two factories cannot stack a
>    second hook. `tests/core/test_turn_phase_reachability.py` drives a real `Runner` through a
>    seat shaped like `ChatbotBlueprint` and fails if the frames stop flowing.
> 4. **Coverage is still partial, and honestly so.** Not every `Runner.run(` site builds its agent
>    through those two factories (e.g. `consumers.py:1425` constructs a bare `Agent` inline for the
>    sandbox default-chat path). Those seats emit no phase, and their badge correctly stays hidden —
>    never faked from `streaming`. CLI and remote seats have no swarm-side per-tool signal at all,
>    for the same reason.

---

## 4. Layout that tracks its container

### Left-anchor grids whose column count follows the container
A grid whose column count is derived from its own width (`repeat(auto-fill, <fixed track>)`) must
set `justify-content: start`.

Centring makes a tile's position a function of the container width:

```
centred:  x(i) = (W - tracksWidth)/2 + i*(track + gap)     ← depends on W
anchored: x(i) = margin            + i*(track + gap)     ← depends only on i
```

So with `center`, tiles slide sideways on **every pixel** of resize and jump on **each column-count
change** — and in a narrow rail the first tile can land at a *negative* x, outside its container.
With `start`, a 1→2→3 column change only appends/removes tracks at the trailing edge and existing
tiles never move.

### Pinned-grid geometry (reference implementation)
`webui/frontend/src/index.css` `.os-fav-grid` — track `5.25rem`, gap `0.5rem`, margin `0.75rem`,
`justify-content: start`, `justify-items: center`.

The sidepane drag already snaps to column detents (`webui/frontend/src/lib/railResize.ts`,
`railWidthForColumns`): 1 col → 118px, 2 → 210px, 3 → 302px, with the ultra-compact/avatar-only
detent at 88px between collapsed and one column. Snapping controls *when* the column count
changes; left-anchoring controls *what happens to the tiles* when it does. Neither substitutes for
the other.

### Verify with real layout — jsdom cannot see this
jsdom has no layout engine, so grid geometry, `getBoundingClientRect`, and centring bugs are
invisible to vitest. Use the real-renderer harness:

```bash
cd webui/frontend
node scripts/measure-pinned-grid.mjs            # sweep + invariant check, exits non-zero on drift
node scripts/measure-pinned-grid.mjs --shots /tmp/shots   # + PNG per detent
```

It sweeps the rail width 88→420px, reports column count and every tile's `x`, and fails if tiles 1
or 2 ever move horizontally. This is how the centring bug was found (70 distinct `x` values) and
how the fix was confirmed (0 movement).

---

## 5. Adding a doctrine

When a rule here is violated in review, fix the code **and** add the rule here with its rationale
and its verification method. A rule that lives only as a test assertion will drift, because nobody
thinks of the test as the specification. If a rule changes behaviour deliberately, say so in the
same entry so the history is readable.
