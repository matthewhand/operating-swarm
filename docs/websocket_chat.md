# Websocket chat (ASGI / Django Channels)

SPA transcript virtualization (look-only) is [ADR-004](./adr/004-virtualized-chat-history.md) (REQ-163). This page is the ASGI/WS contract, not the list window.

The chat UI (Django `templates/chat.html` and the SPA ChatPage) streams over a
websocket at:

```
ws(s)://<host>/ws/ai-demo/<conversation_id>/
```

## Wiring

- `src/swarm/asgi.py` — `application` (referenced by
  `settings.ASGI_APPLICATION`): `ProtocolTypeRouter` with `http` → the normal
  Django ASGI app, and `websocket` →
  `AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(...)))`.
- `src/swarm/routing.py` — `websocket_urlpatterns` mapping
  `ws/ai-demo/<conversation_id>/` to `swarm.consumers.DjangoChatConsumer`.
- `settings.py` — `daphne` (first, so `manage.py runserver` serves ASGI
  including websockets) and `channels` are in `INSTALLED_APPS`. Both are core
  dependencies in `pyproject.toml`, no extra needed.

## Running

Any of these serve both HTTP and the websocket route:

```bash
python manage.py runserver                      # dev (daphne integration)
daphne -b 0.0.0.0 -p 8000 swarm.asgi:application
uvicorn swarm.asgi:application
```

Notes:

- Connections require an **authenticated Django session cookie** (via
  `AuthMiddlewareStack`). A Settings-page API **bearer token does not**
  authenticate the websocket. Anonymous connects are accept-then-closed
  with close code **4401** (`WS_AUTH_REQUIRED_CODE`) and reason
  `authentication required` so the SPA can show a Sign-in CTA instead of
  an opaque failure — except **DEBUG + LAN/loopback**, which mints the
  preview user so a phone on the LAN can chat without signing in
  (`SWARM_ALLOW_ANONYMOUS=0` disables that). `receive()` re-checks auth so a
  frame that races the close cannot append to a transcript or invoke a
  blueprint/LLM.
- Overlapping ``{"message"}`` frames on one socket are serialised
  (REQ-171A-3 / #603): the consumer runs one ``respond_with_*`` at a time
  so ``self.messages`` and HTML ``message-response-*`` frames cannot
  interleave. A second composer Send before the first reply starts is
  queued in the SPA (REQ-90 / #447 pane). ``tool_decision`` / ``status`` /
  ``edit`` frames are not blocked by that lock.
- `Origin` must match `ALLOWED_HOSTS` (AllowedHostsOriginValidator).
- The consumer streams completions from `OPENAI_API_KEY` / `OPENAI_MODEL`
  (optionally `LITELLM_BASE_URL`/`OPENAI_BASE_URL`).
- Frames are HTMx-style HTML partials (`websocket_partials/*.html`); the SPA
  parses the same frames.
- No channel layer is required (the consumer never uses group sends), so
  `CHANNEL_LAYERS`/`channels-redis` configuration is unnecessary for chat.

### Connected vs Unavailable (journey / SPA)

| Badge | Typical cause |
| --- | --- |
| **Connected** | Valid session cookie + ASGI serving `/ws/` |
| **Unavailable — sign in required** | Close code 4401 (no Django session) |
| **Unavailable — websocket unreachable** | Socket never opened (ASGI down, wrong host, origin denied) |

Journey capture (`scripts/capture_user_journey.py`) logs in as `journey-admin`
before `/chat`, then waits for the connection-status badge so a healthy regen
of `spa-chat.png` shows **Connected**. The checked-in desktop/mobile frames
(2026-08-19) show **Connected**; **Unavailable** appears for 4401 / unreachable
— see [SCREENSHOTS.md](./SCREENSHOTS.md).

### Per-agent persistence (REQ-14)

Each agent thread is a Django `ChatConversation`. Writes go through
`ChatRepository` (one canonical row per message). A composer send inserts
exactly one `ChatMessage`; the finished assistant turn inserts one more.
A JSON file under `$SWARM_CHAT_DIR` (default `$SWARM_USER_DATA_DIR/chats`,
`active/<user>/<agent>.json`) is a cache exported after that commit. The
consumer saves when the send is recorded, when a turn finishes
(`assistant_final` / blueprint final partial — REQ-171A-2), and again on
disconnect (same rows, no duplicates). Status and edit frames still save
immediately (edits update the row).

Reload (`GET /chat/thread/?agent=`) and websocket reconnect
(`fetch_conversation`) share one load order — Django first, then a one-way
JSON import when the conversation has no rows (`swarm.core.thread_load`).
`ts` and `edited` survive both hydrate and reconnect. The WS in-memory cache
stays keyed by `(user_id, conversation_id)`. On-mode mint (REQ-171C-4) still
runs before any row load. Retention and trash (`SWARM_CHAT_MAX_AGE_DAYS`)
operate on the database and are on **Settings only** — not in the Chat chrome.

Dropdown changes (REQ-46) record a status event with a timestamp. The SPA
POSTs `/chat/thread/` and, when the socket is open, also sends
`{"type":"status","text":"CLI: antigravity → grok"}`. The consumer persists
that line as **UI metadata** (`ui_events`) and does **not** invoke a blueprint
or LLM.

REQ-70 reconstruction: status/info/hop chrome lives in `ui_events` (side
channel). CLI session select and PR-opened persist append those events via
`append_event`; they do not write `role=status` onto the model-turn list.
The UI reconstructs those lines into transcript chrome. Model context is
built from real user/assistant/tool turns only. Exclude helpers
(`messages_for_model`) remain a safety belt if mixed rows still exist
temporarily — they are not the Success architecture. Compact-fallback and
CLI `render_prompt` use the same turns-only payload.

Tests: `tests/test_asgi_routing.py` (full-stack routing/auth/round-trip) and
`tests/test_consumers.py` (consumer unit tests).
