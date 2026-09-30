# Jeeves Blueprint

**Jeeves** is a multi-agent home and web orchestration blueprint for Operating Swarm, demonstrating multi-agent delegation for web search and home automation, robust fallback for LLM/agent errors, and unified ANSI/emoji UX with spinner feedback.

---

## What This Blueprint Demonstrates
- **Multi-agent delegation and orchestration** for web search and home automation
- **LLM fallback and error handling** with user-friendly messages
- **Unified ANSI/emoji boxes** for operation results, including summaries, counts, and parameters
- **Custom spinner messages**: 'Polishing the silver', 'Generating.', 'Generating..', 'Generating...', 'Running...'
- **Long wait fallback message**: 'Generating... Taking longer than expected'
- **Progress updates** for long-running operations (result counts, summaries)
- **Test mode** for robust, deterministic testing

## Usage
Run with the CLI:
```sh
swarm-cli run jeeves --instruction "Turn off the living room lights and search for pizza recipes."
```

## Test
```sh
uv run pytest -v tests/blueprints/test_jeeves_spinner_and_box.py tests/integration/test_cli_jeeves.py
```

## Compliance
- Agentic: 
- UX (ANSI/emoji): 
- Spinner: 
- Fallback: 
- Test Coverage: 

## Required Env Vars
- `SWARM_TEST_MODE` (optional): Enables test mode for deterministic output.

## Test Mode CLI
When `SWARM_TEST_MODE=1`, the CLI will output raw spinner states (prefixed `[SPINNER]`) and progressive operation boxes for each frame.

## Extending
- See `blueprint_jeeves.py` for agent logic and UX hooks.
- Extend agent capabilities or UX by modifying the `_run_non_interactive` and agent orchestration methods.

---
_Last updated: 2025-04-21_
