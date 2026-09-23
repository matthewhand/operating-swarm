# REQ-863 — Abstracted Sandbox Completion: Bare Metal Host & Daytona SaaS Lifecycle (#253)

> Completes the abstracted sandbox execution framework initiated in REQ-860 (#227). Ensures the default remains "no sandbox" (`none`), while providing a first-class, out-of-the-box experience for **Bare Metal Host (Dangerous)** direct host execution, and completing the cloud lifecycle and workspace synchronization for **Daytona** SaaS microVMs.

**Issue:** [#253](https://github.com/matthewhand/open-swarm-private/issues/253)

---

## 1. Context & Baseline Architecture

In **REQ-860 / #227**, an initial sandbox abstraction was introduced:
- **`SandboxBackend` ABC** (`src/swarm/core/sandbox/base.py`): Common interface for code execution (`execute_python`, `execute_bash`, `read_file`, `write_file`, `is_available`, `cleanup`).
- **Implementations**:
  - `DisabledSandbox`: Backs the default `provider: "none"` (attaches zero execution tools to agents).
  - `LocalSubprocessSandbox`: Backs `provider: "bare_metal"` (direct subprocess execution on host).
  - `DaytonaSandbox`: Backs `provider: "daytona"` (cloud microVMs via the Daytona Python SDK).
  - `MockSandbox` and `LangChainSandboxHarness`.
- **`SandboxManager`** (`src/swarm/core/sandbox/manager.py`): Maps backend operations to `openai-agents` `FunctionTool` wrappers:
  `sandbox_run_python`, `sandbox_run_bash`, `sandbox_read_file`, `sandbox_write_file`.
- **REST Surface & Settings**:
  `GET/PUT /v1/settings/sandbox/` and `POST /v1/settings/sandbox/test` in `src/swarm/views/sandbox_settings_api.py`, exposed in the WebUI via `SandboxesSettingsPane.tsx`.

---

## 2. Investigation Findings & Gap Analysis

While the foundation is merged, several critical gaps remain to make the sandbox fully operational and safe:

### Gap 1: Out-of-the-Box "Bare Metal Host (Dangerous)" Experience
- **User Intent**: The user's primary workflow is running on **bare metal host** directly where Open Swarm operates, with full host tooling.
- **Current Limitation — Overly Strict Path Validation**:
  `LocalSubprocessSandbox._validate_path` rejects any file path not inside `work_dir` with a `PermissionError`. For a user intentionally running in `bare_metal` (dangerous) mode, agents cannot inspect parent directories, user configs, or sibling workspaces.
- **Current Limitation — Aggressive Environment Sanitization**:
  `BLOCKED_ENV_PREFIXES` in `local_sandbox.py` automatically filters out `GH_`, `GITHUB_`, `DATABASE_`, `OPENAI_`, `KEY`, `TOKEN`. In bare metal host execution, CLI tools (such as `gh`, `git`, package managers) require host credentials to function. When `bare_metal` mode is confirmed, full environment inheritance should be supported.
- **Settings & Tool Attachment Alignment**:
  In `blueprint_base.py`, `make_agent` checks `provider not in (None, "", "none")`, while the UI provides both a provider radio and a separate toggle "Attach execution tools". Selecting `bare_metal` should immediately and reliably attach the execution tools to agents without conflicting toggles.

### Gap 2: Daytona SaaS MicroVM Lifecycle & Leak Prevention
- **Missing MicroVM Cleanup**:
  `DaytonaSandbox.cleanup()` is currently an un-implemented no-op `pass`. When `daytona.create()` instantiates a remote microVM, the VM remains running indefinitely in Daytona cloud infrastructure. A clean destruction mechanism (`daytona.remove(sandbox)` or `sandbox.stop()`) on session finish or timeout is essential to prevent runaway cloud billing.
- **Missing Dependency Packaging**:
  `daytona` is not declared in `pyproject.toml`. It should be added under an optional extra:
  ```toml
  [project.optional-dependencies]
  sandbox = ["daytona>=0.5.0"]
  ```
- **Workspace Seeding / Synchronization**:
  A Daytona microVM launches with an empty disk. When an agent runs code in Daytona, it has no access to the current project files unless files are synchronized or a repository is cloned into the sandbox workspace.

### Gap 3: Broadening Execution Tool Attachment
- Currently, only blueprints inheriting from `BlueprintBase` and calling `make_agent()` receive sandbox tools. Standard single-agent chat turns (`respond_with_default_model`) or API agents must also have access to sandbox tools when enabled.

---

## 3. Detailed Requirements

### 3.1 Default Behavior
- The default provider remains **`none`** (`DisabledSandbox`).
- Out-of-the-box fresh installs attach NO execution tools, ensuring zero surprise host code execution.

### 3.2 Bare Metal Host (Dangerous) Execution
1. **Selection & Confirmation**:
   - The user selects `Bare Metal (Dangerous)` in Settings → Sandboxes and confirms the dangerous execution warning dialog/checkbox.
2. **Execution Capabilities**:
   - `execute_bash` executes directly using the host shell (`bash` / `sh`) in the host working directory.
   - `read_file` and `write_file` operate directly on the filesystem. When `bare_metal` is confirmed, path validation allows reading/writing across the workspace without artificial restrictions.
   - Environment variables: Provide an option to inherit the full host environment so developer CLIs (`git`, `gh`, `docker`, `python`) work seamlessly.
3. **Audit & Logging**:
   - Every bash command and python execution in bare metal mode is logged at `INFO` level with timestamp, command string, and duration.

### 3.3 Daytona SaaS MicroVM Integration
1. **Lifecycle Management**:
   - Implement `DaytonaSandbox.cleanup()` to stop/remove sandboxes when the session terminates or when `SandboxManager.cleanup()` is called.
   - Support optional workspace auto-stop TTL (e.g. 15 minutes of inactivity).
2. **Packaging**:
   - Add `sandbox = ["daytona>=0.5.0"]` to `pyproject.toml` optional dependencies.
   - Keep the lazy SDK import pattern so missing Daytona SDK never breaks non-Daytona users.
3. **Workspace File Context**:
   - Provide a mechanism to upload/sync target project files to the Daytona sandbox before execution begins.

---

## 4. Acceptance Criteria

- [ ] **Default Safe**: Fresh install defaults to `provider: "none"` with zero execution tools attached.
- [ ] **Bare Metal Host UX**:
  - [ ] Enabling `bare_metal` in Settings → Sandboxes immediately equips agents with `sandbox_run_bash`, `sandbox_run_python`, `sandbox_read_file`, `sandbox_write_file`.
  - [ ] `LocalSubprocessSandbox` permits executing shell commands and reading files in the project workspace without spurious permission blocks.
  - [ ] Host developer environment variables are preserved when bare metal mode is confirmed.
- [ ] **Daytona Lifecycle**:
  - [ ] `DaytonaSandbox.cleanup()` explicitly destroys/stops remote sandboxes upon session completion.
  - [ ] `pyproject.toml` includes `sandbox` extra with `daytona`.
- [ ] **Tests**:
  - [ ] Unit tests in `tests/core/test_sandbox_bare_metal.py` verify bare metal command execution and environment inheritance.
  - [ ] Unit tests in `tests/core/test_daytona_lifecycle.py` verify sandbox cleanup and lazy degradation when SDK/key is absent.
  - [ ] `tests/views/test_sandbox_settings.py` verifies REST configuration persistence and probe endpoint.
