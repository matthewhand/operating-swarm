# REQ-888 — Docker Desktop Sandbox Provider & Capability Badges (#466)

> Adds a native **Docker** sandbox provider positioned between **Bare metal host** and **Daytona**, establishing capability badging (`desktop` on Docker/Daytona, `cloud` on Daytona) with desktop local execution inspired by the OpenMousBot and Rakazo architecture.

**Issue:** [#466](https://github.com/matthewhand/open-swarm-private/issues/466)  
**Related:** [REQ-860 (Sandboxes)](./REQ-860-sandboxes.md), [REQ-863 (Sandbox Completion)](./REQ-863-sandbox-completion.md), [ADR-003 (Desktop Packaging)](../adr/003-desktop-packaging.md)

---

## 1. Context & User Intent

Currently, **Settings → Sandboxes** provides a binary choice between:
- **`none`** (Default safe: no execution tools attached)
- **`bare_metal`** (Dangerous: unisolated execution directly on host OS)
- **`daytona`** (Cloud microVMs via Daytona SaaS)

There is a major gap between dangerous unisolated host execution and third-party SaaS cloud microVMs: many developers on desktop workstations (macOS, Windows, Linux) have Docker or Docker Desktop running locally and want **ephemeral local container isolation** without leaking credentials, without risking their host filesystem, and without requiring external cloud accounts or API tokens.

This specification introduces:
1. **Docker Sandbox Provider (`docker`)**: Positioned directly between `bare_metal` and `daytona`.
2. **Capability Badges**: Clear visual badges on provider cards in Settings:
   - `Docker`: `desktop`
   - `Daytona`: `desktop` and `cloud`
   - `Bare metal host`: `dangerous`
   - `None`: `default`
3. **Desktop Architectural Alignment**: Adopts the local loopback/desktop execution model from OpenMousBot and Rakazo (ADR-003), auto-discovering local desktop sockets and managing container lifecycle.

---

## 2. Positioning & Provider Hierarchy

In `SandboxesSettingsPane.tsx` and `src/swarm/views/sandbox_settings_api.py`, providers are displayed and ordered as follows:

| Index | Provider ID | Label | Badges | Description |
|---|---|---|---|---|
| 0 | `none` | **None** | `default` | Execution tools are not attached. Safe default. |
| 1 | `bare_metal` | **Bare metal host** | `dangerous` | Executes Python/Bash directly on this host with no isolation. |
| 2 | `docker` | **Docker** | `desktop` | Isolated local execution inside ephemeral containers via Docker Desktop / Docker engine. |
| 3 | `daytona` | **Daytona** | `desktop` `cloud` | Agents execute inside isolated Daytona workspaces (local daemon or cloud microVMs). |

---

## 3. Desktop Architecture & Inspiration from Rakazo / OpenMousBot

In [ADR-003](../adr/003-desktop-packaging.md) and the OpenMousBot/Rakazo execution model, desktop applications operate on a local loopback server controlling local tools and environments. The Docker desktop sandbox adapts this pattern:

1. **Local Socket Auto-Discovery:**
   - Detects the local Docker engine via standard desktop sockets without requiring manual host/port configuration:
     - Linux / macOS: `/var/run/docker.sock`
     - Windows: `//./pipe/docker_engine`
     - Environment variable override: `DOCKER_HOST`
2. **Ephemeral Session Containers:**
   - Rather than executing directly against the host or spinning up heavy persistent VMs, an ephemeral container (e.g. `python:3.11-slim` or configured custom image) is spawned for agent execution.
   - Tagged with `open-swarm-sandbox=<session_id>` for automated tracking and cleanup.
3. **Workspace Mounting:**
   - Mounts the user's project workspace directory (or a copy-on-write scratch workspace) into `/workspace` inside the container.
   - Files created or edited by `sandbox_write_file` / `sandbox_read_file` remain synced with the project tree while isolating execution side effects from the host OS.
4. **Lifecycle & Cleanup:**
   - Containers auto-stop and remove upon session cleanup or TTL inactivity timeout, preventing zombie container buildup on the developer's desktop.
5. **Honest Desktop Health Probe (`POST /v1/settings/sandbox/test`):**
   - Probes the Docker socket (`docker ping` / `docker info`).
   - If Docker Desktop is stopped or inaccessible, returns an honest diagnostic: `"Docker Desktop is not running or socket is inaccessible"`.

---

## 4. Detailed Requirements

### 4.1 UI & Configuration (`SandboxesSettingsPane.tsx`)
1. **Radio List Ordering**:
   - `None` → `Bare metal host` → `Docker` → `Daytona`.
2. **Badges**:
   - `Docker` displays `<span className="badge badge-secondary badge-xs">desktop</span>`.
   - `Daytona` displays `<span className="badge badge-secondary badge-xs">desktop</span>` and `<span className="badge badge-accent badge-xs">cloud</span>`.
   - `Bare metal host` retains `<span className="badge badge-error badge-sm">dangerous</span>`.
   - `None` retains `<span className="badge badge-ghost badge-sm">default</span>`.
3. **Docker Settings Form**:
   - Exposed when `provider === 'docker'`:
     - Container image (default: `python:3.11-slim`)
     - Auto-remove on session finish (checkbox, default `true`)
     - Memory limit (optional string, e.g. `2g`)
     - Extra environment variables (env-var names only)

### 4.2 Backend Implementation
1. **Provider Registry**:
   - Update `ALLOWED_PROVIDERS = ("none", "bare_metal", "docker", "daytona")` in `sandbox_settings_api.py`.
2. **`DockerSandbox` (`src/swarm/core/sandbox/docker_sandbox.py`)**:
   - Implements `SandboxBackend`.
   - Executes `execute_python` and `execute_bash` via Docker container exec API.
   - Executes `read_file` and `write_file` within container `/workspace`.
   - `cleanup()` stops and removes the session's container.
3. **Settings API & Test Probe**:
   - `POST /v1/settings/sandbox/test` when `provider: "docker"` runs a container check:
     - Verifies socket connectivity.
     - Runs a test echo/python evaluation in an ephemeral container.
     - Returns `{ ok: true, detail: "Docker container execution successful", duration_ms: ... }`.
     - Returns actionable error if Docker Desktop is stopped or permissions on `/var/run/docker.sock` fail.

---

## 5. Acceptance Criteria

- [ ] **Provider List Order**: `None` → `Bare metal host` → `Docker` → `Daytona` in both REST descriptor and UI.
- [ ] **Badge Rendering**:
  - [ ] `Docker` card displays `desktop`.
  - [ ] `Daytona` card displays `desktop` and `cloud`.
  - [ ] `Bare metal host` card displays `dangerous`.
  - [ ] `None` card displays `default`.
- [ ] **Docker Options UI**: Selecting `Docker` exposes container image, memory limit, and auto-remove options.
- [ ] **Backend Integration**:
  - [ ] `ALLOWED_PROVIDERS` includes `"docker"`.
  - [ ] `DockerSandbox` implements `SandboxBackend` with socket detection.
  - [ ] `POST /v1/settings/sandbox/test` honestly tests Docker connectivity.
- [ ] **Automated Tests**:
  - [ ] Frontend unit tests in `SandboxesSettings.test.tsx` assert provider order and badge rendering.
  - [ ] Backend unit tests in `tests/views/test_sandbox_settings.py` test REST serialization for `docker`.
  - [ ] Core unit tests in `tests/core/test_sandbox_docker.py` test `DockerSandbox` with mocked Docker API.
