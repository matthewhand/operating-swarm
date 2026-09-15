# REQ-868 — Modernize Unconfigured CLI Agents Error Message with In-App Link (#258)

> Updates the message emitted when no CLI agents are configured. Replaces the outdated static documentation pointer (`see docs/CLI_FUSION.md`) with a direct in-app link to "Manage CLI" (`Settings → CLI Agents`).

**Issue:** [#258](https://github.com/matthewhand/open-swarm-private/issues/258)

---

## 1. Problem Description

When an agent execution path requires an installed CLI agent but none are configured, blueprints currently emit:
```
No CLI agents are configured. Add a 'cli_agents' block to your swarm config (see docs/CLI_FUSION.md).
```

### Issues with Current Message:
1. **Outdated Guidance**: Directs users to read a markdown file in the repository rather than providing an interactive path forward.
2. **Missing In-App Navigation**: The WebUI features an interactive **Manage CLI** settings pane (`SettingsSheet` → `cli-agents` / `CliAgentsSettingsPane.tsx`) where operators can review installed CLIs, check paths, and configure models directly.
3. **User Friction**: Users chatting in the WebUI cannot click a link to resolve the issue directly.

---

## 2. Requirements

### 2.1 Unified Error Message Format
Update the error message across CLI blueprints to provide a direct markdown link to Manage CLI:
```markdown
No CLI agents are configured. Configure your installed CLIs in [Manage CLI](/chat?settings=cli-agents) (Settings → CLI Agents).
```

### 2.2 Affected Blueprints
Update the message in all blueprints that check CLI availability:
- `src/swarm/blueprints/cli_agent/blueprint_cli_agent.py`
- `src/swarm/blueprints/cli_orchestrator/blueprint_cli_orchestrator.py`
- `src/swarm/blueprints/cli_roundtable/blueprint_cli_roundtable.py`
- `src/swarm/blueprints/cli_recurse/blueprint_cli_recurse.py`
- `src/swarm/blueprints/cli_map/blueprint_cli_map.py`
- `src/swarm/blueprints/cli_pipeline/blueprint_cli_pipeline.py`
- `src/swarm/blueprints/cli_planner/blueprint_cli_planner.py`
- `src/swarm/blueprints/persona_council/blueprint_persona_council.py`
- `src/swarm/blueprints/hybrid_swarm/blueprint_hybrid_swarm.py`
- `src/swarm/blueprints/hybrid_team/blueprint_hybrid_team.py`

### 2.3 WebUI Markdown Link Handling
- Ensure that links in chat pointing to `/chat?settings=cli-agents` (or custom protocol `settings:cli-agents`) trigger `openSettingsSheet({ section: 'cli-agents' })` smoothly without causing a hard page reload.

---

## 3. Acceptance Criteria

- [ ] When no CLI agents are configured, blueprints emit the modernized message pointing to `[Manage CLI](/chat?settings=cli-agents) (Settings → CLI Agents)`.
- [ ] No references to `docs/CLI_FUSION.md` remain in runtime user-facing chat error messages.
- [ ] Clicking the link in the WebUI opens the `SettingsSheet` at `section: 'cli-agents'`.
- [ ] **Tests**:
  - [ ] `tests/blueprints/test_cli_agent.py` asserts the new message text format.
  - [ ] Vitest tests in `webui/frontend/src/` verify markdown link interception for settings sheet links.

---

## 4. Locked Sources

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `src/swarm/blueprints/cli_agent/blueprint_cli_agent.py` | CLI Agent blueprint | Update error message to point to `[Manage CLI]` |
| `src/swarm/blueprints/cli_*/blueprint_cli_*.py` | CLI blueprints | Update error message to point to `[Manage CLI]` |
| `webui/frontend/src/components/ChatMessageBubble.tsx` | Markdown renderer / link handler | Ensure settings links open the in-app `SettingsSheet` |
