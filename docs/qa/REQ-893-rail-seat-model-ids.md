# REQ-893 — Rail seats are model ids or they are not advertised as one

> `GET /v1/agents/` is the rail roster and reports `agent_type` per seat. An
> `api` row reads as "POST this to `/v1/chat/completions`" — but three of them
> answered `404 requested model (blueprint) was not found`. A seat that looks
> chattable and then 404s is worse than one that never offered the affordance,
> because the failure names nothing the operator can act on.

**Status: shipped.** Lock test:
`tests/unit/test_req893_rail_seat_model_ids.py`.

---

## 1. Context

Issue #426 reports the roster advertising three seats that completions rejects:

```
GET /v1/agents/  ->  starter-support (kind=api), researcher / writer (builtin)
POST /v1/chat/completions  model=starter-support|researcher|writer
  -> 404 "requested model (blueprint) was not found"
```

Both the REST view and the websocket resolve a chat turn through **one** shared
recipe — `resolve_chat_blueprint_id` (`core/agent_kind.py`) into the discovered
blueprints, via `get_blueprint_instance` (`views/utils.py`). `consumers.py:940`
imports that same helper, so `/ws/ai-demo/` and `/v1/chat/completions` already
agree: the ticket's "WS path must match REST" holds by construction, and only
the *advertisement* was wrong.

The three seats are not the same shape, which is why the ticket left two
checkboxes:

| Seat | Backing thing | Runnable blueprint |
|---|---|---|
| `starter-support` | `SUPPORT_AGENT_ID` (`core/support_agent.py`), a builtin Support seat | **Yes** — `blueprints/support/` (`SupportBlueprint`, `metadata.name = "support"`) |
| `researcher`, `writer` | `agent_router` specialists (`RESERVED_IDS` in `core/router_designs.py`) | **No** — no `blueprints/researcher/`; the persona lives in the router design |

`core/agent_types.py` documents builtins/specialists as "API agents", so the
intent is that they are LiteLLM-chattable. For `starter-support` that is simply
true. For the router specialists it is not: aliasing them to `chatbot` would
answer the call while silently discarding the persona, which is the fake-pass
the ticket forbids.

---

## 2. Requirements

