# Agent Guidelines (AGENTS.md)

This file defines rules, constraints, and architecture invariants for AI coding assistants (Codebuff, OpenHands, Antigravity, Cursor, Copilot, etc.) contributing to **Open Swarm**.

---

## 1. Multi-Agent & PR Hygiene Rules

### Clean PR Descriptions & Commits
- **No local filesystem URIs**: Never include absolute local file paths or environment URIs (e.g. `file:///home/...`, `/tmp/...`) in commit messages, pull request titles, or pull request descriptions. Use repo-relative paths (e.g., `src/swarm/core/bootstrap_provider.py`) or markdown code formatting (`ProviderSetupCard.tsx`).
- **Branch Naming**: Always use standard, clear git branch names:
  - `feat/<issue-number>-<short-slug>`
  - `fix/<issue-number>-<short-slug>`
  - `chore/<issue-number>-<short-slug>`
  - Avoid ambiguous branch names like `tmp-...` or `popup-932`.
- **Commit Messages**: Follow Conventional Commits:
  - `feat(scope): concise description (#issue)`
  - `fix(scope): concise description (#issue)`
  - `test(scope): ... (#issue)`
  - `chore(deps): ... (#issue)`
  - Always append `Closes #XXX` or `Resolves #XXX` in the PR body.

### Component Wrappers & Callback Preservation
- **Never drop event handlers**: When wrapping or refactoring existing inputs or components (e.g., wrapping a `<textarea>` into a specialized `<ChatMessageInput />`), you **must forward all standard event handlers and callbacks**:
  - `onKeyDown`, `onKeyUp`, `onKeyPress`
  - `onChange`, `onInput`
  - `onFocus`, `onBlur`
  - `onPaste`, `onCompositionStart`, `onCompositionEnd`
- *Why*: Dropping `onKeyDown` breaks keyboard shortcuts (Esc to clear, Enter to send, slash-command menu, reply quoting, offline queueing).

### Synchronized Registry Dictionaries & TypeScript Types
- When adding or modifying a role, model, or task class:
  - **Types**: Update the union in `webui/frontend/src/lib/api.ts` (e.g. `AgentRole`).
  - **Aliases**: Update `ROLE_ALIASES` in `webui/frontend/src/lib/agentRoles.ts`.
  - **Badges/Labels**: Update `ROLE_BADGE_LABELS` in `webui/frontend/src/lib/agentRoles.ts`.
  - **Styles**: Add CSS rules in `webui/frontend/src/index.css` (e.g. `.os-agent-role-badge[data-role="..."]`).
  - **Backend**: Update `src/swarm/core/roles/adapters.py` and `src/swarm/core/agent_roles.py`.
- Omitting any dictionary will break TypeScript compilation (`tsc --noEmit`).

---

## 2. Verification Gates (Run Before Every Commit & PR)

Every PR must satisfy all three gates before merging:

1. **Backend Tests**:
   ```bash
   source .venv/bin/activate
   python -m pytest tests/core/ tests/views/ -x -q
   ```
2. **Frontend Vitest Tests**:
   ```bash
   cd webui/frontend
   npm test -- --watchAll=false
   ```
3. **TypeScript & Build Verification**:
   ```bash
   cd webui/frontend
   npm run build
   # or: npx tsc --noEmit
   ```
   *Never merge if `tsc --noEmit` or `npm run build` reports errors.*

---

## 3. Core Architectural Invariants

### First-Class Seat Kinds
- Open Swarm has four first-class seat kinds:
  1. `api`: API-managed model sessions (`ApiKindBase`).
  2. `cli`: Local host subprocess sessions (`CliKindBase`).
  3. `remote`: External agent bridges like Hermes, Herdr, AnythingLLM (`RemoteKindBase`).
  4. `team`: Multi-agent orchestration rosters (`TeamKindBase`).
- All subclass `KindBase` in `src/swarm/core/kind_bases.py`.
- Do not create parallel abstractions for teams or seats outside the `KindBase` hierarchy.

### Composer & Routing Picker Invariants
- **Provider Picker Scope**: The composer provider dropdown (`NavbarRoutingPicker` / `composerPicker.ts`) must **only** adjust routing parameters (`params.provider`, `params.model`). It must **never** switch the active agent seat or overwrite `blueprint_id`.
- **Bootstrap Provider Isolation**: The `bootstrap` provider service is strictly for initial zero-config onboarding (`starter-admin` seat). It must **never** appear in the general composer provider dropdown. It can only be selected in agent settings.
- **File Attachments**: Uploaded file chips must handle progress, category icons, dismissal, cancellation via `AbortController`, and textless sends.

### Context & Session Persistence
- **Conversation Storage**: Django database (`ChatMessage` / `ChatConversation`) and `chat_store` are the canonical source of truth for persisted chat history.
- **Provider Switches**: When an agent switches provider or kind, existing context must be persisted and transferred rather than lost.

### UI & Styling Standards
- **Design Tokens**: Always use CSS theme variables (e.g., `var(--color-base-100)`, `var(--os-rail-gutter)`). Do not hardcode raw hex values (like `#ffffff` or `#000000`) in component CSS where theme tokens exist.
- **Role Badges**: Role color belongs **only** on `.os-agent-role-badge`. Rail rows must never have role fill, left borders, or background outlines.
- **Responsive Layout**: Rail resizing must support drag-to-edge collapse, fixed square avatar tiles, and avoid layout shifts when shrinking sidepanes.

---

## 4. Test Discipline

- **Do Not Weaken Tests**: Never delete, skip (`@pytest.mark.skip`), or relax assertions just to make a suite green unless the underlying requirement has explicitly changed.
- **Add Regression Tests**: Every bug fix must include a test reproducing the original issue. Every new feature must include tests for happy paths, failure modes, and unmount/cancellation lifecycles.
