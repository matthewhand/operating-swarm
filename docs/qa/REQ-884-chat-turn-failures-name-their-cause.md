# REQ-884 — Chat-turn failures name their cause

> Two defects found by one session-authenticated WebSocket probe against a dev
> stack, both of the same class: a server-side fault was reported to the operator
> as something else. A provider-client failure escaped the consumer and killed
> the socket, so the SPA blamed the connection; and an unset `${VAR}` in
> `swarm_config.json` was handed to the OpenAI client as a literal string, so it
> failed much later as an opaque URL/auth error that never named the variable.

**Status: shipped.** Lock test:
`tests/unit/test_req884_chat_turn_failures_name_their_cause.py`.
Behaviour tests: `tests/unit/test_consumer_turn_error_frame.py`,
`tests/unit/test_llm_profile_unresolved_env.py`.

---

## 1. Context

`swarm-cli` / the SPA chat path builds a provider client per turn. Two different
configuration faults on the same path produced one misleading user-facing message:

```
ASGI is not serving /ws/ or Origin does not match ALLOWED_HOSTS. Reconnect
```

That message is emitted by the frontend. It is accurate about the *symptom*
(uvicorn closed the socket) and wrong about the *cause*.

Evidence came from a probe that minted a real Django session and drove the
consumer over `ws/ai-demo/<conversation_id>/` against the dev stack on `:8002`:

1. With `ALLOWED_HOSTS`/Origin settled, the handshake reached
   `101 Switching Protocols` and the consumer accepted (`spa_hello`).
2. A `{"message": ...}` turn was accepted, the user message was echoed and an
   assistant response container was created — then the socket was **aborted**
   with no close frame.
3. The container log named the real fault:

```
openai.OpenAIError: The api_key client option must be set ...
  File ".../uvicorn/protocols/websockets/websockets_sansio_impl.py", line 409, in run_asgi
  File ".../channels/generic/websocket.py", line 204, in websocket_receive
```

4. The same log showed the profile's `base_url` arriving at the client as the
   literal `'${LITELLM_BASE_URL}'` — an unexpanded placeholder from
   `~/.config/swarm/swarm_config.json`, whose `LITELLM_BASE_URL` /
   `LITELLM_API_KEY` were unset.

---

## 2. Finding A — an escaped exception aborts the socket

`DjangoChatConsumer._run_serialised_chat_turn` dispatched to
`respond_with_blueprint` / `respond_with_team_stub` / `respond_with_default_model`
with **no** guard around the dispatch. Those methods handle generation failures
internally (and route them through `send_error_message`), but anything raised
*around* them — most importantly constructing the model client — escaped
`websocket_receive`. Uvicorn then aborted the socket with no close frame, and the
SPA had nothing to report except the connection-level message above.

### Requirement

**R1.** A failure anywhere in the turn dispatch must reach the client as an error
partial on the existing socket, never as an aborted connection.

**R2.** The error partial must reuse the established transport, wording shape and
privacy rules: `send_error_message(contents_div_id, client_safe_error_message(...))`,
with `public=` text that does not claim to be a connection fault.

**R3.** `client_safe_error_message` keeps its documented split — production sends
only the public text, `DJANGO_DEBUG=true` appends a capped exception type/message
for the operator.

### Acceptance criteria

- [x] The dispatch in `_run_serialised_chat_turn` is wrapped in `try/except`.
- [x] The handler logs the exception (`logger.exception`) so the operator can see
      a full traceback even when the socket is already gone.
- [x] It sends an error partial via `send_error_message`, and a failure *of that
      send* is swallowed at debug level (the socket may be gone).
- [x] The message is not appended to `self.messages`, so an error frame cannot
      enter the context of a later turn.
- [x] No credential or raw exception text reaches the client outside debug.

---

## 3. Finding B — an unset `${VAR}` reaches the client literally

`os.path.expandvars` leaves an **unknown** reference untouched. `_substitute_env_vars`
(the loader's deliberate, test-pinned behaviour — see
`tests/core/test_config_manager.py`) therefore returns `"${LITELLM_BASE_URL}"`
unchanged when that variable is unset, and `get_resolved_llm_profile` passed it
straight through. `AsyncOpenAI(base_url="${LITELLM_BASE_URL}")` accepts that
string — it is a perfectly valid value — so the fault surfaced only later, as a
request-time URL/auth error naming nothing useful.

The same holds for `api_key`: a literal `"${LITELLM_API_KEY}"` is a non-empty
string, so the SDK accepts it and sends it as a bearer token. That is worse than
failing: it produces a 401 from the gateway that looks like a revoked credential.

### Requirement

**R4.** A resolved LLM profile must never carry an unresolved `${NAME}` in
`api_key` or `base_url`.

**R5.** The unset variable must be named in a warning, so the operator can fix
configuration without reading source.

