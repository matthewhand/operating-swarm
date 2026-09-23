# ADR-013: Agent-initiated multi-choice questions (`ask_user`)

- **Status:** Accepted for the **spike contract** (2026-09-16). Persistence, Settings toggle, multi-select, and Mode B are follow-ups.
- **Date:** 2026-09-16
- **Issue:** [#221](https://github.com/matthewhand/open-swarm-private/issues/221)
- **Related:** [#206](https://github.com/matthewhand/open-swarm-private/issues/206) / REQ-108 (`wrap_tool_calls` + verdict tools), [#217](https://github.com/matthewhand/open-swarm-private/issues/217) (theme interfaces), [#220](https://github.com/matthewhand/open-swarm-private/issues/220) (streaming opt-in), [#125](https://github.com/matthewhand/open-swarm-private/issues/125) (follow-up chips), [ADR-010](./010-role-agent-invocation-modes.md) (Mode A/B)
- **Supersedes:** none. Complements the existing ```question fence (`decision_question.py` / Support Socratic) which stays the **non-blocking** path.

**Decision:** Mid-turn questions to the operator are an **`ask_user` function_tool** that suspends the openai-agents run the same way Safety elicitation does: in-memory `Future` + a JSON WS frame. The UI renders `QuestionCard` (choice chips + custom free-text as the last option). The answer is a `question_answer` frame, **not** a new user chat turn.

No runtime engine changes. Default **off** (`elicit_questions`). Cap **one** outstanding question per turn. Sanitize ask/choices/answer. Gate elicitation may be pending at the same time; Safety wins the UI.

No secrets. No Neon. No branding changes.

---

## Issue quote

TrueForge can have the LLM ask the operator a question mid-turn: the UI renders multi-choice options plus a custom string input as the last choice, and the selection is sent back to the agent as its answer. Open-swarm has elicitation seeds (gate approval; consumers already push interactive `ui_events`) but no general agent→user question round-trip.

This ADR + spike is **not** the final feature. It picks the cheapest honest mechanism and locks the contract with tests.

---

## 1. Tool vs structured output

| Path | How it runs | Same-run resume? | Verdict |
|------|-------------|------------------|---------|
| **`ask_user` tool** (chosen) | LLM calls a `function_tool`. Runner waits on the tool result. Consumer `elicit_user_question` clones `elicit_tool_approval`. | **Yes** — the tool result is the answer. | Cheapest *honest* suspend. No engine change. Same seam as REQ-108 verdict tools (`function_tool` + named close). |
| **Structured turn output** (```question fence, already shipped) | Agent finishes the turn with a fence. UI may render a card. Operator's pick is the **next** user message. | **No** — new turn. | Keep for Support Socratic / non-blocking cards. Do not pretend it suspends. |
| **Consumer scrapes assistant text** | Pause after `assistant_final`, wait, inject a hidden user/tool message, re-enter the run. | Maybe, by fighting the run loop. | Rejected for the spike. Engine-adjacent. |

**Mode B (ADR-010):** do **not** attach `ask_user` on as-tool / handoff invocation. A role invoked as a tool must not elicit the human on the callee's configure thread. Mode A (human chat WS) is the only spike surface. If a Mode B agent needs a human answer, that is a child Issue (caller-context elicit).

**openai-agents:** `Runner.run` already awaits async tools. `ask_user` is async; the loop stays bounded because `MAX_OUTSTANDING_PER_TURN = 1` and the tool returns a string (never calls itself).

---

## 2. Transport & lifecycle

```text
LLM  --ask_user(ask, choices, other)-->  consumer.elicit_user_question
                                              │
                                              ├─ WS  {"type":"user_question", id, ask, choices, other, agent_id}
                                              │
                                              └─ await Future (300s, same as Safety)
Chat  --question_answer{id, answer}-->  resolve_question_answer  -->  Future.set_result
LLM  <-- tool result: "staging" (or custom text / timeout / interrupted)
```

`question_answer` is handled **off** the chat-turn lock, like `tool_decision`, so the in-flight run can resume.

**Why not a tagged user message?** A `{"message": ...}` frame takes the turn lock and would queue as a **new** turn (REQ-90 / REQ-171A-3). Special-casing `question_id` on user messages is more code for the same resume. The ticket's sketch is answered: we use a sibling of `tool_decision`.

| Event | Spike | Follow-up |
|-------|-------|-----------|
| Disconnect | In-memory Future; 300s timeout → `"timed out; user did not answer"`. Same as Safety. | Persist pending question on the conversation row + TTL. |
| Page refresh | In-flight run dies (WS consumer gone). Card does not come back as answerable. | Rehydrate unanswered cards as stale chrome; do not resume a dead run. |
| `cancel_turn` | Pending questions resolve `"interrupted"`. | — |
| Persist | Not persisted. Not a model turn. | Optional `ui_events` row for display-only history. |

---

## 3. UI surface

- **Blocking card** (`user_question` WS): `QuestionCard` on the current assistant bubble. Radio-list chips + custom free-text as the last option. Single-select only.
- **Non-blocking fence** (```question, already in Support Socratic): same card; pick is `sendText` (next turn). Does not resume the previous run.
- **Follow-up chips (#125 / REQ-85):** after the turn, never mid-token, never in LLM context. Different job — do not reuse chips for a blocking question.
- **Theme (#217):** card uses existing `.os-question-*` DaisyUI tokens (REQ-804). Theme-interface work stays on #217; this spike does not add a new composer/bubble interface.

**Multi-select:** deferred. v1 is one string back to the tool.

---

## 4. Safety / gate interplay

Gate elicitation lives in `wrap_tool_calls` → `elicit_tool_approval` (REQ-108 / #206). `ask_user` is a *different* pending Future.

**They may be pending simultaneously** (parallel tool calls in one model step).

Ordering:

1. **Safety dialog wins the UI.** While any tool on the bubble has `needsApproval`, the question card is **disabled**.
2. Answering Safety does not dismiss the question; the card re-enables.
3. Answering the question does not approve a dangerous tool.
4. Cap still applies: a second `ask_user` while one is outstanding returns `ERROR_CAP` without emitting.

CLI/remote never get `ask_user` (`uses_swarm_approval` is API-only), matching Safety.

---

## 5. Config

`elicit_questions: bool`, default **off** — same opt-in shape as streaming (#220) and `use_suggestions`.

- WS `params.elicit_questions` (true / `"true"` / `"1"` / `"on"`).
- SPA localStorage `swarm_elicit_questions:<agentId>` (`loadElicitQuestions`). No Settings checkbox in this spike.
- Server ignores the flag on CLI/remote channels.

Settings UI + extras-bag persist is a follow-up (mirror `use_suggestions`).

---

## Spike demo

One API seat (`chatbot` / `api_agent`) with `elicit_questions=true`:

- Tool description tells the model to call `ask_user` when it needs a pick.
- Contract tests use `demo_profile_question()`: *"Which profile should I deploy?"* with `staging` / `canary` / `prod` + custom.
- Consumer unit: emit `user_question` → `question_answer` resumes with `"prod"`.
- FE: card renders; chip sends `{type:"question_answer", id, answer}`.

Live LLM is not required for the contract. Enabling: `localStorage.setItem('swarm_elicit_questions:chatbot', 'true')` then ask the seat to pick a deploy profile.

---

## Follow-ups (not this PR)

1. Persist pending questions + stale-on-reload chrome.
2. Settings checkbox per seat (extras bag).
3. Mode B: elicit on the **caller's** human chat, never the callee configure thread.
4. Multi-select.
5. REST `/v1/chat/completions` has no WS to elicit — leave disabled or add a poll/SSE sibling.

---

## Code

* Core: `src/swarm/core/ask_user.py`
* Consumer: `elicit_user_question` / `resolve_question_answer`; install on API chat when opted in.
* SPA: `QuestionCard`, `chatWs` `user_question` / `question_answer`, `ChatPage` mount.
* Tests: `tests/core/test_ask_user.py`, `tests/test_consumers.py`, Vitest card + ChatPage + chatWs.
* QA: [ISSUE-221-ask-user.md](../qa/ISSUE-221-ask-user.md)
