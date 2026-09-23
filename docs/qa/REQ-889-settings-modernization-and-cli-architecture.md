# REQ-889 — Settings Modernization, Protocol-Driven CLI Architecture & Support Agent Integration

> Comprehensive modernization of the Operating Swarm settings system: reorganizing 16 flat tabs into a 5-category information architecture, replacing ad-hoc CLI configuration with a protocol-driven `BaseCliAgent` driver architecture, implementing OpenMousBot-grade candidate discovery and pre-save probes, enabling the Support Agent to scaffold custom CLI subclasses, building a native React chat retention dashboard, consolidating duplicate panes, and adding settings search with an in-UI config editor.

---

## 1. Problem Description & Strategic Motivation

### 1.1 The Freeform CLI Configuration Defect
In `webui/frontend/src/components/CliAgentsSettingsPane.tsx`, users are currently presented with a freeform form asking for `Name` and `Command (comma-separated)`. If a user enters an uncatalogued agentic CLI (e.g. `aider`, `amp`, or a proprietary in-house tool), it inevitably breaks or hangs during chat turns.

An agentic CLI is **not an arbitrary shell script**; it is an interactive agent harness requiring a strict protocol contract:
1. **Non-Interactive Execution**: Passing the prompt via `-p={prompt}` (Claude, Grok), `-o json -p "{prompt}"` (Gemini), `exec -- {prompt}` (Codex), `run -- {prompt}` (OpenCode), or piping into `stdin`.
2. **Output Parsing**: Extracting the agent's text from `json:.result` (Claude), `json:.text` (Grok), `json:.response` (Gemini), or plain text.
3. **Session Resumption**: Re-engaging sessions via `--resume <id>`, `-s <id>`, or inspecting SQLite (`agy`) / JSONL (`qwen`) stores.
4. **Model Listing**: Polling available models via subcommands (`opencode models`) or documented matrices.
5. **Tool Approval Bypasses**: Bypassing interactive confirmation prompts (`--dangerously-skip-permissions`, `--always-approve`, `--yolo`) without which headless execution deadlocks waiting for stdin.

Allowing arbitrary text entry creates broken configurations. Operating Swarm must restrict UI configuration to **known, protocol-compliant CLI drivers**, while providing an extensible **object-oriented driver hierarchy** that the **Support Agent** can scaffold for users.

### 1.2 Information Architecture & Navigation Clutter
The current Settings sheet displays **16 flat, unorganized buttons** with no visual hierarchy, no category grouping, and inconsistent nomenclature (e.g. `"Show LLM profiles"` using an action verb).
- `Hostname` consumes an entire full-page tab for a single text input.
- `AvatarThemePicker` is misplaced under `Rail`.
- `MCP servers` and `Plugins` exist as separate, confusing tabs that both configure `mcpServers`.
- Contextual inspection drawers (`definition`, `blueprint`) are mixed directly into global instance settings.
- There is no search/filter bar to locate specific configuration options.

### 1.3 Incomplete Stub Implementations & Blind Saves
- **Retention**: `RetentionPane` is an empty stub rendering `<a href="/settings/#chat-retention-title">`, forcing users out of the React SPA to an outdated Django HTML template.
- **Remotes**: `AddRemoteForm` commits URLs directly to `swarm_config.json` without any pre-save connectivity or latency verification.
- **System**: `SystemPane` lists `advanced_sections` and instructs users to edit them via `curl` or `swarm-cli` rather than providing an in-app JSON editor.

---

## 2. Architecture & Requirements

### 2.1 Protocol-Driven CLI Architecture (`BaseCliAgent`)

All agentic CLIs must implement an object-oriented Python driver contract inheriting from `BaseCliAgent`:

```python
class BaseCliAgent(abc.ABC):
    """Protocol and execution contract for an agentic CLI harness."""
    name: str
    display_name: str
    default_binary: str
    env_allowlist: list[str] | None = None
    list_capability: str = "unsupported"  # works | paste-only | unsupported

    @abc.abstractmethod
    def build_exec_argv(
        self, prompt: str, session_id: str | None = None, model: str | None = None
    ) -> list[str]:
        """Construct non-interactive argv with prompt, safety bypasses, and flags."""
        ...

    @abc.abstractmethod
    def parse_output(self, stdout: str) -> str:
        """Extract the agent response from stdout (JSON dotpath or text)."""
        ...

    def list_models(self) -> list[str]:
        """Enumerate models supported by this CLI."""
        return []

    def list_sessions(self, cwd: str | None = None) -> list[CliSession]:
        """Enumerate active/past sessions for this CLI."""
        return []

    def resume_session_argv(self, session_id: str) -> list[str]:
        """Flags needed to resume a session."""
        return []

    def smoke_flags(self) -> list[str]:
        """Flags injected only on smoke/verify runs."""
        return []

    def probe_binary(self, binary_path: str) -> ProbeResult:
        """Run <binary> --version with redacted env, 64KB maxBuffer, and 10s SIGKILL."""
        ...
```

