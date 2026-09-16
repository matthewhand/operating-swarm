# REQ-894 — Letta Integration Parity and Spec of Record

> Comprehensive specification of record and QA documentation for the Letta (formerly MemGPT) remote integration in Open Swarm: live resume/chat/stream prove harness, teammate handoff parity, tolerant health probes, and no-mint invariants.

**Status: shipped.**  
Reference issue: #476.  
Verification tests:
- `tests/core/test_letta_remote.py`
- `tests/core/test_remote_teams.py`
- `tests/test_tracked_files_sanitization.py`  
Smoke script: `scripts/prove_letta_remote.py`.

---

## 1. Context & Rationale

Letta (formerly MemGPT) is a stateful memory-agent service providing persistent long-term memory, persona blocks, and workflow agents. In Open Swarm, Letta agents are represented as remote sessions under the unified remotes subsystem (`src/swarm/core/remotes.py`), and callable as teammates/delegates via remote teams (`src/swarm/core/remote_teams.py`).

Prior to REQ-894, the Letta remote implementation had three parity gaps:
1. **Health probe rigidity**: Letta server versions and deployment topologies expose different health endpoints (`/v1/health`, `/v1/health/`, or `/health`). Rigid probes caused false "DEGRADED" states.
2. **Teammate handoff disparity**: `chat_remote` in `remote_teams.py` only supported OpenAI-compatible completions endpoints (`/v1/chat/completions`) or Herdr CLI dispatch (`chat_herdr`). Passing a Letta teammate caused HTTP 404/405 errors because Letta requires posting to `/v1/agents/{id}/messages`.
3. **Smoke harness gaps**: `scripts/prove_letta_remote.py` was limited to health and listing, lacking the full lifecycle proof: health -> list -> resume -> send (sync) -> stream (deltas) -> marker round-trip.

REQ-894 closes these gaps, unifies teammate dispatch, and establishes the formal specification of record for Letta integration.

---

## 2. Capability Matrix

| Capability | Supported | Description |
| :--- | :---: | :--- |
| **health** | ✅ | Probes `/v1/health`, `/v1/health/`, or `/health` with tolerant fallback. Verifies TCP connectivity and HTTP status / auth requirements. |
| **list** | ✅ | Lists existing Letta agents via `GET /v1/agents/` (or `/v1/agents`), normalized to Open Swarm session records (`id`, `title`, `source='letta'`, `channel`, `snippet`). Searchable via title/snippet filter. |
| **resume** | ✅ | Resumes an existing agent by ID. Open Swarm attaches to the existing Letta memory/workflow context without creating a duplicate agent. |
| **send (sync)** | ✅ | Synchronous turn dispatch via fallback `POST /v1/agents/{id}/messages`. Extracts assistant text from `messages` payload. |
| **stream (SSE)** | ✅ | Streaming deltas via `POST /v1/agents/{id}/messages/stream` (`stream_tokens=True`). Yields token deltas with reasoning/ping filtering. |
| **teammate handoff** | ✅ | First-class sidebar & agent router team dispatch via `chat_letta` / `chat_remote(framework="letta")`. Uses resolved agent ID. |
| **operate** | ❌ (Intentional) | Arbitrary remote administrative commands or container operations are not supported for Letta. |
| **agent minting** | ❌ (Invariant) | Open Swarm **never mints new Letta agents**. Sends without a valid session/agent ID are refused with `gap: "letta_agent_required"`. |

---

## 3. Supported Operations

### 3.1 Health Check (`check_health`)
- **Probes**: Sequential candidate inspection:
  1. `spec.health_path` (default `/v1/health`)
  2. `/v1/health/` (FastAPI slash-redirect tolerance)
  3. `/health` (root health endpoint)
- **Success Criteria**: HTTP status in `200..299` (`UP`), or `401`/`403` (`UP` with `auth_required=True` since endpoint is alive).
- **Extracted Version**: Parsed from response JSON (e.g. `{"version": "..."}`).

### 3.2 List Agents / Sessions (`operate(..., "list")`)
- **Endpoint**: `GET /v1/agents/` or `/v1/agents`
- **Output Schema**:
  - `id`: Letta agent UUID (`agent-xxxxxxxx-...`)
  - `title`: Agent name
  - `source`: `"letta"`
  - `channel`: Agent type (e.g. `memgpt_agent`, `workflow_agent`)
  - `snippet`: Agent description
- **Filtering**: `filter_letta_sessions(sessions, query)` performs case-insensitive substring search over ID, title, snippet, and channel.

### 3.3 Chat Send (`operate(..., "send")` & `iter_letta_chat`)
- **Streaming endpoint**: `POST /v1/agents/{agent_id}/messages/stream` with `{"messages": [{"role": "user", "content": prompt}], "stream_tokens": true}`.
- **Sync fallback**: If stream returns 404 or fails to stream, falls back to `POST /v1/agents/{agent_id}/messages`.
- **Response Parsing**: `_letta_assistant_text` extracts visible assistant content from `messages` list, skipping `user_message`, `reasoning_message` (unless no other text), and `tool_call_message`.

