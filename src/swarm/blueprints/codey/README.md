# Codey Blueprint

**Codey** is an agentic code and semantic search/analysis blueprint for Operating Swarm, demonstrating agent-based orchestration, robust UX with ANSI/emoji output, spinner feedback, and resilient fallback for agent/LLM errors.

---

## What This Blueprint Demonstrates
- **Agent-based code and semantic search** (keyword and semantic)
- **LLM fallback and error handling** with user-friendly messages
- **Unified ANSI/emoji boxes** for search/analysis results, including summaries, counts, and parameters
- **Custom spinner messages**: 'Generating.', 'Generating..', 'Generating...', 'Running...'
- **Progress updates** for long-running operations (line numbers, result counts)
- **Test mode** for robust, deterministic testing

## Usage
Run with the CLI:
```sh
swarm-cli run codey --instruction "/codesearch recursion . 5"
```

## Test
```sh
uv run pytest -v tests/blueprints/test_codey.py
```

## Compliance
- Agentic: 
- UX (ANSI/emoji): 
- Spinner: 
- Fallback: 
- Test Coverage: 

## Required Env Vars
- `SWARM_TEST_MODE` (optional): Enables test mode for deterministic output.

## Extending
- See `blueprint_codey.py` for agent logic and UX hooks.
- Extend agent capabilities or UX by modifying the `_run_non_interactive` method.

---
_Last updated: 2025-04-21_

# (Legacy content below)

Codey is an agentic coding assistant blueprint for Operating Swarm, inspired by OpenAI Codex CLI. It orchestrates specialized agents and tools to automate and assist with software engineering tasks, especially those involving code, git, and project workflows.

---

## Features Implemented

- **Global Instructions**: Reads and injects `~/.codey/instructions.md` as a base prompt for orchestration/coordinator agent.
- **Agent Delegation**: Supports delegating tasks to specialized sub-agents (e.g., GitHub agent, code review agent).
- **Tool Integration**: Git, file, and shell tools available to agents (e.g., git status, add, commit, push, file read/write).
- **Dynamic Prompt Construction**: User requests, history, and tool descriptions included in LLM prompt.
- **Basic ANSI/Emoji Output**: Some CLI output uses boxes/emojis for better UX.
- **Rich Syntax Highlighting**: Code fences in assistant responses are colorized via Rich.
- **Slash Commands**: Built-in `/help`, `/compact`, `/model`, `/approval`, `/history`, `/clear`, and `/clearhistory` available.
- **Testable via CLI**: Supports test-driven development and CLI-based interaction.

---

## Features Partially Implemented

- **Project-Level Instructions**: Can be injected manually (e.g., `CODEY.md`), but not auto-loaded.
- **File/Directory Context Awareness**: File tools exist, but no automatic context file loading or project scanning.
- **Rich Output Formatting**: Some ANSI/emoji UX, but not unified or as rich as Codex.
- **Interactive/Approval Mode**: Basic CLI flag (`--approval-mode`) supports interactive prompts for git operations in suggest mode.

---

## Features Not Yet Implemented

- **Automatic Plan/Changelog Updates**: Agent does not maintain `.codey/plan_*.md` or changelogs automatically.
- **Automatic Context Injection**: Agent does not scan/include relevant files automatically in prompts.
- **User Feedback Loop**: No mechanism for user feedback/corrections mid-session.
- **Session Logging/Audit Trail**: No persistent log of actions, plans, or outputs.

---

## Onboarding Tips

- Try `/codesearch <keyword> <path> <max_results>` (e.g. `/codesearch recursion . 5`)
- Try `/semanticsearch <keyword>` for semantic code search with rich result boxes, result counts, and spinner
- Use `/help` for slash commands, `/model` to switch models, `/approval` for approval mode
- Use arrow keys for history, Ctrl+C to quit, Esc to interrupt
- See the main README for advanced onboarding and blueprint discovery

---

## TODO

- [x] Implement interactive/approval mode for agent actions
- [ ] Enable automatic plan/changelog file updates
- [ ] Add project-level instruction auto-loading (e.g., `CODEY.md`)
- [ ] Improve file/directory context awareness and context injection
- [ ] Unify and enhance rich output formatting (boxes, emojis, result summaries)
- [ ] Add user feedback/correction loop
- [ ] Add persistent session logging/audit trail
- [ ] Implement summarization logic for `/compact` slash command
- [ ] Implement model switching for `/model` slash command
- [ ] Implement approval toggle for `/approval` slash command
- [ ] Implement session history persistence for `/history` and `/clearhistory`
- [ ] Enhance screen/context clearing for `/clear` slash command
- [ ] Add interactive overlays for `/help`, `/model`, `/approval`, `/history`
- [ ] Support external editor integration for prompts (e.g., `/edit` or Ctrl+E)
- [ ] Add keyboard shortcut support (Ctrl+J newline, arrow history, Esc interrupt, Ctrl+C quit)
- [ ] Enable streaming token-by-token responses in CLI
- [ ] Expose `/explain` slash command for detailed shell command explanations
- [ ] Add file-related slash commands (`/ls`, `/cat`, `/edit`)
- [ ] Implement live config reload from `.env` or config file
- [ ] Add suggestion/autocomplete for commands

---

Contributions and suggestions welcome! See `~/.codey/instructions.md` for global defaults, and update this TODO list as features are added.
