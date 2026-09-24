# ADR-017: Concurrent per-agent turns — feasibility, minimal path, full design

**Status:** Accepted as an investigation record (#1097). **No behavioural change
ships from this document** — it is the deliverable the ticket asked for, plus a
sequenced PR path.

## 1. What is true today (single-flight, and where it is enforced)

### Model layer

- Django `ChatMessage` (`src/swarm/models/__init__.py:40`) carries
  `sender` (a loose string), `content`, `timestamp`, `tool_call_id`. There is a
  **`sender`** but no stable `turn_id`, no per-message `agent_id`, and no
  turn-lifecycle record.
- The WS thread mirror is `self.messages: list` on the consumer + the
  `IN_MEMORY_CONVERSATIONS` cache keyed `(user_id, conversation_id)`. One
  transcript, no per-turn identity.
- Frontend `ChatMessage` (`features/chat/chatMessages.ts`) has `key`, `role`,
  `streaming`, optional `persona` (#527) — no `agentId`, no `turnId`.

### Backend — the single-flight boundary is one object

`ChatConsumer.receive` routes chat frames to
`_run_serialised_chat_turn` (`src/swarm/consumers.py:507`), which holds
**`self._chat_turn_lock`** (one `asyncio.Lock` per socket) for the whole
`respond_with_*` run. That is the *entire* serialization:

- `self._cancel_event()` is **one** `asyncio.Event` per connection — cancel is
  necessarily global.
- `self.active_agent` is a single attribute, overwritten per turn.
- `self.messages` / `save_conversation` are append-only under the lock; two
  concurrent turns would interleave deltas into one transcript.

So: the ASGI handler is *not* inherently serializing (Channels runs each
`receive` as its own task), and streaming `send` frames are just awaits — the
lock is the only gate. `respond_with_*` itself is agent-parameterised already
(blueprint per message), which is why teams can fan out *sub*-agents inside one
locked turn today.

### Frontend derivations

- `generationIsInFlight(messages, awaitingAssistant)`
  (`lib/chatQueue.ts:161`) is a **global boolean**: any streaming row or the
  awaiting flag.
- `composerBusy = status === 'open' && generationIsInFlight(...)` gates the
  composer morph; `interruptRunningTurn(agent?)` (#1096) already carries an
  agent parameter but the server ignores it (one cancel event).
- The #603 queue drains one row per turn-completion; #198 enter-to-interrupt
  cancels "the" turn; #636 compaction assumes a quiet transcript.

### UI

Per-agent stop (#1096) exists on the working row. Streaming indicators are
per-row already. What does not exist: interleaved streaming from two agents in
one transcript, and a drain-target choice when several agents are busy.

## 2. What works today without any change

Teams/openai-agents fan-out already runs **multiple sub-agent generations
inside one locked turn** — concurrency exists below the boundary. What is
single-flight is the *user-facing seat* boundary: one composer-driven
generation per socket. This is why #1096's per-agent stop is the correct seam:
the UI row exists; only the identity does not.

## 3. Minimal PR path to 2 concurrent agents in one thread

1. **Turn identity in the WS stream** (backend, ~1 PR): mint
   `turn_id = uuid4()` at `_run_serialised_chat_turn` entry; stamp every
   outbound frame for that turn with `turn_id` + `agent_id` (the resolved
   blueprint). Frames are JSON; adding two keys is backward-compatible
   (old SPA ignores unknown keys).
2. **Per-turn cancel events** (backend, same PR): replace
   `self._turn_cancel_event` with `dict[turn_id, asyncio.Event]`
   (plus a "cancel all" fallback when `turn_id` is absent on the frame —
   #198's legacy behaviour survives verbatim).
3. **Per-agent lock granularity** (backend, same PR): key
   `_chat_turn_lock` as `dict[agent_key, asyncio.Lock]` where
   `agent_key = resolved blueprint (or remote name)`. Same agent ⇒ same
   serialisation as today (transcript-correctness per row); different agents ⇒
   parallel. Compaction/save still needs a *transcript* lock (see design).
4. **Frontend turn map** (frontend, ~1 PR): derive
   `turnsInFlightByAgent: Record<agentId, TurnState>` from the stamped frames
   (reducer same shape as #818's `aux_task_started/update` reducer);
   `composerBusy` becomes "any turn in flight" for submit gating only — the
   working row and stop button read the per-agent entry (#1096 already renders
   per row).
5. **Queue drain targeting** (frontend, small): when a queued send is promoted
   and its target agent is busy, either hold (per-agent queue) or promote-and-
   lock behind that agent's lock (server queueing, current semantics per
   agent). Minimal path: keep promote-and-lock — it degrades to today's
   behaviour per agent.

That is the smallest honest slice: two agents, one thread, interleaved
deltas, per-agent stop working end to end.

## 4. Full concurrency design (what "done" looks like)

### Turn lifecycle record

```python
@dataclass
class TurnState:
    turn_id: str
    agent_id: str | None      # resolved blueprint / remote name
    cancel: asyncio.Event
    started_at: float
```

`self.turns: dict[str, TurnState]`. Frames out carry `{turn_id, agent_id}`;
`turn_finished` frames close them. Persistence mirrors it: `ChatMessage` gains
`turn_id` + `agent_id` columns (nullable, backfill-free) and a lightweight
`ChatTurn` row (conversation, turn_id, agent_id, state, started/finished_at)
so reload reconstructs boundaries.

### Locking rules (the doctrine)

- **Per-agent lock** (respond run): serialization per agent row — a second
  send to the *same* agent still queues exactly like REQ-171A-3/#603.
- **Transcript lock** (short, only around `self.messages` mutation +
  `send_html` of the delta): keeps interleaved deltas from corrupting the
  HTML mirror without holding it across LLM awaits.
- **Compaction barrier** (#636): compaction waits for
  `self.turns` to be empty *or* takes the transcript lock exclusive —
  per-agent "quiet" replaces global quiet.

### Ordering guarantees

- Server stamps each outbound frame with a monotonic per-conversation
  `seq`; the SPA buffer orders deltas by `(seq)` not arrival. Deltas from
  different agents interleave only at frame boundaries, never inside a row —
  each delta names its `turn_id`.
- The transcript mirror groups rows per `turn_id`; the SPA's existing
  `threadKey` map gains a turn→agent attribution the same way `persona`
  (#527) rides today.

### Frontend derivations (replace the global boolean)

- `turnsInFlightByAgent` reducer owns busy-ness; `generationIsInFlight`
  stays as a derived "any" helper for submit gating (one line, no caller
  churn).
- The #603 queue rows gain `targetAgent`; drain chooses: target idle →
  promote; target busy → hold with a "waiting for <agent>" hint; no target →
  first-idle agent (current behaviour).
- #198 enter-to-interrupt: interrupts the turn the *queued send would have
  targeted*; if several run, the composer shows the working rows and the
  user clicks the row stop (#1096) — no global stop button anywhere.

### Sequencing of the remaining queues

| Surface | Today | Per-agent equivalent |
|---|---|---|
| #603 queue | FIFO per socket | FIFO per target agent; idle-agent promotion |
| #198 interrupt | global cancel event | cancel by `turn_id`/agent; "cancel all" only when the frame carries no identity |
| #636 compaction | global quiet | transcript-exclusive barrier; agents keep streaming through compaction of *other* rows |
| #818 aux tasks | per-connection registry | unchanged (already task-keyed) |

### Rollout sequencing

1. ADR (this document) → 2. turn identity + per-turn cancel (PR 1) →
3. per-agent locks + transcript lock (PR 2) → 4. frontend turn map + UI (PR 3)
→ 5. queue/compaction per-agent semantics (PR 4). Each PR keeps the full gate
green; after PR 2 the legacy global-cancel path still works, so old clients
degrade gracefully.

## 5. Risks

- **Transcript mirror correctness** — the HTML `send_html` path is the
  sharpest edge; the short transcript lock + `seq` ordering exist precisely
  for it.
- **Rate limits** — two concurrent turns hit provider limits twice as fast;
  the REQ-88 rate-limit surface already renders per provider.
- **CLI/remote seats** — CLI harnesses are process-at-a-time per pane; the
  per-agent lock *is* the honest serialisation there. Concurrency is an
  API/blueprint-seat capability first (declare it, ADR-016 style, rather than
  string-matching kinds).