1. **Concrete Drivers**:
   Ship built-in subclasses for all supported tools:
   - `ClaudeCliAgent` (`claude`)
   - `GrokCliAgent` (`grok`)
   - `GeminiCliAgent` (`gemini`)
   - `CodexCliAgent` (`codex`)
   - `AgyCliAgent` (`agy`)
   - `OpenCodeCliAgent` (`opencode`)
   - `KiloCodeCliAgent` (`kilo`)
   - `PiCliAgent` (`omp`)
   - `QwenCliAgent` (`qwen`)
   - `HermesCliAgent` (`hermes`)
2. **Dynamic Driver Registry (`CliRegistry`)**:
   - Loads all built-in drivers on startup.
   - Automatically imports custom driver subclasses located in `src/swarm/custom_cli_agents/` or `~/.open-swarm/cli_drivers/`.
3. **Backend Discovery & Probe Endpoints**:
   - `GET /v1/cli-agents/candidates?name=<cli>`: Scans every folder in `PATH` (PATHEXT-aware on Windows: `.exe`, `.cmd`, `.bat`) and returns all discovered absolute filesystem paths.
   - `POST /v1/cli-agents/test`: Spawns `<binary> --version` with a 10s SIGKILL timeout, 64KB bounded buffer, and a credential-redacted environment (removing sensitive keys like `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`). Returns `{ ok: true, version: str }` or `{ ok: false, message: str }`.

### 2.2 Support Agent Scaffolding Workflow (`wusupport`)

When a user wishes to connect a new or proprietary agentic CLI (e.g. `aider`, `amp`, `devin-cli`):
1. The user asks the **Support Agent** (`wusupport`): *"Help me integrate a new CLI called `mycli`."*
2. The Support Agent executes an automated integration skill:
   - **Help & Version Inspection**: Runs `mycli --help` and `mycli --version` to discover CLI flags.
   - **Protocol Determination**: Identifies prompt input mode (stdin vs `-p` vs positional), output format (JSON structure vs text), session flags (`--resume`), and model selection (`--model`).
   - **Subclass Scaffolding**: Generates `MyCliAgent(BaseCliAgent)` in `src/swarm/custom_cli_agents/mycli.py`.
   - **Verification Turn**: Executes `probe_binary()` and a single-turn verification prompt (`"Say OK"`).
   - **Live Registration**: Calls `CliRegistry.register()`. The new CLI immediately appears in Settings and the Chat routing dropdown as a verified, first-class participant.

### 2.3 OpenMousBot-Grade CLI Management UI (`CliAgentsSettingsPane`)

1. **No Freeform Entry**: Replace the raw text input form with a **Registered Driver Catalog**.
2. **Interactive `CustomPicker` UX**:
   - **Candidate Dropdown**: Populated dynamically from `GET /v1/cli-agents/candidates?name=<cli>`.
   - **Manual Wrapper Input**: Uses quote-aware tokenization (`splitCliString`) so arguments with spaces work cleanly. No comma-separated string splitting!
   - **Pre-Save Probe**: Enter key or clicking Save triggers `POST /v1/cli-agents/test`.
     - Successful probe -> commits immediately.
     - Failed probe -> displays warning alert: *"Test failed — [reason]. Register this path anyway?"* with *"Edit path"* and *"Save anyway"* buttons.
   - **Live Version Badge**: Renders detected version string (e.g. `v0.42.0`) directly on the CLI row.
   - **One-Click Reset**: When a path override is active, a "Reset" button reverts back to the default catalog binary.

### 2.4 Categorized Settings Navigation (5 Groups)

Restructure the 16 flat navigation tabs in `SettingsSheet.tsx` into 5 logical categories with Lucide icons:

```
🎨 GENERAL & APPEARANCE
   • Appearance (Light/Dark/System theme, top-bar toggle)
   • Avatars & Bubbles (Avatar style pack, bubble streaming toggle)
   • Network & Hostname (Hostname override with live ping indicator)

🤖 MODELS & RUNTIMES
   • CLI Agents (OMB candidate picker, pre-save probe, version badges)
   • LLM Profiles (Default profile, task-class routing, rate limits)
   • Remotes (Hermes, OMB, Rakazo, Herdr, TrueForge + pre-save connectivity test)
   • Sandboxes (Bare metal, Docker Desktop [REQ-888], Daytona Cloud)

🔌 TOOLS & INTEGRATIONS
   • MCP & Plugins Hub (Consolidated stdio, SSE/HTTP, OpenAPI wizard, and tool discovery)
   • Agent Roles (Read-only mechanism & wiring inspector)

🎙️ MEDIA & VOICE
   • Image Generation (Models, base URL, pre-save generation test)
   • Speech (STT transcription & TTS synthesis provider endpoints)

💾 SYSTEM & STORAGE
   • Context Strategy (Compress vs Cull trigger %, cull fraction %)
   • Chat Retention & Persistence (Native React dashboard: active chats, trash, disk usage)
   • Local Store & Config Editor (Store facts + in-app JSON editor for advanced_sections)
```