**R1.** `starter-support` resolves on `POST /v1/chat/completions` and on
`/ws/ai-demo/`, using the **same** `/v1/models` alias recipe that
`api_agent` → `chatbot` already has (#136). No new blueprint class.

**R2.** `starter-support` appears in `GET /v1/models` as its own id, and passes
the completions model gate (`validate_model_access`) that produced the 404.

**R3.** The roster must not advertise a seat as a completions `model` id unless
the shared recipe resolves it. `researcher` / `writer` stay on the rail as
chrome.

**R4.** `researcher` / `writer` are not `/v1/models` ids — they keep their
existing `kind: builtin`, `agent_type: api` classification. **No fifth kind**
is invented, and no LiteLLM catalog entry is touched.

**R5.** The roster states this in machine-readable form: every row carries
`chat_model`, which is the id to POST, or `null` when the seat is
specialist-only. The roster row keeps `agent_id`, so the rail keeps working.

---

## 3. Implementation

* `core/agent_kind.py` — new `STARTER_SUPPORT_RAIL_ID` /
  `STARTER_SUPPORT_BLUEPRINT_ID` pair, mapped in `resolve_chat_blueprint_id`
  next to the existing `api_agent` case.
* `views/utils.py` — `starter-support` cloned from the `support` blueprint entry
  in `_load_all_blueprint_metadata_sync`, mirroring the `api_agent` block, so
  `/v1/models` lists it and `get_blueprint_instance` instantiates the real
  `SupportBlueprint`.
* `views/agent_router_views.py` — `annotate_chat_models()` stamps `chat_model`
  on the roster in both `list_agents` and `get_agent_info`. It accepts either
  the `{agent_id: row}` mapping or the flat list, and reuses
  `resolve_chat_blueprint_id` so the annotation is the recipe rather than a
  re-implementation of it.

### Acceptance criteria

- [x] `resolve_chat_blueprint_id("starter-support") == "support"`, case-insensitive.
- [x] `starter-support` is in `get_available_blueprints_sync()` with the `support`
      `class_type`, not a stub of its own.
- [x] `validate_model_access(None, "starter-support") is True` and
      `get_blueprint_instance("starter-support")` returns an instance.
- [x] `researcher` / `writer` report `chat_model is None` while keeping
      `kind == "builtin"` and `agent_type == "api"`.
- [x] `researcher` / `writer` are absent from `/v1/models`; `starter-support` is
      present.
- [x] Startup invariant test: for **every** roster row, a non-null `chat_model`
      resolves through `resolve_chat_blueprint_id` into the discovered
      blueprints and passes `validate_model_access`. This is the regression
      guard — the next seat added with a persona but no blueprint fails here
      instead of 404ing in production.

---

## 4. Deliberate scope

- **The router specialists keep `agent_type: "api"`.** `core/agent_types.py`
  maps `builtin → api` and the ticket forbids a fifth kind. "Not a completions
  model id" is published as `chat_model: None`, a property of the seat, rather
  than by re-typing the seat.
- **`chat_model` is computed, not hardcoded.** A list of known-specialist ids
  would drift the moment a blueprint is added or removed; deriving it from
  discovery means the roster cannot claim a model that `/v1/models` does not
  list.
- **On discovery failure the roster advertises nothing.** If
  `get_available_blueprints_sync()` raises, every row gets `chat_model: None`
  (with a warning) rather than the roster 500ing or advertising ids that
  cannot resolve. `/v1/models` is built from the same discovery, so an empty
  answer is the truth in that state.
- **Not touched:** `/v1/agents/<id>/send/` (the router's own direct-send path),
  the `agent_router` routing rules, and the LiteLLM catalog.

---

## 5. Locked sources

| Behaviour | Source |
|-----------|--------|
| Rail-id → blueprint recipe | `src/swarm/core/agent_kind.py` (`resolve_chat_blueprint_id`) |
| `/v1/models` alias recipe | `src/swarm/views/utils.py` (`_load_all_blueprint_metadata_sync`) |
| Completions model gate | `src/swarm/views/utils.py` (`validate_model_access`) |
| Shared instance factory (WS + REST) | `src/swarm/views/utils.py` (`get_blueprint_instance`), used by `src/swarm/consumers.py:940` |
| Roster annotation | `src/swarm/views/agent_router_views.py` (`annotate_chat_models`) |
| Support blueprint | `src/swarm/blueprints/support/blueprint_support.py` |

---

## 6. Verification

- `tests/unit/test_req893_rail_seat_model_ids.py` — all of the acceptance
  criteria above. Seven of its eight tests were written first and failed against
  the unfixed tree; the startup-invariant test is vacuously true before the fix
  (no row carries `chat_model`) and becomes the real guard after it.
- `tests/test_agent_router.py`, `tests/core/test_agent_kind.py`,
  `tests/core/test_fleet_seats_resolution.py`,
  `tests/core/test_support_nl_blueprint.py`, `tests/core/test_support_agent.py`,
  `tests/core/test_req74_blueprints_cli_api_only.py`,
  `tests/core/test_blueprint_discovery_behavior.py`,
  `tests/views/test_api_views.py` — 110 tests, 2 failures
  (`test_route_researcher_runner_and_error`, `test_list_agents_endpoint`),
  byte-identical with and without the change and pre-existing on `main`.
- `test_list_agents_includes_support_role` (#426-adjacent, already on `main`)
  still passes: `starter-support` keeps `role == "support"` and
  `agent_type == "api"`.

---

## 7. Follow-up (not part of this requirement)

`researcher` / `writer` are still reachable as *specialists* — `POST
/v1/agents/<id>/send/` and `agent_router`'s own routing both address them. A
follow-up could teach the chat dropdown to offer those seats through the router
(pinned `target_agent`) so the rail affordance leads somewhere useful instead of
being chrome. That is a new capability, not a fix, and the ticket explicitly
scoped this to "make the claim true or stop making it".
