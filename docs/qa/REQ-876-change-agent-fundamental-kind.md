# REQ-876 — Allow Changing Fundamental Agent Kind in Agent Editor (#271)

> Enables changing an agent's fundamental harness kind (`api`, `cli`, `remote`) within the Agent Editor, supported by comprehensive breakage reflection, impact warnings, and safe session transition safeguards.

**Issue:** [#271](https://github.com/matthewhand/open-swarm-private/issues/271)

---

## 1. Context & Motivation

Currently in [`AgentEditor.tsx`](../../webui/frontend/src/components/AgentEditor.tsx), an agent's `agentKind` (`api`, `cli`, `remote`, or `blueprint`) is computed as a read-only attribute derived from its ID prefix, blueprint tags, or catalog registration. Operators cannot change an agent's fundamental kind after initial creation.

Operators need the flexibility to change an agent's fundamental kind—for example, converting a standalone API-based agent into a local CLI-backed agent (e.g. wrapping an agent with `qwen` or `omp`), or promoting a CLI prototype into a managed API blueprint.

Because changing an agent's fundamental kind touches the underlying runtime subclass (`ApiKindBase`, `CliKindBase`, `RemoteKindBase`), session protocol, configuration schema, and team coordination graph, this specification establishes the requirements, reflection on breakage points, and protective mitigations.

---

## 2. Reflection: What Could Changing Fundamental Kind Break?

Changing an agent's fundamental harness kind impacts five critical areas:

### 2.1 Active Chat Sessions & Transcript Formats
- **CLI → API**:
  - CLI agents store session state in external subprocesses or host disk files (`~/.gemini/`, `~/.claude/`, `cli_sessions.json`).
  - Switching to API routes future turns to LiteLLM / OpenAI API endpoints. The prior CLI session handles become orphaned and cannot be resumed by the CLI binary.
- **API → CLI**:
  - API agent transcripts contain structured protocol turns: tool calls, out-of-band HTML swaps, summaries, and context culling offsets (REQ-87).
  - Injecting this structured history into a native CLI subprocess (`qwen`, `omp`, `claude`) can fail because CLI binaries expect raw text or CLI-native session formats.
- **API/CLI → Remote**:
  - Remote agents communicate via HTTP/WebSocket to external harnesses (Hermes, OpenMousBot, Rakazo, Herdr, TrueForge).
  - Existing local session transcripts do not exist on the remote host, causing context loss or 404 session lookup errors.

### 2.2 Configuration & Parameter Invalidation
- **API Specific**: `llm_profile`, `inference_list`, `context_auto_compress_pct`, attached skills, and tool gates are meaningful only for `ApiKindBase`. Switching to CLI or Remote leaves these settings orphaned or inert.
- **CLI Specific**: `command`, `cli` executable name, and `folder` (session working directory). Switching to API leaves no CLI command to execute.
- **Remote Specific**: `base_url`, `api_key_env`, and remote connection bindings. Switching to API or CLI breaks the remote link.

### 2.3 Team Rosters & Multi-Agent Coordination Graphs
- In [`team_rosters.json`](../../team_rosters.json) / `/v1/team-rosters/`, multi-agent teams define communication wires (`wires: { [from]: to[] }`) and Chief of Staff roles.
- `ApiKindBase` agents participate in programmatic `openai-agents` handoff graphs and tool calls.
- `CliKindBase` and `RemoteKindBase` agents run external processes and cannot accept in-process handoff edges or direct programmatic tool invocations.
- Converting an API team member into a CLI agent silently breaks team handoff wires and multi-agent coordination.

### 2.4 Custom Blueprint Python Code Incompatibility
- Custom blueprints created via the blueprint editor or Add Agent wizard generate Python source code:
  - API blueprints subclass `ApiKindBase(KindBase)`.
  - CLI blueprints subclass `CliKindBase(KindBase)`.
  - Remote blueprints subclass `RemoteKindBase(KindBase)`.
- If the kind is changed in metadata without updating the Python class inheritance, the runtime fails during execution with attribute or method mismatch errors.

### 2.5 Rail Storage Keys & Preferences
- Storage keys for pinned agents (`pinnedAgents`), hidden agents (`hiddenAgents`), and rail sections (`railSections`) use kind-specific prefixes (`cli:<id>`, `remote:<id>`).
- Mutating the kind without reconciling IDs can cause the agent to disappear from pinned favorites or drop out of rail sections.

---

## 3. Requirements & Mitigation Strategy

### 3.1 Kind Selector in Agent Editor
1. **Interactive Kind Dropdown**:
   - In `AgentEditor.tsx`, replace the read-only `agentKind` display with an interactive Kind selector (`Select` component with options: `API`, `CLI`, `Remote`).
2. **Dynamic Form Adjustment**:
   - Dynamically reconfigure available form fields based on the selected kind:
     - **API**: Shows LLM Profile picker, Model override, Skills selector, and Auto-compress settings.
     - **CLI**: Shows CLI selection (`qwen`, `omp`, `claude`, etc.), Command, and Working Directory (`folder`).
     - **Remote**: Shows Remote Harness selector (`Hermes`, `TrueForge`, etc.) and connection binding.

### 3.2 Destructive Action Warning & Confirmation Dialog
1. **Impact Warning Banner**:
   - When the operator selects a different kind from the current one, display a modal warning explaining the exact impact:
     - Session history notice: prior sessions will be archived.
     - Settings notice: kind-specific settings will be reset or adapted.
     - Team notice: any teams this agent belongs to will be listed with a warning regarding broken handoff wires.
2. **"Duplicate as New Agent" Alternative**:
   - Provide a prominent button: **"Duplicate as [New Kind] Agent Instead"**.
   - Allows creating a copy of the agent with the new kind while keeping the original agent and its history completely intact.
3. **Explicit Confirmation**:
   - Require explicit user confirmation ("Change Type to [Kind]") before the edit is committed.

### 3.3 Session Archiving & Clean Start
1. **Session Boundary**:
   - When the kind change is confirmed, mark existing sessions for this agent as archived.
   - Insert an in-chat status notice: `"Agent type changed from [OldKind] to [NewKind] on <timestamp>. Started a new session."`
   - Future turns start on a fresh session tailored to the new kind's protocol.

### 3.4 Custom Blueprint Base Class Synchronization
1. **Source Code Migration**:
   - For custom blueprints (`CustomBlueprint` records in the backend):
     - Automatically update the Python source code to import and subclass the matching base class (`ApiKindBase`, `CliKindBase`, `RemoteKindBase`) using `base_class_for_kind(new_kind)`.

### 3.5 Rail Identity & Preferences Migration
1. **State Reconciliation**:
   - Reconcile `pinnedAgents`, `railSections`, `hiddenAgents`, and `unreadAgents` so the agent maintains its rail position, pin status, and custom section assignment after the type change.

---

## 4. Acceptance Criteria

- [ ] `AgentEditor` allows selecting a new fundamental kind (`api`, `cli`, `remote`).
- [ ] Selecting a different kind displays a warning dialog detailing the session, configuration, and team impacts.
- [ ] The dialog offers a non-destructive "Duplicate as New Agent" option.
- [ ] If the agent is in team rosters, those teams are explicitly listed in the warning.
- [ ] Confirming the change archives existing chat sessions and starts a clean session under the new kind.
- [ ] Form fields dynamically adjust to display settings appropriate to the selected kind.
- [ ] Custom blueprint code base classes are updated to match the new kind (`ApiKindBase` <-> `CliKindBase` <-> `RemoteKindBase`).
- [ ] Rail section placement and pinned favorite status are preserved across kind change.
- [ ] **Tests**:
  - [ ] Vitest tests in `AgentEditor.test.tsx` verifying kind change warning dialog, dynamic field re-rendering, and save payload.
  - [ ] Python unit tests in `tests/core/test_agent_kind_migration.py` verifying custom blueprint base class updates and session archiving.

---

## 5. Key Files to Modify

| File | Role | Planned Modification |
| :--- | :--- | :--- |
| `webui/frontend/src/components/AgentEditor.tsx` | Agent editor overlay | Add Kind selector, dynamic fields, warning confirmation modal, and duplicate option. |
| `src/swarm/core/kind_bases.py` | Kind base definitions | Utility for migrating blueprint source code to new kind base class. |
| `src/swarm/views/blueprint_views.py` | Blueprint API views | Backend endpoint handling kind migration, blueprint code update, and session archiving. |
| `webui/frontend/src/lib/agentEdits.ts` | Agent edit persistence | Handle kind transition payload and rail preferences preservation. |