### 3.4 Teammate Chat (`chat_letta` & `chat_remote`)
- Located in `src/swarm/core/remote_teams.py`.
- Signature:
  ```python
  def chat_letta(
      base_url: str,
      messages: list[dict[str, Any]] | str,
      *,
      agent_id: str = "",
      timeout: float = 60.0,
      api_key: str | None = None,
  ) -> str:
  ```
- Resolves endpoint `{base_url}/v1/agents/{agent_id}/messages`.
- Dispatches from `chat_remote` when `framework in ("letta", "memgpt")`, mapping `model` to `agent_id`.

---

## 4. Error Taxonomy

| Error Condition | Surface / Source | Behavior / Message |
| :--- | :--- | :--- |
| **Missing Agent ID** | `operate send` | Returns `OperateResult(ok=False, gap="letta_agent_required", detail="Pick a Letta agent. Open Swarm does not mint new agents...")` |
| **Missing Agent ID** | `iter_letta_chat` | Yields `("", True, "Pick a Letta agent. Open Swarm does not mint new agents...")` without issuing HTTP requests. |
| **Missing Agent ID** | `chat_letta` | Raises `RuntimeError("letta agent id is required (Open Swarm does not mint new agents)")`. |
| **Unconfigured** | `check_health` | Returns `HealthResult(ok=False, state="UNKNOWN", detail="Remote 'letta' is not configured")`. |
| **Missing/Bad API Key**| `list` / `send` | Returns HTTP 401 with `"Letta /v1/agents/ requires a valid API key. Set remotes.letta.api_key or LETTA_API_KEY..."`. |
| **Agent Not Found (404)** | `send` | Yields `"Letta agent '{id}' was not found. List sessions and pick an existing agent."`. |
| **Upstream LLM Failure**| SSE / Sync | Parses upstream `{"error": ...}` or `{"detail": ...}` and returns `"Letta upstream error: <msg>"`. |
| **Empty Response** | SSE / Sync | Fails cleanly with `"Letta returned an empty reply."` or `"remote team response had no message content"`. |
| **Network / TCP Down** | Prober | Returns `HealthResult(ok=False, state="DOWN", detail="tcp <host>:<port> refused/timed out")`. |

---

## 5. Environment Keys & Configuration

| Environment Variable | Config Equivalent | Purpose | Example |
| :--- | :--- | :--- | :--- |
| `LETTA_BASE_URL` | `remotes.letta.base_url` | Root or `/v1` URL of the Letta server. Default `:8283`. | `http://127.0.0.1:8283` |
| `LETTA_API_KEY` | `remotes.letta.api_key` | Authentication token or password for Letta server / Letta Cloud. | `letta-sk-...` |
| `LETTA_AGENT_ID` | `remotes.letta.agent_id` | Optional override default agent ID for smoke testing scripts. | `agent-12345` |
| `REMOTE_TEAM_API_KEY` | - | Generic fallback bearer token across remote teams. | `team-key` |

> [!IMPORTANT]
> No hardcoded IPs, ports, or secrets are ever committed into codebase files. All default specs use placeholders (`${LETTA_BASE_URL}`, `${LETTA_API_KEY}`).

---

## 6. Non-Goals

1. **No Agent Minting in Open Swarm**: Open Swarm does not create Letta agents on-the-fly. Letta agents represent stateful, preconfigured entities created in Letta ADE (Agent Development Environment) or via Letta CLI/API. Open Swarm only attaches, lists, resumes, and routes messages.
2. **Not Replacing Local Memory Engines**: The Letta remote integration connects to an external or self-hosted Letta server; it is distinct from in-process Swarm memories.
3. **No Hardcoded Network Topology**: Neither test suites nor proof scripts assume a live daemon at fixed addresses. Everything is configurable via environment variables and fully mockable in hermetic tests.

---

## 7. Verification & Smoke Testing

### 7.1 Hermetic Unit Tests
Run via pytest:
```bash
uv run pytest tests/core/test_letta_remote.py tests/core/test_remote_teams.py tests/test_tracked_files_sanitization.py
```
Validates:
- No-mint invariants (`iter_letta_chat`, `chat_letta`, `operate send`).
- Tolerant health checks across `/v1/health`, `/v1/health/`, and `/health`.
- Sync and streaming chat fallbacks.
- Catalog and alias definitions (`memgpt` -> `letta`).
- Header and credential sanitization.

### 7.2 Live Smoke Script
Run against a running Letta instance:
```bash
LETTA_BASE_URL="http://<letta-host>:8283" LETTA_API_KEY="<key>" python3 scripts/prove_letta_remote.py
```
Stages proven:
1. **Health**: Probes server health and extracts version metadata.
2. **List**: Retrieves and lists agents as resumable sessions.
3. **Resume**: Selects an active agent; verifies no-session send rejection.
4. **Send (sync)**: Sends a synchronous test turn into the resumed agent.
5. **Stream (deltas)**: Streams token deltas from `/messages/stream`.
6. **Marker round-trip**: Transmits a unique `SWARM-PROOF-<hex>` token and validates round-trip echo.