*Note*: Backward-compatible deep linking (`/chat?settings=<section>`) is strictly preserved for all legacy query parameters.

### 2.5 Native React Chat Retention Dashboard

Eliminate the link to `/settings/#chat-retention-title` and replace `RetentionPane` with a native React dashboard consuming backend endpoints:
1. **API Endpoints**:
   - `GET /v1/chat/retention/stats`: Returns `{ active_count, trash_count, bytes_used, bytes_label, store_dir, max_age_days, chats: [...], trash: [...] }`.
   - `POST /v1/chat/retention/action`: Supports `archive`, `archive_all`, `restore`, and `empty_trash`.
2. **Dashboard UI**:
   - **Metrics Bar**: Stat cards for Active Chats, In Trash, and Disk Used.
   - **Global Actions**: "Archive All to Trash" and "Empty Trash" (with confirmation dialog).
   - **Active Chats List**: Chat agent ID, message count, updated relative time, and "Move to trash" button.
   - **Trash List**: Restorable threads with filename, message count, and "Restore" button.

### 2.6 Deduplication & Enhancements
1. **Merge MCP Servers & Plugins**:
   - Deprecate the barebones `McpServersPane.tsx` (which only supported single-env comma-separated strings).
   - Expand `PluginsServersPane.tsx` into the unified **"MCP & Plugins Hub"** supporting Stdio, SSE/HTTP, OpenAPI proxy wizards, multi-environment variables, and live tool discovery.
2. **Pre-Save Remote Health Check**:
   - In `AddRemoteForm` (`RemotesSettings.tsx`), add a "Test Connection" button that validates the remote base URL and reports status/latency prior to saving.
3. **Settings Quick Search**:
   - Add a search input at the top of the SettingsSheet navigation (`Cmd/Ctrl+K` shortcut).
   - Live filters sections and highlights matching setting items.
4. **In-App Advanced Config Editor**:
   - In `SystemPane`, provide an interactive collapsible JSON editor for `advanced_sections` allowing operators to view and patch sections directly with schema validation.

---

## 3. Acceptance Criteria

- [ ] **Protocol-Driven CLI Drivers**:
  - [ ] Abstract class `BaseCliAgent` created in `src/swarm/core/cli_driver.py`.
  - [ ] Built-in drivers implemented for all shipped CLIs (`claude`, `grok`, `gemini`, `codex`, `agy`, `opencode`, `omp`, `qwen`, `kilo`, `hermes`).
  - [ ] `CliRegistry` dynamically discovers and loads custom drivers from `src/swarm/custom_cli_agents/`.
  - [ ] Support Agent equipped with scaffolding skill to interview user, probe new binary, generate subclass, verify, and register.
- [ ] **OMB-Grade CLI Settings**:
  - [ ] `GET /v1/cli-agents/candidates` returns all matching executable paths on `augmentedPath`.
  - [ ] `POST /v1/cli-agents/test` executes `--version` in a sanitized, credential-redacted environment with a 10s SIGKILL timeout.
  - [ ] `CliAgentsSettingsPane` shows candidate dropdown, quote-aware wrapper input, probe failure override alert, version badges, and one-click reset.
  - [ ] Freeform random name addition is removed in favor of configuring registered drivers.
- [ ] **Categorized Settings Navigation**:
  - [ ] 16 flat tabs restructured into 5 distinct categorized sections with icons and headers.
  - [ ] Hostname integrated into General → Network with status indicator.
  - [ ] Avatar theme picker relocated from Rail into General → Avatars & Bubbles.
  - [ ] Existing deep links (`/chat?settings=cli-agents`, `/chat?settings=llm-profiles`, etc.) continue to navigate correctly.
- [ ] **Native React Retention Dashboard**:
  - [ ] `GET /v1/chat/retention/stats` endpoint exposed.
  - [ ] `RetentionPane` renders active chat stats, disk usage, active thread list, trash list, "Move to trash", "Restore", and "Empty trash" directly in React.
  - [ ] No external redirect to `/settings/#chat-retention-title`.
- [ ] **Consolidation & Enhancements**:
  - [ ] `mcp` and `plugins` consolidated into a unified "MCP & Plugins Hub".
  - [ ] Add Remote form includes a working "Test Connection" button.
  - [ ] Settings Quick Search allows filtering sections by keyword.
  - [ ] SystemPane includes an in-app JSON editor for `advanced_sections`.
- [ ] **Verification**:
  - [ ] Unit tests for `BaseCliAgent`, `CliRegistry`, candidate discovery, and CLI probe endpoints in `tests/unit/`.
  - [ ] Vitest component tests for the modernized `CliAgentsSettingsPane`, categorized `SettingsSheet`, and native `RetentionPane`.
