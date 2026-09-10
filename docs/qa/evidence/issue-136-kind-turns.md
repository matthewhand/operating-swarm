# Issue #136 — recorded kind-turn evidence

Captured from `uv run pytest` on this branch. No secrets, no live paid
providers, no hostnames. Dummy test Bearer is a fixture string, never a
production token.

Command:

```bash
uv run pytest \
  tests/api/test_issue136_kind_chat_e2e.py \
  tests/core/test_agent_kind.py \
  tests/unit/test_issue136_csrf_bearer.py \
  tests/api/test_cli_fusion_api.py \
  tests/blueprints/test_software_dev.py \
  tests/blueprints/test_chatbot.py \
  -q --tb=line --no-cov
```

Result: **63 passed**.

| Path | Test | Outcome |
|------|------|---------|
| Guest / anon | `test_guest_without_credentials_is_denied` | 403 credentials (FAIL, honest) |
| Session, no CSRF | `test_session_without_csrf_is_denied` | 403 CSRF |
| Login primes CSRF | `test_login_and_accounts_login_prime_csrftoken` | `/login/` + `/accounts/login/` set `csrftoken` |
| Session + CSRF + Referer | `test_session_csrf_cycle_completes_a_turn` | 200 Support turn |
| SPA contract | `test_spa_chat_fetch_sends_credentials_and_csrf_header` | `credentials: 'include'` + `X-CSRFToken` from `csrftoken` |
| Bearer, no CSRF cookie | `test_bearer_without_csrf_cookie_completes_a_turn` | 200, not CSRF 403 |
| Bearer + session cookie | `test_bearer_plus_session_cookie_does_not_need_csrf` | 200 |
| CLI agent | `test_kind_turn_bearer_final_reply[cli_agent]` | 200 `CLI-ECHO:` |
| API agent | `test_kind_turn_bearer_final_reply[api_agent]` | 200 `You said:` |
| Blueprint | `test_kind_turn_bearer_final_reply[support]` | 200 team onboarder |
| Team / software_dev | `test_kind_turn_bearer_final_reply[software_dev]` + handoff test | 200 status; engineer BLOCKED |
| Stream | `test_kind_turn_streamed_sse` | SSE + `[DONE]` |
| Honest errors | unknown model 404; empty `cli_agents` named | PASS |
| Routed CSRF flag | `test_chat_completions_url_is_csrf_exempt_for_asgi` | `csrf_exempt` on both URL callbacks |
| `/v1/models` | `test_models_list_includes_api_agent_rail_id` | lists `api_agent` + `chatbot` + `cli_agent` + `support` + `software_dev` |

Full pytest listing: `/opt/cursor/artifacts/issue136_kind_chat_pytest.log` on the
agent run (not a secret).
