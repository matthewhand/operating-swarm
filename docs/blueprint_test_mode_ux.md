# Blueprint Test Mode & UX Standards

This document describes the standards and patterns for test-mode output, spinner/box UX, and subprocess simulation in Operating Swarm blueprints.

## 1. Spinner/Box/UX Output in Test Mode

- **Purpose:** Ensures that blueprint outputs are testable, visually consistent, and user-friendly.
- **Key Patterns:**
  - Use ANSI/emoji boxes to summarize operation type, parameters, and results.
  - For search and analysis operations, display spinner lines such as:
    - `Generating.`
    - `Generating..`
    - `Generating...`
    - `Running...`
    - `Generating... Taking longer than expected`
  - Show progressive updates (e.g., line numbers, result counts) for long-running operations.
- **Implementation Example:**

```python
spinner_lines = [
    "Generating.",
    "Generating..",
    "Generating...",
    "Running...",
    "Generating... Taking longer than expected"
]
for line in spinner_lines:
    print(line)
print_search_progress_box(
    op_type="Semantic Search Spinner",
    results=[*spinner_lines, "Found 7 matches", "Processed", "✨"],
    ... # other params
)
```

## 2. Subprocess Simulation for Test Mode

- **Purpose:** Allows blueprints to simulate subprocess lifecycle (`!run`, `!status`) for robust, deterministic testing.
- **Utility:** Use `TestSubprocessSimulator` from `swarm.core.test_utils`.
- **Pattern:**

```python
from swarm.core.test_utils import TestSubprocessSimulator

simulator = getattr(self, '_test_subproc_sim', None)
if simulator is None:
    simulator = TestSubprocessSimulator()
    self._test_subproc_sim = simulator

# On '!run ...'
proc_id = simulator.launch(command)
# On '!status ...'
status = simulator.status(proc_id)
```

- **Behavior:**
  - `!run ...` yields a fake process ID and launch message.
  - `!status ...` returns `{"status": "running"}` if <1s since launch, else `{"status": "finished"}`.

## 3. Example Test Patterns

- **Spinner/Box Test:**
```python
async def test_spinner_and_box(capsys):
    os.environ["SWARM_TEST_MODE"] = "1"
    blueprint = MyBlueprint()
    messages = [{"role": "user", "content": "/search love"}]
    async for _ in blueprint.run(messages):
        pass
    out = capsys.readouterr().out
    assert "Generating." in out
    assert "✨" in out
```

- **Subprocess Test:**
```python
async def test_subprocess_launch_and_status():
    os.environ["SWARM_TEST_MODE"] = "1"
    blueprint = MyBlueprint()
    messages = [{"role": "user", "content": "!run sleep 1"}]
    async for chunk in blueprint.run(messages):
        ... # assert launch
    messages = [{"role": "user", "content": f"!status {proc_id}"}]
    async for chunk in blueprint.run(messages):
        ... # assert running/finished
```

## 4. Adoption

- All new and existing blueprints should:
  - Use these patterns for test-mode UX and subprocess simulation.
  - Ensure test coverage for spinner/box/UX and subprocess scenarios.
  - Avoid ad-hoc or custom test-mode logic.

## 5. Automated Compliance Utility

- Use `scripts/check_ux_compliance.py` to scan all blueprints for spinner/box/emoji/summary compliance in test mode.
- This utility supplements the robust compliance tests in `tests/blueprints/`.
- Blueprints that do not emit all required UX elements will log warnings but will not block development.
- Review test logs for details and update blueprints as needed for full compliance.

---

For questions or further improvements, see `swarm/core/test_utils.py` and blueprint test files for reference implementations.
