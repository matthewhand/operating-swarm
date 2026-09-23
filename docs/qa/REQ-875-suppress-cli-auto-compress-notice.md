# REQ-875 — Suppress "Auto Compress Skipped" Notices for CLI Agents (#269)

> Restricts context auto-compression and its "Auto-compress skipped — model context length unknown" status notice to the API subclass (`ApiKindBase`), completely suppressing it for CLI agents (`CliKindBase`).

**Issue:** [#269](https://github.com/matthewhand/open-swarm-private/issues/269)

---

## 1. Context & Root Cause Analysis

When chatting with CLI agents (such as `qwen`, `omp`, `claude`, `grok`, or `cli_agent`), the chat transcript currently displays a status notice:
```text
Auto-compress skipped — model context length unknown.
```

Investigation of the backend pipeline revealed:

1. **Context Compression is an API Subclass Feature**:
   - In Open Swarm, context auto-compression (REQ-87) and culling are designed specifically for the **API subclass** (`ApiKindBase`), where Open Swarm manages the token budget and context window across LLM completions.
   - CLI agents (`CliKindBase`) manage their own sessions, transcripts, and context natively in their host processes.
2. **Defective Kind Classification**:
   - In [`src/swarm/core/agent_kind.py`](../../src/swarm/core/agent_kind.py) (`classify_agent_kind`):
     ```python
     text = (raw or "").strip().lower()
     if text.startswith("cli:"):
         return "cli"
     # ...
     return "api"
     ```
     Raw CLI names (such as `qwen`, `omp`, or `cli_agent`) do not start with the prefix `cli:`. As a result, `classify_agent_kind("qwen")` incorrectly returns `"api"`.
3. **Consumer Compression Trigger**:
   - In [`src/swarm/consumers.py`](../../src/swarm/consumers.py) (`_auto_compress_before_send`):
     - It checks `if classify_agent_kind(active_id) != "api": return None`. Because `"qwen"` was classified as `"api"`, it proceeds into `prepare_context_before_send`.
     - It also fails to inspect `params.get("cli")` when routing parameters indicate a CLI turn.
4. **Unknown Context Length Notice Broadcast**:
   - In [`src/swarm/core/context_compress_policy.py`](../../src/swarm/core/context_compress_policy.py), because CLI agents do not have token limits configured in LiteLLM profiles, `max_ctx` is `None`.
   - The policy assigns `result.info = UNKNOWN_MAX_INFO` (`"Auto-compress skipped — model context length unknown."`).
   - `consumers.py` broadcasts `result.info` via `_status_line_html(result.info)` as a visible chat status notice.

---

## 2. Requirements

### 2.1 Bypass Compression for CLI Agents in WebSocket Consumer
1. **Parameter Inspection**:
   - In `src/swarm/consumers.py` (`_auto_compress_before_send`):
     - If `params` contains a `"cli"` key (e.g. `params.get("cli")`), immediately return `None`.
     - If `active_id` or `model_id` resolves to a CLI agent (`classify_agent_kind == "cli"`, `is_cli_agent`, or `cli_from_rail_id`), immediately return `None`.
2. **Zero Status Notices for CLI**:
   - Ensure no `UNKNOWN_MAX_INFO` status HTML is ever broadcast for CLI turns.

### 2.2 Accurate CLI Classification in `agent_kind.py`
1. **Catalog CLI Recognition**:
   - Update `classify_agent_kind(raw)` in `src/swarm/core/agent_kind.py`:
     - If `raw` matches `cli_agent` or any known catalog CLI name (via `is_catalog_cli` or `cli_from_rail_id`), classify as `"cli"`.
     - Also check if the underlying blueprint class is an instance or subclass of `CliKindBase`.

### 2.3 Silence in `context_compress_policy.py`
1. **Return Clean Result for Non-API Agents**:
   - In `auto_compact_before_send`:
     - If `raw_agent` is classified as `"cli"` or `params.get("cli")` is present:
       - Return `AutoCompactResult(acted=False, reason="cli_agent", info=None, ...)`.
       - Never set `info` to `UNKNOWN_MAX_INFO` for CLI agents.

---

## 3. Acceptance Criteria

- [ ] When sending messages to CLI agents (`qwen`, `omp`, `codex`, `grok`, etc.), the notice `"Auto-compress skipped — model context length unknown."` is never displayed in the chat.
- [ ] Context compression is strictly bypassed for all CLI turns.
- [ ] `classify_agent_kind` correctly classifies `cli_agent` and catalog CLI names as `"cli"`.
- [ ] API subclass agents (`ApiKindBase` / `chatbot` / `api_agent`) continue to run context compression normally.
- [ ] **Tests**:
  - [ ] Python unit tests in `tests/core/test_context_compress_policy.py` verifying `auto_compact_before_send` returns `info=None` for CLI agent names and CLI parameters.
  - [ ] Python unit tests in `tests/core/test_agent_kind.py` asserting `classify_agent_kind("qwen") == "cli"` and `classify_agent_kind("cli_agent") == "cli"`.

---

## 4. Key Files to Modify

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `src/swarm/consumers.py` | Chat websocket consumer | In `_auto_compress_before_send`, check `params.get("cli")` and bypass compression for CLI turns. |
| `src/swarm/core/agent_kind.py` | Agent kind classifier | Classify catalog CLI names and `cli_agent` as `"cli"`. |
| `src/swarm/core/context_compress_policy.py` | Compression policy | Return `info=None` and `reason="cli_agent"` when given CLI agent identifiers. |
| `tests/core/test_context_compress_policy.py` | Unit tests | Add test assertions that CLI agent turns never yield `UNKNOWN_MAX_INFO`. |
