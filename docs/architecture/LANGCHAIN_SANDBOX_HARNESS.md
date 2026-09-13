# RFC: LangChain Harness and Sandbox Integration (Complementing Core `openai-agent()`)

- **Status**: Proposed / Implemented (Initial Bare-Metal Harness & Manager)
- **Author**: Swarm Specialist
- **Date**: 2026-09-13
- **Related Issue**: [#195](https://github.com/matthewhand/open-swarm-private/issues/195)

---

## 1. Executive Summary

As Open Swarm coordinates multi-agent graphs across CLI, API, Blueprints, and Remotes, agents frequently require tool capabilities to execute code (Python REPL), invoke shell scripts (Bash), and read/write workspace artifacts.

Without execution harnesses and sandboxing:
- Arbitrary code execution threatens host stability, security, and secret isolation (e.g. LLM API keys present in host environment variables).
- Different frameworks solve this differently: **OpenManus** / **OpenMousBot** focuses on tool-level containment (Docker execution, E2B microVMs, subprocess pipes), while **LangChain** provides modular execution harnesses (`langchain_experimental.tools.python`, `langchain_community.tools.ShellTool`, and container wrappers).

This RFC establishes:
1. **The Architectural Principle: Complement, Not Replace.**  
   `openai-agent()` remains the mandatory, core orchestration engine governing agent turn loops, system prompts, function calling schemas, handoff transitions, streaming, and state machines. LangChain is utilized strictly as an execution harness / sandbox backend beneath agent tools.
2. **Initial Bare-Metal Host Execution**:  
   The initial implementation defaults to safe, bare-metal process execution in the designated host workspace, eliminating heavyweight Docker requirements for standard installs and tests.
3. **Pluggable Sandbox Abstraction**:  
   A modular `SandboxBackend` architecture supporting `local` bare-metal execution, `mock` deterministic testing, `langchain_repl` evaluation, and a clearly documented roadmap for containerized Docker and E2B microVM runners.

---

## 2. Comparative Analysis: OpenManus vs LangChain Sandbox Approaches

| Dimension | OpenManus / OpenMousBot | LangChain Sandbox Harness | Open Swarm Hybrid Model |
| :--- | :--- | :--- | :--- |
| **Primary Focus** | Autonomous agent turn loop + built-in bash/python tools | Standardized modular execution tools and harness abstractions | Core `openai-agent()` reasoning + LangChain/local sandbox harness |
| **Isolation Mechanism** | Subprocess containment, optional Docker wrapper, E2B microVMs | `PythonAstREPLTool`, Docker tools, E2B data analysis wrappers | Pluggable `SandboxBackend`: Local bare metal (sanitized env), LangChain REPL, Mock, Docker (roadmap) |
| **Tool Calling Contract** | Bespoke tool registry & JSON dispatch | LangChain `BaseTool` / runnable interfaces | Native `openai-agents` `function_tool` wrapping sandbox calls |
| **Secret Isolation** | Strips environment variables before child process spawn | Relies on external container or process configuration | Automatic stripping of `OPENAI_`, `ANTHROPIC_`, tokens, passwords from subprocess env |
| **Deployment Footprint** | Monolithic or containerized agent run | Framework-heavy if full LangChain imported | Lightweight: LangChain is an optional harness; zero hard dependency failures |

### OpenManus Tool Isolation Patterns
OpenManus incorporates tools such as `PythonExecute` and `BashExecute`. In its containerized distribution, commands are piped into a running Docker container or E2B sandbox session. When running locally, it isolates stdout/stderr and sets execution timeouts, but can expose host secrets if environment variables are inherited unchecked.

### LangChain Execution Harness Patterns
LangChain decouples execution harnesses into specialized tools:
- `langchain_experimental.tools.python.PythonAstREPLTool`: Evaluates code with AST parsing, locals/globals management, and output capture.
- `langchain_community.tools.ShellTool`: Provides platform-aware shell execution.
- Docker & E2B tools: Encapsulate sandboxed execution behind standard tool invocations.

---

## 3. Core Architectural Decision: Complementing vs Replacing `openai-agent()`

> **Key Rule**: LangChain **complements** rather than replaces `openai-agent()`.

```mermaid
flowchart TD
    subgraph Core Orchestration ["Core Orchestrator (openai-agents)"]
        A[User Message / API Request] --> B[openai-agents Agent Runner]
        B --> C[LLM Reasoning & Turn Loop]
        C --> D[Function Tool Schema & Selection]
        C --> E[Multi-Agent Handoffs]
    end

    subgraph Tool Boundary ["Open Swarm Tool Adapter"]
        D --> F[function_tool Callables]
        F --> G[SandboxManager.as_function_tools]
    end

    subgraph Execution Harness ["Sandbox Execution Harness"]
        G --> H[SandboxManager]
        H -->|Default| I[LocalSubprocessSandbox (Bare Metal)]
        H -->|Configured| J[LangChainSandboxHarness]
        H -->|Test / Offline| K[MockSandbox]
        H -->|Roadmap| L[Docker / E2B Sandbox]
    end
```

### Why Not Replace `openai-agent()` with LangChain?
1. **Handoff & Agent Graph Integrity**: Open Swarm's orchestration leverages `openai-agents` native `handoff(...)` graphs and `agent-as-tool` primitives. Replacing the core loop with LangChain `AgentExecutor` would break graph determinism, persona definitions, and consensus panels.
2. **Schema & Streaming Parity**: Open Swarm's WebUI and `/v1/chat/completions` API rely on exact token-by-token streaming, tool call deltas, and state transitions emitted by `agents.Runner`.
3. **Granular Fusion**: Orchestrating agents can select when to reach for sandboxed evaluation without shifting the entire reasoning runtime to another framework.

---

## 4. Architecture & Implementation in `src/swarm/core/sandbox/`

The sandbox architecture is organized into five modular components:

```
src/swarm/core/sandbox/
├── __init__.py           # Public exports: SandboxManager, backends, result types
├── base.py               # SandboxBackend ABC, SandboxConfig, SandboxExecutionResult
├── local_sandbox.py      # Local bare-metal subprocess sandbox with env sanitization
├── mock_sandbox.py       # Deterministic in-memory sandbox for unit tests and fallback
├── langchain_sandbox.py  # LangChain harness adapter with safe fallback
└── manager.py            # Factory, config resolution, and openai-agents function_tool adapter
```

### 1. Unified Execution Contract (`base.py`)
All backends implement `SandboxBackend`:
```python
class SandboxBackend(ABC):
    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult: ...
    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult: ...
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> bool: ...
    def is_available(self) -> bool: ...
    def cleanup(self) -> None: ...
```

### 2. Bare-Metal Host Execution (`local_sandbox.py`)
- **Default behavior**: Executes Python code and Bash scripts on the bare-metal host within the configured working directory (`work_dir`).
- **Secret Sanitization**: Automatically scrubs sensitive host environment variables (`OPENAI_*`, `ANTHROPIC_*`, `SECRET*`, `TOKEN*`, `KEY*`, `DATABASE_*`, `NEON_*`) to prevent prompt-injection attacks or untrusted scripts from exfiltrating credentials.
- **Path Confinement**: Asserts that file read/write targets remain inside configured `allowed_paths`.
- **Timeout Enforcement**: Process timeouts terminate stuck or runaway processes.

### 3. LangChain Harness (`langchain_sandbox.py`)
- Evaluates code using `PythonAstREPLTool` or `PythonREPLTool` if `langchain_experimental` is present.
- If LangChain is not installed, it gracefully degrades to `MockSandbox` or `LocalSubprocessSandbox` according to `fallback_to_mock`.

### 4. Bridge to `openai-agent()` (`manager.py`)
`SandboxManager.as_function_tools()` converts sandbox capabilities directly into `openai-agents` `function_tool` instances:
- `sandbox_run_python(code: str) -> str`
- `sandbox_run_bash(command: str) -> str`
- `sandbox_read_file(path: str) -> str`
- `sandbox_write_file(path: str, content: str) -> str`

---

## 5. Configuration & Blueprint Usage

### Configuration in `swarm_config.json`
```json
{
  "sandbox": {
    "backend": "local",
    "timeout": 30,
    "workspace": "./workspace",
    "allowed_paths": ["./workspace"],
    "sanitize_env": true,
    "fallback_to_mock": true
  }
}
```

### Dropping Sandbox Tools into an Agent
```python
from agents import Agent
from swarm.core.sandbox import SandboxManager, SandboxConfig

# 1. Initialize sandbox manager (defaults to bare metal local execution)
sandbox_mgr = SandboxManager(config=SandboxConfig(backend_type="local", timeout_seconds=45))

# 2. Extract tools for openai-agents
tools = sandbox_mgr.as_function_tools()

# 3. Create native openai-agent with sandbox capabilities
coding_agent = Agent(
    name="CodeRunner",
    instructions="Write and verify Python scripts using your sandbox tools.",
    tools=tools,
)
```

---

## 6. Roadmap: Containerized & MicroVM Sandboxing

While the current implementation provides bare-metal and LangChain REPL harnesses, the pluggable `SandboxBackend` interface directly prepares Open Swarm for future containerized backends:

1. **Docker Container Backend (`DockerSandbox`)**:
   - Spawns an isolated container per session or worker (`docker run --rm -v ...`).
   - Limits memory, CPU, and network egress (`--network none` for offline sandboxing).
   - Maps host workspaces into `/workspace` inside the container.
2. **E2B MicroVM Backend (`E2BSandbox`)**:
   - Integrates with E2B Cloud Sandboxes (Firecracker microVMs).
   - Instant 100ms startup for multi-tenant and untrusted cloud executions.
3. **LangChain Docker / Sandbox Tool Harmonization**:
   - Standardize LangChain community container tools through the `LangChainSandboxHarness` backend.
