# Issue #221 — Agent-initiated questions (spike)

Issue: #`221`. ADR: [013-agent-initiated-questions.md](../adr/013-agent-initiated-questions.md).

**Intent:** Investigation + cheapest honest spike. An API seat can ask the operator a multi-choice question mid-turn; the UI renders choices plus custom free-text; the answer resumes the **same** run as the `ask_user` tool result.

No secrets. No Neon. No Operating Swarm branding edits.

---

## Contract (locked by tests)

| # | Criterion | Owner | Evidence |
|---|-----------|-------|----------|
| 1 | Default off | `elicit_questions_enabled` | `tests/core/test_ask_user.py` |
| 2 | CLI/remote never enable | same | same |
| 3 | Sanitize ask/choices/answer (`sanitize_model_text`, length caps) | `normalize_question` / `normalize_answer` | same |
| 4 | Cap one outstanding question per turn | `AskUserSession.ask` | same (`ERROR_CAP`) |
| 5 | Demo payload: deploy-profile, 3 choices + custom | `demo_profile_question` | same |
| 6 | WS `question_answer` is off the turn lock | consumer | `tests/test_consumers.py` |
| 7 | `elicit_user_question` emits `user_question`; answer resumes | consumer | same |
| 8 | FE parses `user_question` / builds `question_answer` | `chatWs.ts` | `webui/frontend/src/lib/__tests__/chatWs.test.ts` |
| 9 | Card: radio choices + custom last option | `QuestionCard` | `QuestionCard.test.tsx` |
| 10 | ChatPage sends `question_answer`; card disabled while Safety pending | `ChatPage` | `ChatPage.test.tsx` |

Run:

```bash
uv run pytest tests/core/test_ask_user.py tests/test_consumers.py -k "question or ask_user" -q
cd webui/frontend && npx vitest run src/lib/__tests__/chatWs.test.ts src/lib/__tests__/decisionQuestion.test.ts src/lib/__tests__/elicitQuestions.test.ts src/components/__tests__/QuestionCard.test.tsx src/pages/__tests__/ChatPage.test.tsx
```

---

## Live demo (optional, needs an LLM)

1. Chat with the **chatbot** / `api_agent` seat.
2. Opt in for that seat:

   ```js
   localStorage.setItem('swarm_elicit_questions:chatbot', 'true')
   ```

3. Ask: “Which profile should I deploy? Ask me with choices.”
4. Expect a card: staging / canary / prod + Custom profile.
5. Pick **staging**. The model should continue the same turn using that answer.
6. If a Safety Allow/Deny dialog is also up, the card stays disabled until Safety is resolved.

Without the localStorage flag the tool is not attached; the model cannot elicit.

---

## Follow-ups (not this spike)

- Persist pending questions across refresh / disconnect.
- Settings checkbox (mirror `use_suggestions`).
- Mode B elicit on the caller thread (ADR-010).
- Multi-select.
- REST completions have no WS elicit path.

---

## Not in scope

- Runtime engine changes.
- Infinite question loops (capped at one outstanding).
- Changing Operating Swarm / product branding.