**R6.** Env substitution semantics stay unchanged: the loader keeps leaving
unknown references alone (a documented contract with its own tests), and the
guard lives in the resolver, not in substitution.

### Acceptance criteria

- [x] `drop_unresolved_env_values(profile)` removes only values that still
      contain a braced `${NAME}` placeholder and returns the missing names.
- [x] `get_resolved_llm_profile` applies it after `_apply_litellm_overrides`, so a
      variable that *is* set still overrides normally.
- [x] One `logger.warning` names the profile and every missing variable, and says
      the values were ignored.
- [x] Dropping `api_key` restores the SDK's own `OPENAI_API_KEY` lookup; dropping
      `base_url` avoids sending a request to a literal `${...}` target.

---

## 4. Deliberate scope

- **`model` is not dropped.** A bad model id fails at request time with the model
  name quoted back, so it already names the offending value. Dropping it to `None`
  would replace a clear error with a vaguer one. Pinned by
  `test_resolver_deliberately_keeps_a_placeholder_model`.
- **Only the braced `${NAME}` form is matched.** An unbraced `$NAME` can appear
  inside a literal secret (`sk-live$abc`), and a false positive there would
  discard a working credential.
- **`drop_unresolved_env_values` warns rather than raises.** `llm_profile` is also
  read for inspection (CLI surfaces, model-id resolution) and by test-mode runs
  that need no client at all. Raising in the resolver broke three legitimate
  callers during development; naming-and-dropping fixes the misleading value
  without changing what a profile *read* means.

---

## 5. Locked sources

| Behaviour | Source |
|-----------|--------|
| Turn dispatch guard + error frame | `src/swarm/consumers.py:576-625` |
| Placeholder detection | `src/swarm/core/config_loader.py:36` (`unresolved_env_placeholders`) |
| Placeholder drop | `src/swarm/core/config_loader.py:59` (`drop_unresolved_env_values`) |
| Resolver integration | `src/swarm/core/config_loader.py:522` |
| Debug/prod error text | `src/swarm/utils/env_utils.py` (`client_safe_error_message`) |

---

## 6. Verification

- `tests/unit/test_consumer_turn_error_frame.py` — an escaping exception sends one
  error frame with a non-empty message; production text leaks neither the
  exception type nor an embedded secret; debug text does (documented trade-off);
  the error frame does not enter model context.
- `tests/unit/test_llm_profile_unresolved_env.py` — placeholder detection across
  nested values, no false positive on unbraced `$`, drop + warning naming the
  variables, env-set substitution unaffected, real values untouched, `model`
  intentionally kept, and `_get_model_instance` never forwarding a placeholder to
  the client.
- Live: the same probe that aborted the socket now completes two consecutive
  turns with the socket intact (`socket_survived_two_turns: True`, no `ABORTED`).
- Live (dev stack on `:8002`, the container reads the host's
  `~/.config/swarm/swarm_config.json`): resolving profile `default` logs the
  warning naming `LITELLM_API_KEY` / `LITELLM_BASE_URL` and returns
  `['cost', 'intelligence', 'model', 'provider', 'speed']` — no `api_key`, no
  `base_url`, and no placeholders left to send.

---

## 7. Follow-ups (not part of this requirement)

1. **Set the operator's own credentials.** The dev stack still has no
   `LITELLM_BASE_URL` / `LITELLM_API_KEY`; the probe deliberately did not invent
   secrets, so chat replies still cannot be generated until they are set in `.env`
   (gitignored) or `~/.config/swarm/.env`.
2. **Audit the other client-construction sites.** Seven blueprint subclasses
   duplicate `_get_model_instance` and build `AsyncOpenAI` themselves
   (`poets`, `stewie`, `chatbot`, `jeeves`, `whiskeytango_foxtrot`, `suggestion`,
   `dynamic_team`). They inherit the resolver's fix, but the duplication is why
   this class of bug is easy to reintroduce.
3. **Consider a config-doctor surface.** `requirements.py` already aggregates
   `unresolved_env` for MCP servers; an LLM-profile equivalent could surface the
   same warning at `swarm-cli` startup instead of on first chat.
4. **Unrelated finding, found while verifying:** `load_full_configuration` with no
   override resolves its default through `paths.get_swarm_config_file()`, which
   returns `~/.config/swarm/config.yaml` — a file nothing writes, loaded with
   `json.load`. So every no-override caller silently proceeds with an empty base
   config; `requirements.load_active_config()` is one, which is why an
   MCP-compliance check can report nothing missing. The loader's own discovery
   (`find_config_file`) would return the real `swarm_config.json`. Changing that
   default is not a one-liner: `tests/core/test_paths.py` pins the `config.yaml`
   name, and pointing the default at discovery would make several tests read the
   developer's real XDG config instead of their fixtures.
